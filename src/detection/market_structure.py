"""
Market structure detection: swing highs/lows, HH/HL/LL/LH, Break of Structure.

Key rule from bootcamp: candle body CLOSURES determine structure, not wicks.
"""

import pandas as pd
from typing import Optional


def find_swing_highs(df: pd.DataFrame, n: int = 3) -> list[dict]:
    """
    A swing high is where the close is higher than the N closes on each side.
    Returns list of {index, price, timestamp}.
    """
    highs = []
    closes = df["close"].values
    for i in range(n, len(df) - n):
        is_high = all(closes[i] > closes[i - j] for j in range(1, n + 1)) and \
                  all(closes[i] > closes[i + j] for j in range(1, n + 1))
        if is_high:
            highs.append({
                "index": i,
                "price": float(closes[i]),
                "timestamp": df["timestamp"].iloc[i].isoformat(),
            })
    return highs


def find_swing_lows(df: pd.DataFrame, n: int = 3) -> list[dict]:
    """
    A swing low is where the close is lower than the N closes on each side.
    """
    lows = []
    closes = df["close"].values
    for i in range(n, len(df) - n):
        is_low = all(closes[i] < closes[i - j] for j in range(1, n + 1)) and \
                 all(closes[i] < closes[i + j] for j in range(1, n + 1))
        if is_low:
            lows.append({
                "index": i,
                "price": float(closes[i]),
                "timestamp": df["timestamp"].iloc[i].isoformat(),
            })
    return lows


def classify_trend(swing_highs: list[dict], swing_lows: list[dict], lookback: int = 3) -> dict:
    """
    Uptrend:    de laatste `lookback` swing highs zijn stijgend EN lows zijn stijgend
    Downtrend:  de laatste `lookback` swing highs zijn dalend EN lows zijn dalend
    Consolidatie: gemengd of te weinig swings

    Gebruikt alleen de LAATSTE `lookback` swings — niet alle 20+.
    Dit voorkomt dat één kleine correctie in een sterke trend de classificatie breekt.
    """
    result = {
        "trend": "CONSOLIDATIE",
        "last_hh": None,
        "last_hl": None,
        "last_ll": None,
        "last_lh": None,
        "reasoning": "",
    }

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        result["reasoning"] = "Onvoldoende swings voor trendclassificatie"
        return result

    # Gebruik alleen de meest recente swings
    recent_highs = swing_highs[-lookback:]
    recent_lows = swing_lows[-lookback:]

    highs_ascending = all(
        recent_highs[i]["price"] > recent_highs[i - 1]["price"]
        for i in range(1, len(recent_highs))
    )
    lows_ascending = all(
        recent_lows[i]["price"] > recent_lows[i - 1]["price"]
        for i in range(1, len(recent_lows))
    )
    highs_descending = all(
        recent_highs[i]["price"] < recent_highs[i - 1]["price"]
        for i in range(1, len(recent_highs))
    )
    lows_descending = all(
        recent_lows[i]["price"] < recent_lows[i - 1]["price"]
        for i in range(1, len(recent_lows))
    )

    last_hh = recent_highs[-1]
    last_hl = recent_lows[-1]

    if highs_ascending and lows_ascending:
        result["trend"] = "UPTREND"
        result["last_hh"] = last_hh
        result["last_hl"] = last_hl
        result["reasoning"] = (
            f"HH ${last_hh['price']:,.0f} > vorige HH ${recent_highs[-2]['price']:,.0f}, "
            f"HL ${last_hl['price']:,.0f} > vorige HL ${recent_lows[-2]['price']:,.0f} "
            f"(laatste {len(recent_highs)} highs, {len(recent_lows)} lows)"
        )
    elif highs_descending and lows_descending:
        result["trend"] = "DOWNTREND"
        result["last_ll"] = last_hl
        result["last_lh"] = last_hh
        result["reasoning"] = (
            f"LL ${last_hl['price']:,.0f} < vorige LL ${recent_lows[-2]['price']:,.0f}, "
            f"LH ${last_hh['price']:,.0f} < vorige LH ${recent_highs[-2]['price']:,.0f} "
            f"(laatste {len(recent_highs)} highs, {len(recent_lows)} lows)"
        )
    else:
        prev_h = recent_highs[-2]["price"] if len(recent_highs) >= 2 else "?"
        prev_l = recent_lows[-2]["price"] if len(recent_lows) >= 2 else "?"
        result["reasoning"] = (
            f"Gemengde structuur — HH {last_hh['price']:,.0f} vs vorige {prev_h}, "
            f"HL {last_hl['price']:,.0f} vs vorige {prev_l}"
        )

    return result


def detect_break_of_structure(
    df: pd.DataFrame,
    swing_highs: list[dict],
    swing_lows: list[dict],
) -> Optional[dict]:
    """
    Bullish BOS: candle body closes above the most recent swing high.
    Bearish BOS: candle body closes below the most recent swing low.

    Returns the most recent BOS event or None.
    """
    if not swing_highs or not swing_lows:
        return None

    last_sh = swing_highs[-1]
    last_sl = swing_lows[-1]

    # Check candles after the last swing high/low
    bos_events = []

    for i in range(last_sh["index"] + 1, len(df)):
        if df["close"].iloc[i] > last_sh["price"]:
            bos_events.append({
                "richting": "BULLISH",
                "prijs": float(df["close"].iloc[i]),
                "doorbroken_swing": last_sh["price"],
                "timestamp": df["timestamp"].iloc[i].isoformat(),
                "index": i,
            })
            break

    for i in range(last_sl["index"] + 1, len(df)):
        if df["close"].iloc[i] < last_sl["price"]:
            bos_events.append({
                "richting": "BEARISH",
                "prijs": float(df["close"].iloc[i]),
                "doorbroken_swing": last_sl["price"],
                "timestamp": df["timestamp"].iloc[i].isoformat(),
                "index": i,
            })
            break

    if not bos_events:
        return None

    # Return the most recent BOS
    return max(bos_events, key=lambda x: x["index"])


def detect(df: pd.DataFrame, timeframe: str, n: int = 3, lookback: int = 3) -> dict:
    """
    Full market structure detection for one timeframe.

    Returns the detection report dict for this timeframe.
    """
    if df.empty or len(df) < n * 2 + 1:
        return {"timeframe": timeframe, "trend": "ONVOLDOENDE_DATA", "error": "Te weinig candles"}

    swing_highs = find_swing_highs(df, n=n)
    swing_lows = find_swing_lows(df, n=n)
    trend_info = classify_trend(swing_highs, swing_lows, lookback=lookback)
    bos = detect_break_of_structure(df, swing_highs, swing_lows)

    return {
        "timeframe": timeframe,
        "trend": trend_info["trend"],
        "trend_reasoning": trend_info["reasoning"],
        "laatste_hh": trend_info["last_hh"],
        "laatste_hl": trend_info["last_hl"],
        "laatste_ll": trend_info["last_ll"],
        "laatste_lh": trend_info["last_lh"],
        "alle_swing_highs": swing_highs[-5:],   # laatste 5 voor context
        "alle_swing_lows": swing_lows[-5:],
        "laatste_bos": bos,
        "totaal_swing_highs": len(swing_highs),
        "totaal_swing_lows": len(swing_lows),
    }
