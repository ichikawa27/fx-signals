"""
Discord通知モジュール
シグナルをDiscord Webhookで送信 → iPhoneのDiscordアプリでプッシュ通知を受信
"""
import json
import urllib.request
from datetime import datetime


def _price_format(pip_unit):
    """pip_unit に応じた価格フォーマット文字列を返す"""
    if pip_unit < 0.001:
        return "{:.5f}"  # EURUSD等（0.0001刻み）
    return "{:.3f}"      # JPY系（0.01刻み）


def format_signal_message(signal):
    """シグナルをDiscord用メッセージにフォーマット（指値注文テンプレ入り）"""

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

    # 価格表示桁数を pip_unit から決定
    pip_unit = signal.get("pip_unit", 0.01)
    fmt = _price_format(pip_unit)

    entry_price = signal["price"]
    tp_price = signal.get("tp_price")
    sl_price = signal.get("sl_price")
    tp_pips = signal.get("tp_pips", 0)
    sl_pips = signal.get("sl_pips", 0)
    entry_low = signal.get("entry_low", entry_price)
    entry_high = signal.get("entry_high", entry_price)

    # 指値注文テンプレ（コードブロックで等幅表示）
    if tp_price is not None and sl_price is not None:
        order_template = (
            "```\n"
            f"エントリー指値: {fmt.format(entry_low)} 〜 {fmt.format(entry_high)}\n"
            f"TP（利確）   : {fmt.format(tp_price)}  (+{tp_pips}pips)\n"
            f"SL（損切）   : {fmt.format(sl_price)}  (-{sl_pips}pips)\n"
            "有効期限     : 6時間\n"
            "ロット      : 自己判断（小額推奨）\n"
            "```"
        )
        order_field = {
            "name": ":dart: 指値注文テンプレ（OCO推奨）",
            "value": order_template,
            "inline": False,
        }
    else:
        # 後方互換性：旧シグナル形式の場合
        order_field = None

    fields = []

    # 指値テンプレを最初に表示（一番見たい情報）
    if order_field:
        fields.append(order_field)

    # 基本情報
    fields.extend([
        {
            "name": "シグナル価格",
            "value": f"`{fmt.format(entry_price)}`",
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
    ])

    embed = {
        "title": f"{icon} {signal['pair']} {action_jp}",
        "color": color,
        "fields": fields,
        "footer": {
            "text": "30分以内に指値設定推奨 | TP/SL自動 | 投資判断は自己責任",
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
