import logging
import time
from datetime import datetime, timezone

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from src.metrics import prometheus_metrics as metrics

log = logging.getLogger(__name__)

TESTNET_URL = "https://api.hyperliquid-testnet.xyz"
MAINNET_URL = "https://api.hyperliquid.xyz"


class TradeExecutor:
    def __init__(self, private_key: str, testnet: bool = True):
        base_url = TESTNET_URL if testnet else MAINNET_URL
        self.account = Account.from_key(private_key)
        self.info = Info(base_url, skip_ws=True)
        self.exchange = Exchange(self.account, base_url)
        self._sz_decimals_cache: dict[str, int] = {}

    def get_sz_decimals(self, coin: str) -> int:
        if coin not in self._sz_decimals_cache:
            meta = self.info.meta()
            for asset in meta.get("universe", []):
                if asset["name"] == coin:
                    self._sz_decimals_cache[coin] = asset["szDecimals"]
                    break
            else:
                self._sz_decimals_cache[coin] = 3
        return self._sz_decimals_cache[coin]

    def place_limit_order(self, coin: str, richting: str, entry: float, sz_usd: float) -> dict:
        start = time.time()
        try:
            sz_decimals = self.get_sz_decimals(coin)
            sz = round(sz_usd / entry, sz_decimals)
            if sz <= 0:
                return {"status": "error", "reden": "Positiegrootte te klein"}

            is_buy = richting == "LONG"
            result = self.exchange.order(
                coin, is_buy, sz, entry,
                {"limit": {"tif": "Gtc"}},
            )
            elapsed = time.time() - start
            metrics.order_placement_latency_seconds.labels(coin=coin).observe(elapsed)

            if result.get("status") == "ok":
                statuses = result["response"]["data"]["statuses"]
                oid = (
                    statuses[0].get("resting", {}).get("oid")
                    or statuses[0].get("filled", {}).get("oid")
                )
                log.info(f"[{coin}] Order geplaatst: OID={oid}, {richting} {sz} @ {entry}")
                return {
                    "status": "ok",
                    "hl_order_id": str(oid),
                    "sz_coin": sz,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            else:
                err = result.get("response", "onbekend")
                log.error(f"[{coin}] Order mislukt: {err}")
                metrics.errors_total.labels(type="order_failed").inc()
                return {"status": "error", "reden": str(err)}

        except Exception as e:
            log.error(f"[{coin}] Order exception: {e}", exc_info=True)
            metrics.errors_total.labels(type="order_failed").inc()
            return {"status": "error", "reden": str(e)}

    def close_position_market(self, coin: str, richting: str, sz_usd: float, entry: float) -> dict:
        try:
            sz_decimals = self.get_sz_decimals(coin)
            sz_coin = round(sz_usd / entry, sz_decimals)
            result = self.exchange.market_close(coin, sz=sz_coin)
            if result.get("status") == "ok":
                log.info(f"[{coin}] Positie gesloten via market_close")
                return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
            else:
                err = result.get("response", "onbekend")
                log.error(f"[{coin}] Sluiting mislukt: {err}")
                return {"status": "error", "reden": str(err)}
        except Exception as e:
            log.error(f"[{coin}] Sluiting exception: {e}", exc_info=True)
            return {"status": "error", "reden": str(e)}
