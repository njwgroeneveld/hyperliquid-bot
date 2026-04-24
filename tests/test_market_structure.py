"""
Tests voor market_structure.py
"""

import pandas as pd
import pytest
from src.detection import market_structure


def make_df(closes: list[float], highs: list[float] | None = None, lows: list[float] | None = None) -> pd.DataFrame:
    n = len(closes)
    if highs is None:
        highs = [c * 1.01 for c in closes]
    if lows is None:
        lows = [c * 0.99 for c in closes]
    timestamps = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [100.0] * n,
    })


class TestSwingHighs:
    def test_basic_swing_high(self):
        # Duidelijke piek in het midden
        closes = [100, 101, 102, 110, 102, 101, 100, 99, 98]
        df = make_df(closes)
        highs = market_structure.find_swing_highs(df, n=3)
        assert len(highs) == 1
        assert highs[0]["price"] == 110

    def test_no_swing_high_flat(self):
        closes = [100, 100, 100, 100, 100, 100, 100]
        df = make_df(closes)
        highs = market_structure.find_swing_highs(df, n=3)
        assert highs == []

    def test_multiple_swing_highs(self):
        # Two clear peaks separated enough so each passes the n=2 lookback check
        closes = [80, 90, 110, 100, 95, 120, 100, 95, 115, 100, 90, 80]
        df = make_df(closes)
        highs = market_structure.find_swing_highs(df, n=2)
        assert len(highs) >= 2


class TestSwingLows:
    def test_basic_swing_low(self):
        closes = [100, 99, 98, 90, 98, 99, 100, 101, 102]
        df = make_df(closes)
        lows = market_structure.find_swing_lows(df, n=3)
        assert len(lows) == 1
        assert lows[0]["price"] == 90


class TestTrend:
    def test_uptrend_detected(self):
        swing_highs = [{"price": 100, "timestamp": "t1"}, {"price": 110, "timestamp": "t2"}, {"price": 120, "timestamp": "t3"}]
        swing_lows = [{"price": 90, "timestamp": "t1"}, {"price": 95, "timestamp": "t2"}, {"price": 100, "timestamp": "t3"}]
        result = market_structure.classify_trend(swing_highs, swing_lows)
        assert result["trend"] == "UPTREND"

    def test_downtrend_detected(self):
        swing_highs = [{"price": 120, "timestamp": "t1"}, {"price": 110, "timestamp": "t2"}, {"price": 100, "timestamp": "t3"}]
        swing_lows = [{"price": 100, "timestamp": "t1"}, {"price": 90, "timestamp": "t2"}, {"price": 80, "timestamp": "t3"}]
        result = market_structure.classify_trend(swing_highs, swing_lows)
        assert result["trend"] == "DOWNTREND"

    def test_consolidation_mixed(self):
        swing_highs = [{"price": 100, "timestamp": "t1"}, {"price": 110, "timestamp": "t2"}, {"price": 105, "timestamp": "t3"}]
        swing_lows = [{"price": 90, "timestamp": "t1"}, {"price": 85, "timestamp": "t2"}, {"price": 95, "timestamp": "t3"}]
        result = market_structure.classify_trend(swing_highs, swing_lows)
        assert result["trend"] == "CONSOLIDATIE"

    def test_insufficient_swings(self):
        result = market_structure.classify_trend([{"price": 100, "timestamp": "t1"}], [])
        assert result["trend"] == "CONSOLIDATIE"


class TestBOS:
    def test_bullish_bos(self):
        # Swing high at 110, then price closes above it
        closes = [100, 105, 110, 107, 105, 103, 102, 115]
        df = make_df(closes)
        swing_highs = [{"index": 2, "price": 110, "timestamp": "t2"}]
        swing_lows = [{"index": 6, "price": 102, "timestamp": "t6"}]
        bos = market_structure.detect_break_of_structure(df, swing_highs, swing_lows)
        assert bos is not None
        assert bos["richting"] == "BULLISH"

    def test_no_bos_when_price_stays_below(self):
        closes = [100, 110, 105, 103, 101, 100, 99, 98]
        df = make_df(closes)
        swing_highs = [{"index": 1, "price": 110, "timestamp": "t1"}]
        swing_lows = [{"index": 7, "price": 98, "timestamp": "t7"}]
        bos = market_structure.detect_break_of_structure(df, swing_highs, swing_lows)
        # No BOS because price never closes above 110 after index 1
        assert bos is None or bos["richting"] != "BULLISH"


class TestFullDetect:
    def test_full_detect_returns_dict(self):
        closes = [100, 105, 102, 108, 104, 110, 106, 112, 108, 115, 111, 118]
        df = make_df(closes)
        result = market_structure.detect(df, "4H", n=2)
        assert "trend" in result
        assert "timeframe" in result
        assert result["timeframe"] == "4H"

    def test_insufficient_data(self):
        df = make_df([100, 101])
        result = market_structure.detect(df, "1H")
        assert result["trend"] == "ONVOLDOENDE_DATA"
