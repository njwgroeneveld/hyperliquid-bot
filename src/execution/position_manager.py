import logging
from datetime import datetime, timezone

from src.logging.database import Database
from src.execution.trade_executor import TradeExecutor
from src.metrics import prometheus_metrics as metrics

log = logging.getLogger(__name__)


class PositionManager:
    def __init__(self, db: Database, executor: TradeExecutor, settings: dict):
        self.db = db
        self.executor = executor
        self.max_duration_hours = settings["risk"]["max_trade_duration_hours"]

    def run_once(self, all_mids: dict[str, float]) -> None:
        for trade in self.db.get_open_trades():
            coin = trade["coin"]
            current_price = all_mids.get(coin)
            if current_price is None:
                log.warning(f"[{coin}] Geen prijs beschikbaar — sla over")
                continue
            self._check_trade(trade, float(current_price))

    def _check_trade(self, trade: dict, current_price: float) -> None:
        richting = trade["richting"]
        stop_loss = float(trade["stop_loss"])
        target = float(trade["target"])
        timestamp_open = trade["timestamp_open"]

        open_dt = datetime.fromisoformat(timestamp_open.replace("Z", "+00:00"))
        hours_open = (datetime.now(timezone.utc) - open_dt).total_seconds() / 3600
        if hours_open >= self.max_duration_hours:
            self._close_trade(trade, current_price, "TIMEOUT")
            return

        if richting == "LONG":
            if current_price <= stop_loss:
                self._close_trade(trade, current_price, "STOP_LOSS")
            elif current_price >= target:
                self._close_trade(trade, current_price, "TARGET")
        else:
            if current_price >= stop_loss:
                self._close_trade(trade, current_price, "STOP_LOSS")
            elif current_price <= target:
                self._close_trade(trade, current_price, "TARGET")

    def _close_trade(self, trade: dict, close_prijs: float, reden: str) -> None:
        coin = trade["coin"]
        richting = trade["richting"]
        entry = float(trade["entry"])
        positie_usd = float(trade.get("positie_usd") or 0)
        risico_usd = float(trade.get("risico_usd") or 0)

        result = self.executor.close_position_market(coin, richting, positie_usd, entry)
        if result["status"] != "ok":
            log.error(f"[{coin}] Sluiting mislukt: {result.get('reden')}")
            return

        if richting == "LONG":
            resultaat_usd = round((close_prijs - entry) / entry * positie_usd, 2)
        else:
            resultaat_usd = round((entry - close_prijs) / entry * positie_usd, 2)

        resultaat_r = round(resultaat_usd / risico_usd, 2) if risico_usd > 0 else 0.0
        timestamp_close = datetime.now(timezone.utc).isoformat()

        self.db.close_trade(
            trade["trade_id"],
            close_prijs,
            resultaat_usd,
            resultaat_r,
            reden,
            timestamp_close,
        )

        direction = richting.lower()
        outcome = "win" if resultaat_usd >= 0 else "loss"
        metrics.trades_total.labels(coin=coin, direction=direction, outcome=outcome).inc()
        metrics.pnl_usd.labels(coin=coin).set(resultaat_usd)
        metrics.open_positions.labels(coin=coin, direction=direction).set(0)

        log.info(
            f"[{coin}] Trade gesloten: {reden} | "
            f"Resultaat: ${resultaat_usd:+.2f} ({resultaat_r:+.2f}R)"
        )
