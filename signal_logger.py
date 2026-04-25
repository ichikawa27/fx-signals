"""
シグナル記録モジュール
シグナルが発生したタイミングで logs/signals.csv に追記する
"""
import os
import csv
from datetime import datetime

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
SIGNALS_CSV = os.path.join(LOGS_DIR, "signals.csv")

FIELDS = [
    "signal_id",
    "signal_time",
    "sent_time",
    "pair",
    "action",
    "entry_price",
    "strategy",
    "strength",
    "backtest_winrate",
    "backtest_pf",
    "reason",
]


def _to_iso(t):
    if hasattr(t, "isoformat"):
        return t.isoformat()
    return str(t)


def make_signal_id(signal):
    return f"{_to_iso(signal['time'])}_{signal['pair']}_{signal['strategy']}_{signal['action']}"


def log_signal(signal):
    """シグナル1件をCSVに追記"""
    os.makedirs(LOGS_DIR, exist_ok=True)
    file_exists = os.path.exists(SIGNALS_CSV)

    row = {
        "signal_id": make_signal_id(signal),
        "signal_time": _to_iso(signal["time"]),
        "sent_time": datetime.now().isoformat(timespec="seconds"),
        "pair": signal["pair"],
        "action": signal["action"],
        "entry_price": float(signal["price"]),
        "strategy": signal["strategy"],
        "strength": round(float(signal.get("strength", 0)), 4),
        "backtest_winrate": signal.get("backtest_winrate", 0),
        "backtest_pf": signal.get("backtest_pf", 0),
        "reason": signal.get("reason", ""),
    }

    with open(SIGNALS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
