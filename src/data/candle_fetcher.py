import time
from datetime import datetime, timezone

import pandas as pd

from src.data.hyperliquid_client import HyperliquidClient


INTERVAL_MS = {
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


class CandleFetcher:
    def __init__(self, client: HyperliquidClient):
        self.client = client

    def fetch(self, coin: str, interval: str, lookback: int = 200) -> pd.DataFrame:
        """
        Fetch the last `lookback` closed candles for coin/interval.
        Returns a DataFrame with columns:
          timestamp, open, high, low, close, volume
        sorted ascending by time.
        """
        interval_ms = INTERVAL_MS.get(interval)
        if interval_ms is None:
            raise ValueError(f"Unsupported interval: {interval}. Use {list(INTERVAL_MS)}")

        end_ms = int(time.time() * 1000)
        start_ms = end_ms - interval_ms * (lookback + 1)

        raw = self.client.get_candles(coin, interval, start_ms, end_ms)
        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        df = df.rename(columns={
            "t": "timestamp_ms",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
        })

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Drop the current (incomplete) candle — keep only closed candles
        df = df.iloc[:-1].reset_index(drop=True)

        return df.tail(lookback).reset_index(drop=True)
