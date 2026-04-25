"""
シグナル評価スクリプト
logs/signals.csv の各シグナルについて、1h/4h/24h 後の価格と比較してリターンを計算し
logs/results.csv に追記する。
launchd で1時間ごとに実行される想定。
"""
import os
import csv
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone

from config import PAIRS, EVALUATION

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
SIGNALS_CSV = os.path.join(LOGS_DIR, "signals.csv")
RESULTS_CSV = os.path.join(LOGS_DIR, "results.csv")

RESULT_FIELDS = [
    "signal_id",
    "horizon_hours",
    "entry_time",
    "entry_price",
    "exit_time",
    "exit_price",
    "pair",
    "strategy",
    "action",
    "return_pips_gross",
    "return_pips_net",
    "return_pct",
    "win",
    "evaluated_at",
]


def load_evaluated():
    """既に評価済みの (signal_id, horizon) の集合"""
    if not os.path.exists(RESULTS_CSV):
        return set()
    df = pd.read_csv(RESULTS_CSV)
    if len(df) == 0:
        return set()
    return set(zip(df["signal_id"].astype(str), df["horizon_hours"].astype(int)))


def load_signals():
    if not os.path.exists(SIGNALS_CSV):
        return pd.DataFrame()
    return pd.read_csv(SIGNALS_CSV)


def to_utc(ts):
    """pd.Timestamp/datetime を UTC aware に変換"""
    t = pd.Timestamp(ts)
    if t.tz is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def fetch_price_at(ticker, target_time):
    """target_time 以降で最初に確定している1h足の終値を返す"""
    start = (target_time - timedelta(days=1)).strftime("%Y-%m-%d")
    end = (target_time + timedelta(days=2)).strftime("%Y-%m-%d")
    try:
        df = yf.download(ticker, start=start, end=end, interval="1h", progress=False)
    except Exception as e:
        print(f"    [取得エラー] {ticker}: {e}")
        return None, None
    if len(df) == 0:
        return None, None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Close"]].dropna()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    candidates = df[df.index >= target_time]
    if len(candidates) == 0:
        return None, None
    first = candidates.iloc[0]
    return first.name, float(first["Close"])


def evaluate_all():
    signals = load_signals()
    if len(signals) == 0:
        print("シグナル記録がありません")
        return 0

    evaluated = load_evaluated()
    now = datetime.now(timezone.utc)
    horizons = EVALUATION["horizons_hours"]

    new_rows = []

    for _, sig in signals.iterrows():
        signal_id = sig["signal_id"]
        pair = sig["pair"]
        if pair not in PAIRS:
            continue

        entry_time = to_utc(sig["signal_time"])
        entry_price = float(sig["entry_price"])
        action = sig["action"]
        pair_cfg = PAIRS[pair]
        pip_unit = pair_cfg["pip_unit"]
        spread = pair_cfg["spread_pips"]

        for h in horizons:
            if (signal_id, h) in evaluated:
                continue

            target_exit = entry_time + timedelta(hours=h)
            if target_exit > now:
                continue  # まだホライズンに到達していない

            actual_exit_time, exit_price = fetch_price_at(pair_cfg["ticker"], target_exit)
            if exit_price is None:
                print(f"    [スキップ] {signal_id} h={h}: 出口価格取得できず")
                continue

            if action == "BUY":
                diff = exit_price - entry_price
            else:
                diff = entry_price - exit_price

            gross_pips = diff / pip_unit
            net_pips = gross_pips - 2 * spread
            return_pct = diff / entry_price * 100

            new_rows.append({
                "signal_id": signal_id,
                "horizon_hours": h,
                "entry_time": entry_time.isoformat(),
                "entry_price": entry_price,
                "exit_time": actual_exit_time.isoformat(),
                "exit_price": exit_price,
                "pair": pair,
                "strategy": sig["strategy"],
                "action": action,
                "return_pips_gross": round(gross_pips, 2),
                "return_pips_net": round(net_pips, 2),
                "return_pct": round(return_pct, 4),
                "win": 1 if net_pips > 0 else 0,
                "evaluated_at": now.isoformat(timespec="seconds"),
            })

    if not new_rows:
        print(f"[{now.isoformat(timespec='seconds')}] 新規評価なし (シグナル={len(signals)}, 評価済={len(evaluated)})")
        return 0

    os.makedirs(LOGS_DIR, exist_ok=True)
    file_exists = os.path.exists(RESULTS_CSV)
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)

    print(f"[{now.isoformat(timespec='seconds')}] {len(new_rows)}件評価追加 "
          f"(win={sum(r['win'] for r in new_rows)}/{len(new_rows)})")
    return len(new_rows)


if __name__ == "__main__":
    evaluate_all()
