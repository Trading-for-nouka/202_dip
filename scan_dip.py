import yfinance as yf
import pandas as pd
import os
import json
import requests
from datetime import datetime, timedelta, timezone
from strategy_params import calc_dip_levels
from claude_comment import generate_comments_batch

# --- 設定 ---
OWNER = "trading-for-nouka"
REPO = "102_market_phase"
FILE_PATH = "market_phase.json"
TOKEN = os.environ.get("PAT_TOKEN")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")
UNIVERSE_FILE = "universe496.csv"
JSON_FILE = "selected_positions_dip.json"

# --- 乖離率の許容範囲（バックテスト最優秀値）---
DEV_LOWER = -6.0
DEV_UPPER =  2.0

# --- 売買代金フィルター（TOPIX区分別）---
TURNOVER_FILTER = {
    "TOPIX Core30":  0,
    "TOPIX Large70": 5e8,
    "TOPIX Mid400":  1e8,
}


def get_market_phase():
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"token {TOKEN}" if TOKEN else "",
        "Accept": "application/vnd.github.v3.raw"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("phase", "NEUTRAL")
    except:
        pass
    return "NEUTRAL"


def is_near_earnings(ticker, days=5):
    try:
        stock = yf.Ticker(ticker)
        cal = stock.calendar
        if cal is None or cal.empty:
            return False
        earnings_date = cal.iloc[0, 0]
        if hasattr(earnings_date, 'date'):
            earnings_date = earnings_date.date()
        today    = datetime.now().date()
        deadline = today + timedelta(days=days)
        return today <= earnings_date <= deadline
    except:
        return False


def send_discord(message):
    if DISCORD_WEBHOOK:
        requests.post(DISCORD_WEBHOOK, json={"content": message})


def scan_dip():
    phase = get_market_phase()

    if phase in ["RISK_OFF", "CRASH"]:
        msg = f"🚫 **【押し目スキャン】{phase} モードのため停止中**"
        print(msg)
        send_discord(msg)
        return

    if not os.path.exists(UNIVERSE_FILE):
        print(f"❌ {UNIVERSE_FILE} が見つかりません。")
        return

    # --- 銘柄リスト読み込み ---
    df_univ = None
    for enc in ['cp932', 'utf-8-sig', 'utf-8']:
        try:
            df_univ = pd.read_csv(UNIVERSE_FILE, encoding=enc)
            print(f"✅ CSVを {enc} で読み込みました。({len(df_univ)}行)")
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"❌ {enc} での読み込みエラー: {e}")
            break

    if df_univ is None or df_univ.empty:
        print(f"❌ {UNIVERSE_FILE} の読み込みに失敗しました。")
        send_discord(f"❌ 【押し目スキャン】{UNIVERSE_FILE} の読み込みに失敗しました。")
        return

    df_univ.columns = df_univ.columns.str.strip()

    targets = []
    for _, row in df_univ.iterrows():
        code = str(row.iloc[0]).split('.')[0].strip()
        if code and code.isdigit():
            targets.append({
                "ticker":     f"{code}.T",
                "name":       str(row.iloc[1]),
                "sector":     str(row.iloc[2]),
                "index_type": str(row.iloc[3]) if len(row) >= 4 else "TOPIX Mid400",
            })

    if not targets:
        msg = f"❌ 【押し目スキャン】{UNIVERSE_FILE} から有効な銘柄を取得できませんでした。"
        print(msg)
        send_discord(msg)
        return

    # --- ベンチマーク（TOPIX）のリターン取得 ---
    bench_return_20 = None
    try:
        bench = yf.download("1306.T", period="4mo", auto_adjust=True, progress=False)
        if isinstance(bench.columns, pd.MultiIndex):
            bench.columns = bench.columns.get_level_values(0)
        if len(bench) >= 21:
            bench_return_20 = float(bench["Close"].pct_change(20).iloc[-1])
    except Exception as e:
        print(f"⚠️ ベンチマーク取得失敗: {e}")

    if bench_return_20 is None:
        print("⚠️ ベンチマーク取得失敗のためRSフィルターをスキップします。結果は参考値として扱ってください。")

    # --- 一括ダウンロード（496銘柄を1回で取得）---
    tickers = [item["ticker"] for item in targets]
    print(f"📥 データ取得中... {len(tickers)}銘柄")
    data = yf.download(tickers, period="4mo", auto_adjust=True, progress=False, group_by="ticker")
    print(f"🚀 スキャン開始 (Phase: {phase})...")

    results = []

    for item in targets:
        ticker = item["ticker"]
        try:
            if ticker not in data.columns.get_level_values(0):
                print(f"  ✗ {ticker} スキップ: データなし")
                continue

            df = data[ticker].copy().dropna()
            if len(df) < 60:
                continue

            close  = df["Close"]
            low    = df["Low"]
            volume = df["Volume"]

            ma25 = close.rolling(window=25).mean()
            ma5  = close.rolling(window=5).mean()

            curr_close = float(close.iloc[-1])
            curr_ma25  = float(ma25.iloc[-1])
            curr_ma5   = float(ma5.iloc[-1])
            prev_ma25  = float(ma25.iloc[-5])

            if not (curr_ma25 > prev_ma25):
                continue

            recent_low   = float(low.tail(3).min())
            is_near_ma25 = curr_ma25 * 0.97 <= recent_low <= curr_ma25 * 1.03
            if not is_near_ma25:
                continue

            if not (curr_close > curr_ma5):
                continue

            dev = ((curr_close - curr_ma25) / curr_ma25) * 100
            if not (DEV_LOWER <= dev <= DEV_UPPER):
                continue

            if bench_return_20 is not None:
                stock_return_20 = float(close.pct_change(20).iloc[-1])
                rs = stock_return_20 - bench_return_20
                if rs <= 0:
                    print(f"  {ticker} スキップ（RSが市場以下: {rs:.3f}）")
                    continue
            else:
                rs = None

            vol_ma20  = float(volume.rolling(20).mean().iloc[-1])
            vol_today = float(volume.iloc[-1])
            rvol = vol_today / vol_ma20 if vol_ma20 > 0 else 0
            if rvol < 0.8:
                print(f"  {ticker} スキップ（出来高不足: RVOL={rvol:.2f}）")
                continue

            turnover_min = TURNOVER_FILTER.get(item["index_type"], 1e8)
            if curr_close * vol_today < turnover_min:
                print(f"  {ticker} スキップ（売買代金不足）")
                continue

            if is_near_earnings(ticker):
                print(f"  {ticker} スキップ（決算近接）")
                continue

            atr14  = float((df["High"] - df["Low"]).rolling(14).mean().iloc[-1])
            levels = calc_dip_levels(curr_close, curr_ma25, atr14)

            results.append({
                "ticker": ticker,
                "name":   item["name"],
                "sector": item["sector"],
                "close":  round(curr_close, 1),
                "price":  round(curr_close, 1),
                "dev":    round(dev, 1),
                "rvol":   round(rvol, 2),
                "rs":     round(rs * 100, 2) if rs is not None else None,
                "ma25":   round(curr_ma25, 1),
                "atr14":  round(atr14, 1),
                "entry_low":  levels["entry_low"],
                "entry_high": levels["entry_high"],
                "stop_loss":  levels["stop_loss"],
                "target":     levels["target"],
                "hold_days":  levels["hold_days"],
            })

        except Exception as e:
            print(f"❌ {ticker} エラー: {e}")
            continue

    jst = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9)))
    p_icon = "🟢" if phase == "BULL" else "🟡"

    if results:
        results = sorted(results, key=lambda x: abs(x["dev"]))

        # JSON保存をコメント生成の前に実施（APIエラーで結果が消えないように）
        today_str = datetime.now().strftime("%Y-%m-%d")
        new_entries = [
            {
                "ticker":        r["ticker"],
                "name":          r["name"],
                "entry_date":    today_str,
                "entry_price":   r["price"],
                "highest_price": r["price"],
                "stop_loss":     r["stop_loss"],
                "strategy":      "dip",
            }
            for r in results
        ]
        existing = []
        if os.path.exists(JSON_FILE):
            try:
                with open(JSON_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, ValueError):
                existing = []
        existing_tickers = {p["ticker"] for p in existing}
        added = [e for e in new_entries if e["ticker"] not in existing_tickers]
        existing.extend(added)
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f"💾 {JSON_FILE} に {len(added)} 件追記しました（重複スキップ: {len(new_entries) - len(added)} 件）")

        # コメント生成（失敗してもランキング結果は維持）
        print("💬 Claude APIコメント生成中...")
        results = generate_comments_batch("dip", results, max_count=5) or results

        msg  = f"{p_icon} **【押し目スキャン】反発の兆し ({phase})**\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        for r in results:
            rs_str   = f"RS: {r['rs']:+.1f}%" if r["rs"] is not None else "RS: -"
            dev_sign = "+" if r["dev"] >= 0 else ""
            msg += (
                f"🔹 **{r['name']}** ({r['ticker']})\n"
                f"　 業種: {r['sector']}\n"
                f"　 株価: {r['price']:.1f}円 | 乖離: {dev_sign}{r['dev']}% | RVOL: {r['rvol']} | {rs_str}\n"
                f"　 📌 購入: {r['entry_low']}〜{r['entry_high']}円 | 🛑 損切: {r['stop_loss']}円 | 🎯 目標: {r['target']}円\n"
            )
            if r.get("comment"):
                msg += f"　 💬 {r['comment']}\n"
            msg += "\n"
        msg += f"✅ 該当: {len(results)}銘柄\n"
        msg += f"🕒 {jst.strftime('%Y/%m/%d %H:%M')} JST\n"

        send_discord(msg)
        print(f"✅ Discordへ通知を送信しました。({len(results)}銘柄)")

        for r in results[:5]:
            send_discord(
                f"🛒 **{r['name']}（{r['ticker']}）**\n"
                f"　 📌 {r['entry_low']}〜{r['entry_high']}円 | 🛑 {r['stop_loss']}円\n"
                f"📎 {r['ticker']}|dip|{r['price']}|{r['stop_loss']}|{r['name']}"
            )
    else:
        msg = (
            f"{p_icon} **【押し目スキャン】({phase})**\n"
            f"🕒 {jst.strftime('%Y/%m/%d %H:%M')} JST\n"
            f"ℹ️ 条件に合致する銘柄はありませんでした。"
        )
        send_discord(msg)
        print("ℹ️ 条件に合致する銘柄はありませんでした。")


if __name__ == "__main__":
    scan_dip()
