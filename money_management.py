"""
資金管理（マネーマネジメント）モジュール

- 1%リスクルールに基づく推奨ロット計算
- 直近の連敗・ドローダウン・当日損失のチェック・警告生成

JPY建て口座前提。クロス通貨ペアは USDJPY 概算レートで近似計算。
"""
import os
import math
import pandas as pd
from datetime import datetime, timezone

from config import PAIRS, MONEY_MANAGEMENT

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
RESULTS_TPSL_CSV = os.path.join(LOGS_DIR, "results_tpsl.csv")


def calculate_recommended_lot(pair, sl_pips):
    """1%リスクルール（or 設定値）に基づいて推奨ロット数を計算

    JPY建て口座前提:
      - JPY系ペア（USDJPY等）: 1ロット=10万通貨、1pips=1,000円/lot
      - クロス通貨（EURUSD等）: 1pips ≈ 100,000 × pip_unit × USDJPY 円/lot

    Returns:
        float: 推奨ロット数（lot_step に丸め）。データ不足や 0 の場合は 0.0
    """
    if pair not in PAIRS or sl_pips <= 0:
        return 0.0

    pair_cfg = PAIRS[pair]
    pip_unit = pair_cfg.get("pip_unit", 0.01)

    balance = MONEY_MANAGEMENT.get("account_balance", 0)
    risk_pct = MONEY_MANAGEMENT.get("risk_per_trade_pct", 1.0)
    usdjpy = MONEY_MANAGEMENT.get("usdjpy_estimate", 150.0)
    lot_step = MONEY_MANAGEMENT.get("lot_step", 0.01)

    if balance <= 0:
        return 0.0

    risk_amount = balance * (risk_pct / 100)

    # 1ロット（10万通貨）あたりの 1pips の価値（円換算）
    if pair.endswith("JPY"):
        pip_value_per_lot = 100000 * pip_unit  # 例: USDJPY → 1,000円/pip
    else:
        # クロス通貨: USDJPYレートで概算
        pip_value_per_lot = 100000 * pip_unit * usdjpy

    if pip_value_per_lot <= 0:
        return 0.0

    raw_lot = risk_amount / (sl_pips * pip_value_per_lot)

    # lot_step に切り捨て（過剰リスク防止のため切り捨て）
    if lot_step > 0:
        return math.floor(raw_lot / lot_step) * lot_step
    return raw_lot


def get_warnings():
    """直近の取引履歴から警告状態を判定

    Returns:
        list of dict: [{level: "warning"|"critical", message: str}]
        空リストなら警告なし
    """
    warnings = []

    if not os.path.exists(RESULTS_TPSL_CSV):
        return warnings

    try:
        df = pd.read_csv(RESULTS_TPSL_CSV)
    except Exception:
        return warnings

    if len(df) == 0:
        return warnings

    # 時系列ソート
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True, errors="coerce")
    df = df.dropna(subset=["entry_time"]).sort_values("entry_time").reset_index(drop=True)

    if len(df) == 0:
        return warnings

    max_losses = MONEY_MANAGEMENT.get("max_consecutive_losses", 3)
    max_dd_pips = MONEY_MANAGEMENT.get("max_drawdown_pips", 100)
    max_daily_pips = MONEY_MANAGEMENT.get("max_daily_loss_pips", 50)

    # 1. 連敗チェック
    consecutive_losses = 0
    for win in reversed(df["win"].tolist()):
        if int(win) == 0:
            consecutive_losses += 1
        else:
            break

    if consecutive_losses >= max_losses:
        warnings.append({
            "level": "warning",
            "message": f"直近{consecutive_losses}連敗中。今回は見送り推奨"
        })

    # 2. 累積ドローダウン（pipsベース、最大ピークからの下落幅）
    cumulative = df["return_pips_net"].cumsum()
    peak = cumulative.cummax()
    current_dd_pips = float(peak.iloc[-1] - cumulative.iloc[-1])

    if current_dd_pips >= max_dd_pips:
        warnings.append({
            "level": "critical",
            "message": f"ピークから{current_dd_pips:.1f}pipsのドローダウン。ロット縮小or停止推奨"
        })

    # 3. 当日損失（UTC基準）
    today = pd.Timestamp.now(tz="UTC").normalize()
    today_df = df[df["entry_time"] >= today]
    today_loss_pips = today_df[today_df["return_pips_net"] < 0]["return_pips_net"].sum()
    today_loss_pips_abs = abs(float(today_loss_pips))

    if today_loss_pips_abs >= max_daily_pips:
        warnings.append({
            "level": "warning",
            "message": f"本日{today_loss_pips_abs:.1f}pipsの損失。今日はクールダウン推奨"
        })

    return warnings
