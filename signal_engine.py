"""
リアルタイムシグナル検出エンジン
最適化済み戦略で売買シグナルをリアルタイムに検出する
"""
import os
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands
from ta.trend import SMAIndicator
from datetime import datetime, timedelta
from event_filter import detect_volatility_spikes, get_scheduled_events
from config import PAIRS
from money_management import calculate_recommended_lot, get_warnings

# シグナル重複チェック用（GitHub Actions等のステートレス環境でも動作する）
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
SIGNALS_CSV = os.path.join(LOGS_DIR, "signals.csv")


def _is_recent_duplicate(pair, strategy_name, action, hours=1):
    """signals.csv から過去N時間以内の同一シグナルを検索

    GitHub Actions のような毎回新規プロセスで起動される環境では、
    インスタンス変数 (self.last_signals) は維持されないため、
    過去のシグナルログから判定する。
    """
    if not os.path.exists(SIGNALS_CSV):
        return False
    try:
        df = pd.read_csv(SIGNALS_CSV)
        if len(df) == 0:
            return False
        df["signal_time"] = pd.to_datetime(df["signal_time"], utc=True, errors="coerce")
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=hours)
        recent = df[
            (df["signal_time"] >= cutoff) &
            (df["pair"] == pair) &
            (df["strategy"] == strategy_name) &
            (df["action"] == action)
        ]
        return len(recent) > 0
    except Exception as e:
        print(f"  [重複チェックエラー] {e}")
        return False


class SignalEngine:
    """シグナル検出エンジン"""

    def __init__(self, strategies, event_filter_config):
        self.strategies = strategies
        self.event_config = event_filter_config
        # 重複チェックは signals.csv ベース（_is_recent_duplicate）で行う
        # → ステートレス環境（GitHub Actions等）でも正常動作する

    def compute_indicators(self, df, strategy_config):
        """テクニカル指標を計算"""
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        params = strategy_config["params"]
        indicators = {}

        stype = strategy_config["type"]

        if stype in ("rsi", "bb_rsi"):
            rsi = RSIIndicator(close, window=params["rsi_period"])
            indicators["rsi"] = rsi.rsi()

        if stype in ("bb_rsi", "bb"):
            bb = BollingerBands(close, window=params["bb_period"], window_dev=params["bb_std"])
            indicators["bb_upper"] = bb.bollinger_hband()
            indicators["bb_lower"] = bb.bollinger_lband()
            indicators["bb_mid"] = bb.bollinger_mavg()

        if stype == "stochastic":
            stoch = StochasticOscillator(
                high, low, close,
                window=params["k_period"],
                smooth_window=params["d_period"],
            )
            indicators["stoch_k"] = stoch.stoch()
            indicators["stoch_d"] = stoch.stoch_signal()

        # SMA Cross（移動平均クロス、トレンドフォロー）
        if stype == "sma_cross":
            sma_fast = SMAIndicator(close, window=params["fast_period"])
            sma_slow = SMAIndicator(close, window=params["slow_period"])
            indicators["sma_fast"] = sma_fast.sma_indicator()
            indicators["sma_slow"] = sma_slow.sma_indicator()

        # Donchian Channel（過去N期間の高安値ブレイクアウト）
        if stype == "donchian":
            period = params["period"]
            # 1本前までのN期間の高安値（現足のbreakout判定用）
            indicators["donchian_high"] = high.rolling(period).max().shift(1)
            indicators["donchian_low"] = low.rolling(period).min().shift(1)

        return indicators

    def check_signal(self, df, strategy_name, strategy_config):
        """
        1つの戦略でシグナルをチェック

        Returns:
            dict or None: シグナル情報。なければNone
        """
        if len(df) < 50:
            return None

        indicators = self.compute_indicators(df, strategy_config)
        params = strategy_config["params"]
        stype = strategy_config["type"]

        current_close = df["Close"].iloc[-1]
        signal = None

        if stype == "rsi":
            rsi_now = indicators["rsi"].iloc[-1]
            rsi_prev = indicators["rsi"].iloc[-2]
            if pd.isna(rsi_now):
                return None

            if rsi_now < params["rsi_lower"] and rsi_prev >= params["rsi_lower"]:
                signal = {
                    "action": "BUY",
                    "reason": f"RSI({params['rsi_period']})が{rsi_now:.1f}に下落 (閾値:{params['rsi_lower']})",
                    "strength": min((params["rsi_lower"] - rsi_now) / 10, 1.0),
                }
            elif rsi_now > params["rsi_upper"] and rsi_prev <= params["rsi_upper"]:
                signal = {
                    "action": "SELL",
                    "reason": f"RSI({params['rsi_period']})が{rsi_now:.1f}に上昇 (閾値:{params['rsi_upper']})",
                    "strength": min((rsi_now - params["rsi_upper"]) / 10, 1.0),
                }

        elif stype == "bb_rsi":
            rsi_now = indicators["rsi"].iloc[-1]
            bb_lower = indicators["bb_lower"].iloc[-1]
            bb_upper = indicators["bb_upper"].iloc[-1]
            if pd.isna(rsi_now) or pd.isna(bb_lower):
                return None

            if current_close < bb_lower and rsi_now < params["rsi_lower"]:
                signal = {
                    "action": "BUY",
                    "reason": (f"BB下限({bb_lower:.3f})割れ + RSI({rsi_now:.1f}) < {params['rsi_lower']}"),
                    "strength": min((params["rsi_lower"] - rsi_now) / 15 + (bb_lower - current_close) / current_close * 100, 1.0),
                }
            elif current_close > bb_upper and rsi_now > params["rsi_upper"]:
                signal = {
                    "action": "SELL",
                    "reason": (f"BB上限({bb_upper:.3f})超え + RSI({rsi_now:.1f}) > {params['rsi_upper']}"),
                    "strength": min((rsi_now - params["rsi_upper"]) / 15 + (current_close - bb_upper) / current_close * 100, 1.0),
                }

        elif stype == "stochastic":
            k_now = indicators["stoch_k"].iloc[-1]
            d_now = indicators["stoch_d"].iloc[-1]
            k_prev = indicators["stoch_k"].iloc[-2]
            d_prev = indicators["stoch_d"].iloc[-2]
            if pd.isna(k_now) or pd.isna(d_now):
                return None

            # 売られすぎ圏でGC
            if (k_now < params["lower"] and
                    k_now > d_now and k_prev <= d_prev):
                signal = {
                    "action": "BUY",
                    "reason": f"ストキャス(%K={k_now:.1f}, %D={d_now:.1f}) 売られすぎ圏でGC",
                    "strength": min((params["lower"] - k_now) / 20, 1.0),
                }
            # 買われすぎ圏でDC
            elif (k_now > params["upper"] and
                  k_now < d_now and k_prev >= d_prev):
                signal = {
                    "action": "SELL",
                    "reason": f"ストキャス(%K={k_now:.1f}, %D={d_now:.1f}) 買われすぎ圏でDC",
                    "strength": min((k_now - params["upper"]) / 20, 1.0),
                }

        # SMA Cross（移動平均クロス、トレンドフォロー）
        elif stype == "sma_cross":
            sma_fast_now = indicators["sma_fast"].iloc[-1]
            sma_slow_now = indicators["sma_slow"].iloc[-1]
            sma_fast_prev = indicators["sma_fast"].iloc[-2]
            sma_slow_prev = indicators["sma_slow"].iloc[-2]
            if pd.isna(sma_fast_now) or pd.isna(sma_slow_now):
                return None

            # ゴールデンクロス（短期が長期を上抜け）→ 順張り買い
            if sma_fast_now > sma_slow_now and sma_fast_prev <= sma_slow_prev:
                gap_pct = (sma_fast_now - sma_slow_now) / sma_slow_now * 100
                signal = {
                    "action": "BUY",
                    "reason": f"SMAゴールデンクロス（短期{sma_fast_now:.3f} > 長期{sma_slow_now:.3f}, 乖離{gap_pct:.2f}%）",
                    "strength": min(gap_pct * 5, 1.0),
                }
            # デッドクロス（短期が長期を下抜け）→ 順張り売り
            elif sma_fast_now < sma_slow_now and sma_fast_prev >= sma_slow_prev:
                gap_pct = (sma_slow_now - sma_fast_now) / sma_slow_now * 100
                signal = {
                    "action": "SELL",
                    "reason": f"SMAデッドクロス（短期{sma_fast_now:.3f} < 長期{sma_slow_now:.3f}, 乖離{gap_pct:.2f}%）",
                    "strength": min(gap_pct * 5, 1.0),
                }

        # Donchian Breakout（過去N期間の高安値ブレイクアウト）
        elif stype == "donchian":
            high_now = float(df["High"].iloc[-1])
            low_now = float(df["Low"].iloc[-1])
            donchian_high = indicators["donchian_high"].iloc[-1]
            donchian_low = indicators["donchian_low"].iloc[-1]
            if pd.isna(donchian_high) or pd.isna(donchian_low):
                return None

            # 高値ブレイク（上抜け）→ 順張り買い
            if high_now > donchian_high:
                breakout_pct = (high_now - donchian_high) / donchian_high * 100
                signal = {
                    "action": "BUY",
                    "reason": f"Donchian高値ブレイク（{donchian_high:.3f}を上抜け、現価{current_close:.3f}）",
                    "strength": min(breakout_pct * 10, 1.0),
                }
            # 安値ブレイク（下抜け）→ 順張り売り
            elif low_now < donchian_low:
                breakout_pct = (donchian_low - low_now) / donchian_low * 100
                signal = {
                    "action": "SELL",
                    "reason": f"Donchian安値ブレイク（{donchian_low:.3f}を下抜け、現価{current_close:.3f}）",
                    "strength": min(breakout_pct * 10, 1.0),
                }

        if signal is None:
            return None

        # 重複チェック（signals.csv から過去1時間以内の同一シグナルを確認）
        if _is_recent_duplicate(strategy_config["pair"], strategy_name, signal["action"]):
            return None

        # TP/SL価格を計算（指値注文用）
        pair_name = strategy_config["pair"]
        pair_cfg = PAIRS.get(pair_name, {})
        tp_pips = pair_cfg.get("tp_pips", 0)
        sl_pips = pair_cfg.get("sl_pips", 0)
        pip_unit = pair_cfg.get("pip_unit", 0.01)
        spread_pips = pair_cfg.get("spread_pips", 0)
        # 推奨指値範囲は ±2pips
        entry_offset = 2 * pip_unit

        if signal["action"] == "BUY":
            tp_price = current_close + tp_pips * pip_unit
            sl_price = current_close - sl_pips * pip_unit
        else:  # SELL
            tp_price = current_close - tp_pips * pip_unit
            sl_price = current_close + sl_pips * pip_unit

        # 資金管理：推奨ロット計算 + 警告生成
        recommended_lot = calculate_recommended_lot(pair_name, sl_pips)
        money_warnings = get_warnings()

        signal.update({
            "strategy": strategy_name,
            "pair": pair_name,
            "price": current_close,
            "time": df.index[-1],
            "backtest_winrate": strategy_config["backtest_winrate"],
            "backtest_pf": strategy_config["backtest_pf"],
            # 指値注文テンプレ用
            "tp_price": tp_price,
            "sl_price": sl_price,
            "tp_pips": tp_pips,
            "sl_pips": sl_pips,
            "entry_low": current_close - entry_offset,
            "entry_high": current_close + entry_offset,
            "pip_unit": pip_unit,
            "spread_pips": spread_pips,
            # 資金管理
            "recommended_lot": recommended_lot,
            "warnings": money_warnings,
        })

        return signal

    def is_event_period(self, df):
        """現在がイベント影響期間かどうか判定"""
        if not self.event_config.get("enabled", True):
            return False, ""

        now = datetime.utcnow()

        # カレンダーイベントチェック
        events = get_scheduled_events(
            pd.Timestamp(now - timedelta(days=1)),
            pd.Timestamp(now + timedelta(days=1)),
        )
        hours_before = self.event_config.get("hours_before", 2)
        hours_after = self.event_config.get("hours_after", 4) + 24

        for event_date in events:
            start = event_date - timedelta(hours=hours_before)
            end = event_date + timedelta(hours=hours_after)
            if start <= pd.Timestamp(now) <= end:
                return True, f"経済指標イベント付近 ({event_date.strftime('%m/%d')})"

        # ボラティリティスパイクチェック
        if len(df) > 30:
            spikes = detect_volatility_spikes(
                df,
                window=self.event_config.get("vol_window", 24),
                threshold=self.event_config.get("vol_threshold", 3.0),
            )
            if spikes.iloc[-1] or (len(spikes) > 1 and spikes.iloc[-2]):
                return True, "ボラティリティスパイク検出"

        return False, ""

    def scan_all(self, pair_data):
        """
        全戦略をスキャンしてシグナルを返す

        Parameters:
            pair_data: dict of {pair_name: DataFrame}

        Returns:
            list of signal dicts
        """
        signals = []

        for strategy_name, config in self.strategies.items():
            pair = config["pair"]
            if pair not in pair_data:
                continue

            df = pair_data[pair]

            # イベントフィルター
            is_event, event_reason = self.is_event_period(df)
            if is_event:
                continue  # イベント期間中はシグナルをスキップ

            signal = self.check_signal(df, strategy_name, config)
            if signal:
                signals.append(signal)

        return signals
