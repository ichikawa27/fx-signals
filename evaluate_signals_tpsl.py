"""
TP/SL ベース シグナル評価スクリプト

logs/signals.csv の各シグナルについて、
シグナル発生後の 1時間足を順次チェックし、TP/SL のどちらが先にヒットしたかを判定する。
結果は logs/results_tpsl.csv に追記される。

GitHub Actions で1時間ごとに実行される想定。

【判定ロジック】
- BUYシグナル:
    - High >= TP価格 → TPヒット（勝ち）
    - Low <= SL価格 → SLヒット（負け）
- SELLシグナル:
    - Low <= TP価格 → TPヒット（勝ち）
    - High >= SL価格 → SLヒット（負け）
- 同一bar内でTPとSL両方が範囲内 → tie_breaker（デフォルト: SL先=保守的）
- max_holding_bars 本見てもどちらもヒットしない → TIMEOUT（24h時点の終値で強制決済）

【近似精度の限界】
1h足のHigh/Lowで判定するため、1h以内の値動き順序は分からない。
完全な精度には Tick データが必要。バックテストでも同じ近似を使うのが標準。
"""
import os
import csv
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone

from config import PAIRS, TPSL_EVALUATION

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
SIGNALS_CSV = os.path.join(LOGS_DIR, "signals.csv")
RESULTS_TPSL_CSV = os.path.join(LOGS_DIR, "results_tpsl.csv")

RESULT_FIELDS = [
    "signal_id",
    "pair",
    "strategy",
    "action",
    "entry_time",
    "entry_price",
    "tp_price",
    "sl_price",
    "exit_time",
    "exit_price",
    "hit_type",          # TP / SL / TIMEOUT
    "holding_bars",      # ヒットまでの1h足の本数
    "return_pips_gross", # スプレッド控除前のpips
    "return_pips_net",   # スプレッド控除後のpips
    "return_pct",        # 価格変化率
    "win",               # 1 if TP, 0 if SL/TIMEOUT(マイナスの場合)
    "evaluated_at",
]


def load_evaluated_ids():
    """既に評価済みの signal_id の集合を返す"""
    if not os.path.exists(RESULTS_TPSL_CSV):
        return set()
    df = pd.read_csv(RESULTS_TPSL_CSV)
    if len(df) == 0:
        return set()
    return set(df["signal_id"].astype(str))


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


def fetch_bars_after(ticker, start_time, max_hours=24):
    """start_time 以降の1h足を最大 max_hours 時間分取得

    Returns:
        DataFrame (UTC index, columns: Open, High, Low, Close)
        またはエラー時に空のDataFrame
    """
    # データ取得範囲（少し余裕を持たせる）
    fetch_start = (start_time - timedelta(days=1)).strftime("%Y-%m-%d")
    fetch_end = (start_time + timedelta(days=3)).strftime("%Y-%m-%d")

    try:
        df = yf.download(ticker, start=fetch_start, end=fetch_end, interval="1h", progress=False)
    except Exception as e:
        print(f"    [取得エラー] {ticker}: {e}")
        return pd.DataFrame()

    if len(df) == 0:
        return pd.DataFrame()

    # MultiIndexの解消（yfinance最近の挙動対応）
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close"]].dropna()

    # タイムゾーン正規化
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    # シグナル発生時刻以降のbarだけ
    df = df[df.index > start_time]

    # 最大本数で切る
    return df.head(max_hours)


def evaluate_signal_tpsl(signal_row):
    """1シグナルのTP/SL評価

    Returns:
        dict (RESULT_FIELDS の値) または None（評価不能）
    """
    pair = signal_row["pair"]
    if pair not in PAIRS:
        return None

    pair_cfg = PAIRS[pair]
    pip_unit = pair_cfg["pip_unit"]
    spread = pair_cfg["spread_pips"]
    tp_pips = pair_cfg["tp_pips"]
    sl_pips = pair_cfg["sl_pips"]
    tie_breaker = TPSL_EVALUATION.get("tie_breaker", "sl_first")
    max_bars = TPSL_EVALUATION.get("max_holding_bars", 24)

    entry_time = to_utc(signal_row["signal_time"])
    entry_price = float(signal_row["entry_price"])
    action = signal_row["action"]

    # TP/SL価格を計算
    if action == "BUY":
        tp_price = entry_price + tp_pips * pip_unit
        sl_price = entry_price - sl_pips * pip_unit
    elif action == "SELL":
        tp_price = entry_price - tp_pips * pip_unit
        sl_price = entry_price + sl_pips * pip_unit
    else:
        return None

    # シグナル発生後のbarを取得
    bars = fetch_bars_after(pair_cfg["ticker"], entry_time, max_hours=max_bars)
    if len(bars) == 0:
        # まだデータが揃っていない、または取得失敗
        return None

    # 1本ずつ判定
    exit_time = None
    exit_price = None
    hit_type = None
    holding_bars = 0

    for idx, bar in bars.iterrows():
        holding_bars += 1
        high = float(bar["High"])
        low = float(bar["Low"])

        if action == "BUY":
            tp_hit = high >= tp_price
            sl_hit = low <= sl_price
        else:  # SELL
            tp_hit = low <= tp_price
            sl_hit = high >= sl_price

        if tp_hit and sl_hit:
            # 同一bar内で両方ヒット → tie_breaker
            if tie_breaker == "sl_first":
                hit_type = "SL"
                exit_price = sl_price
            else:
                hit_type = "TP"
                exit_price = tp_price
            exit_time = idx
            break
        elif tp_hit:
            hit_type = "TP"
            exit_price = tp_price
            exit_time = idx
            break
        elif sl_hit:
            hit_type = "SL"
            exit_price = sl_price
            exit_time = idx
            break

    # max_bars 本見てもヒットせず → TIMEOUT
    if hit_type is None:
        if len(bars) < max_bars:
            # まだ24h経過していない → 評価保留
            return None
        last_bar = bars.iloc[-1]
        hit_type = "TIMEOUT"
        exit_time = bars.index[-1]
        exit_price = float(last_bar["Close"])

    # 損益計算
    if action == "BUY":
        diff = exit_price - entry_price
    else:
        diff = entry_price - exit_price

    gross_pips = diff / pip_unit
    net_pips = gross_pips - 2 * spread  # 往復スプレッド
    return_pct = diff / entry_price * 100
    win = 1 if net_pips > 0 else 0

    return {
        "signal_id": signal_row["signal_id"],
        "pair": pair,
        "strategy": signal_row["strategy"],
        "action": action,
        "entry_time": entry_time.isoformat(),
        "entry_price": entry_price,
        "tp_price": round(tp_price, 5),
        "sl_price": round(sl_price, 5),
        "exit_time": exit_time.isoformat(),
        "exit_price": round(exit_price, 5),
        "hit_type": hit_type,
        "holding_bars": holding_bars,
        "return_pips_gross": round(gross_pips, 2),
        "return_pips_net": round(net_pips, 2),
        "return_pct": round(return_pct, 4),
        "win": win,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def evaluate_all():
    signals = load_signals()
    if len(signals) == 0:
        print("シグナル記録がありません")
        return 0

    evaluated_ids = load_evaluated_ids()
    new_rows = []
    skipped = 0
    pending = 0

    for _, sig in signals.iterrows():
        signal_id = str(sig["signal_id"])
        if signal_id in evaluated_ids:
            skipped += 1
            continue

        result = evaluate_signal_tpsl(sig)
        if result is None:
            pending += 1
            continue

        new_rows.append(result)

    if not new_rows:
        print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
              f"新規TP/SL評価なし (シグナル={len(signals)}, 評価済={len(evaluated_ids)}, 保留={pending})")
        return 0

    os.makedirs(LOGS_DIR, exist_ok=True)
    file_exists = os.path.exists(RESULTS_TPSL_CSV)
    with open(RESULTS_TPSL_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)

    # サマリ表示
    tp_count = sum(1 for r in new_rows if r["hit_type"] == "TP")
    sl_count = sum(1 for r in new_rows if r["hit_type"] == "SL")
    timeout_count = sum(1 for r in new_rows if r["hit_type"] == "TIMEOUT")
    win_count = sum(r["win"] for r in new_rows)

    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
          f"{len(new_rows)}件のTP/SL評価追加 "
          f"(TP={tp_count}, SL={sl_count}, TIMEOUT={timeout_count}, "
          f"win={win_count}/{len(new_rows)})")
    return len(new_rows)


if __name__ == "__main__":
    evaluate_all()
