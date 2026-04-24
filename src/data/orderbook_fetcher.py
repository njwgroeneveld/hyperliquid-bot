from src.data.hyperliquid_client import HyperliquidClient


class OrderbookFetcher:
    def __init__(self, client: HyperliquidClient):
        self.client = client

    def fetch(self, coin: str) -> dict:
        """
        Fetch L2 orderbook and return parsed bids/asks.

        Returns:
            {
                "coin": "BTC",
                "bids": [{"price": float, "size": float}, ...],  # descending
                "asks": [{"price": float, "size": float}, ...],  # ascending
            }
        """
        raw = self.client.get_l2_book(coin)
        levels = raw.get("levels", [[], []])
        bids_raw, asks_raw = levels[0], levels[1]

        def parse_levels(raw_levels: list) -> list[dict]:
            return [
                {"price": float(lvl["px"]), "size": float(lvl["sz"])}
                for lvl in raw_levels
            ]

        return {
            "coin": coin,
            "bids": parse_levels(bids_raw),
            "asks": parse_levels(asks_raw),
        }

    def fetch_meta(self, coin: str) -> dict:
        """
        Fetch OI and funding rate for a single coin from metaAndAssetCtxs.

        Returns:
            {
                "open_interest": float,
                "funding_rate": float,
                "mark_price": float,
                "oracle_price": float,
            }
        """
        meta_list = self.client.get_meta_and_asset_ctxs()
        if not meta_list or len(meta_list) < 2:
            return {}

        universe = meta_list[0].get("universe", [])
        asset_ctxs = meta_list[1]

        coin_index = None
        for i, asset in enumerate(universe):
            if asset.get("name") == coin:
                coin_index = i
                break

        if coin_index is None or coin_index >= len(asset_ctxs):
            return {}

        ctx = asset_ctxs[coin_index]
        return {
            "open_interest": float(ctx.get("openInterest", 0)),
            "funding_rate": float(ctx.get("funding", 0)),
            "mark_price": float(ctx.get("markPx", 0)),
            "oracle_price": float(ctx.get("oraclePx", 0)),
        }
