"""
Claude API integratie voor het genereren van Nederlandse trade argumentatie.

Elke trade krijgt een gedetailleerde redenering in het Nederlands zodat je
achteraf kunt beoordelen of de bot de markt correct heeft gelezen.
"""

import os
import json
from typing import Optional


def generate_trade_argumentation(
    detection_report: dict,
    decision_report: dict,
    trade_params: dict,
    api_key: Optional[str] = None,
) -> str:
    """
    Genereer Nederlandse trade argumentatie via Claude.

    Args:
        detection_report: volledig detectierapport van de Detector
        decision_report:  volledig beslissingsrapport van de beslissingsboom
        trade_params:     entry, stop_loss, target, richting, rr

    Returns:
        Nederlandse argumentatie als string
    """
    try:
        import anthropic
    except ImportError:
        return "[Anthropic SDK niet geïnstalleerd — pip install anthropic]"

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return "[ANTHROPIC_API_KEY niet ingesteld — geen argumentatie gegenereerd]"

    client = anthropic.Anthropic(api_key=key)

    # Bouw een beknopte samenvatting van de detectie voor de prompt
    coin = detection_report.get("coin", "?")
    prijs = detection_report.get("huidige_prijs", 0)
    richting = decision_report.get("richting", "?")
    score = decision_report.get("eindscore", "?")
    vertrouwen = decision_report.get("vertrouwen", "?")

    struct_4h = detection_report.get("structuur_4h", {})
    struct_1h = detection_report.get("structuur_1h", {})
    mom_1h = detection_report.get("momentum_1h", {})
    of = detection_report.get("order_flow", {})
    sessie = decision_report.get("sessie", {})

    stappen_tekst = "\n".join([
        f"  Stap {s['stap']} ({s['naam']}): {s['resultaat']} — {s['bewijs']}"
        for s in decision_report.get("stappen", [])
    ])

    zone = decision_report.get("geselecteerde_zone", {}) or {}

    prompt = f"""Je bent een ervaren price action trader die een trade wil uitleggen aan een junior trader.

Genereer een duidelijke, leesbare argumentatie in het Nederlands voor de volgende trade.
Wees concreet, gebruik de prijsniveaus en noem de specifieke redenen. Max 4-5 zinnen.

=== TRADE DETAILS ===
Coin: {coin}
Richting: {richting}
Entry: ${trade_params.get('entry', '?'):,.0f}
Stop-loss: ${trade_params.get('stop_loss', '?'):,.0f}
Target: ${trade_params.get('target', '?'):,.0f}
R/R: {trade_params.get('rr', '?')}R
Score: {score} | Vertrouwen: {vertrouwen}
Huidige prijs: ${prijs:,.0f}

=== MARKTSTRUCTUUR ===
4H trend: {struct_4h.get('trend', '?')} — {struct_4h.get('trend_reasoning', '')}
1H trend: {struct_1h.get('trend', '?')}

=== GESELECTEERDE ZONE ===
Type: {zone.get('type', '?')} {'demand' if richting == 'LONG' else 'supply'} zone
Bereik: ${zone.get('laag', '?'):,.0f} – ${zone.get('hoog', '?'):,.0f}
Imbalance aanwezig: {zone.get('imbalance', '?')}

=== MOMENTUM (1H) ===
Beoordeling: {mom_1h.get('impuls_beoordeling', '?')}
Verwachte richting: {mom_1h.get('verwachte_richting', '?')}

=== ORDER FLOW ===
OI: {of.get('open_interest', {}).get('interpretatie', '?')}
Funding: {of.get('funding_rate', {}).get('uitleg', '?')}

=== BESLISSINGSBOOM STAPPEN ===
{stappen_tekst}

=== SESSIE ===
{sessie.get('sessie', '?') if sessie else '?'}

Schrijf nu de Nederlandse argumentatie:"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Haiku voor snelheid en lage kosten
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        return f"[Argumentatie mislukt: {e}]"


def generate_no_trade_summary(decision_report: dict) -> str:
    """
    Eenvoudige (lokale) samenvatting waarom er GEEN trade is genomen.
    Geen API call nodig.
    """
    beslissing = decision_report.get("beslissing", "?")
    score = decision_report.get("eindscore", "?")
    veto = decision_report.get("veto_reden")

    stappen = decision_report.get("stappen", [])
    rode_stappen = [s for s in stappen if s.get("resultaat") in ("ROOD", "VETO")]
    gele_stappen = [s for s in stappen if s.get("resultaat") == "GEEL"]

    if veto:
        return f"Geen trade — hard veto: {veto}"

    redenen = []
    for s in rode_stappen:
        redenen.append(f"Stap {s['stap']} ({s['naam']}): {s['bewijs']}")
    for s in gele_stappen:
        redenen.append(f"Stap {s['stap']} ({s['naam']}): {s['bewijs']} [geel]")

    if redenen:
        return f"Geen trade (score {score}): " + " | ".join(redenen[:3])
    return f"Geen trade — score {score} onvoldoende"
