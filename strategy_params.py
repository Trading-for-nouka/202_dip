# バックテスト実績値に基づく戦略別パラメータ定数
# 更新日時      : 2026-05-10
# バックテスト  : 2016-01-01 〜 2025-12-31
# スコア(PF×勝率): 1.1297
# 勝率: 55.0% | PF: 2.05 | 取引数: 649
# RS>8% + RSI≤50 フィルター追加後（グリッドサーチ最適化済み）

STRATEGY_PARAMS = {

    # ============================================================
    # 押し目買い戦略（scan_dip.py）
    # 実績: 勝率55.0% / PF2.05 / 保有15日
    # 最優秀パラメータ: DEV=-6〜+2% / RVOL≥0.8 / MA25 / RS>8% / RSI≤50
    # ============================================================
    "dip": {
        # エントリーゾーン（MA25乖離率ベース）
        "dev_lower":        -0.06,  # MA25の-6%
        "dev_upper":        +0.02,  # MA25の+2%

        # リスク管理
        "stop_atr_mult":    1.5,
        "hold_days":        15,

        # RSフィルター（バックテスト最適化済み）
        "rs_threshold":     0.08,   # RS下限: TOPIXより+8%以上アウトパフォーム
        "rsi_max":          50,     # RSI上限: 50以下（売られ過ぎ圏）

        # バックテスト実績（RS>8% + RSI≤50 適用後）
        "win_rate":         0.550,
        "profit_factor":    2.054,
        "avg_return_15d":   0.019,  # 15日平均リターン
    },
}


def calc_dip_levels(close, ma25, atr14):
    """
    押し目買い戦略の定量売買水準を計算する。

    Args:
        close (float): 当日終値
        ma25  (float): 25日移動平均
        atr14 (float): 14日ATR

    Returns:
        dict: entry_low, entry_high, stop_loss, target, hold_days
    """
    p = STRATEGY_PARAMS["dip"]

    entry_low  = ma25 * (1 + p["dev_lower"])   # MA25 × 0.94
    entry_high = ma25 * (1 + p["dev_upper"])   # MA25 × 1.02
    stop_loss  = entry_low - p["stop_atr_mult"] * atr14
    target     = entry_high * (1 + p["avg_return_15d"] * p["hold_days"])

    return {
        "entry_low":  round(entry_low),
        "entry_high": round(entry_high),
        "stop_loss":  round(stop_loss),
        "target":     round(target),
        "hold_days":  p["hold_days"],
        "win_rate":   p["win_rate"],
        "pf":         p["profit_factor"],
    }
