"""
FX過去データ取得スクリプト
USD/JPY, EUR/USD, GBP/JPY の過去データをyfinanceから取得
"""
import yfinance as yf
import pandas as pd
import os

PAIRS = {
    "USDJPY": "USDJPY=X",
    "EURUSD": "EURUSD=X",
    "GBPJPY": "GBPJPY=X",
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def fetch_fx_data(period="5y", interval="1h"):
    """
    FXデータを取得してCSVに保存

    Parameters:
        period: 取得期間 (1h足は最大730日=約2年、1d足は最大5年)
        interval: 足の間隔 (1m, 5m, 15m, 1h, 1d, etc.)
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    for name, ticker in PAIRS.items():
        print(f"Fetching {name} ({ticker}) ... ", end="")
        df = yf.download(ticker, period=period, interval=interval, progress=False)

        # マルチレベルカラムをフラット化
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        csv_path = os.path.join(DATA_DIR, f"{name}_{interval}.csv")
        df.to_csv(csv_path)
        print(f"{len(df)} rows -> {csv_path}")

    print("\nDone!")


if __name__ == "__main__":
    # 1時間足（最大約2年分）- メインのバックテスト用
    fetch_fx_data(period="2y", interval="1h")

    # 日足（5年分）- 長期検証用
    fetch_fx_data(period="5y", interval="1d")
