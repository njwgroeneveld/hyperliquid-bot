"""
Tests voor decision_tree.py, entry_calculator.py en position_sizer.py
"""

import pytest
from src.decision import decision_tree
from src.decision.entry_calculator import calculate_entry, find_target
from src.decision.position_sizer import calculate, validate_position


# ─── Helpers ───────────────────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "strategy": {
        "zone_proximity_pct": 0.02,
        "swing_n": 3,
        "equal_tolerance": 0.0015,
        "impulse_min_body_pct": 0.60,
        "impulse_min_move_pct": 0.003,
    },
    "risk": {
        "risk_per_trade": 0.01,
        "max_leverage": 2,
        "min_risk_reward": 2.0,
        "stop_buffer_pct": 0.001,
    }
}


def make_detection(
    trend_4h="UPTREND",
    trend_1h="UPTREND",
    demand_zones=None,
    supply_zones=None,
    open_imbalances_1h=None,
    eq_highs=None,
    eq_lows=None,
    oi_interpretatie="ECHTE_VRAAG",
    funding_sentiment="NEUTRAAL",
    prijs=95000,
) -> dict:
    demand_zones = demand_zones or []
    supply_zones = supply_zones or []
    open_imbalances_1h = open_imbalances_1h or []
    eq_highs = eq_highs or []
    eq_lows = eq_lows or []

    return {
        "coin": "BTC",
        "huidige_prijs": prijs,
        "structuur_4h": {
            "trend": trend_4h,
            "trend_reasoning": f"4H {trend_4h}",
            "alle_swing_highs": [],
            "alle_swing_lows": [],
        },
        "structuur_1h": {
            "trend": trend_1h,
            "trend_reasoning": f"1H {trend_1h}",
            "laatste_bos": None,
        },
        "zones_4h": {
            "demand_zones": demand_zones,
            "supply_zones": supply_zones,
        },
        "zones_1h": {"demand_zones": [], "supply_zones": []},
        "imbalances_4h": {"open_imbalances": []},
        "imbalances_1h": {"open_imbalances": open_imbalances_1h},
        "liquiditeit_4h": {
            "equal_highs": eq_highs,
            "equal_lows": eq_lows,
            "open_eq_highs": [h for h in eq_highs if not h.get("gesweept")],
            "open_eq_lows": [l for l in eq_lows if not l.get("gesweept")],
        },
        "liquiditeit_1h": {
            "equal_highs": [],
            "equal_lows": [],
            "open_eq_highs": [],
            "open_eq_lows": [],
        },
        "momentum_4h": {"impuls_beoordeling": "STERK", "verwachte_richting": "BULLISH_CONTINUATIE"},
        "momentum_1h": {"impuls_beoordeling": "STERK", "verwachte_richting": "BULLISH_CONTINUATIE"},
        "order_flow": {
            "order_book": {"grootste_buy_wall": None, "grootste_sell_wall": None},
            "open_interest": {"interpretatie": oi_interpretatie, "trend": "STIJGEND"},
            "funding_rate": {"sentiment": funding_sentiment, "huidig": 0.0001, "uitleg": "neutraal"},
        },
    }


def make_demand_zone(laag=93000, hoog=93500, prijs=95000) -> dict:
    return {
        "id": "DZ-001", "timeframe": "4H",
        "laag": laag, "hoog": hoog,
        "midden": (laag + hoog) / 2,
        "type": "EXTREME", "imbalance": True, "geldig": True,
        "afstand_pct": abs(prijs - (laag + hoog) / 2) / prijs * 100,
        "gevormd_op": "2025-04-22T12:00:00",
    }


def make_supply_zone(laag=96000, hoog=96500, prijs=95000) -> dict:
    return {
        "id": "SZ-001", "timeframe": "4H",
        "laag": laag, "hoog": hoog,
        "midden": (laag + hoog) / 2,
        "type": "EXTREME", "imbalance": True, "geldig": True,
        "afstand_pct": abs(prijs - (laag + hoog) / 2) / prijs * 100,
        "gevormd_op": "2025-04-23T08:00:00",
    }


# ─── Beslissingsboom tests ──────────────────────────────────────────────────────

class TestStap1Trend:
    def test_consolidatie_geeft_veto(self):
        det = make_detection(trend_4h="CONSOLIDATIE")
        result = decision_tree.evaluate(det, DEFAULT_SETTINGS)
        assert result["beslissing"] == decision_tree.BESLISSING_VETO
        assert result["veto_reden"] is not None

    def test_uptrend_geeft_long_richting(self):
        det = make_detection(trend_4h="UPTREND", demand_zones=[make_demand_zone()])
        result = decision_tree.evaluate(det, DEFAULT_SETTINGS)
        assert result["richting"] == "LONG"

    def test_downtrend_geeft_short_richting(self):
        det = make_detection(
            trend_4h="DOWNTREND", trend_1h="DOWNTREND",
            supply_zones=[make_supply_zone()],
        )
        # Override momentum voor short
        det["momentum_1h"]["verwachte_richting"] = "BEARISH_CONTINUATIE"
        det["momentum_4h"]["verwachte_richting"] = "BEARISH_CONTINUATIE"
        result = decision_tree.evaluate(det, DEFAULT_SETTINGS)
        assert result["richting"] == "SHORT"


class TestStap2Zone:
    def test_geen_zone_stopt_beslissingsboom(self):
        det = make_detection(trend_4h="UPTREND", demand_zones=[])
        result = decision_tree.evaluate(det, DEFAULT_SETTINGS)
        assert result["beslissing"] == decision_tree.BESLISSING_GEEN_TRADE
        assert result["groene_stappen"] < 6

    def test_zone_te_ver_geeft_geel(self):
        # Zone 10% verwijderd — buiten proximity_pct van 2%
        zone = make_demand_zone(laag=84000, hoog=84500, prijs=95000)
        det = make_detection(trend_4h="UPTREND", demand_zones=[zone])
        result = decision_tree.evaluate(det, DEFAULT_SETTINGS)
        stap2 = next(s for s in result["stappen"] if s["stap"] == 2)
        assert stap2["resultaat"] == "GEEL"

    def test_zone_dichtbij_geeft_groen(self):
        zone = make_demand_zone(laag=93500, hoog=94000, prijs=95000)  # 1.3% weg
        det = make_detection(trend_4h="UPTREND", demand_zones=[zone])
        result = decision_tree.evaluate(det, DEFAULT_SETTINGS)
        stap2 = next(s for s in result["stappen"] if s["stap"] == 2)
        assert stap2["resultaat"] == "GROEN"


class TestStap3Imbalance:
    def test_open_imbalance_op_pad_geeft_veto(self):
        zone = make_demand_zone(laag=93000, hoog=93500, prijs=95000)
        # Imbalance op het pad (tussen zone en prijs)
        blocking_imb = {"laag": 93600, "hoog": 94000, "midden": 93800, "richting": "BULLISH", "status": "OPEN"}
        det = make_detection(
            trend_4h="UPTREND",
            demand_zones=[zone],
            open_imbalances_1h=[blocking_imb],
        )
        result = decision_tree.evaluate(det, DEFAULT_SETTINGS)
        assert result["beslissing"] == decision_tree.BESLISSING_VETO

    def test_geen_imbalance_op_pad_geeft_groen(self):
        zone = make_demand_zone(laag=93500, hoog=94000, prijs=95000)
        det = make_detection(trend_4h="UPTREND", demand_zones=[zone], open_imbalances_1h=[])
        result = decision_tree.evaluate(det, DEFAULT_SETTINGS)
        stap3 = next((s for s in result["stappen"] if s["stap"] == 3), None)
        if stap3:
            assert stap3["resultaat"] == "GROEN"


class TestStap5Bevestiging:
    def test_1h_tegenstrijdig_stopt(self):
        zone = make_demand_zone(laag=93500, hoog=94000, prijs=95000)
        det = make_detection(trend_4h="UPTREND", trend_1h="DOWNTREND", demand_zones=[zone])
        result = decision_tree.evaluate(det, DEFAULT_SETTINGS)
        assert result["beslissing"] == decision_tree.BESLISSING_GEEN_TRADE


class TestVolledige_Entry:
    def test_ideale_long_setup_geeft_entry(self):
        """Perfecte setup: uptrend, dichtbije zone, geen imbalances, goede 1H, sterk momentum."""
        zone = make_demand_zone(laag=93500, hoog=94000, prijs=95000)
        det = make_detection(
            trend_4h="UPTREND",
            trend_1h="UPTREND",
            demand_zones=[zone],
            oi_interpretatie="ECHTE_VRAAG",
            funding_sentiment="OVERSOLD_SHORTS",
        )
        result = decision_tree.evaluate(det, DEFAULT_SETTINGS)
        assert result["is_entry"] is True
        assert result["richting"] == "LONG"
        assert result["geselecteerde_zone"] is not None

    def test_score_bevat_alle_stappen(self):
        zone = make_demand_zone(laag=93500, hoog=94000, prijs=95000)
        det = make_detection(trend_4h="UPTREND", demand_zones=[zone])
        result = decision_tree.evaluate(det, DEFAULT_SETTINGS)
        assert len(result["stappen"]) >= 3  # minstens de stappen die zijn doorlopen


# ─── Entry calculator tests ────────────────────────────────────────────────────

class TestEntryCalculator:
    def _make_df_1h(self, n=20, base=93000, atr_size=500):
        """Maak een nep 1H DataFrame met bekende ATR."""
        import pandas as pd
        timestamps = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
        rows = []
        for i in range(n):
            rows.append({
                "timestamp": timestamps[i],
                "open": base, "high": base + atr_size,
                "low": base - atr_size, "close": base, "volume": 100.0
            })
        return pd.DataFrame(rows)

    def test_long_entry_in_midden_zone(self):
        zone = {"laag": 93000, "hoog": 94000, "midden": 93500}
        result = calculate_entry(zone, "LONG", stop_buffer_pct=0.001)
        assert result["entry"] == pytest.approx(93500, abs=1)
        assert result["stop_loss"] < 93000

    def test_short_entry_in_midden_zone(self):
        zone = {"laag": 96000, "hoog": 97000, "midden": 96500}
        result = calculate_entry(zone, "SHORT", stop_buffer_pct=0.001)
        assert result["entry"] == pytest.approx(96500, abs=1)
        assert result["stop_loss"] > 97000

    def test_lege_zone_geeft_lege_dict(self):
        result = calculate_entry(None, "LONG")
        assert result == {}

    def test_stop_afstand_positief(self):
        zone = {"laag": 93000, "hoog": 94000, "midden": 93500}
        result = calculate_entry(zone, "LONG")
        assert result["stop_afstand_pct"] > 0

    def test_atr_stop_groter_dan_fallback(self):
        """ATR-stop geeft meer ruimte dan vaste 0.1% fallback."""
        zone = {"laag": 93000, "hoog": 94000, "midden": 93500}
        df = self._make_df_1h(atr_size=500)  # ATR ~500
        result_atr = calculate_entry(zone, "LONG", df_1h=df, atr_multiplier=1.5)
        result_fixed = calculate_entry(zone, "LONG", stop_buffer_pct=0.001)
        assert result_atr["stop_loss"] < result_fixed["stop_loss"]  # ATR stop verder weg
        assert result_atr["atr"] > 0
        assert "ATR" in result_atr["stop_methode"]

    def test_funding_cost_berekening(self):
        from src.decision.entry_calculator import estimate_funding_cost
        detection = make_detection()
        detection["order_flow"]["funding_rate"]["huidig"] = 0.0003  # 0.03% per 8h
        result = estimate_funding_cost(detection, "LONG", leverage=2, avg_trade_hours=16)
        # 0.03% × 2 leverage × 2 perioden = 0.12%
        assert result["geschatte_kosten_pct"] == pytest.approx(0.12, abs=0.01)
        assert result["is_kostenpost"] is True

    def test_target_met_geldige_eq_high(self):
        detection = make_detection(prijs=95000)
        detection["liquiditeit_4h"]["open_eq_highs"] = [
            {"prijs": 98000, "touches": 2, "gesweept": False}
        ]
        result = find_target(detection, "LONG", entry=93500, stop_loss=92900, min_rr=2.0)
        assert result["haalbaar"] is True
        assert result["target"] == 98000
        assert result["rr"] >= 2.0

    def test_geen_target_als_rr_te_laag(self):
        detection = make_detection(prijs=95000)
        detection["liquiditeit_4h"]["open_eq_highs"] = [
            {"prijs": 93600, "touches": 2, "gesweept": False}  # te dichtbij
        ]
        result = find_target(detection, "LONG", entry=93500, stop_loss=92900, min_rr=2.0)
        assert result["haalbaar"] is False


# ─── Position sizer tests ──────────────────────────────────────────────────────

class TestPositionSizer:
    def test_basis_berekening(self):
        result = calculate(
            portfolio_usd=10000,
            entry=93500,
            stop_loss=92900,
            risk_pct=0.01,
            leverage=2,
        )
        assert result["risico_usd"] == pytest.approx(100, abs=1)
        assert result["afstand_stop_pct"] == pytest.approx(0.641, abs=0.01)
        assert result["positiegrootte_usd"] > 0
        assert result["margin_usd"] == pytest.approx(result["positiegrootte_usd"] / 2, abs=1)

    def test_nul_portfolio_geeft_fout(self):
        result = calculate(0, 93500, 92900)
        assert "error" in result

    def test_gelijke_entry_stop_geeft_fout(self):
        result = calculate(10000, 93500, 93500)
        assert "error" in result

    def test_validatie_te_grote_positie(self):
        # Positie groter dan 5% van portfolio
        positie = {"positiegrootte_usd": 1500}
        result = validate_position(positie, max_position_pct=0.05, portfolio_usd=10000)
        assert result["geldig"] is False
        assert "gecorrigeerde_positie" in result

    def test_validatie_binnen_limiet(self):
        positie = {"positiegrootte_usd": 400}
        result = validate_position(positie, max_position_pct=0.05, portfolio_usd=10000)
        assert result["geldig"] is True
