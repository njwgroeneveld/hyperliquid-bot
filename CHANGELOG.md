# Changelog

## v0.3.0 — 2026-05-07

### Tactische wijzigingen (op basis van Tactiek Paper v2 2026-05-07)

- **Wijziging 1 — Imbalance grootte-drempel**: Micro-imbalances (<0.15% van prijs, gelijk aan
  `equal_tolerance`) geven nu GEEL in plaats van hard VETO in stap 3. Grote imbalances
  (≥0.15%) blijven een harde VETO als de zone binnen bereik is. Nieuwe parameter:
  `imbalance_min_size_pct: 0.0015` in `config/settings.yaml`.
- **Wijziging 2 — Zone nabijheid 2% → 3%**: `zone_proximity_pct` verhoogd van 0.02 naar 0.03.
  HYPE op 2.3% van zone is nu bereikbaar. Enkelvoudige parameterwijziging.

### Verwacht effect

1-3 trades/week (was 0 in 8 dagen bij v0.2.0). TAO heeft meeste kans door veel micro-imbalances;
HYPE profiteert direct van de ruimere zone-drempel.

## v0.2.0 — 2026-04-29

### Tactische wijzigingen (op basis van Tactiek Paper 2026-04-26)

- **1A – 2/3 trend regel**: ZWAKKE_UPTREND/ZWAKKE_DOWNTREND worden herkend wanneer
  meerderheid van swing paren een richting bevestigt. Voorkomt CONSOLIDATIE-veto bij
  markten als SOL met duidelijke richting maar één afwijkende swing.
- **1B – BOS als trendbevestiging**: Recente Break-of-Structure op 4H in dezelfde
  richting upgradet ZWAKKE_*TREND naar volledige UPTREND/DOWNTREND.
- **2A – ZWAKKE zones zonder imbalance**: Impulse candles zonder open price gap creëren
  een ZWAKKE zone als fallback. Beslissingsboom geeft GEEL (niet ROOD) zodat BTC SHORT
  door stap 2 kan komen.
- **2B – Volume multiplier 1.5× → 1.2×**: Minder streng volume filter op 4H timeframes
  waar volume meer variabiliteit heeft. Waarde doorgegeven vanuit settings.yaml.

### Infrastructuur

- Versioned deployment flow: elke versie als eigen pod + PVC via `scripts/deploy-version.sh`
- GH Actions bouwt Docker image met versie-tag op main én dev branch
- Paperclip agent keten: Develop → Test → Review voor gevalideerde deploys

## v0.1.0 — 2026-04-26

- Initiële versie van de Hyperliquid trading bot
- Price action detectie: market structure, supply/demand zones, imbalance, liquidity sweeps, momentum
- Multi-timeframe analyse: 4H trend + 1H entry bevestiging
- Beslissingsboom met 7-stappen score systeem
- Order flow analyse via Hyperliquid API
- Sessie timing: London / New York
- Trade logging naar SQLite (database/bot.db)
- Telegram alerts
- Prometheus metrics + Grafana dashboard
- Paperclip AI Trading Bedrijf setup met 6 agents
