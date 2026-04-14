# strategy_params.py
# バックテスト実績値に基づく戦略別パラメータ定数
# 2015-2025 日本大型株ユニバース実績

STRATEGY_PARAMS = {

    # ============================================================
    # ブレイクアウト戦略（scan.py）
    # 実績: 勝率53% / PF1.25 / 保有21日
    # ============================================================
    "breakout": {
        # エントリーゾーン（ATRベース）
        "entry_atr_low":    0.0,    # 終値そのまま（即エントリー下限）
        "entry_atr_high":   0.3,    # 終値 + 0.3×ATR（翌日寄り付き許容上限）

        # リスク管理
        "stop_atr_mult":    1.5,    # 損切り: エントリー下限 - 1.5×ATR
        "target_rr":        2.0,    # 利確: リスクの2倍（RR=2.0）

        # 保有期間
        "hold_days":        21,

        # バックテスト実績
        "win_rate":         0.53,
        "profit_factor":    1.25,
    },

    # ============================================================
    # 押し目買い戦略（scan_dip.py）
    # 実績: 勝率53.5% / PF1.25 / 保有10日 / 平均リターン+0.427%
    # 最優秀パラメータ: DEV=-5〜+5% / RVOL≥1.5 / RS有
    # ============================================================
    "dip": {
        # エントリーゾーン（MA25乖離率ベース）
        "dev_lower":        -0.05,  # MA25の-5%（押し目下限）
        "dev_upper":        +0.05,  # MA25の+5%（押し目上限）

        # リスク管理
        "stop_atr_mult":    1.5,    # 損切り: エントリー下限 - 1.5×ATR
        "hold_days":        10,

        # バックテスト実績
        "win_rate":         0.535,
        "profit_factor":    1.25,
        "avg_return_10d":   0.00427,  # 10日平均リターン
    },
}


def calc_breakout_levels(close, atr14):
    """
    ブレイクアウト戦略の定量売買水準を計算する。

    Args:
        close (float): 当日終値
        atr14 (float): 14日ATR

    Returns:
        dict: entry_low, entry_high, stop_loss, target
    """
    p = STRATEGY_PARAMS["breakout"]

    entry_low  = close + p["entry_atr_low"]  * atr14   # = close
    entry_high = close + p["entry_atr_high"] * atr14   # = close + 0.3×ATR

    risk       = entry_low - (entry_low - p["stop_atr_mult"] * atr14)
    stop_loss  = entry_low - p["stop_atr_mult"] * atr14
    target     = entry_high + p["target_rr"] * risk

    return {
        "entry_low":  round(entry_low),
        "entry_high": round(entry_high),
        "stop_loss":  round(stop_loss),
        "target":     round(target),
        "hold_days":  p["hold_days"],
        "win_rate":   p["win_rate"],
        "pf":         p["profit_factor"],
    }


def calc_dip_levels(close, ma25, atr14):
    """
    押し目買い戦略の定量売買水準を計算する。

    Args:
        close (float): 当日終値
        ma25  (float): 25日移動平均
        atr14 (float): 14日ATR

    Returns:
        dict: entry_low, entry_high, stop_loss, target
    """
    p = STRATEGY_PARAMS["dip"]

    entry_low  = ma25 * (1 + p["dev_lower"])   # MA25 × 0.95
    entry_high = ma25 * (1 + p["dev_upper"])   # MA25 × 1.05
    stop_loss  = entry_low - p["stop_atr_mult"] * atr14
    # 利確: 10日平均リターン × 保有日数分をentry_highに上乗せ
    target     = entry_high * (1 + p["avg_return_10d"] * p["hold_days"])

    return {
        "entry_low":  round(entry_low),
        "entry_high": round(entry_high),
        "stop_loss":  round(stop_loss),
        "target":     round(target),
        "hold_days":  p["hold_days"],
        "win_rate":   p["win_rate"],
        "pf":         p["profit_factor"],
    }
