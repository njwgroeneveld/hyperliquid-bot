"""
Tests voor momentum.py
"""

import pandas as pd
import pytest
from src.detection import momentum


def make_df(candles: list[dict]) -> pd.DataFrame:
    n = len(candles)
    timestamps = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    df = pd.DataFrame(candles)
    df["timestamp"] = timestamps
    df["volume"] = 100.0
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def candle(o, h, l, c) -> dict:
    return {"open": o, "high": h, "low": l, "close": c}


class TestSingleCandle:
    def test_strong_impulse_candle(self):
        # Large body, tiny wicks
        row = pd.Series({"open": 100, "high": 110.5, "low": 99.5, "close": 110})
        result = momentum.assess_single_candle(row)
        assert result["type"] == "STERKE_IMPULS"
        assert result["richting"] == "BULLISH"

    def test_indecision_candle(self):
        # Small body, equal wicks = doji-like
        row = pd.Series({"open": 100, "high": 105, "low": 95, "close": 100.5})
        result = momentum.assess_single_candle(row)
        assert result["type"] in ("INDECISIE", "NORMAAL")

    def test_doji_zero_range(self):
        row = pd.Series({"open": 100, "high": 100, "low": 100, "close": 100})
        result = momentum.assess_single_candle(row)
        assert result["type"] == "DOJI"

    def test_bearish_impulse(self):
        row = pd.Series({"open": 110, "high": 110.5, "low": 99.5, "close": 100})
        result = momentum.assess_single_candle(row)
        assert result["richting"] == "BEARISH"


class TestMultiCandle:
    def test_strong_bullish_momentum(self):
        candles = [
            candle(100, 103, 100, 102),
            candle(102, 105, 102, 104),
            candle(104, 108, 104, 107),
            candle(107, 111, 107, 110),
            candle(110, 114, 110, 113),
            candle(113, 117, 113, 116),
        ]
        df = make_df(candles)
        result = momentum.assess_multi_candle(df, n=6)
        assert result["bullish_count"] == 6
        assert result["dominante_richting"] == "BULLISH"
        assert result["beoordeling"] in ("STERK", "MEDIUM")

    def test_weak_choppy_momentum(self):
        # Alternating candles, large wicks
        candles = [
            candle(100, 108, 92, 101),
            candle(101, 109, 93, 99),
            candle(99,  107, 91, 102),
            candle(102, 110, 94, 100),
            candle(100, 108, 92, 98),
            candle(98,  106, 90, 101),
        ]
        df = make_df(candles)
        result = momentum.assess_multi_candle(df, n=6)
        assert result["beoordeling"] == "ZWAK"

    def test_insufficient_data(self):
        df = make_df([candle(100, 101, 99, 100)])
        result = momentum.assess_multi_candle(df, n=6)
        assert "beoordeling" in result


class TestFullDetect:
    def test_returns_required_fields(self):
        candles = [candle(100 + i, 101 + i, 99 + i, 100 + i) for i in range(10)]
        df = make_df(candles)
        result = momentum.detect(df, "1H")
        assert "laatste_candle" in result
        assert "multi_candle_6" in result
        assert "impuls_beoordeling" in result
        assert "verwachte_richting" in result
