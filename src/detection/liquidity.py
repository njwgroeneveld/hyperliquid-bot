"""
Liquiditeitsdetectie: equal highs/lows en sweep events.

Equal highs/lows zijn predictabele liquiditeitsclusters.
Nooit verkopen boven equal highs — eerst sweep afwachten.
"""

import pandas as pd
from typing import Optional


def find_equal_levels(
    swing_points: list[dict],
    tolerance: float = 0.0015,
    label: str = "EQH",
) -> list[dict]:
    """
    Group swing points that are within `tolerance` (e.g. 0.15%) of each other.
    Each group = one equal level.
    """
    if len(swing_points) < 2:
        return []

    # Sort by price
    sorted_points = sorted(swing_points, key=lambda x: x["price"])
    groups = []
    current_group = [sorted_points[0]]

    for i in range(1, len(sorted_points)):
        ref_price = current_group[0]["price"]
        current_price = sorted_points[i]["price"]
        if abs(current_price - ref_price) / ref_price <= tolerance:
            current_group.append(sorted_points[i])
        else:
            if len(current_group) >= 2:
                groups.append(_build_level(current_group, label))
            current_group = [sorted_points[i]]

    if len(current_group) >= 2:
        groups.append(_build_level(current_group, label))

    return groups


def _build_level(group: list[dict], label: str) -> dict:
    prices = [p["price"] for p in group]
    timestamps = [p["timestamp"] for p in group]
    return {
        "id": f"{label}-{int(sum(prices) / len(prices)):d}",
        "prijs": round(sum(prices) / len(prices), 4),
        "min_prijs": min(prices),
        "max_prijs": max(prices),
        "touches": len(group),
        "eerste_touch": min(timestamps),
        "laatste_touch": max(timestamps),
        "type": label,
        "gesweept": False,
        "sweep_tijd": None,
        "sweep_bevestigd": False,
    }


def detect_sweeps(
    levels: list[dict],
    df: pd.DataFrame,
    direction: str,
) -> list[dict]:
    """
    For each level, check if a candle has swept through it (wick beyond level)
    and then closed back on the other side (confirmed sweep).

    direction: 'HIGH' or 'LOW'
    """
    for level in levels:
        level_price = level["prijs"]
        for i in range(len(df)):
            if direction == "HIGH":
                # Sweep: wick above level, body closes back below
                if df["high"].iloc[i] > level_price:
                    level["gesweept"] = True
                    level["sweep_tijd"] = str(df["timestamp"].iloc[i])
                    # Confirmed if body closes below level
                    if df["close"].iloc[i] < level_price:
                        level["sweep_bevestigd"] = True
                    break
            else:
                # Sweep: wick below level, body closes back above
                if df["low"].iloc[i] < level_price:
                    level["gesweept"] = True
                    level["sweep_tijd"] = str(df["timestamp"].iloc[i])
                    if df["close"].iloc[i] > level_price:
                        level["sweep_bevestigd"] = True
                    break
    return levels


def detect(
    df: pd.DataFrame,
    swing_highs: list[dict],
    swing_lows: list[dict],
    timeframe: str,
    tolerance: float = 0.0015,
) -> dict:
    """
    Full liquidity detection.
    Returns detection report dict.
    """
    equal_highs = find_equal_levels(swing_highs, tolerance, label="EQH")
    equal_lows = find_equal_levels(swing_lows, tolerance, label="EQL")

    # Check sweeps on recent candles (last 50)
    recent_df = df.tail(50).reset_index(drop=True)
    equal_highs = detect_sweeps(equal_highs, recent_df, "HIGH")
    equal_lows = detect_sweeps(equal_lows, recent_df, "LOW")

    current_price = float(df["close"].iloc[-1])

    # Find nearest unsweept levels above/below current price
    nearest_eq_high = _nearest_above(equal_highs, current_price)
    nearest_eq_low = _nearest_below(equal_lows, current_price)

    return {
        "timeframe": timeframe,
        "huidige_prijs": current_price,
        "equal_highs": equal_highs,
        "equal_lows": equal_lows,
        "dichtstbijzijnde_eq_high": nearest_eq_high,
        "dichtstbijzijnde_eq_low": nearest_eq_low,
        "totaal_eq_highs": len(equal_highs),
        "totaal_eq_lows": len(equal_lows),
        "open_eq_highs": [l for l in equal_highs if not l["gesweept"]],
        "open_eq_lows": [l for l in equal_lows if not l["gesweept"]],
    }


def _nearest_above(levels: list[dict], price: float) -> Optional[dict]:
    candidates = [l for l in levels if l["prijs"] > price and not l["gesweept"]]
    return min(candidates, key=lambda x: x["prijs"]) if candidates else None


def _nearest_below(levels: list[dict], price: float) -> Optional[dict]:
    candidates = [l for l in levels if l["prijs"] < price and not l["gesweept"]]
    return max(candidates, key=lambda x: x["prijs"]) if candidates else None
