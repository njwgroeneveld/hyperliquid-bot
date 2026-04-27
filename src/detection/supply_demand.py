"""
Supply & Demand zone identificatie.

Demand zone: laatste candle VOOR een impulsieve bullish beweging met imbalance.
Supply zone: laatste candle VOOR een impulsieve bearish beweging met imbalance.

Extreme zone = verste zone van huidige prijs in de huidige leg.
Zone is eenmalig geldig — zodra geraakt, niet meer bruikbaar.
"""

import pandas as pd
from typing import Optional


def _is_impulse_candle(
    df: pd.DataFrame,
    index: int,
    direction: str,
    min_body_pct: float = 0.60,
    min_move_pct: float = 0.003,
    volume_multiplier: float = 1.5,
) -> bool:
    """
    Een impuls candle heeft:
    - Grote body (>60% van range)
    - Minimale prijsbeweging (0.3%)
    - Volume boven 20-periode gemiddelde × multiplier (institutionele interesse)
    """
    row = df.iloc[index]
    candle_range = row["high"] - row["low"]
    if candle_range == 0:
        return False

    body = abs(row["close"] - row["open"])
    body_pct = body / candle_range
    move_pct = candle_range / row["open"]

    # Volume check: impuls moet boven gemiddeld volume liggen
    vol_start = max(0, index - 20)
    avg_volume = df["volume"].iloc[vol_start:index].mean()
    high_volume = (avg_volume == 0) or (df["volume"].iloc[index] >= avg_volume * volume_multiplier)

    if direction == "BULLISH":
        return (
            row["close"] > row["open"]
            and body_pct >= min_body_pct
            and move_pct >= min_move_pct
            and high_volume
        )
    else:
        return (
            row["close"] < row["open"]
            and body_pct >= min_body_pct
            and move_pct >= min_move_pct
            and high_volume
        )


def _has_imbalance_after(df: pd.DataFrame, index: int) -> bool:
    """Check if there's an imbalance (gap) after the impulse candle."""
    if index >= len(df) - 2:
        return False
    return df["high"].iloc[index] < df["low"].iloc[index + 2] or \
           df["low"].iloc[index] > df["high"].iloc[index + 2]


def _zone_status(
    df: pd.DataFrame,
    zone_index: int,
    zone_low: float,
    zone_high: float,
    zone_type: str,
) -> tuple[bool, bool, int]:
    """
    Bepaal of een zone aangeraakt en/of doorbroken is.

    Wyckoff-principe: een zone is pas ONGELDIG als een candle er doorheen SLUIT.
    Meerdere aanrakingen zonder sluiting = zone wordt sterker, niet zwakker.

    Returns:
        geraakt (bool):   wick heeft de zone bereikt
        doorbroken (bool): candle heeft door de zone gesloten → ongeldig
        touch_count (int): aantal keren aangeraakt
    """
    geraakt = False
    doorbroken = False
    touch_count = 0

    for i in range(zone_index + 2, len(df)):
        candle_low = df["low"].iloc[i]
        candle_high = df["high"].iloc[i]
        candle_close = df["close"].iloc[i]

        # Aanraking via wick
        if candle_low <= zone_high and candle_high >= zone_low:
            geraakt = True
            touch_count += 1

        # Doorbraak via candle close
        if zone_type == "DEMAND" and candle_close < zone_low:
            doorbroken = True
            break
        elif zone_type == "SUPPLY" and candle_close > zone_high:
            doorbroken = True
            break

    return geraakt, doorbroken, touch_count


def detect(
    df: pd.DataFrame,
    timeframe: str,
    min_body_pct: float = 0.60,
    min_move_pct: float = 0.003,
    volume_multiplier: float = 1.5,
) -> dict:
    """
    Find all demand and supply zones in df.

    Wyckoff-regel: zone is ongeldig wanneer een candle er doorheen SLUIT.
    Meerdere aanrakingen zonder sluiting = sterker bewijs, niet zwakker.
    """
    if df.empty or len(df) < 4:
        return {"timeframe": timeframe, "demand_zones": [], "supply_zones": []}

    demand_met_imb = []
    demand_zonder_imb = []
    supply_met_imb = []
    supply_zonder_imb = []
    current_price = float(df["close"].iloc[-1])

    for i in range(1, len(df) - 2):
        if _is_impulse_candle(df, i, "BULLISH", min_body_pct, min_move_pct, volume_multiplier):
            has_imb = _has_imbalance_after(df, i)
            zone_candle = df.iloc[i - 1]
            zone_low = float(min(zone_candle["open"], zone_candle["close"]))
            zone_high = float(max(zone_candle["open"], zone_candle["close"]))
            zone_low = min(zone_low, float(zone_candle["low"]))

            geraakt, doorbroken, touch_count = _zone_status(df, i - 1, zone_low, zone_high, "DEMAND")

            zone = {
                "id": f"DZ-{timeframe}-{i:04d}",
                "timeframe": timeframe,
                "laag": round(zone_low, 4),
                "hoog": round(zone_high, 4),
                "midden": round((zone_low + zone_high) / 2, 4),
                "imbalance": has_imb,
                "geraakt": geraakt,
                "touch_count": touch_count,
                "doorbroken": doorbroken,
                "geldig": not doorbroken,
                "afstand_pct": round(abs(current_price - (zone_low + zone_high) / 2) / current_price * 100, 2),
                "gevormd_op": str(df["timestamp"].iloc[i - 1]),
                "impulse_candle_index": i,
            }
            if has_imb:
                demand_met_imb.append(zone)
            else:
                demand_zonder_imb.append(zone)

        elif _is_impulse_candle(df, i, "BEARISH", min_body_pct, min_move_pct, volume_multiplier):
            has_imb = _has_imbalance_after(df, i)
            zone_candle = df.iloc[i - 1]
            zone_low = float(min(zone_candle["open"], zone_candle["close"]))
            zone_high = float(max(zone_candle["open"], zone_candle["close"]))
            zone_high = max(zone_high, float(zone_candle["high"]))

            geraakt, doorbroken, touch_count = _zone_status(df, i - 1, zone_low, zone_high, "SUPPLY")

            zone = {
                "id": f"SZ-{timeframe}-{i:04d}",
                "timeframe": timeframe,
                "laag": round(zone_low, 4),
                "hoog": round(zone_high, 4),
                "midden": round((zone_low + zone_high) / 2, 4),
                "imbalance": has_imb,
                "geraakt": geraakt,
                "touch_count": touch_count,
                "doorbroken": doorbroken,
                "geldig": not doorbroken,
                "afstand_pct": round(abs(current_price - (zone_low + zone_high) / 2) / current_price * 100, 2),
                "gevormd_op": str(df["timestamp"].iloc[i - 1]),
                "impulse_candle_index": i,
            }
            if has_imb:
                supply_met_imb.append(zone)
            else:
                supply_zonder_imb.append(zone)

    # Zones mét imbalance krijgen EXTREME/MIDDEL classificatie
    valid_demand_reg = [z for z in demand_met_imb if z["geldig"]]
    valid_supply_reg = [z for z in supply_met_imb if z["geldig"]]
    _classify_zone_type(valid_demand_reg, current_price, "DEMAND")
    _classify_zone_type(valid_supply_reg, current_price, "SUPPLY")

    # ZWAKKE zones (zonder imbalance) alleen als fallback wanneer geen reguliere zones bestaan
    valid_demand_zwak = [z for z in demand_zonder_imb if z["geldig"]]
    valid_supply_zwak = [z for z in supply_zonder_imb if z["geldig"]]
    for z in valid_demand_zwak:
        z["type"] = "ZWAKKE"
    for z in valid_supply_zwak:
        z["type"] = "ZWAKKE"

    valid_demand = valid_demand_reg if valid_demand_reg else valid_demand_zwak
    valid_supply = valid_supply_reg if valid_supply_reg else valid_supply_zwak

    alle_demand = demand_met_imb + demand_zonder_imb
    alle_supply = supply_met_imb + supply_zonder_imb

    return {
        "timeframe": timeframe,
        "huidige_prijs": current_price,
        "demand_zones": valid_demand,
        "supply_zones": valid_supply,
        "alle_demand_zones": alle_demand,
        "alle_supply_zones": alle_supply,
        "totaal_geldige_demand": len(valid_demand),
        "totaal_geldige_supply": len(valid_supply),
    }


def _classify_zone_type(zones: list[dict], current_price: float, side: str) -> None:
    """
    Mutates zones in-place to add 'type': 'EXTREME' or 'MIDDEL'.
    Extreme = furthest from current price (for demand: lowest; for supply: highest).
    """
    if not zones:
        return

    if side == "DEMAND":
        furthest = min(zones, key=lambda z: z["midden"])
    else:
        furthest = max(zones, key=lambda z: z["midden"])

    for z in zones:
        z["type"] = "EXTREME" if z["id"] == furthest["id"] else "MIDDEL"
