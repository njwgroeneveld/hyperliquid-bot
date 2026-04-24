"""
Imbalance detectie: open price gaps tussen candles.

Een imbalance bestaat als:
  - high van candle N < low van candle N+2  (bullish imbalance, prijsgat naar boven)
  - low van candle N > high van candle N+2  (bearish imbalance, prijsgat naar beneden)

Gevuld als een latere candle de wick of body door de gap beweegt.
"""

import pandas as pd


def detect(df: pd.DataFrame, timeframe: str) -> dict:
    """
    Detect all open and filled imbalances in df.
    Returns detection report dict.
    """
    if df.empty or len(df) < 3:
        return {"timeframe": timeframe, "imbalances": []}

    imbalances = []
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    timestamps = df["timestamp"].values

    for i in range(len(df) - 2):
        candle_high = highs[i]
        candle_low = lows[i]
        next_next_low = lows[i + 2]
        next_next_high = highs[i + 2]

        # Bullish imbalance: gap between top of candle i and bottom of candle i+2
        if candle_high < next_next_low:
            imb_low = float(candle_high)
            imb_high = float(next_next_low)
            richting = "BULLISH"

            # Check if any subsequent candle has filled the gap
            status, filled_at = _check_filled(df, i + 2, imb_low, imb_high, "BULLISH")

            imbalances.append({
                "id": f"IMB-{timeframe}-{i:04d}",
                "timeframe": timeframe,
                "laag": imb_low,
                "hoog": imb_high,
                "midden": (imb_low + imb_high) / 2,
                "richting": richting,
                "status": status,
                "gevormd_candle_index": i,
                "gevormd_op": str(timestamps[i]),
                "gevuld_op": filled_at,
            })

        # Bearish imbalance: gap between bottom of candle i and top of candle i+2
        elif candle_low > next_next_high:
            imb_low = float(next_next_high)
            imb_high = float(candle_low)
            richting = "BEARISH"

            status, filled_at = _check_filled(df, i + 2, imb_low, imb_high, "BEARISH")

            imbalances.append({
                "id": f"IMB-{timeframe}-{i:04d}",
                "timeframe": timeframe,
                "laag": imb_low,
                "hoog": imb_high,
                "midden": (imb_low + imb_high) / 2,
                "richting": richting,
                "status": status,
                "gevormd_candle_index": i,
                "gevormd_op": str(timestamps[i]),
                "gevuld_op": filled_at,
            })

    open_imbalances = [imb for imb in imbalances if imb["status"] == "OPEN"]
    filled_imbalances = [imb for imb in imbalances if imb["status"] == "GEVULD"]

    return {
        "timeframe": timeframe,
        "imbalances": imbalances,
        "open_imbalances": open_imbalances,
        "gevulde_imbalances": filled_imbalances,
        "totaal_open": len(open_imbalances),
        "totaal_gevuld": len(filled_imbalances),
    }


def _check_filled(
    df: pd.DataFrame,
    start_index: int,
    imb_low: float,
    imb_high: float,
    richting: str,
) -> tuple[str, str | None]:
    """
    Check if any candle after start_index has entered the imbalance gap.
    Returns ("GEVULD", timestamp) or ("OPEN", None).
    """
    for j in range(start_index + 1, len(df)):
        candle_low = df["low"].iloc[j]
        candle_high = df["high"].iloc[j]
        # If candle wick has entered the gap zone
        if candle_low <= imb_high and candle_high >= imb_low:
            return "GEVULD", str(df["timestamp"].iloc[j])
    return "OPEN", None


def get_open_imbalances_between(
    imbalances_report: dict,
    price_from: float,
    price_to: float,
) -> list[dict]:
    """
    Filter open imbalances that lie between two price levels.
    Useful for checking if path to a zone is clear.
    """
    lo = min(price_from, price_to)
    hi = max(price_from, price_to)

    return [
        imb for imb in imbalances_report.get("open_imbalances", [])
        if imb["laag"] >= lo and imb["hoog"] <= hi
    ]
