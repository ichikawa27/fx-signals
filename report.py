"""
戦略別パフォーマンスレポート
logs/results.csv を読み込み、戦略・ホライズン別に勝率/PF/平均リターンを集計する。
"""
import os
import pandas as pd

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
SIGNALS_CSV = os.path.join(LOGS_DIR, "signals.csv")
RESULTS_CSV = os.path.join(LOGS_DIR, "results.csv")


def aggregate(df):
    """戦略別に集計"""
    rows = []
    for strat, grp in df.groupby("strategy"):
        gains = grp.loc[grp["return_pips_net"] > 0, "return_pips_net"].sum()
        losses = -grp.loc[grp["return_pips_net"] < 0, "return_pips_net"].sum()
        pf = round(gains / losses, 2) if losses > 0 else float("inf")
        rows.append({
            "戦略": strat,
            "件数": len(grp),
            "勝ち": int(grp["win"].sum()),
            "勝率%": round(grp["win"].mean() * 100, 1),
            "平均pips": round(grp["return_pips_net"].mean(), 2),
            "累計pips": round(grp["return_pips_net"].sum(), 2),
            "PF": pf,
        })
    return pd.DataFrame(rows).sort_values("勝率%", ascending=False)


def print_report():
    if not os.path.exists(RESULTS_CSV):
        print("評価結果ファイルがありません。evaluate_signals.py を先に実行してください。")
        return

    results = pd.read_csv(RESULTS_CSV)
    if len(results) == 0:
        print("評価結果が空です。")
        return

    total_signals = len(pd.read_csv(SIGNALS_CSV)) if os.path.exists(SIGNALS_CSV) else 0

    print(f"\n{'=' * 78}")
    print(f"  FX Signal Bot - パフォーマンスレポート")
    print(f"  総シグナル数: {total_signals}  /  評価レコード: {len(results)}")
    print(f"{'=' * 78}")

    for h in sorted(results["horizon_hours"].unique()):
        sub = results[results["horizon_hours"] == h]
        agg = aggregate(sub)

        overall_wr = sub["win"].mean() * 100
        overall_pips = sub["return_pips_net"].sum()

        print(f"\n■ ホライズン {h}h  "
              f"(件数={len(sub)}, 勝率={overall_wr:.1f}%, 累計pips={overall_pips:+.1f})")
        print("-" * 78)
        print(agg.to_string(index=False))

    # 通貨ペア別の24hサマリー
    if 24 in results["horizon_hours"].unique():
        sub = results[results["horizon_hours"] == 24]
        print(f"\n■ 通貨ペア別（24hホライズン）")
        print("-" * 78)
        pair_agg = sub.groupby("pair").agg(
            件数=("win", "count"),
            勝率_pct=("win", lambda x: round(x.mean() * 100, 1)),
            累計pips=("return_pips_net", lambda x: round(x.sum(), 2)),
        )
        print(pair_agg.to_string())


if __name__ == "__main__":
    print_report()
