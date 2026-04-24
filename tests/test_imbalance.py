"""
Tests voor imbalance.py
"""

import pandas as pd
import pytest
from src.detection import imbalance


def make_df(highs: list, lows: list, closes: list | None = None) -> pd.DataFrame:
    n = len(highs)
    if closes is None:
        closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    opens = closes[:]
    timestamps = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [100.0] * n,
    })


class TestImbalanceDetection:
    def test_bullish_imbalance_detected(self):
        # Candle 0 high=100, candle 2 low=105 → gap 100-105 (bullish)
        highs = [100, 110, 120, 118, 116]
        lows =  [95,  105, 108, 110, 111]
        df = make_df(highs, lows)
        result = imbalance.detect(df, "1H")
        assert result["totaal_open"] > 0 or result["totaal_gevuld"] > 0

    def test_bearish_imbalance_detected(self):
        # Candle 0 low=100, candle 2 high=95 → gap 95-100 (bearish)
        highs = [110, 100, 95, 93, 91]
        lows  = [100, 92,  88, 85, 83]
        df = make_df(highs, lows)
        result = imbalance.detect(df, "1H")
        assert result["totaal_open"] > 0 or result["totaal_gevuld"] > 0

    def test_filled_imbalance(self):
        # Gap between candle 0 and 2, but candle 3 fills it
        highs = [100, 105, 110, 102]
        lows  = [95,  102, 107,  98]
        df = make_df(highs, lows)
        result = imbalance.detect(df, "1H")
        # If there's an imbalance, check status tracking works
        assert "imbalances" in result
        assert "open_imbalances" in result

    def test_no_imbalance_when_candles_overlap(self):
        # All candles overlap — no gap
        highs = [105, 106, 107, 108]
        lows  = [95,  96,  97,  98]
        df = make_df(highs, lows)
        result = imbalance.detect(df, "1H")
        assert result["totaal_open"] == 0

    def test_empty_df(self):
        df = pd.DataFrame()
        result = imbalance.detect(df, "1H")
        assert result["imbalances"] == []


class TestGetOpenImbalancesBetween:
    def test_filter_between_prices(self):
        report = {
            "open_imbalances": [
                {"laag": 100, "hoog": 105},
                {"laag": 200, "hoog": 210},
                {"laag": 150, "hoog": 155},
            ]
        }
        result = imbalance.get_open_imbalances_between(report, 90, 160)
        assert len(result) == 2
        prices = [(r["laag"], r["hoog"]) for r in result]
        assert (100, 105) in prices
        assert (150, 155) in prices
