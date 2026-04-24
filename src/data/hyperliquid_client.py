import requests
from typing import Optional


HYPERLIQUID_API_URL = "https://api.hyperliquid.xyz/info"


class HyperliquidClient:
    """Low-level client for the Hyperliquid REST API."""

    def __init__(self, timeout: int = 10):
        self.url = HYPERLIQUID_API_URL
        self.session = requests.Session()
        self.timeout = timeout

    def _post(self, payload: dict) -> dict | list:
        response = self.session.post(self.url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_candles(self, coin: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
        """
        Fetch OHLCV candles.
        interval: '1h', '4h', '1d', etc.
        start_ms / end_ms: epoch milliseconds
        """
        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms,
            },
        }
        return self._post(payload)

    def get_l2_book(self, coin: str) -> dict:
        """Fetch L2 orderbook (bids + asks up to 20 levels)."""
        payload = {"type": "l2Book", "coin": coin}
        return self._post(payload)

    def get_meta_and_asset_ctxs(self) -> list:
        """Fetch all assets metadata + OI + funding rates in one call."""
        payload = {"type": "metaAndAssetCtxs"}
        return self._post(payload)

    def get_all_mids(self) -> dict:
        """Fetch mid prices for all assets."""
        payload = {"type": "allMids"}
        return self._post(payload)
