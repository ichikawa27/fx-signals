"""
Phase 7 戦略パラメータ最適化スクリプト（狭い範囲、ウォークフォワード重視）

対象: SMA Cross（双方向）, Donchian Breakout
方針:
  - パラメータ範囲を狭く（カーブフィッティング防止）
  - ウォークフォワード分析で頑健性確認（既存 optimize.py と同じ手法）
  - 各戦略 9-25通り以内のグリッドサーチ
  - 実運用での乖離を考慮し、PF×0.5、勝率×0.7 を実用評価値とする

実行: python optimize_phase7.py
"""
import os
import warnings
import pandas as pd
import numpy as np
from backtesting import Backtest
from backtest import (
    SMA_Cross_Both_Strategy,
    Donchian_Strategy,
    load_data,
    SPREAD_PIPS,
)
from event_filter import filter_event_periods
from optimize import optimize_strategy, run_walk_forward, get_commission

warnings.filterwarnings("ignore")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


# ============================================================
# 最適化対象（狭い範囲）
# ============================================================
# パラメータ数を絞ることでカーブフィッティングを最小化
OPTIMIZE_TARGETS = [
    {
        "name": "SMA Cross双方向",
        "class": SMA_Cross_Both_Strategy,
        "params": dict(
            # 業界で実績のある3パターンに絞る
            fast_period=[10, 20, 30],
            slow_period=[30, 50, 100],
        ),
        # constraint で fast < slow に絞る
        "constraint": lambda p: p.fast_period < p.slow_period,
    },
    {
        "name": "Donchian Breakout",
        "class": Donchian_Strategy,
        "params": dict(
            # タートル・トレーダーの古典値 + 短期版
            period=[10, 20, 50],
        ),
        "constraint": None,
    },
]

# Phase 7 戦略の対象ペア（EURUSD は無効化中なのでスキップ）
PAIRS = ["USDJPY", "GBPJPY"]


def optimize_with_constraint(pair, target, df, label=""):
    """制約付き最適化（fast < slow など）"""
    commission = get_commission(pair, df)

    bt = Backtest(
        df, target["class"],
        cash=1_000_000,
        commission=commission,
        exclusive_orders=True,
    )

    optimize_kwargs = dict(
        **target["params"],
        maximize="Equity Final [$]",
        max_tries=200,  # 範囲が狭いので十分
        return_heatmap=False,
    )
    if target.get("constraint"):
        optimize_kwargs["constraint"] = target["constraint"]

    try:
        stats = bt.optimize(**optimize_kwargs)

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


def run_walk_forward_p7(pair, target, df, n_splits=4, label=""):
    """Phase 7 用ウォークフォワード（制約対応）"""
    split_size = len(df) // n_splits
    oof_results = []

    for i in range(n_splits - 1):
        train = df.iloc[i * split_size: (i + 1) * split_size]
        test = df.iloc[(i + 1) * split_size: (i + 2) * split_size]

        if len(train) < 200 or len(test) < 100:
            continue

        commission = get_commission(pair, train)

        bt_train = Backtest(train, target["class"], cash=1_000_000,
                            commission=commission, exclusive_orders=True)
        try:
            optimize_kwargs = dict(
                **target["params"],
                maximize="Equity Final [$]",
                max_tries=100,
                return_heatmap=False,
            )
            if target.get("constraint"):
                optimize_kwargs["constraint"] = target["constraint"]

            train_stats = bt_train.optimize(**optimize_kwargs)
        except Exception:
            continue

        strategy = train_stats._strategy
        opt_params = {}
        for param_name in target["params"].keys():
            opt_params[param_name] = getattr(strategy, param_name)

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

    return {
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


def main():
    all_results = []

    print("=" * 80)
    print("  Phase 7 戦略 パラメータ最適化（狭い範囲、ウォークフォワード重視）")
    print("=" * 80)
    print("  対象戦略: SMA Cross双方向, Donchian Breakout")
    print("  対象ペア: USDJPY, GBPJPY (EURUSD は無効化中)")
    print()

    for pair in PAIRS:
        print(f"\n{'='*70}")
        print(f"  {pair}")
        print(f"{'='*70}")

        df_raw = load_data(pair, "1h")
        df_filtered, stats = filter_event_periods(df_raw, method="both")
        print(f"  データ: {len(df_raw)}行 (イベント除外後: {len(df_filtered)}行, -{stats['removed_pct']}%)")

        for target in OPTIMIZE_TARGETS:
            print(f"\n  --- {target['name']} ---")

            # 1) 全データで最適化
            print(f"    [全データ] 最適化中... ", end="", flush=True)
            r = optimize_with_constraint(pair, target, df_raw, "全データ")
            print(f"勝率:{r['勝率(%)']:.1f}% PF:{r['PF']:.2f} リターン:{r['リターン(%)']:.2f}% ({r['トレード数']}回)")
            all_results.append(r)

            # 2) イベント除外で最適化
            print(f"    [イベント除外] 最適化中... ", end="", flush=True)
            r = optimize_with_constraint(pair, target, df_filtered, "イベント除外")
            print(f"勝率:{r['勝率(%)']:.1f}% PF:{r['PF']:.2f} リターン:{r['リターン(%)']:.2f}% ({r['トレード数']}回)")
            all_results.append(r)

            # 3) WF検証（全データ）
            print(f"    [WF検証 全データ] 検証中... ", end="", flush=True)
            wf = run_walk_forward_p7(pair, target, df_raw, n_splits=4, label="全データ")
            if wf:
                print(f"勝率:{wf['勝率(%)']:.1f}% PF:{wf['PF']:.2f} リターン:{wf['リターン(%)']:.2f}%")
                all_results.append(wf)
            else:
                print("データ不足")

            # 4) WF検証（イベント除外）
            print(f"    [WF検証 イベント除外] 検証中... ", end="", flush=True)
            wf = run_walk_forward_p7(pair, target, df_filtered, n_splits=4, label="イベント除外")
            if wf:
                print(f"勝率:{wf['勝率(%)']:.1f}% PF:{wf['PF']:.2f} リターン:{wf['リターン(%)']:.2f}%")
                all_results.append(wf)
            else:
                print("データ不足")

    # 結果集計
    df_results = pd.DataFrame(all_results)

    # WF検証結果のランキング（過学習リスク排除した実力値）
    wf = df_results[df_results["条件"].str.contains("WF")].copy()
    if len(wf) > 0:
        wf = wf[wf["トレード数"] >= 5]  # Phase 7 はサンプル少なめなので閾値緩和
        if len(wf) > 0:
            wf["スコア"] = (
                wf["勝率(%)"] / 100 * 40 +
                wf["PF"].clip(0, 5) / 5 * 30 +
                wf["リターン(%)"].clip(-50, 100) / 100 * 30
            )
            # 実用評価（保守的）
            wf["実用勝率(%)"] = (wf["勝率(%)"] * 0.7).round(1)
            wf["実用PF"] = (wf["PF"] * 0.5).round(2)

            wf_sorted = wf.sort_values("スコア", ascending=False)

            print(f"\n{'='*100}")
            print("  ウォークフォワード検証 ランキング（実用評価込み）")
            print(f"  ※ 実用勝率/PF はバックテスト値に係数を掛けた保守的予想値")
            print(f"{'='*100}")
            print(f"{'順位':>4s} | {'ペア':>8s} | {'戦略':>20s} | {'条件':>20s} | "
                  f"{'勝率':>6s} | {'実用':>6s} | {'PF':>5s} | {'実用':>5s} | {'取引':>4s} | {'リターン':>8s}")
            print("-" * 100)
            for i, (_, row) in enumerate(wf_sorted.head(10).iterrows()):
                print(f"  {i+1:2d}  | {row['通貨ペア']:>8s} | {row['戦略']:>20s} | {row['条件']:>20s} | "
                      f"{row['勝率(%)']:5.1f}% | {row['実用勝率(%)']:5.1f}% | {row['PF']:5.2f} | "
                      f"{row['実用PF']:5.2f} | {row['トレード数']:4d}回 | {row['リターン(%)']:7.2f}%")

    # 最適化結果のランキング
    opt = df_results[~df_results["条件"].str.contains("WF")].copy()
    opt = opt[opt["トレード数"] >= 10]
    if len(opt) > 0:
        opt["スコア"] = (
            opt["勝率(%)"] / 100 * 40 +
            opt["PF"].clip(0, 5) / 5 * 30 +
            opt["リターン(%)"].clip(-50, 100) / 100 * 30
        )
        opt_sorted = opt.sort_values("スコア", ascending=False)

        print(f"\n{'='*100}")
        print("  最適化結果 ランキング（参考値、カーブフィッティング注意）")
        print(f"{'='*100}")
        for i, (_, row) in enumerate(opt_sorted.head(8).iterrows()):
            print(f"  {i+1:2d}  | {row['通貨ペア']:>8s} | {row['戦略']:>20s} | {row['条件']:>14s} | "
                  f"勝率:{row['勝率(%)']:5.1f}% | PF:{row['PF']:5.2f} | "
                  f"DD:{row['最大DD(%)']:6.2f}% | 取引:{row['トレード数']:4d}回")
            print(f"        → {row['最適パラメータ']}")

    # CSV保存
    csv_path = os.path.join(DATA_DIR, "optimization_phase7_results.csv")
    df_results.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n結果を保存: {csv_path}")

    # 採用判断ガイド
    print(f"\n{'='*80}")
    print("  採用判断ガイド")
    print(f"{'='*80}")
    print("  ✅ 採用OK: WF検証で 実用PF >= 1.5 かつ 実用勝率 >= 40% の戦略")
    print("  ⚠️ 慎重 : WF検証で 実用PF 1.0-1.5 の戦略 → さらにデータ蓄積が必要")
    print("  ❌ 不採用: WF検証で 実用PF < 1.0 の戦略 → カーブフィッティングの可能性高")
    print()
    print("  上記基準で採用OKの戦略のパラメータを config.py に反映してください。")


if __name__ == "__main__":
    main()
