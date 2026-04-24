"""
Momentum detectie: individuele candle kwaliteit + multi-candle bewegingsbeoordeling.

Sleutelregel: body vs wick ratio bepaalt de kracht van de beweging.
Grote bodies = controle. Grote wicks = twijfel/afwijzing.
"""

import pandas as pd


def assess_single_candle(row: pd.Series) -> dict:
    """
    Beoordeel één candle op momentum.
    """
    candle_range = row["high"] - row["low"]
    if candle_range == 0:
        return {"type": "DOJI", "body_pct": 0, "wick_pct": 0, "richting": "NEUTRAAL"}

    body = abs(row["close"] - row["open"])
    body_pct = body / candle_range
    upper_wick = row["high"] - max(row["open"], row["close"])
    lower_wick = min(row["open"], row["close"]) - row["low"]
    wick_pct = (upper_wick + lower_wick) / candle_range

    richting = "BULLISH" if row["close"] > row["open"] else "BEARISH"

    if body_pct >= 0.60 and wick_pct <= 0.20:
        candle_type = "STERKE_IMPULS"
    elif body_pct >= 0.60:
        candle_type = "IMPULS"
    elif body_pct < 0.30:
        candle_type = "INDECISIE"
    elif (upper_wick > 2 * body and richting == "BEARISH") or \
         (lower_wick > 2 * body and richting == "BULLISH"):
        candle_type = "REVERSAL_WICK"
    else:
        candle_type = "NORMAAL"

    return {
        "type": candle_type,
        "richting": richting,
        "body_pct": round(body_pct, 3),
        "wick_pct": round(wick_pct, 3),
        "upper_wick": round(upper_wick, 4),
        "lower_wick": round(lower_wick, 4),
    }


def assess_multi_candle(df: pd.DataFrame, n: int = 6) -> dict:
    """
    Beoordeel de laatste N candles als een beweging.
    Kijkt naar: snelheid, grootte, vloeiendheid (weinig tegengestelde candles), pushback.
    """
    recent = df.tail(n).reset_index(drop=True)
    if len(recent) < 2:
        return {"beoordeling": "ONVOLDOENDE_DATA"}

    bullish_count = int((recent["close"] > recent["open"]).sum())
    bearish_count = int((recent["close"] < recent["open"]).sum())

    # Gemiddelde body grootte als % van open prijs
    bodies = ((recent["close"] - recent["open"]).abs() / recent["open"]).tolist()
    gem_body_pct = round(float(sum(bodies) / len(bodies)), 4)

    # Grote wicks aanwezig?
    candle_ranges = (recent["high"] - recent["low"])
    wicks = (
        (recent["high"] - recent[["open", "close"]].max(axis=1)) +
        (recent[["open", "close"]].min(axis=1) - recent["low"])
    )
    gem_wick_ratio = float((wicks / candle_ranges.replace(0, 1)).mean())
    grote_wicks = gem_wick_ratio > 0.40

    # Pushback: hoeveel tegengestelde candles in de dominante richting
    dominant = "BULLISH" if bullish_count >= bearish_count else "BEARISH"
    pushback_count = bearish_count if dominant == "BULLISH" else bullish_count
    pushback_aanwezig = pushback_count >= n // 3

    # Snelheid: totale prijsbeweging over periode
    totale_beweging_pct = abs(recent["close"].iloc[-1] - recent["close"].iloc[0]) / recent["close"].iloc[0]
    snelheid = round(float(totale_beweging_pct), 4)

    # Algehele beoordeling
    if gem_body_pct > 0.003 and not grote_wicks and not pushback_aanwezig:
        beoordeling = "STERK"
    elif gem_body_pct < 0.001 or (grote_wicks and pushback_aanwezig):
        beoordeling = "ZWAK"
    else:
        beoordeling = "MEDIUM"

    # Verwachte richting (voor confirmatie check)
    if bullish_count > bearish_count and beoordeling in ("STERK", "MEDIUM"):
        verwachte_richting = "BULLISH_CONTINUATIE"
    elif bearish_count > bullish_count and beoordeling in ("STERK", "MEDIUM"):
        verwachte_richting = "BEARISH_CONTINUATIE"
    elif beoordeling == "ZWAK" and grote_wicks:
        verwachte_richting = "MOGELIJKE_REVERSAL"
    else:
        verwachte_richting = "ONDUIDELIJK"

    return {
        "n_candles": n,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "dominante_richting": dominant,
        "gem_body_pct": gem_body_pct,
        "grote_wicks": grote_wicks,
        "gem_wick_ratio": round(gem_wick_ratio, 3),
        "pushback_aanwezig": pushback_aanwezig,
        "pushback_count": pushback_count,
        "snelheid_pct": snelheid,
        "beoordeling": beoordeling,
        "verwachte_richting": verwachte_richting,
    }


def detect(df: pd.DataFrame, timeframe: str) -> dict:
    """
    Full momentum detection.
    Returns detection report dict.
    """
    if df.empty or len(df) < 6:
        return {"timeframe": timeframe, "error": "Te weinig data"}

    laatste_candle = assess_single_candle(df.iloc[-1])
    vorige_candle = assess_single_candle(df.iloc[-2])
    multi = assess_multi_candle(df, n=6)

    return {
        "timeframe": timeframe,
        "laatste_candle": laatste_candle,
        "vorige_candle": vorige_candle,
        "multi_candle_6": multi,
        "impuls_beoordeling": multi["beoordeling"],
        "verwachte_richting": multi["verwachte_richting"],
    }
