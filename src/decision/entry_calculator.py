"""
Entry-, stop-loss- en targetberekening op basis van de geselecteerde zone.

Verbeteringen t.o.v. v1:
  - Stop-loss is ATR-gebaseerd (dynamisch) in plaats van vaste 0.1%
  - Funding-kosten worden afgetrokken van het verwachte reward bij targetkeuze
"""

import pandas as pd
import numpy as np


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    Average True Range over de laatste `period` candles.
    TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
    """
    if df.empty or len(df) < period + 1:
        return 0.0

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    trs = []
    for i in range(1, len(df)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    return float(np.mean(trs[-period:]))


def calculate_entry(
    zone: dict,
    richting: str,
    df_1h: pd.DataFrame | None = None,
    atr_period: int = 14,
    atr_multiplier: float = 1.5,
    stop_buffer_pct: float = 0.001,
) -> dict:
    """
    Bereken entry, stop-loss en stop-afstand.

    Stop-loss = zone_rand ± (ATR × multiplier).
    Als df_1h niet beschikbaar → fallback naar vaste stop_buffer_pct.
    """
    if not zone:
        return {}

    zone_laag = zone["laag"]
    zone_hoog = zone["hoog"]
    entry = (zone_laag + zone_hoog) / 2

    # Bereken ATR voor dynamische stop
    atr = calculate_atr(df_1h, atr_period) if df_1h is not None and not df_1h.empty else 0.0

    if atr > 0:
        stop_afstand = atr * atr_multiplier
        stop_methode = f"ATR({atr_period})×{atr_multiplier} = {atr:.2f}×{atr_multiplier}"
    else:
        stop_afstand = entry * stop_buffer_pct
        stop_methode = f"Fallback {stop_buffer_pct*100:.1f}%"

    if richting == "LONG":
        stop_loss = zone_laag - stop_afstand
        stop_afstand_pct = (entry - stop_loss) / entry * 100
    else:
        stop_loss = zone_hoog + stop_afstand
        stop_afstand_pct = (stop_loss - entry) / entry * 100

    return {
        "entry": round(entry, 2),
        "stop_loss": round(stop_loss, 2),
        "stop_afstand_pct": round(stop_afstand_pct, 3),
        "atr": round(atr, 2),
        "stop_methode": stop_methode,
    }


def estimate_funding_cost(
    detection: dict,
    richting: str,
    leverage: int = 2,
    avg_trade_hours: float = 12.0,
) -> dict:
    """
    Schat de funding-kosten voor de verwachte handelsduur.

    funding_cost_pct = |funding_rate| × leverage × (avg_trade_hours / 8)
    (funding wordt elke 8 uur betaald op Hyperliquid)

    Een long positie bij positieve funding betaalt; negatieve funding ontvangt.
    Een short positie bij negatieve funding betaalt; positieve funding ontvangt.
    """
    of = detection.get("order_flow", {})
    funding_rate = of.get("funding_rate", {}).get("huidig", 0.0)
    periods = avg_trade_hours / 8.0

    if richting == "LONG":
        # Positieve funding = long betaalt → kostenpost
        cost_pct = funding_rate * leverage * periods
    else:
        # Negatieve funding = short betaalt → kostenpost
        cost_pct = -funding_rate * leverage * periods

    # Positief = kosten, negatief = ontvangst
    return {
        "funding_rate_per_8h": round(funding_rate, 6),
        "verwachte_perioden": round(periods, 1),
        "geschatte_kosten_pct": round(cost_pct * 100, 4),
        "is_kostenpost": cost_pct > 0,
    }


def find_target(
    detection: dict,
    richting: str,
    entry: float,
    stop_loss: float,
    min_rr: float = 2.0,
    leverage: int = 2,
    avg_trade_hours: float = 12.0,
) -> dict:
    """
    Zoek het beste target en valideer R/R na aftrek van verwachte funding-kosten.
    """
    risico = abs(entry - stop_loss)
    if risico == 0:
        return {"haalbaar": False, "reden": "Risico is 0 (entry = stop)"}

    funding = estimate_funding_cost(detection, richting, leverage, avg_trade_hours)
    funding_cost_pct = funding["geschatte_kosten_pct"] / 100  # als fractie van positie

    kandidaten = []

    liq_4h = detection.get("liquiditeit_4h", {})
    liq_1h = detection.get("liquiditeit_1h", {})

    if richting == "LONG":
        for lvl in liq_4h.get("open_eq_highs", []) + liq_1h.get("open_eq_highs", []):
            if lvl["prijs"] > entry:
                bruto_reward = lvl["prijs"] - entry
                netto_reward = bruto_reward - (entry * funding_cost_pct)
                rr = netto_reward / risico if risico > 0 else 0
                kandidaten.append({"prijs": lvl["prijs"], "type": "EQUAL_HIGH", "rr": round(rr, 2), "bruto_rr": round(bruto_reward / risico, 2)})

        for imb in detection.get("imbalances_4h", {}).get("open_imbalances", []):
            if imb["midden"] > entry:
                bruto_reward = imb["midden"] - entry
                netto_reward = bruto_reward - (entry * funding_cost_pct)
                rr = netto_reward / risico if risico > 0 else 0
                kandidaten.append({"prijs": imb["midden"], "type": "IMBALANCE", "rr": round(rr, 2), "bruto_rr": round(bruto_reward / risico, 2)})

        for z in detection.get("zones_4h", {}).get("supply_zones", []):
            if z["laag"] > entry:
                bruto_reward = z["laag"] - entry
                netto_reward = bruto_reward - (entry * funding_cost_pct)
                rr = netto_reward / risico if risico > 0 else 0
                kandidaten.append({"prijs": z["laag"], "type": "SUPPLY_ZONE", "rr": round(rr, 2), "bruto_rr": round(bruto_reward / risico, 2)})

    else:  # SHORT
        for lvl in liq_4h.get("open_eq_lows", []) + liq_1h.get("open_eq_lows", []):
            if lvl["prijs"] < entry:
                bruto_reward = entry - lvl["prijs"]
                netto_reward = bruto_reward - (entry * funding_cost_pct)
                rr = netto_reward / risico if risico > 0 else 0
                kandidaten.append({"prijs": lvl["prijs"], "type": "EQUAL_LOW", "rr": round(rr, 2), "bruto_rr": round(bruto_reward / risico, 2)})

        for imb in detection.get("imbalances_4h", {}).get("open_imbalances", []):
            if imb["midden"] < entry:
                bruto_reward = entry - imb["midden"]
                netto_reward = bruto_reward - (entry * funding_cost_pct)
                rr = netto_reward / risico if risico > 0 else 0
                kandidaten.append({"prijs": imb["midden"], "type": "IMBALANCE", "rr": round(rr, 2), "bruto_rr": round(bruto_reward / risico, 2)})

        for z in detection.get("zones_4h", {}).get("demand_zones", []):
            if z["hoog"] < entry:
                bruto_reward = entry - z["hoog"]
                netto_reward = bruto_reward - (entry * funding_cost_pct)
                rr = netto_reward / risico if risico > 0 else 0
                kandidaten.append({"prijs": z["hoog"], "type": "DEMAND_ZONE", "rr": round(rr, 2), "bruto_rr": round(bruto_reward / risico, 2)})

    haalbare = [k for k in kandidaten if k["rr"] >= min_rr]

    if not haalbare:
        return {
            "target": None,
            "target_type": None,
            "rr": None,
            "haalbaar": False,
            "funding": funding,
            "reden": f"Geen target met min {min_rr}R na funding-aftrek ({len(kandidaten)} kandidaten te klein)",
            "alle_kandidaten": sorted(kandidaten, key=lambda x: x["rr"], reverse=True)[:5],
        }

    beste = min(haalbare, key=lambda x: x["prijs"]) if richting == "LONG" else max(haalbare, key=lambda x: x["prijs"])

    return {
        "target": round(beste["prijs"], 2),
        "target_type": beste["type"],
        "rr": beste["rr"],
        "bruto_rr": beste["bruto_rr"],
        "haalbaar": True,
        "funding": funding,
        "alle_kandidaten": sorted(kandidaten, key=lambda x: x["rr"], reverse=True)[:5],
    }
