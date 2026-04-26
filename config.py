"""
FXシグナル設定ファイル
バックテスト最適化結果に基づくパラメータ
"""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ============================================================
# Discord Webhook URL（.envファイルから読み込み）
# ============================================================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# ============================================================
# 監視対象通貨ペア
# ============================================================
PAIRS = {
    "USDJPY": {
        "ticker": "USDJPY=X",       # yfinance用
        "twelve": "USD/JPY",         # Twelve Data用
        "pip_unit": 0.01,            # 1pip = 0.01
        "spread_pips": 0.3,
        # TP/SL設定（リスクリワード比 1:2、最大保有24h）
        "tp_pips": 30,
        "sl_pips": 15,
    },
    "EURUSD": {
        "ticker": "EURUSD=X",
        "twelve": "EUR/USD",
        "pip_unit": 0.0001,
        "spread_pips": 0.2,
        "tp_pips": 20,
        "sl_pips": 10,
    },
    "GBPJPY": {
        "ticker": "GBPJPY=X",
        "twelve": "GBP/JPY",
        "pip_unit": 0.01,
        "spread_pips": 0.8,
        # GBPJPYはボラティリティが高いため、TP/SLも広め
        "tp_pips": 50,
        "sl_pips": 25,
    },
}

# ============================================================
# 戦略設定（最適化済みパラメータ）
# ============================================================
STRATEGIES = {
    # WF検証1位: GBP/JPY BB+RSI (勝率79.4%, PF6.63)
    "GBPJPY_BB_RSI": {
        "pair": "GBPJPY",
        "type": "bb_rsi",
        "params": {
            "bb_period": 20,
            "bb_std": 2.5,
            "rsi_period": 14,
            "rsi_lower": 25,
            "rsi_upper": 70,
        },
        "backtest_winrate": 79.4,
        "backtest_pf": 6.63,
    },
    # WF検証2位: USD/JPY BB+RSI (勝率69.7%, PF5.65)
    "USDJPY_BB_RSI": {
        "pair": "USDJPY",
        "type": "bb_rsi",
        "params": {
            "bb_period": 20,
            "bb_std": 2.5,
            "rsi_period": 16,
            "rsi_lower": 30,
            "rsi_upper": 60,
        },
        "backtest_winrate": 69.7,
        "backtest_pf": 5.65,
    },
    # WF検証3位: USD/JPY RSI逆張り (勝率69.4%, PF6.97)
    "USDJPY_RSI": {
        "pair": "USDJPY",
        "type": "rsi",
        "params": {
            "rsi_period": 14,
            "rsi_lower": 30,
            "rsi_upper": 70,
        },
        "backtest_winrate": 69.4,
        "backtest_pf": 6.97,
    },
    # WF検証5位: GBP/JPY ストキャスティクス (勝率65.3%, PF3.71, 取引数最多)
    "GBPJPY_STOCH": {
        "pair": "GBPJPY",
        "type": "stochastic",
        "params": {
            "k_period": 10,
            "d_period": 4,
            "lower": 20,
            "upper": 80,
        },
        "backtest_winrate": 65.3,
        "backtest_pf": 3.71,
    },
    # WF検証6位: USD/JPY ストキャスティクス (勝率78.7%, PF1.85)
    "USDJPY_STOCH": {
        "pair": "USDJPY",
        "type": "stochastic",
        "params": {
            "k_period": 10,
            "d_period": 4,
            "lower": 20,
            "upper": 80,
        },
        "backtest_winrate": 78.7,
        "backtest_pf": 1.85,
    },
    # EUR/USD ストキャスティクス (最適化ランキング9位, 取引数140回で安定)
    "EURUSD_STOCH": {
        "pair": "EURUSD",
        "type": "stochastic",
        "params": {
            "k_period": 10,
            "d_period": 4,
            "lower": 20,
            "upper": 80,
        },
        "backtest_winrate": 71.4,
        "backtest_pf": 2.14,
    },
}

# ============================================================
# イベントフィルター設定
# ============================================================
EVENT_FILTER = {
    "enabled": True,
    "method": "both",           # "calendar", "volatility", "both"
    "hours_before": 2,          # イベント前の除外時間
    "hours_after": 4,           # イベント後の除外時間
    "vol_window": 24,           # ボラティリティ計算ウィンドウ
    "vol_threshold": 3.0,       # ボラスパイク閾値（σ倍）
}

# ============================================================
# データ取得設定
# ============================================================
DATA_FETCH = {
    "interval": "1h",           # 1時間足
    "lookback_bars": 200,       # テクニカル計算に必要な過去足数
    "check_interval_sec": 300,  # チェック間隔（秒）= 5分
}

# ============================================================
# シグナル評価設定
# ============================================================
EVALUATION = {
    # 旧評価方式（N時間後の終値で評価）
    "horizons_hours": [1, 4, 24],
}

# ============================================================
# TP/SL評価設定
# ============================================================
TPSL_EVALUATION = {
    # 最大保有時間（これを超えたら強制決済）
    "max_holding_hours": 24,
    # 1h足の本数（24時間 = 24本）。これより多いと評価できないシグナルもある
    "max_holding_bars": 24,
    # 同一bar内でTP/SLどちらにもヒットした場合の扱い
    # "sl_first": 保守的（SL先と仮定、業界標準）
    # "tp_first": 楽観的（TP先と仮定）
    "tie_breaker": "sl_first",
}

# ============================================================
# 資金管理設定（マネーマネジメント）
# ============================================================
MONEY_MANAGEMENT = {
    # 口座情報（JPY建て前提）
    "account_balance": 1000000,        # 円。実際の運用額に合わせて変更
    "account_currency": "JPY",         # 現状 JPY のみサポート

    # リスク管理
    "risk_per_trade_pct": 1.0,         # 1トレードあたりのリスク（口座残高の%）

    # クロス通貨ペア（EURUSD等）のロット計算で使う USDJPY 概算レート
    # 精度優先なら yfinance で動的取得に変更可能
    "usdjpy_estimate": 150.0,

    # ロット粒度（業者によって 0.01 or 0.1）
    "lot_step": 0.01,

    # 警告閾値
    "max_consecutive_losses": 3,        # 連敗警告
    "max_drawdown_pips": 100,           # 累積ドローダウン警告（pips）
    "max_daily_loss_pips": 50,          # 当日損失警告（pips）
}
