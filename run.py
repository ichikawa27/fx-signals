"""
FXシグナルBot メインランナー
定期的にデータを取得し、シグナルを検出してDiscordに通知する
"""
import sys
import time
import signal as sig
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

from config import PAIRS, STRATEGIES, EVENT_FILTER, DATA_FETCH, DISCORD_WEBHOOK_URL
from signal_engine import SignalEngine
from notifier import send_discord_notification, send_status_message
from signal_logger import log_signal


class FXSignalBot:
    def __init__(self):
        self.engine = SignalEngine(STRATEGIES, EVENT_FILTER)
        self.running = True
        self.check_count = 0
        self.signal_count = 0

        # Ctrl+Cでの終了処理
        sig.signal(sig.SIGINT, self._handle_shutdown)
        sig.signal(sig.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        print("\n\nシャットダウン中...")
        self.running = False

    def fetch_latest_data(self):
        """全ペアの最新1時間足データを取得"""
        pair_data = {}
        interval = DATA_FETCH["interval"]

        for pair_name, pair_config in PAIRS.items():
            try:
                df = yf.download(
                    pair_config["ticker"],
                    period="60d",  # テクニカル計算に十分な量
                    interval=interval,
                    progress=False,
                )
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()

                if len(df) > 0:
                    pair_data[pair_name] = df
            except Exception as e:
                print(f"  [データ取得エラー] {pair_name}: {e}")

        return pair_data

    def run_once(self):
        """1回分のチェックサイクル"""
        self.check_count += 1
        now = datetime.now()
        print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] チェック #{self.check_count}")

        # FX市場の営業時間チェック（土日は休場）
        weekday = now.weekday()
        if weekday == 5:  # 土曜
            print("  市場休場（土曜日）- スキップ")
            return
        if weekday == 6:  # 日曜
            hour = now.hour
            if hour < 22:  # 日曜22時(JST)頃にウェリントン市場が開く
                print("  市場休場（日曜日）- スキップ")
                return

        # データ取得
        print("  データ取得中...", end=" ", flush=True)
        pair_data = self.fetch_latest_data()
        print(f"{len(pair_data)}ペア取得完了")

        for pair_name, df in pair_data.items():
            latest = df.index[-1]
            price = df["Close"].iloc[-1]
            print(f"    {pair_name}: {price:.3f} (最新: {latest})")

        # イベントチェック
        is_event = False
        event_reason = ""
        for pair_name, df in pair_data.items():
            is_event, event_reason = self.engine.is_event_period(df)
            if is_event:
                break

        if is_event:
            print(f"  [イベント期間] {event_reason} - シグナルをミュート")
            return

        # シグナルスキャン
        signals = self.engine.scan_all(pair_data)

        if signals:
            for s in signals:
                self.signal_count += 1
                print(f"\n  >>> シグナル検出! <<<")
                print(f"      {s['pair']} {s['action']} @ {s['price']:.3f}")
                print(f"      戦略: {s['strategy']}")
                print(f"      根拠: {s['reason']}")
                print(f"      BT勝率: {s['backtest_winrate']:.1f}%  PF: {s['backtest_pf']:.2f}")

                try:
                    log_signal(s)
                except Exception as e:
                    print(f"      [記録エラー] {e}")

                send_discord_notification(DISCORD_WEBHOOK_URL, s)
        else:
            print("  シグナルなし")

    def run(self):
        """メインループ"""
        interval = DATA_FETCH["check_interval_sec"]

        print("=" * 60)
        print("  FX Signal Bot 起動")
        print("=" * 60)
        print(f"  監視ペア: {', '.join(PAIRS.keys())}")
        print(f"  戦略数:   {len(STRATEGIES)}")
        print(f"  チェック間隔: {interval}秒 ({interval // 60}分)")
        print(f"  イベントフィルター: {'ON' if EVENT_FILTER['enabled'] else 'OFF'}")
        print(f"  Discord通知: {'設定済み' if DISCORD_WEBHOOK_URL else '未設定（ログのみ）'}")
        print(f"  停止: Ctrl+C")
        print("=" * 60)

        send_status_message(
            DISCORD_WEBHOOK_URL,
            f"FX Signal Bot 起動\n"
            f"監視: {', '.join(PAIRS.keys())}\n"
            f"戦略: {len(STRATEGIES)}個\n"
            f"チェック間隔: {interval // 60}分"
        )

        while self.running:
            try:
                self.run_once()
            except Exception as e:
                print(f"  [エラー] {e}")

            if not self.running:
                break

            # 次のチェックまで待機（1秒刻みでCtrl+Cに応答）
            print(f"\n  次のチェックまで {interval}秒...")
            for _ in range(interval):
                if not self.running:
                    break
                time.sleep(1)

        # 終了処理
        print(f"\n{'='*60}")
        print(f"  Bot停止")
        print(f"  チェック回数: {self.check_count}")
        print(f"  検出シグナル: {self.signal_count}")
        print(f"{'='*60}")

        send_status_message(DISCORD_WEBHOOK_URL, "FX Signal Bot 停止")


def test_mode():
    """テストモード: 現在のデータで1回だけチェック"""
    print("=" * 60)
    print("  FX Signal Bot - テストモード")
    print("=" * 60)

    bot = FXSignalBot()
    bot.run_once()

    print(f"\n{'='*60}")
    print("  テスト完了")
    print("  本番起動: python run.py")
    print(f"{'='*60}")


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_mode()
    elif "--once" in sys.argv:
        # 1回だけスキャンして終了（GitHub Actions / cron 用）
        print("=" * 60)
        print("  FX Signal Bot - シングルラン")
        print("=" * 60)
        bot = FXSignalBot()
        bot.run_once()
        print("\n  シングルラン完了")
    else:
        bot = FXSignalBot()
        bot.run()
