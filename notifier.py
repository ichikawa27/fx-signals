"""
Discord通知モジュール
シグナルをDiscord Webhookで送信 → iPhoneのDiscordアプリでプッシュ通知を受信
"""
import json
import urllib.request
from datetime import datetime


def format_signal_message(signal):
    """シグナルをDiscord用メッセージにフォーマット"""

    # BUY/SELLで色とアイコンを分ける
    if signal["action"] == "BUY":
        color = 0x00FF00  # 緑
        icon = ":chart_with_upwards_trend:"
        action_jp = "買いシグナル"
    else:
        color = 0xFF0000  # 赤
        icon = ":chart_with_downwards_trend:"
        action_jp = "売りシグナル"

    # シグナル強度をバーで表示
    strength = signal.get("strength", 0.5)
    bars = int(strength * 5)
    strength_bar = "█" * bars + "░" * (5 - bars)

    embed = {
        "title": f"{icon} {signal['pair']} {action_jp}",
        "color": color,
        "fields": [
            {
                "name": "価格",
                "value": f"`{signal['price']:.5f}`" if signal['price'] < 10 else f"`{signal['price']:.3f}`",
                "inline": True,
            },
            {
                "name": "戦略",
                "value": signal["strategy"],
                "inline": True,
            },
            {
                "name": "シグナル強度",
                "value": f"`{strength_bar}` ({strength:.0%})",
                "inline": True,
            },
            {
                "name": "根拠",
                "value": signal["reason"],
                "inline": False,
            },
            {
                "name": "BT勝率 / PF",
                "value": f"{signal['backtest_winrate']:.1f}% / {signal['backtest_pf']:.2f}",
                "inline": True,
            },
            {
                "name": "データ時刻",
                "value": str(signal.get("time", "N/A")),
                "inline": True,
            },
        ],
        "footer": {
            "text": "FX Signal Bot | テクニカル分析に基づくシグナルです。投資判断は自己責任で行ってください。",
        },
        "timestamp": datetime.utcnow().isoformat(),
    }

    return embed


def send_discord_notification(webhook_url, signal):
    """Discord Webhookでシグナルを送信"""
    if not webhook_url:
        print(f"  [通知スキップ] Webhook URL未設定 - {signal['pair']} {signal['action']}")
        return False

    embed = format_signal_message(signal)
    payload = {
        "username": "FX Signal Bot",
        "embeds": [embed],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "FXSignalBot/1.0 (Python)",
        },
    )

    try:
        with urllib.request.urlopen(req) as response:
            if response.status in (200, 204):
                print(f"  [通知送信OK] {signal['pair']} {signal['action']}")
                return True
            else:
                print(f"  [通知エラー] HTTP {response.status}")
                return False
    except Exception as e:
        print(f"  [通知エラー] {e}")
        return False


def send_status_message(webhook_url, message):
    """ステータスメッセージを送信（起動/停止通知等）"""
    if not webhook_url:
        print(f"  [通知スキップ] {message}")
        return

    payload = {
        "username": "FX Signal Bot",
        "embeds": [{
            "title": ":gear: System",
            "description": message,
            "color": 0x808080,
            "timestamp": datetime.utcnow().isoformat(),
        }],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "FXSignalBot/1.0 (Python)",
        },
    )

    try:
        with urllib.request.urlopen(req) as response:
            pass
    except Exception:
        pass


def send_event_mute_message(webhook_url, reason):
    """イベントミュート通知"""
    if not webhook_url:
        return

    payload = {
        "username": "FX Signal Bot",
        "embeds": [{
            "title": ":pause_button: シグナル一時停止",
            "description": f"経済指標イベントのためシグナルをミュートします\n理由: {reason}",
            "color": 0xFFAA00,
            "timestamp": datetime.utcnow().isoformat(),
        }],
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "FXSignalBot/1.0 (Python)",
        },
    )

    try:
        with urllib.request.urlopen(req) as response:
            pass
    except Exception:
        pass
