"""
Order flow analyse: order walls, liquidatieclusters, open interest, funding rate.
"""

import math


def detect_order_walls(
    orderbook: dict,
    current_price: float,
    bucket_pct: float = 0.001,
    wall_threshold_pct: float = 0.02,
    top_n: int = 5,
) -> dict:
    """
    Aggregeer het orderbook in price buckets en vind de grootste clusters.

    bucket_pct: grootte van elke bucket (0.1% van prijs)
    wall_threshold_pct: minimum grootte (als % van totaal) om wall te zijn
    """
    bids = orderbook.get("bids", [])
    asks = orderbook.get("asks", [])

    def aggregate_to_buckets(levels: list[dict], bucket_size: float) -> dict:
        buckets: dict[int, float] = {}
        for lvl in levels:
            bucket_key = int(lvl["price"] / bucket_size)
            buckets[bucket_key] = buckets.get(bucket_key, 0.0) + lvl["size"]
        return buckets

    bucket_size = current_price * bucket_pct

    bid_buckets = aggregate_to_buckets(bids, bucket_size)
    ask_buckets = aggregate_to_buckets(asks, bucket_size)

    def top_walls(buckets: dict, n: int) -> list[dict]:
        sorted_buckets = sorted(buckets.items(), key=lambda x: x[1], reverse=True)
        return [
            {"prijs": round(bucket_key * bucket_size, 2), "grootte": round(size, 4)}
            for bucket_key, size in sorted_buckets[:n]
        ]

    buy_walls = sorted(top_walls(bid_buckets, top_n), key=lambda x: x["prijs"], reverse=True)
    sell_walls = sorted(top_walls(ask_buckets, top_n), key=lambda x: x["prijs"])

    grootste_buy = buy_walls[0] if buy_walls else None
    grootste_sell = sell_walls[0] if sell_walls else None

    return {
        "grootste_buy_wall": grootste_buy,
        "grootste_sell_wall": grootste_sell,
        "top_buy_walls": buy_walls,
        "top_sell_walls": sell_walls,
        "totaal_bid_volume": round(sum(b["size"] for b in bids), 4),
        "totaal_ask_volume": round(sum(a["size"] for a in asks), 4),
    }


def interpret_open_interest(oi_current: float, oi_previous: float, price_current: float, price_previous: float) -> dict:
    """
    Interpreteer OI trend gecombineerd met prijsrichting.
    """
    oi_stijgend = oi_current > oi_previous
    prijs_stijgend = price_current > price_previous

    if oi_stijgend and prijs_stijgend:
        interpretatie = "ECHTE_VRAAG"
        uitleg = "Stijgend OI + stijgende prijs = nieuwe longs openen"
    elif oi_stijgend and not prijs_stijgend:
        interpretatie = "SHORTS_ACCUMULEREN"
        uitleg = "Stijgend OI + dalende prijs = nieuwe shorts openen, squeeze mogelijk"
    elif not oi_stijgend and prijs_stijgend:
        interpretatie = "SHORT_SQUEEZE"
        uitleg = "Dalend OI + stijgende prijs = shorts sluiten gedwongen"
    else:
        interpretatie = "LONG_LIQUIDATIES"
        uitleg = "Dalend OI + dalende prijs = longs worden geliquideerd"

    oi_change_pct = (oi_current - oi_previous) / oi_previous * 100 if oi_previous > 0 else 0

    return {
        "waarde": round(oi_current, 2),
        "vorige_waarde": round(oi_previous, 2),
        "verandering_pct": round(oi_change_pct, 2),
        "trend": "STIJGEND" if oi_stijgend else "DALEND",
        "interpretatie": interpretatie,
        "uitleg": uitleg,
    }


def interpret_funding_rate(funding_rate: float) -> dict:
    """
    Interpreteer de funding rate.
    Positief = veel longs, negatief = veel shorts.
    """
    pct = funding_rate * 100  # Convert to percentage

    if funding_rate > 0.0003:
        sentiment = "OVERKOCHT_LONGS"
        uitleg = f"Funding {pct:.4f}% — veel longs, duur om long te zijn"
    elif funding_rate < -0.0001:
        sentiment = "OVERSOLD_SHORTS"
        uitleg = f"Funding {pct:.4f}% — veel shorts, squeeze risico aanwezig"
    else:
        sentiment = "NEUTRAAL"
        uitleg = f"Funding {pct:.4f}% — gebalanceerde markt"

    return {
        "huidig": round(funding_rate, 6),
        "huidig_pct": round(pct, 4),
        "sentiment": sentiment,
        "uitleg": uitleg,
    }


def detect(
    orderbook: dict,
    meta: dict,
    meta_previous: dict | None,
    coin: str,
    current_price: float,
) -> dict:
    """
    Full order flow detection.
    meta: {'open_interest', 'funding_rate', 'mark_price', ...}
    meta_previous: same structure from previous hour (for OI trend)
    """
    # Order walls
    if orderbook and orderbook.get("bids"):
        order_walls = detect_order_walls(orderbook, current_price)
    else:
        order_walls = {"error": "Geen orderbook data"}

    # OI
    oi = meta.get("open_interest", 0)
    oi_prev = meta_previous.get("open_interest", oi) if meta_previous else oi
    price_prev = meta_previous.get("mark_price", current_price) if meta_previous else current_price

    oi_info = interpret_open_interest(oi, oi_prev, current_price, price_prev)

    # Funding
    funding = meta.get("funding_rate", 0)
    funding_info = interpret_funding_rate(funding)

    return {
        "coin": coin,
        "huidige_prijs": current_price,
        "order_book": order_walls,
        "open_interest": oi_info,
        "funding_rate": funding_info,
    }
