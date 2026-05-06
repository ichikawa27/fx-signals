"""
FXバックテストエンジン
複数のテクニカル戦略を全通貨ペアで自動検証し、勝率の高い戦略を特定する
"""
import os
import glob
import warnings
import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
from ta.trend import SMAIndicator, EMAIndicator, MACD, IchimokuIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands

warnings.filterwarnings("ignore")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load_data(pair, interval="1h"):
    """CSVからデータを読み込み、backtesting.py用に整形"""
    path = os.path.join(DATA_DIR, f"{pair}_{interval}.csv")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    # backtesting.pyはOpen/High/Low/Close/Volumeカラムが必要
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df


# ============================================================
# 戦略定義
# ============================================================

class RSI_Strategy(Strategy):
    """RSI逆張り"""
    rsi_period = 14
    rsi_lower = 30
    rsi_upper = 70

    def init(self):
        close = pd.Series(self.data.Close, index=range(len(self.data.Close)))
        rsi = RSIIndicator(close, window=self.rsi_period).rsi()
        self.rsi = self.I(lambda: rsi.values)

    def next(self):
        if self.rsi[-1] < self.rsi_lower and not self.position:
            self.buy()
        elif self.rsi[-1] > self.rsi_upper and self.position:
            self.position.close()


class MACD_Strategy(Strategy):
    """MACDクロス"""
    fast = 12
    slow = 26
    signal = 9

    def init(self):
        close = pd.Series(self.data.Close, index=range(len(self.data.Close)))
        macd = MACD(close, window_fast=self.fast, window_slow=self.slow, window_sign=self.signal)
        self.macd_line = self.I(lambda: macd.macd().values)
        self.signal_line = self.I(lambda: macd.macd_signal().values)

    def next(self):
        if self.macd_line[-1] > self.signal_line[-1] and self.macd_line[-2] <= self.signal_line[-2]:
            if not self.position:
                self.buy()
        elif self.macd_line[-1] < self.signal_line[-1] and self.macd_line[-2] >= self.signal_line[-2]:
            if self.position:
                self.position.close()


class BollingerBand_Strategy(Strategy):
    """ボリンジャーバンド逆張り"""
    bb_period = 20
    bb_std = 2

    def init(self):
        close = pd.Series(self.data.Close, index=range(len(self.data.Close)))
        bb = BollingerBands(close, window=self.bb_period, window_dev=self.bb_std)
        self.bb_upper = self.I(lambda: bb.bollinger_hband().values)
        self.bb_lower = self.I(lambda: bb.bollinger_lband().values)
        self.bb_mid = self.I(lambda: bb.bollinger_mavg().values)

    def next(self):
        if self.data.Close[-1] < self.bb_lower[-1] and not self.position:
            self.buy()
        elif self.data.Close[-1] > self.bb_upper[-1] and self.position:
            self.position.close()


class SMA_Cross_Strategy(Strategy):
    """移動平均クロス"""
    fast_period = 10
    slow_period = 50

    def init(self):
        close = pd.Series(self.data.Close, index=range(len(self.data.Close)))
        self.sma_fast = self.I(lambda: SMAIndicator(close, window=self.fast_period).sma_indicator().values)
        self.sma_slow = self.I(lambda: SMAIndicator(close, window=self.slow_period).sma_indicator().values)

    def next(self):
        if self.sma_fast[-1] > self.sma_slow[-1] and self.sma_fast[-2] <= self.sma_slow[-2]:
            if not self.position:
                self.buy()
        elif self.sma_fast[-1] < self.sma_slow[-1] and self.sma_fast[-2] >= self.sma_slow[-2]:
            if self.position:
                self.position.close()


class EMA_Cross_Strategy(Strategy):
    """EMAクロス"""
    fast_period = 12
    slow_period = 26

    def init(self):
        close = pd.Series(self.data.Close, index=range(len(self.data.Close)))
        self.ema_fast = self.I(lambda: EMAIndicator(close, window=self.fast_period).ema_indicator().values)
        self.ema_slow = self.I(lambda: EMAIndicator(close, window=self.slow_period).ema_indicator().values)

    def next(self):
        if self.ema_fast[-1] > self.ema_slow[-1] and self.ema_fast[-2] <= self.ema_slow[-2]:
            if not self.position:
                self.buy()
        elif self.ema_fast[-1] < self.ema_slow[-1] and self.ema_fast[-2] >= self.ema_slow[-2]:
            if self.position:
                self.position.close()


class Stochastic_Strategy(Strategy):
    """ストキャスティクス"""
    k_period = 14
    d_period = 3
    lower = 20
    upper = 80

    def init(self):
        high = pd.Series(self.data.High, index=range(len(self.data.High)))
        low = pd.Series(self.data.Low, index=range(len(self.data.Low)))
        close = pd.Series(self.data.Close, index=range(len(self.data.Close)))
        stoch = StochasticOscillator(high, low, close, window=self.k_period, smooth_window=self.d_period)
        self.k = self.I(lambda: stoch.stoch().values)
        self.d = self.I(lambda: stoch.stoch_signal().values)

    def next(self):
        if self.k[-1] < self.lower and self.k[-1] > self.d[-1] and self.k[-2] <= self.d[-2]:
            if not self.position:
                self.buy()
        elif self.k[-1] > self.upper and self.k[-1] < self.d[-1] and self.k[-2] >= self.d[-2]:
            if self.position:
                self.position.close()


class RSI_MACD_Strategy(Strategy):
    """RSI + MACD 複合"""
    rsi_period = 14
    rsi_lower = 40
    fast = 12
    slow = 26
    signal = 9

    def init(self):
        close = pd.Series(self.data.Close, index=range(len(self.data.Close)))
        rsi = RSIIndicator(close, window=self.rsi_period).rsi()
        self.rsi = self.I(lambda: rsi.values)
        macd = MACD(close, window_fast=self.fast, window_slow=self.slow, window_sign=self.signal)
        self.macd_line = self.I(lambda: macd.macd().values)
        self.signal_line = self.I(lambda: macd.macd_signal().values)

    def next(self):
        macd_cross_up = (self.macd_line[-1] > self.signal_line[-1] and
                         self.macd_line[-2] <= self.signal_line[-2])
        macd_cross_down = (self.macd_line[-1] < self.signal_line[-1] and
                           self.macd_line[-2] >= self.signal_line[-2])

        if macd_cross_up and self.rsi[-1] < self.rsi_lower and not self.position:
            self.buy()
        elif macd_cross_down and self.position:
            self.position.close()


class BB_RSI_Strategy(Strategy):
    """ボリンジャーバンド + RSI 複合"""
    bb_period = 20
    bb_std = 2
    rsi_period = 14
    rsi_lower = 35
    rsi_upper = 65

    def init(self):
        close = pd.Series(self.data.Close, index=range(len(self.data.Close)))
        bb = BollingerBands(close, window=self.bb_period, window_dev=self.bb_std)
        self.bb_upper = self.I(lambda: bb.bollinger_hband().values)
        self.bb_lower = self.I(lambda: bb.bollinger_lband().values)
        rsi = RSIIndicator(close, window=self.rsi_period).rsi()
        self.rsi = self.I(lambda: rsi.values)

    def next(self):
        if (self.data.Close[-1] < self.bb_lower[-1] and
                self.rsi[-1] < self.rsi_lower and not self.position):
            self.buy()
        elif (self.data.Close[-1] > self.bb_upper[-1] and
              self.rsi[-1] > self.rsi_upper and self.position):
            self.position.close()


class SMA_Triple_Strategy(Strategy):
    """3本移動平均線（短期・中期・長期）"""
    short = 5
    mid = 20
    long = 75

    def init(self):
        close = pd.Series(self.data.Close, index=range(len(self.data.Close)))
        self.sma_s = self.I(lambda: SMAIndicator(close, window=self.short).sma_indicator().values)
        self.sma_m = self.I(lambda: SMAIndicator(close, window=self.mid).sma_indicator().values)
        self.sma_l = self.I(lambda: SMAIndicator(close, window=self.long).sma_indicator().values)

    def next(self):
        # パーフェクトオーダー（短期>中期>長期）で買い
        if (self.sma_s[-1] > self.sma_m[-1] > self.sma_l[-1] and
                not (self.sma_s[-2] > self.sma_m[-2] > self.sma_l[-2])):
            if not self.position:
                self.buy()
        # 逆パーフェクトオーダーで決済
        elif (self.sma_s[-1] < self.sma_m[-1] < self.sma_l[-1] and self.position):
            self.position.close()


class SMA_Cross_Both_Strategy(Strategy):
    """移動平均クロス（双方向、Phase 7用）

    既存 SMA_Cross_Strategy は買いのみだが、これは売りも対応。
    signal_engine.py の sma_cross と同じロジック。
    """
    fast_period = 20
    slow_period = 50

    def init(self):
        close = pd.Series(self.data.Close, index=range(len(self.data.Close)))
        self.sma_fast = self.I(lambda: SMAIndicator(close, window=self.fast_period).sma_indicator().values)
        self.sma_slow = self.I(lambda: SMAIndicator(close, window=self.slow_period).sma_indicator().values)

    def next(self):
        # ゴールデンクロス → 買い（既存ポジションがあればクローズしてから）
        if self.sma_fast[-1] > self.sma_slow[-1] and self.sma_fast[-2] <= self.sma_slow[-2]:
            if self.position:
                self.position.close()
            self.buy()
        # デッドクロス → 売り
        elif self.sma_fast[-1] < self.sma_slow[-1] and self.sma_fast[-2] >= self.sma_slow[-2]:
            if self.position:
                self.position.close()
            self.sell()


class Donchian_Strategy(Strategy):
    """Donchian Channel ブレイクアウト（双方向、Phase 7用）

    過去N期間の高安値ブレイクで順張り。タートル・トレーダーの古典手法。
    signal_engine.py の donchian と同じロジック。
    """
    period = 20

    def init(self):
        high = pd.Series(self.data.High, index=range(len(self.data.High)))
        low = pd.Series(self.data.Low, index=range(len(self.data.Low)))
        # 1bar前までの過去N期間の高安値
        self.donchian_high = self.I(
            lambda: high.rolling(self.period).max().shift(1).values
        )
        self.donchian_low = self.I(
            lambda: low.rolling(self.period).min().shift(1).values
        )

    def next(self):
        if pd.isna(self.donchian_high[-1]) or pd.isna(self.donchian_low[-1]):
            return
        high_now = self.data.High[-1]
        low_now = self.data.Low[-1]

        # 高値ブレイク → 買い
        if high_now > self.donchian_high[-1]:
            if self.position:
                self.position.close()
            self.buy()
        # 安値ブレイク → 売り
        elif low_now < self.donchian_low[-1]:
            if self.position:
                self.position.close()
            self.sell()


# ============================================================
# バックテスト実行
# ============================================================

STRATEGIES = [
    ("RSI逆張り", RSI_Strategy),
    ("MACDクロス", MACD_Strategy),
    ("ボリンジャーバンド逆張り", BollingerBand_Strategy),
    ("SMAクロス(10/50)", SMA_Cross_Strategy),
    ("EMAクロス(12/26)", EMA_Cross_Strategy),
    ("ストキャスティクス", Stochastic_Strategy),
    ("RSI+MACD複合", RSI_MACD_Strategy),
    ("BB+RSI複合", BB_RSI_Strategy),
    ("3本SMA(5/20/75)", SMA_Triple_Strategy),
]

PAIRS = ["USDJPY", "EURUSD", "GBPJPY"]
SPREAD_PIPS = {"USDJPY": 0.3, "EURUSD": 0.2, "GBPJPY": 0.8}  # 一般的なスプレッド


def run_all_backtests(interval="1h"):
    """全戦略×全ペアでバックテスト実行"""
    results = []

    for pair in PAIRS:
        print(f"\n{'='*60}")
        print(f"  {pair} ({interval})")
        print(f"{'='*60}")

        df = load_data(pair, interval)

        # スプレッドをコミッションとして近似（片道、%換算）
        avg_price = df["Close"].mean()
        if "JPY" in pair:
            spread_cost = SPREAD_PIPS[pair] * 0.01 / avg_price * 100  # pips -> %
        else:
            spread_cost = SPREAD_PIPS[pair] * 0.0001 / avg_price * 100

        for name, strat_class in STRATEGIES:
            try:
                bt = Backtest(
                    df, strat_class,
                    cash=1_000_000,  # 100万円
                    commission=spread_cost / 100,
                    exclusive_orders=True,
                )
                stats = bt.run()

                result = {
                    "通貨ペア": pair,
                    "戦略": name,
                    "勝率(%)": round(stats["Win Rate [%]"], 1) if not pd.isna(stats["Win Rate [%]"]) else 0,
                    "リターン(%)": round(stats["Return [%]"], 2),
                    "最大DD(%)": round(stats["Max. Drawdown [%]"], 2),
                    "トレード数": stats["# Trades"],
                    "PF": round(stats["Profit Factor"], 2) if not pd.isna(stats.get("Profit Factor")) else 0,
                    "シャープ比": round(stats["Sharpe Ratio"], 2) if not pd.isna(stats.get("Sharpe Ratio")) else 0,
                    "期間": f"{df.index[0].strftime('%Y-%m')} ~ {df.index[-1].strftime('%Y-%m')}",
                }
                results.append(result)
                mark = "***" if result["勝率(%)"] >= 55 and result["トレード数"] >= 20 else "   "
                print(f"  {mark} {name:20s} | 勝率:{result['勝率(%)']:5.1f}% | "
                      f"PF:{result['PF']:5.2f} | DD:{result['最大DD(%)']:6.2f}% | "
                      f"取引:{result['トレード数']:4d}回 | リターン:{result['リターン(%)']:7.2f}%")
            except Exception as e:
                print(f"       {name:20s} | ERROR: {e}")

    return pd.DataFrame(results)


def show_ranking(df_results):
    """勝率ランキングを表示（十分なトレード数があるもののみ）"""
    # トレード数が20以上のものに絞る
    df = df_results[df_results["トレード数"] >= 20].copy()

    if len(df) == 0:
        print("\n十分なトレード数(20回以上)の戦略がありませんでした")
        return

    # スコア = 勝率 * 0.4 + PF正規化 * 0.3 + シャープ比正規化 * 0.3
    df["スコア"] = (
        df["勝率(%)"] / 100 * 40 +
        df["PF"].clip(0, 5) / 5 * 30 +
        df["シャープ比"].clip(-2, 5) / 5 * 30
    )

    df_sorted = df.sort_values("スコア", ascending=False)

    print(f"\n{'='*80}")
    print("  総合ランキング TOP15（トレード数20回以上）")
    print(f"{'='*80}")
    print(f"{'順位':>4s} | {'通貨ペア':>8s} | {'戦略':>22s} | {'勝率':>6s} | {'PF':>5s} | "
          f"{'DD':>7s} | {'取引数':>5s} | {'リターン':>8s} | {'スコア':>5s}")
    print("-" * 80)

    for i, (_, row) in enumerate(df_sorted.head(15).iterrows()):
        print(f"  {i+1:2d}  | {row['通貨ペア']:>8s} | {row['戦略']:>22s} | "
              f"{row['勝率(%)']:5.1f}% | {row['PF']:5.2f} | "
              f"{row['最大DD(%)']:6.2f}% | {row['トレード数']:4d}回 | "
              f"{row['リターン(%)']:7.2f}% | {row['スコア']:5.1f}")

    # CSVに保存
    csv_path = os.path.join(DATA_DIR, "backtest_results.csv")
    df_sorted.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n結果を保存: {csv_path}")


if __name__ == "__main__":
    print("=" * 60)
    print("  FXバックテスト - 9戦略 × 3通貨ペア 自動検証")
    print("=" * 60)

    # 1時間足でテスト
    print("\n>>> 1時間足バックテスト <<<")
    results_1h = run_all_backtests("1h")
    show_ranking(results_1h)

    # 日足でもテスト
    print("\n\n>>> 日足バックテスト <<<")
    results_1d = run_all_backtests("1d")
    show_ranking(results_1d)
