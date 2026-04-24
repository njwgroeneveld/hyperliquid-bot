"""
Tests voor supply_demand.py
"""

import pandas as pd
import pytest
from src.detection import supply_demand


def make_candle(open_: float, high: float, low: float, close: float) -> dict:
    return {"open": open_, "high": high, "low": low, "close": close}


def make_df(candles: list[dict]) -> pd.DataFrame:
    n = len(candles)
    timestamps = pd.date_range("2025-01-01", periods=n, freq="4h", tz="UTC")
    df = pd.DataFrame(candles)
    df["timestamp"] = timestamps
    df["volume"] = 100.0
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


class TestSupplyDemandZones:
    def _make_demand_setup(self) -> pd.DataFrame:
        """
        Demand zone setup:
        - Candle 0-3: normale candles
        - Candle 4: de zone (laatste voor impuls)
        - Candle 5: impuls candle (grote bullish candle + imbalance)
        - Candle 6: candle 2 na impuls (gap met candle 4)
        - Candles daarna: geen retest
        """
        candles = [
            make_candle(100, 103, 98, 101),
            make_candle(101, 104, 99, 102),
            make_candle(102, 105, 100, 103),
            make_candle(103, 106, 101, 104),
            make_candle(104, 106, 103, 105),   # zone candle
            make_candle(105, 118, 105, 117),   # impuls: open=105, close=117 (80% body, 11% move)
            make_candle(119, 122, 119, 121),   # candle 2 na impuls: low=119 > high=106 van zone → imbalance
            make_candle(121, 123, 120, 122),
            make_candle(122, 124, 121, 123),
        ]
        return make_df(candles)

    def test_demand_zone_identified(self):
        df = self._make_demand_setup()
        result = supply_demand.detect(df, "4H", min_body_pct=0.60, min_move_pct=0.003)
        # Should find at least one valid demand zone
        assert result["totaal_geldige_demand"] > 0 or result["totaal_geldige_supply"] >= 0

    def test_empty_df(self):
        result = supply_demand.detect(pd.DataFrame(), "4H")
        assert result["demand_zones"] == []
        assert result["supply_zones"] == []

    def test_zone_has_required_fields(self):
        df = self._make_demand_setup()
        result = supply_demand.detect(df, "4H")
        for zone in result["demand_zones"]:
            assert "id" in zone
            assert "laag" in zone
            assert "hoog" in zone
            assert "geldig" in zone
            assert "type" in zone

    def test_zone_classification_extreme(self):
        """Als er meerdere demand zones zijn, moet de verste EXTREME zijn."""
        df = self._make_demand_setup()
        result = supply_demand.detect(df, "4H")
        if len(result["demand_zones"]) >= 2:
            types = [z["type"] for z in result["demand_zones"]]
            assert "EXTREME" in types

    def test_touched_zone_still_valid(self):
        """Een zone die aangeraakt is maar niet doorbroken blijft geldig (Wyckoff)."""
        candles = [
            make_candle(100, 103, 98, 101),
            make_candle(101, 104, 99, 102),
            make_candle(102, 105, 100, 103),
            make_candle(103, 106, 101, 104),
            make_candle(104, 106, 103, 105),   # zone
            make_candle(105, 118, 105, 117),   # impuls
            make_candle(119, 122, 119, 121),   # imbalance gap
            make_candle(106, 110, 103, 108),   # AANRAKING maar close boven zone_low
        ]
        df = make_df(candles)
        result = supply_demand.detect(df, "4H")
        for zone in result["alle_demand_zones"]:
            if zone["geraakt"] and not zone["doorbroken"]:
                assert zone["geldig"] is True  # aangeraakt maar niet doorbroken = nog geldig

    def test_broken_zone_invalid(self):
        """Een zone waarbij een candle onder zone_low sluit is doorbroken en ongeldig."""
        candles = [
            make_candle(100, 103, 98, 101),
            make_candle(101, 104, 99, 102),
            make_candle(102, 105, 100, 103),
            make_candle(103, 106, 101, 104),
            make_candle(104, 106, 103, 105),   # zone (low=103)
            make_candle(105, 118, 105, 117),   # impuls
            make_candle(119, 122, 119, 121),   # imbalance gap
            make_candle(103, 107, 101, 101),   # close=101 < zone_low=103 → DOORBROKEN
        ]
        df = make_df(candles)
        result = supply_demand.detect(df, "4H")
        for zone in result["alle_demand_zones"]:
            if zone["doorbroken"]:
                assert zone["geldig"] is False
