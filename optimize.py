"""
パラメータ最適化スクリプト
上位戦略のパラメータを最適化し、イベント除外あり/なしで比較する
"""
import os
import warnings
import pandas as pd
import numpy as np
from backtesting import Backtest
from backtest import (
    RSI_Strategy, MACD_Strategy, BollingerBand_Strategy,
    Stochastic_Strategy, BB_RSI_Strategy, SMA_Cross_Strategy,
    load_data, SPREAD_PIPS,
)
from event_filter import filter_event_periods

warnings.filterwarnings("ignore")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# 最適化対象: 1時間足TOP5の戦略
OPTIMIZE_TARGETS = [
    {
        "name": "RSI逆張り",
        "class": RSI_Strategy,
        "params": dict(
            rsi_period=range(8, 22, 2),
            rsi_lower=range(20, 40, 5),
            rsi_upper=range(60, 85, 5),
        ),
    },
    {
        "name": "ストキャスティクス",
        "class": Stochastic_Strategy,
        "params": dict(
            k_period=range(8, 22, 2),
            d_period=range(2, 6, 1),
            lower=range(15, 35, 5),
            upper=range(65, 90, 5),
        ),
    },
    {
        "name": "ボリンジャーバンド逆張り",
        "class": BollingerBand_Strategy,
        "params": dict(
            bb_period=range(14, 30, 2),
            bb_std=[1.5, 2.0, 2.5, 3.0],
        ),
    },
    {
        "name": "BB+RSI複合",
        "class": BB_RSI_Strategy,
        "params": dict(
            bb_period=range(14, 26, 2),
            bb_std=[1.5, 2.0, 2.5],
            rsi_period=range(10, 20, 2),
            rsi_lower=range(25, 45, 5),
            rsi_upper=range(55, 75, 5),
        ),
    },
    {
        "name": "MACDクロス",
        "class": MACD_Strategy,
        "params": dict(
            fast=range(8, 16, 2),
            slow=range(20, 34, 2),
            signal=range(5, 12, 2),
        ),
    },
]

PAIRS = ["USDJPY", "EURUSD", "GBPJPY"]


def get_commission(pair, df):
    """スプレッドコストを%に変換"""
    avg_price = df["Close"].mean()
    if "JPY" in pair:
        return SPREAD_PIPS[pair] * 0.01 / avg_price * 100 / 100
    else:
        return SPREAD_PIPS[pair] * 0.0001 / avg_price * 100 / 100


def optimize_strategy(pair, target, df, label=""):
    """1つの戦略を最適化"""
    commission = get_commission(pair, df)

    bt = Backtest(
        df, target["class"],
        cash=1_000_000,
        commission=commission,
        exclusive_orders=True,
    )

    try:
        stats = bt.optimize(
            **target["params"],
            maximize="Equity Final [$]",
            max_tries=500,
            return_heatmap=False,
        )

        # 最適化されたパラメータを取得
        strategy = stats._strategy
        opt_params = {}
        for param_name in target["params"].keys():
            opt_params[param_name] = getattr(strategy, param_name)

        return {
            "通貨ペア": pair,
            "戦略": target["name"],
            "条件": label,
            "勝率(%)": round(stats["Win Rate [%]"], 1) if not pd.isna(stats["Win Rate [%]"]) else 0,
            "リターン(%)": round(stats["Return [%]"], 2),
            "最大DD(%)": round(stats["Max. Drawdown [%]"], 2),
            "トレード数": stats["# Trades"],
            "PF": round(stats["Profit Factor"], 2) if not pd.isna(stats.get("Profit Factor")) else 0,
            "シャープ比": round(stats["Sharpe Ratio"], 2) if not pd.isna(stats.get("Sharpe Ratio")) else 0,
            "最適パラメータ": str(opt_params),
        }
    except Exception as e:
        return {
            "通貨ペア": pair, "戦略": target["name"], "条件": label,
            "勝率(%)": 0, "リターン(%)": 0, "最大DD(%)": 0,
            "トレード数": 0, "PF": 0, "シャープ比": 0,
            "最適パラメータ": f"ERROR: {e}",
        }


def run_walk_forward(pair, target, df, n_splits=4, label=""):
    """
    ウォークフォワード検証
    データを n_splits に分割し、前半で最適化 → 後半で検証
    """
    split_size = len(df) // n_splits
    oof_results = []

    for i in range(n_splits - 1):
        train = df.iloc[i * split_size: (i + 1) * split_size]
        test = df.iloc[(i + 1) * split_size: (i + 2) * split_size]

        if len(train) < 200 or len(test) < 100:
            continue

        commission = get_commission(pair, train)

        # 訓練データで最適化
        bt_train = Backtest(train, target["class"], cash=1_000_000,
                            commission=commission, exclusive_orders=True)
        try:
            train_stats = bt_train.optimize(
                **target["params"],
                maximize="Equity Final [$]",
                max_tries=300,
                return_heatmap=False,
            )
        except Exception:
            continue

        # 最適化パラメータを取得
        strategy = train_stats._strategy
        opt_params = {}
        for param_name in target["params"].keys():
            opt_params[param_name] = getattr(strategy, param_name)

        # テストデータで検証（最適化パラメータを固定）
        bt_test = Backtest(test, target["class"], cash=1_000_000,
                           commission=commission, exclusive_orders=True)
        try:
            test_stats = bt_test.run(**opt_params)
            if test_stats["# Trades"] > 0:
                oof_results.append({
                    "win_rate": test_stats["Win Rate [%]"],
                    "return": test_stats["Return [%]"],
                    "pf": test_stats["Profit Factor"] if not pd.isna(test_stats.get("Profit Factor")) else 0,
                    "trades": test_stats["# Trades"],
                    "max_dd": test_stats["Max. Drawdown [%]"],
                })
        except Exception:
            continue

    if not oof_results:
        return None

    avg = {
        "通貨ペア": pair,
        "戦略": target["name"],
        "条件": label + " [WF検証]",
        "勝率(%)": round(np.mean([r["win_rate"] for r in oof_results]), 1),
        "リターン(%)": round(np.mean([r["return"] for r in oof_results]), 2),
        "最大DD(%)": round(np.min([r["max_dd"] for r in oof_results]), 2),
        "トレード数": sum(r["trades"] for r in oof_results),
        "PF": round(np.mean([r["pf"] for r in oof_results if r["pf"] > 0]), 2),
        "シャープ比": 0,
        "最適パラメータ": f"WF {n_splits}分割平均",
    }
    return avg


def main():
    all_results = []

    for pair in PAIRS:
        print(f"\n{'='*70}")
        print(f"  {pair} パラメータ最適化")
        print(f"{'='*70}")

        df_raw = load_data(pair, "1h")
        df_filtered, stats = filter_event_periods(df_raw, method="both")

        print(f"  データ: {len(df_raw)}行 (イベント除外後: {len(df_filtered)}行, -{stats['removed_pct']}%)")

        for target in OPTIMIZE_TARGETS:
            print(f"\n  --- {target['name']} ---")

            # 1) フル データで最適化
            print(f"    [全データ] 最適化中... ", end="", flush=True)
            result_full = optimize_strategy(pair, target, df_raw, "全データ")
            print(f"勝率:{result_full['勝率(%)']:.1f}% PF:{result_full['PF']:.2f} "
                  f"リターン:{result_full['リターン(%)']:.2f}% ({result_full['トレード数']}回)")
            all_results.append(result_full)

            # 2) イベント除外で最適化
            print(f"    [イベント除外] 最適化中... ", end="", flush=True)
            result_filtered = optimize_strategy(pair, target, df_filtered, "イベント除外")
            print(f"勝率:{result_filtered['勝率(%)']:.1f}% PF:{result_filtered['PF']:.2f} "
                  f"リターン:{result_filtered['リターン(%)']:.2f}% ({result_filtered['トレード数']}回)")
            all_results.append(result_filtered)

            # 3) ウォークフォワード検証（全データ）
            print(f"    [WF検証 全データ] 検証中... ", end="", flush=True)
            wf_result = run_walk_forward(pair, target, df_raw, n_splits=4, label="全データ")
            if wf_result:
                print(f"勝率:{wf_result['勝率(%)']:.1f}% PF:{wf_result['PF']:.2f} "
                      f"リターン:{wf_result['リターン(%)']:.2f}%")
                all_results.append(wf_result)
            else:
                print("データ不足")

            # 4) ウォークフォワード検証（イベント除外）
            print(f"    [WF検証 イベント除外] 検証中... ", end="", flush=True)
            wf_result_f = run_walk_forward(pair, target, df_filtered, n_splits=4, label="イベント除外")
            if wf_result_f:
                print(f"勝率:{wf_result_f['勝率(%)']:.1f}% PF:{wf_result_f['PF']:.2f} "
                      f"リターン:{wf_result_f['リターン(%)']:.2f}%")
                all_results.append(wf_result_f)
            else:
                print("データ不足")

    # 結果をまとめて表示
    df_results = pd.DataFrame(all_results)

    # WF検証結果だけ抽出してランキング
    wf = df_results[df_results["条件"].str.contains("WF")].copy()
    if len(wf) > 0:
        wf = wf[wf["トレード数"] >= 10]
        wf["スコア"] = (
            wf["勝率(%)"] / 100 * 40 +
            wf["PF"].clip(0, 5) / 5 * 30 +
            wf["リターン(%)"].clip(-50, 100) / 100 * 30
        )
        wf_sorted = wf.sort_values("スコア", ascending=False)

        print(f"\n{'='*90}")
        print("  ウォークフォワード検証 ランキング（過学習リスクを排除した実力値）")
        print(f"{'='*90}")
        print(f"{'順位':>4s} | {'ペア':>8s} | {'戦略':>20s} | {'条件':>18s} | {'勝率':>6s} | "
              f"{'PF':>5s} | {'DD':>7s} | {'取引数':>5s} | {'リターン':>8s}")
        print("-" * 90)
        for i, (_, row) in enumerate(wf_sorted.head(15).iterrows()):
            print(f"  {i+1:2d}  | {row['通貨ペア']:>8s} | {row['戦略']:>20s} | {row['条件']:>18s} | "
                  f"{row['勝率(%)']:5.1f}% | {row['PF']:5.2f} | {row['最大DD(%)']:6.2f}% | "
                  f"{row['トレード数']:4d}回 | {row['リターン(%)']:7.2f}%")

    # 最適化結果（WFでない）のランキング
    opt = df_results[~df_results["条件"].str.contains("WF")].copy()
    opt = opt[opt["トレード数"] >= 20]
    opt["スコア"] = (
        opt["勝率(%)"] / 100 * 40 +
        opt["PF"].clip(0, 5) / 5 * 30 +
        opt["リターン(%)"].clip(-50, 100) / 100 * 30
    )
    opt_sorted = opt.sort_values("スコア", ascending=False)

    print(f"\n{'='*90}")
    print("  最適化結果 ランキング（パラメータ最適化済み、参考値）")
    print(f"{'='*90}")
    print(f"{'順位':>4s} | {'ペア':>8s} | {'戦略':>20s} | {'条件':>12s} | {'勝率':>6s} | "
          f"{'PF':>5s} | {'DD':>7s} | {'取引数':>5s} | {'リターン':>8s} | パラメータ")
    print("-" * 90)
    for i, (_, row) in enumerate(opt_sorted.head(10).iterrows()):
        print(f"  {i+1:2d}  | {row['通貨ペア']:>8s} | {row['戦略']:>20s} | {row['条件']:>12s} | "
              f"{row['勝率(%)']:5.1f}% | {row['PF']:5.2f} | {row['最大DD(%)']:6.2f}% | "
              f"{row['トレード数']:4d}回 | {row['リターン(%)']:7.2f}%")
        print(f"        → {row['最適パラメータ']}")

    # CSV保存
    csv_path = os.path.join(DATA_DIR, "optimization_results.csv")
    df_results.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n結果を保存: {csv_path}")


if __name__ == "__main__":
    main()
