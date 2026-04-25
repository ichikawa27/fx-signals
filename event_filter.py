"""
経済指標イベントフィルター

investpy等の外部APIが不安定なため、以下の2つのアプローチで対応:
1. 定期イベント（毎月の雇用統計、FOMC等）をルールベースで生成
2. ボラティリティ急騰をイベントの代理指標として検出

アプローチ2が実用的：イベントの「結果」（急激な値動き）を直接検出するため、
カレンダーに載らないサプライズイベントもカバーできる。
"""
import pandas as pd
import numpy as np
from datetime import time


def get_scheduled_events(start_date, end_date):
    """
    主要な定期経済イベントの日付を生成（ルールベース）
    完全ではないが、主要イベントの大部分をカバー

    対象:
    - 米雇用統計 (毎月第1金曜)
    - FOMC (年8回、概ね6週間ごと)
    - 日銀金融政策決定会合 (年8回)
    - ECB理事会 (年8回)
    - 米CPI (毎月中旬)
    """
    # タイムゾーンを揃える
    start_date = pd.Timestamp(start_date).tz_localize(None)
    end_date = pd.Timestamp(end_date).tz_localize(None)
    dates = pd.date_range(start_date, end_date, freq="D")
    event_dates = set()

    for date in dates:
        # 米雇用統計: 毎月第1金曜日
        if date.weekday() == 4 and date.day <= 7:
            event_dates.add(date.normalize())

        # 米CPI: 毎月10日〜15日あたり（概算で12日前後）
        if date.day in [11, 12, 13] and date.weekday() < 5:
            event_dates.add(date.normalize())

    # FOMC (2024-2026の概算日程 - 実際の日程に近い)
    fomc_months = [1, 3, 5, 6, 7, 9, 11, 12]
    for year in range(start_date.year, end_date.year + 1):
        for month in fomc_months:
            # FOMCは概ね月の中旬〜下旬
            for day in [15, 16, 17, 18, 19, 20]:
                try:
                    d = pd.Timestamp(year, month, day)
                    if d.weekday() in [1, 2]:  # 火曜か水曜
                        event_dates.add(d.normalize())
                        break
                except ValueError:
                    continue

    return sorted(event_dates)


def detect_volatility_spikes(df, window=24, threshold=3.0):
    """
    ボラティリティの急騰を検出（イベントの代理指標）

    Parameters:
        df: OHLCデータ
        window: ボラティリティ計算ウィンドウ（足数）
        threshold: 標準偏差の何倍以上をスパイクとするか

    Returns:
        スパイクが検出された時間帯のインデックス
    """
    # 1足あたりの変動率
    returns = (df["Close"] / df["Close"].shift(1) - 1).abs()

    # ローリング平均と標準偏差
    rolling_mean = returns.rolling(window=window).mean()
    rolling_std = returns.rolling(window=window).std()

    # 閾値超え = ボラティリティスパイク
    spikes = returns > (rolling_mean + threshold * rolling_std)

    return spikes


def create_event_mask(df, method="volatility", hours_before=2, hours_after=4,
                      vol_window=24, vol_threshold=3.0):
    """
    イベント影響を受ける時間帯のマスクを作成

    Parameters:
        df: OHLCデータ（DatetimeIndex）
        method: "volatility" (ボラスパイク検出) or "calendar" (定期イベント) or "both"
        hours_before: イベント前の除外時間
        hours_after: イベント後の除外時間

    Returns:
        bool Series (True = イベント影響なし = 使用可能)
    """
    # タイムゾーンを統一（tz-naive化）
    idx = df.index.tz_localize(None) if df.index.tz is not None else df.index
    mask = pd.Series(True, index=idx)

    if method in ("calendar", "both"):
        event_dates = get_scheduled_events(idx[0], idx[-1])
        for event_date in event_dates:
            start = event_date - pd.Timedelta(hours=hours_before)
            end = event_date + pd.Timedelta(hours=hours_after + 24)
            mask.loc[(idx >= start) & (idx <= end)] = False

    if method in ("volatility", "both"):
        spikes = detect_volatility_spikes(df, window=vol_window, threshold=vol_threshold)
        spike_times = idx[spikes]
        for spike_time in spike_times:
            start = spike_time - pd.Timedelta(hours=hours_before)
            end = spike_time + pd.Timedelta(hours=hours_after)
            mask.loc[(idx >= start) & (idx <= end)] = False

    return mask


def filter_event_periods(df, method="both", **kwargs):
    """
    イベント期間を除外したデータフレームを返す

    Returns:
        filtered_df: イベント除外後のデータ
        stats: 除外統計
    """
    mask = create_event_mask(df, method=method, **kwargs)
    mask.index = df.index  # 元のインデックスに戻す
    filtered = df[mask].copy()

    stats = {
        "original_rows": len(df),
        "filtered_rows": len(filtered),
        "removed_rows": len(df) - len(filtered),
        "removed_pct": round((1 - len(filtered) / len(df)) * 100, 1),
    }

    return filtered, stats


if __name__ == "__main__":
    import os
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

    for pair in ["USDJPY", "EURUSD", "GBPJPY"]:
        path = os.path.join(DATA_DIR, f"{pair}_1h.csv")
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()

        print(f"\n{pair}:")
        for method in ["calendar", "volatility", "both"]:
            _, stats = filter_event_periods(df, method=method)
            print(f"  {method:12s}: {stats['removed_rows']:5d}行除外 "
                  f"({stats['removed_pct']}%) → {stats['filtered_rows']}行残り")
