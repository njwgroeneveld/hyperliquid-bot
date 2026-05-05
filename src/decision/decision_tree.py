"""
7-stappen beslissingsboom op basis van detectierapporten.

Elke stap geeft: GROEN / GEEL (punt aftrek) / ROOD (stop) / VETO (altijd stop).
Hard veto's stoppen de boom onmiddellijk, ongeacht andere scores.

Ingangspunt: decision_tree.evaluate(detection_report, settings) → beslissingsrapport
"""

from datetime import datetime, timezone


RESULTAAT_GROEN = "GROEN"
RESULTAAT_GEEL = "GEEL"
RESULTAAT_ROOD = "ROOD"
RESULTAAT_VETO = "VETO"

BESLISSING_ENTRY_HOOG = "ENTRY_HOOG_VERTROUWEN"
BESLISSING_ENTRY_MEDIUM = "ENTRY_MEDIUM_VERTROUWEN"
BESLISSING_GEEN_TRADE = "GEEN_TRADE"
BESLISSING_VETO = "VETO_GEEN_TRADE"


def _stap_1_trend(detection: dict) -> dict:
    """Stap 1: Is er een duidelijke 4H trend?"""
    struct_4h = detection.get("structuur_4h", {})
    trend = struct_4h.get("trend", "ONBEKEND")

    if trend == "UPTREND":
        return {
            "stap": 1, "naam": "Trendrichting (4H)",
            "resultaat": RESULTAAT_GROEN,
            "richting": "LONG",
            "waarde": trend,
            "bewijs": struct_4h.get("trend_reasoning", ""),
            "veto": False,
        }
    elif trend == "DOWNTREND":
        return {
            "stap": 1, "naam": "Trendrichting (4H)",
            "resultaat": RESULTAAT_GROEN,
            "richting": "SHORT",
            "waarde": trend,
            "bewijs": struct_4h.get("trend_reasoning", ""),
            "veto": False,
        }
    elif trend == "ZWAKKE_UPTREND":
        return {
            "stap": 1, "naam": "Trendrichting (4H)",
            "resultaat": RESULTAAT_GEEL,
            "richting": "LONG",
            "waarde": trend,
            "bewijs": f"Zwakke opwaartse trend — gedeeltelijke structuurbevestiging: {struct_4h.get('trend_reasoning', '')}",
            "veto": False,
        }
    elif trend == "ZWAKKE_DOWNTREND":
        return {
            "stap": 1, "naam": "Trendrichting (4H)",
            "resultaat": RESULTAAT_GEEL,
            "richting": "SHORT",
            "waarde": trend,
            "bewijs": f"Zwakke neerwaartse trend — gedeeltelijke structuurbevestiging: {struct_4h.get('trend_reasoning', '')}",
            "veto": False,
        }
    else:
        return {
            "stap": 1, "naam": "Trendrichting (4H)",
            "resultaat": RESULTAAT_VETO,
            "richting": None,
            "waarde": trend,
            "bewijs": f"Geen duidelijke trend: {trend} — beslissingsboom gestopt",
            "veto": True,
        }


def _stap_2_zone(detection: dict, richting: str, proximity_pct: float = 0.02) -> dict:
    """Stap 2: Is er een extreme zone in de trendrichting, en nadert de prijs?"""
    prijs = detection.get("huidige_prijs", 0)
    zones_4h = detection.get("zones_4h", {})
    zones_1h = detection.get("zones_1h", {})

    if richting == "LONG":
        candidates = zones_4h.get("demand_zones", []) + zones_1h.get("demand_zones", [])
        # Alleen zones ONDER huidige prijs zijn relevant voor long entry
        candidates = [z for z in candidates if z["hoog"] <= prijs * 1.001]
    else:
        candidates = zones_4h.get("supply_zones", []) + zones_1h.get("supply_zones", [])
        candidates = [z for z in candidates if z["laag"] >= prijs * 0.999]

    if not candidates:
        return {
            "stap": 2, "naam": "Supply/Demand zone",
            "resultaat": RESULTAAT_ROOD,
            "zone": None,
            "bewijs": f"Geen geldige {richting} zone gevonden",
            "veto": False,
        }

    # Kies de beste zone: extreme zone bij voorkeur, anders dichtstbijzijnde
    extreme_zones = [z for z in candidates if z.get("type") == "EXTREME"]
    beste_zone = extreme_zones[0] if extreme_zones else candidates[0]

    # Controleer nabijheid
    zone_midden = beste_zone["midden"]
    afstand_pct = abs(prijs - zone_midden) / prijs

    zone_type = beste_zone.get("type", "?")

    if afstand_pct <= proximity_pct:
        if zone_type == "ZWAKKE":
            return {
                "stap": 2, "naam": "Supply/Demand zone",
                "resultaat": RESULTAAT_GEEL,
                "zone": beste_zone,
                "bewijs": (
                    f"{'Demand' if richting == 'LONG' else 'Supply'} zone gevonden (ZWAKKE — geen imbalance): "
                    f"${beste_zone['laag']:,.0f}–${beste_zone['hoog']:,.0f}, "
                    f"afstand {afstand_pct*100:.1f}% van huidige prijs"
                ),
                "veto": False,
            }
        return {
            "stap": 2, "naam": "Supply/Demand zone",
            "resultaat": RESULTAAT_GROEN,
            "zone": beste_zone,
            "bewijs": (
                f"{'Demand' if richting == 'LONG' else 'Supply'} zone gevonden: "
                f"${beste_zone['laag']:,.0f}–${beste_zone['hoog']:,.0f} "
                f"({zone_type}), "
                f"afstand {afstand_pct*100:.1f}% van huidige prijs"
            ),
            "veto": False,
        }
    else:
        return {
            "stap": 2, "naam": "Supply/Demand zone",
            "resultaat": RESULTAAT_GEEL,
            "zone": beste_zone,
            "bewijs": (
                f"Zone gevonden ({zone_type}) maar prijs nog {afstand_pct*100:.1f}% verwijderd "
                f"(max {proximity_pct*100:.0f}%) — wachten"
            ),
            "veto": False,
        }


def _stap_3_imbalance(detection: dict, richting: str, zone: dict | None, zone_binnen_bereik: bool = True) -> dict:
    """
    Stap 3: Is de weg naar de zone vrij van open imbalances?

    Voor LONG: zijn er open imbalances TUSSEN huidige prijs en de demand zone?
    Hard VETO alleen als zone al binnen bereik is (stap 2 GROEN).
    Als zone nog ver weg is (stap 2 GEEL): blokkerende imbalances geven GEEL — score aftrek, geen stop.
    """
    prijs = detection.get("huidige_prijs", 0)
    imb_1h = detection.get("imbalances_1h", {})

    if zone is None:
        return {
            "stap": 3, "naam": "Imbalance check",
            "resultaat": RESULTAAT_GEEL,
            "bewijs": "Geen zone bekend — imbalance check overgeslagen",
            "veto": False,
        }

    zone_midden = zone["midden"]
    open_imbs = imb_1h.get("open_imbalances", [])

    # Vind imbalances die tussen huidige prijs en de zone liggen
    if richting == "LONG":
        blocking = [
            imb for imb in open_imbs
            if imb["laag"] >= zone_midden and imb["hoog"] <= prijs
        ]
    else:
        blocking = [
            imb for imb in open_imbs
            if imb["hoog"] <= zone_midden and imb["laag"] >= prijs
        ]

    if blocking:
        imb_omschrijving = ", ".join(f"${i['laag']:,.0f}–${i['hoog']:,.0f}" for i in blocking)
        if zone_binnen_bereik:
            return {
                "stap": 3, "naam": "Imbalance check",
                "resultaat": RESULTAAT_VETO,
                "blokkerende_imbalances": blocking,
                "bewijs": (
                    f"{len(blocking)} open imbalance(s) blokkeert pad naar zone: {imb_omschrijving}"
                ),
                "veto": True,
            }
        return {
            "stap": 3, "naam": "Imbalance check",
            "resultaat": RESULTAAT_GEEL,
            "blokkerende_imbalances": blocking,
            "bewijs": (
                f"{len(blocking)} open imbalance(s) op pad naar zone (zone nog buiten bereik): {imb_omschrijving}"
            ),
            "veto": False,
        }

    return {
        "stap": 3, "naam": "Imbalance check",
        "resultaat": RESULTAAT_GROEN,
        "bewijs": "Geen blokkerende imbalances — pad naar zone is vrij",
        "veto": False,
    }


def _stap_4_liquiditeit(detection: dict, richting: str, zone: dict | None) -> dict:
    """
    Stap 4: Blokkeren equal highs/lows de entry?

    LONG: equal lows al gesweept (goed) + geen unswept equal highs direct boven entry
    SHORT: equal highs al gesweept (goed) + geen unswept equal lows direct onder entry
    """
    liq_4h = detection.get("liquiditeit_4h", {})
    liq_1h = detection.get("liquiditeit_1h", {})
    prijs = detection.get("huidige_prijs", 0)

    if richting == "LONG":
        # Check: ongesweepte equal highs direct boven entry (binnen 1.5%)
        open_eq_highs = liq_4h.get("open_eq_highs", []) + liq_1h.get("open_eq_highs", [])
        blocking_highs = [
            h for h in open_eq_highs
            if h["prijs"] > prijs and (h["prijs"] - prijs) / prijs < 0.015
        ]

        # Check: waren equal lows al gesweept (gunstig teken)
        eq_lows_gesweept = any(
            l["gesweept"] for l in liq_4h.get("equal_lows", []) + liq_1h.get("equal_lows", [])
            if l["prijs"] < prijs
        )

        if blocking_highs and not eq_lows_gesweept:
            return {
                "stap": 4, "naam": "Liquiditeitsfilter",
                "resultaat": RESULTAAT_VETO,
                "bewijs": (
                    f"Ongesweepte equal highs boven entry: "
                    + ", ".join(f"${h['prijs']:,.0f} ({h['touches']}x)" for h in blocking_highs)
                    + " — prijs zal waarschijnlijk eerst die liquiditeit halen"
                ),
                "veto": True,
            }
        elif blocking_highs:
            return {
                "stap": 4, "naam": "Liquiditeitsfilter",
                "resultaat": RESULTAAT_GEEL,
                "bewijs": (
                    f"Equal highs boven entry maar equal lows al gesweept — licht risico: "
                    + ", ".join(f"${h['prijs']:,.0f}" for h in blocking_highs)
                ),
                "veto": False,
            }
        else:
            sweep_tekst = "Equal lows recent gesweept — sell-side liquiditeit geconsumeerd" if eq_lows_gesweept else "Geen blokkerende equal highs"
            return {
                "stap": 4, "naam": "Liquiditeitsfilter",
                "resultaat": RESULTAAT_GROEN,
                "bewijs": sweep_tekst,
                "veto": False,
            }

    else:  # SHORT
        open_eq_lows = liq_4h.get("open_eq_lows", []) + liq_1h.get("open_eq_lows", [])
        blocking_lows = [
            l for l in open_eq_lows
            if l["prijs"] < prijs and (prijs - l["prijs"]) / prijs < 0.015
        ]

        eq_highs_gesweept = any(
            h["gesweept"] for h in liq_4h.get("equal_highs", []) + liq_1h.get("equal_highs", [])
            if h["prijs"] > prijs
        )

        if blocking_lows and not eq_highs_gesweept:
            return {
                "stap": 4, "naam": "Liquiditeitsfilter",
                "resultaat": RESULTAAT_VETO,
                "bewijs": (
                    f"Ongesweepte equal lows onder entry — prijs haalt eerst die liquiditeit: "
                    + ", ".join(f"${l['prijs']:,.0f}" for l in blocking_lows)
                ),
                "veto": True,
            }
        elif blocking_lows:
            return {
                "stap": 4, "naam": "Liquiditeitsfilter",
                "resultaat": RESULTAAT_GEEL,
                "bewijs": f"Equal lows onder entry maar equal highs al gesweept — licht risico",
                "veto": False,
            }
        else:
            sweep_tekst = "Equal highs recent gesweept — buy-side liquiditeit geconsumeerd" if eq_highs_gesweept else "Geen blokkerende equal lows"
            return {
                "stap": 4, "naam": "Liquiditeitsfilter",
                "resultaat": RESULTAAT_GROEN,
                "bewijs": sweep_tekst,
                "veto": False,
            }


def _stap_5_bevestiging_1h(detection: dict, richting: str) -> dict:
    """
    Stap 5: Bevestigt de 1H structuur de 4H richting?

    Bullish bevestiging: 1H heeft een structuurshift naar bullish (hogere high na lagere low)
    Bearish bevestiging: 1H heeft een structuurshift naar bearish
    """
    struct_1h = detection.get("structuur_1h", {})
    trend_1h = struct_1h.get("trend", "ONBEKEND")
    bos_1h = struct_1h.get("laatste_bos")

    gewenste_trend = "UPTREND" if richting == "LONG" else "DOWNTREND"
    tegengestelde_trend = "DOWNTREND" if richting == "LONG" else "UPTREND"

    if trend_1h == gewenste_trend:
        return {
            "stap": 5, "naam": "1H bevestiging",
            "resultaat": RESULTAAT_GROEN,
            "bewijs": f"1H trend ({trend_1h}) bevestigt 4H richting {richting}",
            "veto": False,
        }
    elif trend_1h == tegengestelde_trend:
        # Hard stop: 1H tegenstrijdig met 4H
        return {
            "stap": 5, "naam": "1H bevestiging",
            "resultaat": RESULTAAT_ROOD,
            "bewijs": f"1H trend ({trend_1h}) is tegenstrijdig met 4H richting {richting}",
            "veto": False,
        }
    else:
        # Consolidatie of onduidelijk op 1H — punt aftrek maar geen veto
        bos_tekst = ""
        if bos_1h:
            bos_richting = bos_1h.get("richting", "?")
            gewenste_bos = "BULLISH" if richting == "LONG" else "BEARISH"
            if bos_richting == gewenste_bos:
                bos_tekst = f" — BOS {bos_richting} aanwezig op 1H, gedeeltelijke bevestiging"

        return {
            "stap": 5, "naam": "1H bevestiging",
            "resultaat": RESULTAAT_GEEL,
            "bewijs": f"1H neutraal ({trend_1h}) — geen bevestiging maar ook geen tegenwerking{bos_tekst}",
            "veto": False,
        }


def _stap_6_momentum(detection: dict, richting: str) -> dict:
    """
    Stap 6: Bevestigt momentum de trendrichting?

    GROEN: impuls sterk, correctie zwak en choppy
    GEEL: neutraal momentum
    ROOD: sterke correctie (momentum draait om)
    """
    mom_4h = detection.get("momentum_4h", {})
    mom_1h = detection.get("momentum_1h", {})

    beoordeling_4h = mom_4h.get("impuls_beoordeling", "MEDIUM")
    beoordeling_1h = mom_1h.get("impuls_beoordeling", "MEDIUM")
    verwachte_richting_1h = mom_1h.get("verwachte_richting", "ONDUIDELIJK")

    gewenste_continuatie = "BULLISH_CONTINUATIE" if richting == "LONG" else "BEARISH_CONTINUATIE"
    verkeerde_continuatie = "BEARISH_CONTINUATIE" if richting == "LONG" else "BULLISH_CONTINUATIE"

    if verwachte_richting_1h == gewenste_continuatie and beoordeling_1h in ("STERK", "MEDIUM"):
        return {
            "stap": 6, "naam": "Momentum bevestiging",
            "resultaat": RESULTAAT_GROEN,
            "bewijs": (
                f"1H momentum: {beoordeling_1h} ({verwachte_richting_1h}), "
                f"4H momentum: {beoordeling_4h}"
            ),
            "veto": False,
        }
    elif verwachte_richting_1h == verkeerde_continuatie and beoordeling_1h == "STERK":
        return {
            "stap": 6, "naam": "Momentum bevestiging",
            "resultaat": RESULTAAT_ROOD,
            "bewijs": (
                f"Sterke tegenstrijdige impuls op 1H: {verwachte_richting_1h} — "
                f"correctie te sterk voor {richting} entry"
            ),
            "veto": False,
        }
    elif verwachte_richting_1h == "MOGELIJKE_REVERSAL":
        return {
            "stap": 6, "naam": "Momentum bevestiging",
            "resultaat": RESULTAAT_GEEL,
            "bewijs": f"Mogelijke reversal signalen op 1H — grote wicks zichtbaar",
            "veto": False,
        }
    else:
        return {
            "stap": 6, "naam": "Momentum bevestiging",
            "resultaat": RESULTAAT_GEEL,
            "bewijs": f"Neutraal momentum — 1H: {beoordeling_1h}, 4H: {beoordeling_4h}",
            "veto": False,
        }


def _stap_7_order_flow(detection: dict, richting: str, zone: dict | None) -> dict:
    """
    Stap 7: Bevestigt order flow de trendrichting?

    GROEN: buy wall onder entry + liquidatiecluster shorts (voor long)
    GEEL: neutraal order book
    ROOD: grote sell wall direct boven entry
    """
    of = detection.get("order_flow", {})
    prijs = detection.get("huidige_prijs", 0)

    order_book = of.get("order_book", {})
    oi_info = of.get("open_interest", {})
    funding_info = of.get("funding_rate", {})

    oi_interpretatie = oi_info.get("interpretatie", "ONBEKEND")
    funding_sentiment = funding_info.get("sentiment", "NEUTRAAL")

    score_punten = 0
    bewijs_delen = []

    # OI interpretatie
    if richting == "LONG":
        gunstige_oi = ("ECHTE_VRAAG", "SHORTS_ACCUMULEREN")  # shorts accumuleren = squeeze mogelijk
        if oi_interpretatie in gunstige_oi:
            score_punten += 1
            bewijs_delen.append(f"OI: {oi_interpretatie}")
        elif oi_interpretatie == "LONG_LIQUIDATIES":
            score_punten -= 1
            bewijs_delen.append(f"OI: {oi_interpretatie} — ongunstig")
    else:
        gunstige_oi = ("LONG_LIQUIDATIES", "ECHTE_VRAAG")  # dalende prijs + echte vraag = sterke bears
        if oi_interpretatie == "LONG_LIQUIDATIES":
            score_punten += 1
            bewijs_delen.append(f"OI: {oi_interpretatie}")
        elif oi_interpretatie == "SHORT_SQUEEZE":
            score_punten -= 1
            bewijs_delen.append(f"OI: SHORT_SQUEEZE — ongunstig voor short")

    # Funding rate
    if richting == "LONG" and funding_sentiment == "OVERSOLD_SHORTS":
        score_punten += 1
        bewijs_delen.append(f"Funding negatief — veel shorts, squeeze risico")
    elif richting == "SHORT" and funding_sentiment == "OVERKOCHT_LONGS":
        score_punten += 1
        bewijs_delen.append(f"Funding positief — veel longs, long squeeze risico")
    elif funding_sentiment == "NEUTRAAL":
        bewijs_delen.append("Funding neutraal")

    # Order walls
    grootste_buy = order_book.get("grootste_buy_wall")
    grootste_sell = order_book.get("grootste_sell_wall")

    if richting == "LONG" and grootste_buy and zone:
        # Buy wall onder of in de zone = goed
        if grootste_buy["prijs"] <= zone.get("hoog", prijs) * 1.001:
            score_punten += 1
            bewijs_delen.append(f"Buy wall ${grootste_buy['prijs']:,.0f} ({grootste_buy['grootte']:.1f} BTC) onder/in zone")

    if richting == "SHORT" and grootste_sell and zone:
        if grootste_sell["prijs"] >= zone.get("laag", prijs) * 0.999:
            score_punten += 1
            bewijs_delen.append(f"Sell wall ${grootste_sell['prijs']:,.0f} ({grootste_sell['grootte']:.1f} BTC) boven/in zone")

    # Blokkerende sell wall voor long
    if richting == "LONG" and grootste_sell:
        if prijs < grootste_sell["prijs"] < prijs * 1.01:
            bewijs_delen.append(f"⚠️ Sell wall ${grootste_sell['prijs']:,.0f} direct boven entry")
            if score_punten > 0:
                score_punten -= 1

    bewijs = " | ".join(bewijs_delen) if bewijs_delen else "Geen order flow data beschikbaar"

    if score_punten >= 2:
        resultaat = RESULTAAT_GROEN
    elif score_punten <= -1:
        resultaat = RESULTAAT_ROOD
    else:
        resultaat = RESULTAAT_GEEL

    return {
        "stap": 7, "naam": "Order flow",
        "resultaat": resultaat,
        "score_punten": score_punten,
        "bewijs": bewijs,
        "veto": False,
    }


def _sessie_bonus(detection: dict) -> dict:
    """Sessiebonus: geen veto, wel context."""
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour

    if 8 <= hour < 12:
        sessie = "London"
        resultaat = RESULTAAT_GROEN
    elif 13 <= hour < 17:
        sessie = "New York"
        resultaat = RESULTAAT_GROEN
    elif 1 <= hour < 7:
        sessie = "Asia"
        resultaat = RESULTAAT_GEEL
    else:
        sessie = "Off-session"
        resultaat = RESULTAAT_GEEL

    return {
        "sessie": sessie,
        "resultaat": resultaat,
        "bewijs": f"Huidige sessie: {sessie} (UTC {hour:02d}:xx)",
    }


def evaluate(detection: dict, settings: dict) -> dict:
    """
    Doorloop alle 7 stappen en geef een volledig beslissingsrapport terug.

    Returns:
        {
          timestamp, coin, stappen, sessie, eindscore, beslissing, richting,
          geselecteerde_zone, veto_reden
        }
    """
    proximity_pct = settings["strategy"]["zone_proximity_pct"]
    coin = detection.get("coin", "?")
    timestamp = datetime.now(timezone.utc).isoformat()

    stappen = []
    veto_reden = None
    richting = None
    geselecteerde_zone = None

    # Stap 1 — Trend
    s1 = _stap_1_trend(detection)
    stappen.append(s1)
    if s1["veto"]:
        veto_reden = s1["bewijs"]
        return _build_report(timestamp, coin, stappen, None, geselecteerde_zone,
                             BESLISSING_VETO, veto_reden, 0, 7)
    richting = s1["richting"]

    # Stap 2 — Zone
    s2 = _stap_2_zone(detection, richting, proximity_pct)
    stappen.append(s2)
    geselecteerde_zone = s2.get("zone")
    if s2["resultaat"] == RESULTAAT_ROOD:
        return _build_report(timestamp, coin, stappen, richting, geselecteerde_zone,
                             BESLISSING_GEEN_TRADE, "Geen geldige zone", _score(stappen), 7)

    # Stap 3 — Imbalance
    zone_binnen_bereik = s2["resultaat"] == RESULTAAT_GROEN
    s3 = _stap_3_imbalance(detection, richting, geselecteerde_zone, zone_binnen_bereik)
    stappen.append(s3)
    if s3["veto"]:
        veto_reden = s3["bewijs"]
        return _build_report(timestamp, coin, stappen, richting, geselecteerde_zone,
                             BESLISSING_VETO, veto_reden, _score(stappen), 7)

    # Stap 4 — Liquiditeit
    s4 = _stap_4_liquiditeit(detection, richting, geselecteerde_zone)
    stappen.append(s4)
    if s4["veto"]:
        veto_reden = s4["bewijs"]
        return _build_report(timestamp, coin, stappen, richting, geselecteerde_zone,
                             BESLISSING_VETO, veto_reden, _score(stappen), 7)

    # Stap 5 — 1H bevestiging
    s5 = _stap_5_bevestiging_1h(detection, richting)
    stappen.append(s5)
    if s5["resultaat"] == RESULTAAT_ROOD:
        return _build_report(timestamp, coin, stappen, richting, geselecteerde_zone,
                             BESLISSING_GEEN_TRADE, "1H tegenstrijdig met 4H", _score(stappen), 7)

    # Stap 6 — Momentum
    s6 = _stap_6_momentum(detection, richting)
    stappen.append(s6)
    if s6["resultaat"] == RESULTAAT_ROOD:
        return _build_report(timestamp, coin, stappen, richting, geselecteerde_zone,
                             BESLISSING_GEEN_TRADE, "Momentum omgekeerd", _score(stappen), 7)

    # Stap 7 — Order flow
    s7 = _stap_7_order_flow(detection, richting, geselecteerde_zone)
    stappen.append(s7)

    # Sessie bonus
    sessie_info = _sessie_bonus(detection)

    # Eindscore
    groene_stappen = _score(stappen)
    totaal_stappen = 7

    if groene_stappen >= 7:
        beslissing = BESLISSING_ENTRY_HOOG
    elif groene_stappen >= 6:
        beslissing = BESLISSING_ENTRY_MEDIUM
    else:
        beslissing = BESLISSING_GEEN_TRADE

    return _build_report(
        timestamp, coin, stappen, richting, geselecteerde_zone,
        beslissing, veto_reden, groene_stappen, totaal_stappen,
        sessie_info=sessie_info,
    )


def _score(stappen: list[dict]) -> int:
    """Tel het aantal groene stappen (exclusief veto's en gele stappen)."""
    return sum(1 for s in stappen if s.get("resultaat") == RESULTAAT_GROEN)


def _build_report(
    timestamp: str,
    coin: str,
    stappen: list[dict],
    richting: str | None,
    zone: dict | None,
    beslissing: str,
    veto_reden: str | None,
    groene_stappen: int,
    totaal_stappen: int,
    sessie_info: dict | None = None,
) -> dict:
    is_entry = beslissing in (BESLISSING_ENTRY_HOOG, BESLISSING_ENTRY_MEDIUM)
    vertrouwen = "HOOG" if beslissing == BESLISSING_ENTRY_HOOG else ("MEDIUM" if beslissing == BESLISSING_ENTRY_MEDIUM else "GEEN")

    return {
        "timestamp": timestamp,
        "coin": coin,
        "richting": richting,
        "stappen": stappen,
        "sessie": sessie_info,
        "eindscore": f"{groene_stappen}/{totaal_stappen}",
        "groene_stappen": groene_stappen,
        "beslissing": beslissing,
        "is_entry": is_entry,
        "vertrouwen": vertrouwen,
        "geselecteerde_zone": zone,
        "veto_reden": veto_reden,
    }
