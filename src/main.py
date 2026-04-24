"""
Hyperliquid Trading Bot — startpunt.

Fase C/D: Testnet execution + positiebeheer + Prometheus metrics + Telegram alerts.

Gebruik: python -m src.main
         HYPERLIQUID_PRIVATE_KEY=0x... HYPERLIQUID_TESTNET=true python -m src.main
"""

import logging
import os
import sys
import time
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()
from pathlib import Path

import yaml
from apscheduler.schedulers.background import BackgroundScheduler

from src.data.hyperliquid_client import HyperliquidClient
from src.data.candle_fetcher import CandleFetcher
from src.data.orderbook_fetcher import OrderbookFetcher
from src.detection.detector import Detector
from src.decision import decision_tree
from src.decision.entry_calculator import calculate_entry, find_target
from src.decision.position_sizer import calculate, validate_position
from src.ai.argumentation import generate_trade_argumentation, generate_no_trade_summary
from src.logging.detection_logger import DetectionLogger
from src.logging.decision_logger import DecisionLogger
from src.logging.trade_logger import TradeLogger
from src.logging.database import Database
from src.execution.trade_executor import TradeExecutor
from src.execution.position_manager import PositionManager
from src.alerts import telegram_alert as telegram
from src.metrics import prometheus_metrics as metrics


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

PAPER_PORTFOLIO_USD = 1_000
CORRELATED_GROUP = {"BTC", "ETH", "SOL"}


def load_config() -> tuple[dict, list[str]]:
    with open("config/settings.yaml", encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    with open("config/coins.yaml", encoding="utf-8") as f:
        coins_cfg = yaml.safe_load(f)
    active_coins = [c["symbol"] for c in coins_cfg["active_coins"] if c.get("active")]
    settings["logging"]["log_dir"] = os.getenv("LOG_DIR", settings["logging"]["log_dir"])
    settings["logging"]["database_path"] = os.getenv(
        "DATABASE_PATH", settings["logging"]["database_path"]
    )
    return settings, active_coins


def make_executor() -> "TradeExecutor | None":
    private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY")
    if not private_key:
        log.warning("HYPERLIQUID_PRIVATE_KEY niet ingesteld — dry-run modus (geen echte orders)")
        return None
    testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"
    return TradeExecutor(private_key, testnet=testnet)


def make_trade_id(coin: str, richting: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return f"{coin}-{richting[:1]}-{ts}"


class AnalysisLoop:
    def __init__(
        self,
        settings: dict,
        coins: list[str],
        executor: "TradeExecutor | None" = None,
    ):
        self.settings = settings
        self.coins = coins
        self.executor = executor
        self.lookback = settings["timeframes"]["candle_lookback"]
        self.risk_pct = settings["risk"]["risk_per_trade"]
        self.leverage = settings["risk"]["max_leverage"]
        self.min_rr = settings["risk"]["min_risk_reward"]
        self.stop_buffer = settings["risk"]["stop_buffer_pct"]

        self.client = HyperliquidClient()
        self.candle_fetcher = CandleFetcher(self.client)
        self.orderbook_fetcher = OrderbookFetcher(self.client)
        self.detector = Detector(settings)

        log_dir = settings["logging"]["log_dir"]
        self.detection_logger = DetectionLogger(f"{log_dir}/detection")
        self.decision_logger = DecisionLogger(f"{log_dir}/decisions")
        self.trade_logger = TradeLogger(f"{log_dir}/trades")
        self.db = Database(settings["logging"]["database_path"])

        self._prev_meta: dict[str, dict] = {}
        self._open_paper_trades: dict[str, str] = {}
        self._consecutive_errors: int = 0

    def run_for_coin(self, coin: str):
        log.info(f"[{coin}] Analyse gestart")
        metrics.analysis_runs_total.labels(coin=coin).inc()
        start = time.time()

        try:
            df_4h = self.candle_fetcher.fetch(coin, "4h", self.lookback)
            df_1h = self.candle_fetcher.fetch(coin, "1h", self.lookback)

            if df_4h.empty or df_1h.empty:
                log.warning(f"[{coin}] Geen candle data — sla over")
                return

            orderbook = self.orderbook_fetcher.fetch(coin)
            meta = self.orderbook_fetcher.fetch_meta(coin)
            meta_prev = self._prev_meta.get(coin)
            self._prev_meta[coin] = meta

            detection = self.detector.run(coin, df_4h, df_1h, orderbook, meta, meta_prev)
            self.detection_logger.save(detection)
            self.db.insert_detection(detection)

            trend_map = {"UPTREND": 1, "DOWNTREND": -1, "CONSOLIDATIE": 0}
            trend_val = trend_map.get(detection.get("structuur_4h", {}).get("trend", ""), 0)
            metrics.trend_status.labels(coin=coin).set(trend_val)
            metrics.zones_found.labels(coin=coin, type="demand").set(
                len(detection.get("zones_4h", {}).get("demand_zones", []))
            )
            metrics.zones_found.labels(coin=coin, type="supply").set(
                len(detection.get("zones_4h", {}).get("supply_zones", []))
            )
            metrics.funding_rate.labels(coin=coin).set(
                detection.get("order_flow", {}).get("funding_rate", {}).get("huidig", 0)
            )

            beslissing = decision_tree.evaluate(detection, self.settings)
            self.decision_logger.save(beslissing)
            self.db.insert_decision(beslissing)

            score = beslissing["eindscore"]
            is_entry = beslissing["is_entry"]
            richting = beslissing.get("richting")
            prijs = detection["huidige_prijs"]

            score_float = float(str(score).split("/")[0]) if "/" in str(score) else float(score)
            metrics.decision_score.labels(coin=coin).set(score_float)

            log.info(
                f"[{coin}] Score {score} | Beslissing: {beslissing['beslissing']} | "
                f"Richting: {richting} | Prijs: ${prijs:,.2f}"
            )

            if is_entry and richting and beslissing.get("geselecteerde_zone"):
                if self._correlatie_geblokkeerd(coin, richting):
                    log.info(
                        f"[{coin}] Entry geblokkeerd — al een {richting} positie open "
                        f"in gecorreleerde crypto groep"
                    )
                else:
                    self._handle_entry(coin, detection, beslissing, prijs, df_1h=df_1h)
            else:
                samenvatting = generate_no_trade_summary(beslissing)
                log.info(f"[{coin}] {samenvatting}")

            self._consecutive_errors = 0
            metrics.consecutive_errors.set(0)

        except Exception as e:
            self._consecutive_errors += 1
            metrics.errors_total.labels(type="api_error").inc()
            metrics.consecutive_errors.set(self._consecutive_errors)
            log.error(f"[{coin}] Fout tijdens analyse: {e}", exc_info=True)
            if self._consecutive_errors >= 3:
                telegram.alert_bot_error(str(e), self._consecutive_errors)
        finally:
            elapsed = time.time() - start
            metrics.loop_duration_seconds.labels(loop="analysis").observe(elapsed)

    def _correlatie_geblokkeerd(self, coin: str, richting: str) -> bool:
        max_correlated = self.settings["risk"].get("max_correlated_positions", 99)
        if max_correlated >= len(CORRELATED_GROUP):
            return False
        if coin not in CORRELATED_GROUP:
            return False
        actief = sum(
            1 for c, r in self._open_paper_trades.items()
            if c in CORRELATED_GROUP and r == richting
        )
        return actief >= max_correlated

    def _handle_entry(
        self, coin: str, detection: dict, beslissing: dict, prijs: float, df_1h=None
    ):
        richting = beslissing["richting"]
        zone = beslissing["geselecteerde_zone"]
        vertrouwen = beslissing["vertrouwen"]

        atr_period = self.settings["risk"]["atr_period"]
        atr_multiplier = self.settings["risk"]["atr_stop_multiplier"]
        avg_trade_hours = self.settings["risk"]["avg_trade_duration_hours"]

        entry_params = calculate_entry(
            zone, richting, df_1h,
            atr_period=atr_period,
            atr_multiplier=atr_multiplier,
            stop_buffer_pct=self.settings["risk"]["stop_buffer_pct"],
        )
        if not entry_params:
            log.warning(f"[{coin}] Entry berekening mislukt")
            return

        entry = entry_params["entry"]
        stop_loss = entry_params["stop_loss"]

        target_info = find_target(
            detection, richting, entry, stop_loss, self.min_rr,
            leverage=self.leverage,
            avg_trade_hours=avg_trade_hours,
        )
        if not target_info["haalbaar"]:
            log.info(f"[{coin}] Geen haalbaar target: {target_info['reden']}")
            return

        target = target_info["target"]
        rr = target_info["rr"]

        positie = calculate(PAPER_PORTFOLIO_USD, entry, stop_loss, self.risk_pct, self.leverage)

        trade_params = {"entry": entry, "stop_loss": stop_loss, "target": target, "rr": rr}
        argumentatie = generate_trade_argumentation(detection, beslissing, trade_params)

        sessie_info = beslissing.get("sessie") or {}
        trade_id = make_trade_id(coin, richting)

        hl_order_id = None
        status = "OPEN_PAPER"
        if self.executor is not None:
            order_result = self.executor.place_limit_order(
                coin, richting, entry, positie.get("positiegrootte_usd", 0)
            )
            if order_result["status"] == "ok":
                hl_order_id = order_result["hl_order_id"]
                status = "OPEN"
                log.info(f"[{coin}] Testnet order geplaatst: OID={hl_order_id}")
            else:
                log.error(f"[{coin}] Order plaatsing mislukt: {order_result.get('reden')}")
                return

        trade_log = {
            "trade_id": trade_id,
            "timestamp_open": datetime.now(timezone.utc).isoformat(),
            "coin": coin,
            "richting": richting,
            "entry": entry,
            "stop_loss": stop_loss,
            "target": target,
            "leverage": self.leverage,
            "positiegrootte_usd": positie.get("positiegrootte_usd"),
            "margin_usd": positie.get("margin_usd"),
            "risico_usd": positie.get("risico_usd"),
            "verwacht_reward_usd": round(positie.get("risico_usd", 0) * rr, 2) if rr else None,
            "risk_reward": f"{rr}R",
            "vertrouwen": vertrouwen,
            "score": beslissing["eindscore"],
            "sessie": sessie_info.get("sessie", "?"),
            "detectie_snapshot": detection,
            "beslissing_snapshot": beslissing,
            "claude_argumentatie": argumentatie,
            "status": status,
            "hl_order_id": hl_order_id,
            "timestamp_close": None,
            "close_prijs": None,
            "resultaat_usd": None,
            "resultaat_r": None,
            "close_reden": None,
        }

        self.trade_logger.save(trade_log)
        self.db.insert_trade(trade_log)
        self._open_paper_trades[coin] = richting

        metrics.open_positions.labels(coin=coin, direction=richting.lower()).set(1)
        telegram.alert_trade_opened(trade_log)

        label = "TESTNET TRADE" if self.executor else "PAPER TRADE"
        log.info(
            f"\n{'='*60}\n"
            f"[{coin}] {label} GESIGNALEERD\n"
            f"  Richting:  {richting}\n"
            f"  Entry:     ${entry:,.2f}\n"
            f"  Stop-loss: ${stop_loss:,.2f} ({entry_params['stop_afstand_pct']:.2f}%)\n"
            f"  Target:    ${target:,.2f} ({rr}R)\n"
            f"  Positie:   ${positie.get('positiegrootte_usd', '?'):,.0f}"
            f" (margin ${positie.get('margin_usd', '?'):,.0f})\n"
            f"  Risico:    ${positie.get('risico_usd', '?'):,.2f}\n"
            f"  Score:     {beslissing['eindscore']} | Vertrouwen: {vertrouwen}\n"
            f"  Sessie:    {sessie_info.get('sessie', '?')}\n"
            f"\n  Argumentatie:\n  {argumentatie}\n"
            f"{'='*60}"
        )

    def run_all(self):
        now = datetime.now(timezone.utc)
        log.info(f"=== Analyseloop gestart: {now.isoformat()} ===")
        for coin in self.coins:
            self.run_for_coin(coin)
            time.sleep(1)
        metrics.last_successful_run_timestamp.labels(loop="analysis").set(time.time())


def main():
    log_dir = os.getenv("LOG_DIR", "logs")
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    port = int(os.getenv("METRICS_PORT", "8080"))
    metrics.start_metrics_server(port)
    log.info(f"Metrics server gestart op poort {port}")
    log.info("Hyperliquid Trading Bot opgestart (Fase C/D — Testnet Execution)")

    settings, coins = load_config()

    executor = make_executor()
    client = HyperliquidClient()
    analysis_loop = AnalysisLoop(settings, coins, executor=executor)

    stop_event = threading.Event()

    if executor is not None:
        db = analysis_loop.db
        pos_manager = PositionManager(db, executor, settings)

        def _position_loop():
            while not stop_event.is_set():
                start = time.time()
                try:
                    all_mids = client.get_all_mids()
                    pos_manager.run_once(all_mids)
                    metrics.last_successful_run_timestamp.labels(loop="position").set(
                        time.time()
                    )
                except Exception as e:
                    log.error(f"Positiebeheer fout: {e}", exc_info=True)
                    metrics.errors_total.labels(type="api_error").inc()
                finally:
                    elapsed = time.time() - start
                    metrics.loop_duration_seconds.labels(loop="position").observe(elapsed)
                stop_event.wait(30)

        threading.Thread(
            target=_position_loop, daemon=True, name="position-loop"
        ).start()
        log.info("Positiebeheer loop gestart (interval: 30s)")
    else:
        log.info("Dry-run modus — positiebeheer uitgeschakeld")

    analysis_loop.run_all()

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(analysis_loop.run_all, "cron", minute=0, id="analysis_loop")
    scheduler.start()
    log.info(f"Scheduler actief — analyseloop draait elk uur voor: {coins}")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("Bot gestopt door gebruiker")
        scheduler.shutdown()
        stop_event.set()


if __name__ == "__main__":
    main()
