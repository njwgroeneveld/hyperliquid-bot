"""
Positiegrootte berekening.

Formule:
  risico_per_trade = portfolio_waarde * risk_pct (standaard 1%)
  afstand_stop     = abs(entry - stop_loss) / entry
  positiegrootte   = risico_per_trade / afstand_stop

Leverage verlaagt de benodigde margin maar verhoogt de positie.
"""


def calculate(
    portfolio_usd: float,
    entry: float,
    stop_loss: float,
    risk_pct: float = 0.01,
    leverage: int = 2,
) -> dict:
    """
    Bereken positiegrootte in USD en aantal coins.

    Args:
        portfolio_usd: totale portfoliowaarde in USD
        entry:         entry prijs
        stop_loss:     stop-loss prijs
        risk_pct:      fractie van portfolio dat je bereid bent te verliezen (standaard 1%)
        leverage:      hefboom (standaard 2x)

    Returns dict met:
        risico_usd, positiegrootte_usd, margin_usd, coins, leveraged_exposure
    """
    if entry <= 0 or stop_loss <= 0 or portfolio_usd <= 0:
        return {"error": "Ongeldige invoer — prijs of portfolio is 0"}

    risico_usd = portfolio_usd * risk_pct
    afstand_stop = abs(entry - stop_loss) / entry

    if afstand_stop == 0:
        return {"error": "Entry en stop-loss zijn gelijk"}

    # Positiegrootte zonder leverage
    positie_usd = risico_usd / afstand_stop

    # Met leverage: we hoeven minder margin in te zetten
    margin_usd = positie_usd / leverage
    leveraged_exposure = positie_usd

    # Aantal coins
    coins = positie_usd / entry

    # Verwacht verlies en winst bij target (indien bekend)
    verlies_usd = risico_usd  # altijd 1R

    return {
        "portfolio_usd": round(portfolio_usd, 2),
        "risk_pct": risk_pct,
        "risico_usd": round(risico_usd, 2),
        "afstand_stop_pct": round(afstand_stop * 100, 3),
        "positiegrootte_usd": round(positie_usd, 2),
        "margin_usd": round(margin_usd, 2),
        "leveraged_exposure_usd": round(leveraged_exposure, 2),
        "leverage": leverage,
        "coins": round(coins, 6),
        "max_verlies_usd": round(verlies_usd, 2),
    }


def validate_position(position: dict, max_position_pct: float = 0.05, portfolio_usd: float = 1000) -> dict:
    """
    Controleer of de positie binnen de risicolimieten valt.
    max_position_pct: maximale positiegrootte als % van portfolio (standaard 5%)
    """
    max_positie = portfolio_usd * max_position_pct
    positie = position.get("positiegrootte_usd", 0)

    if positie > max_positie:
        return {
            "geldig": False,
            "reden": f"Positie ${positie:,.0f} overschrijdt maximum ${max_positie:,.0f} ({max_position_pct*100:.0f}% van portfolio)",
            "gecorrigeerde_positie": round(max_positie, 2),
        }

    return {"geldig": True, "reden": "Positie binnen limieten"}
