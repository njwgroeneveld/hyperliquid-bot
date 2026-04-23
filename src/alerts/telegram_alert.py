import logging
import os

import requests

log = logging.getLogger(__name__)

_BOT_TOKEN: str | None = None
_CHAT_ID: str | None = None


def _init() -> None:
    global _BOT_TOKEN, _CHAT_ID
    _BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    _CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


_init()


def _send(text: str) -> bool:
    if not _BOT_TOKEN or not _CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": _CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        log.warning(f"Telegram send mislukt: {e}")
        return False


def alert_trade_opened(trade: dict) -> bool:
    msg = (
        f"<b>TRADE GEOPEND</b> — {trade.get('coin', '?')}\n"
        f"Richting: {trade.get('richting', '?')}\n"
        f"Entry: ${trade.get('entry', 0):,.2f}\n"
        f"Stop-loss: ${trade.get('stop_loss', 0):,.2f}\n"
        f"Target: ${trade.get('target', 0):,.2f}\n"
        f"R/R: {trade.get('risk_reward', '?')} | Score: {trade.get('score', '?')} | "
        f"Sessie: {trade.get('sessie', '?')}"
    )
    return _send(msg)


def alert_trade_closed(
    trade_id: str, coin: str, reden: str, resultaat_usd: float, resultaat_r: float
) -> bool:
    emoji = "✅" if resultaat_usd >= 0 else "❌"
    msg = (
        f"{emoji} <b>TRADE GESLOTEN</b> — {coin}\n"
        f"Reden: {reden}\n"
        f"Resultaat: ${resultaat_usd:+.2f} ({resultaat_r:+.2f}R)\n"
        f"Trade ID: {trade_id}"
    )
    return _send(msg)


def alert_bot_error(error_msg: str, consecutive_count: int) -> bool:
    msg = (
        f"⚠️ <b>BOT FOUT</b>\n"
        f"Opeenvolgende fouten: {consecutive_count}\n"
        f"Fout: {error_msg}"
    )
    return _send(msg)


def alert_daily_loss(loss_pct: float) -> bool:
    msg = (
        f"🚨 <b>DAGELIJKS VERLIESALERT</b>\n"
        f"Verlies: {loss_pct:.1f}%"
    )
    return _send(msg)
