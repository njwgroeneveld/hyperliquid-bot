# Hyperliquid Trading Bot — Volledige Blauwdruk

## Inhoudsopgave
1. [Projectoverzicht](#1-projectoverzicht)
2. [Strategie](#2-strategie)
3. [Architectuur](#3-architectuur)
4. [Detectielaag](#4-detectielaag)
5. [Beslissingsboom](#5-beslissingsboom)
6. [Order Flow Analyse](#6-order-flow-analyse)
7. [Risk Management](#7-risk-management)
8. [Trade Logging & Argumentatie](#8-trade-logging--argumentatie)
9. [Monitoring & Alerts](#9-monitoring--alerts)
10. [Testprotocol](#10-testprotocol)
11. [Mappenstructuur](#11-mappenstructuur)
12. [Technische Stack](#12-technische-stack)
13. [Fasering](#13-fasering)

---

## 1. Projectoverzicht

Een autonome trading bot die op Hyperliquid perpetuals handelt op basis van:
- Price action analyse (gebaseerd op bootcamp Ep. 1-12)
- Multi-timeframe analyse (4H trend + 1H bevestiging)
- Order flow data via Hyperliquid API
- Sessie timing (London/NY)

Elke analyse, detectie en trade wordt volledig gelogd met argumentatie zodat de
kwaliteit van detectie en beslissingen onafhankelijk beoordeeld kan worden.

### Kernprincipes
- Geen indicators — alleen raw price action
- Narrative-based trading: verhaal lezen achter candles
- Detectie verifieerbaar vóór trade uitvoering
- Volledige audit trail per trade

---

## 2. Strategie

### Gebaseerd op bootcamp concepten (Ep. 1-12)

| Concept | Episoade | Toepassing in bot |
|---|---|---|
| Price Action / Candlesticks | Ep. 1 | Candle body vs wick analyse |
| Market Structure | Ep. 2 | HH/HL/LL/LH detectie, BOS |
| Supply & Demand | Ep. 3 | Zone identificatie, extreme zones |
| Imbalance | Ep. 4 | Open price ranges, entry filter |
| Efficient Ranges | Ep. 5 | Doorbroken zones, doorloop richting |
| Equal High/Low Liquidity | Ep. 6 | Sweep detectie, magnet targets |
| Trend Liquidity | Ep. 7 | Trend line sweeps herkennen |
| Candle Momentum | Ep. 8 | Body/wick ratio analyse |
| Multi-Candle Momentum | Ep. 9 | Snelheid, grootte, vloeiendheid |
| Timeframes | Ep. 10 | 4H context + 1H entry |
| Sessies | Ep. 11 | London/NY timing |
| Narratief lezen | Ep. 12 | "If this then that" logica |

### Marktrichtingen

```
4H: Higher Highs + Higher Lows  → UPTREND  → alleen LONG
4H: Lower Lows + Lower Highs    → DOWNTREND → alleen SHORT
4H: Onduidelijk/chaotisch       → CONSOLIDATIE → niets doen
```

### Coins

```
Start:    BTC, ETH, SOL
Criteria: dagelijks volume >$50M op Hyperliquid
          duidelijke trending structuur
          voldoende liquiditeit (lage slippage)
Later:    uitbreiden op basis van bewezen resultaten
```

### Timeframe logica

```
4H chart → RICHTING bepalen (macro trend, zones)
1H chart → ENTRY bevestigen (micro structuur, timing)

4H data update: elke 4 uur
1H data update: elk uur
Beslissingsboom draait: elk uur bij 1H candle close
```

### Trade duur

```
Gemiddeld:  4 - 16 uur
Snel:       1 - 3 uur (sweep-gebaseerde trades)
Traag:      12 - 24 uur (zone-gebaseerde trades)
Maximum:    24 uur → daarna forceer sluiting
```

---

## 3. Architectuur

### Twee onafhankelijke loops

```
┌─────────────────────────────────────────────┐
│  LOOP 1 — Analyseloop (elk uur)             │
│                                             │
│  Bij elke 1H candle close:                  │
│  1. Haal nieuwe marktdata op                │
│  2. Update detectielaag                     │
│  3. Genereer detectierapport                │
│  4. Doorloop beslissingsboom                │
│  5. Genereer beslissingsrapport             │
│  6. Indien entry → trade plaatsen           │
│  7. Sla alles op in database                │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  LOOP 2 — Positiebeheer (elke 30 seconden) │
│                                             │
│  Voor elke open positie:                    │
│  1. Check stop-loss geraakt?                │
│  2. Check target bereikt?                   │
│  3. Check positie >24 uur open?             │
│  4. Check dagelijks verliesplafond?         │
│  5. Stuur alert indien nodig                │
└─────────────────────────────────────────────┘
```

### Dataflow

```
Hyperliquid API
      │
      ├── OHLCV candles (1H + 4H)
      ├── L2 orderbook
      ├── Open interest
      ├── Funding rates
      └── Liquidatiedata
            │
            ▼
      Detectielaag
      (structuur, zones, imbalance, liquiditeit, momentum, orderflow)
            │
            ▼
      Beslissingsboom
      (7 stappen, score X/7)
            │
            ├── Geen entry → detectierapport opslaan
            └── Entry → trade plaatsen + volledige log opslaan
                              │
                              ▼
                    Claude API
                    (genereert Nederlandse argumentatie)
                              │
                              ▼
                    Database + Alert
```

---

## 4. Detectielaag

De detectielaag draait elk uur en bepaalt wat de bot "ziet" in de markt.
Dit is volledig los van de handelsbeslissing — ook als er geen trade is,
wordt het detectierapport opgeslagen zodat detectiekwaliteit gecontroleerd
kan worden.

### 4.1 Marktstructuur detectie

**Swing High / Swing Low identificatie:**
```
- Alleen candle body closures tellen (geen wicks)
- Swing High: candle body close hoger dan N candles links en rechts
- Swing Low:  candle body close lager dan N candles links en rechts
- N = 3 (instelbaar)
```

**Trendrichting:**
```
Uptrend:      elke HH hoger dan vorige HH
              elke HL hoger dan vorige HL
Downtrend:    elke LL lager dan vorige LL
              elke LH lager dan vorige LH
Consolidatie: HH gevolgd door LL (chaotisch)
```

**Break of Structure (BOS):**
```
Bullish BOS: candle body sluit boven vorige swing high
Bearish BOS: candle body sluit onder vorige swing low
```

**Output detectierapport (structuur):**
```
{
  "timeframe": "4H",
  "trend": "UPTREND",
  "laatste_HH": {"prijs": 95100, "tijd": "2025-04-23 06:00"},
  "laatste_HL": {"prijs": 92800, "tijd": "2025-04-22 18:00"},
  "laatste_BOS": {"prijs": 94200, "tijd": "2025-04-23 02:00", "richting": "bullish"}
}
```

### 4.2 Supply & Demand zone detectie

**Demand zone identificatie:**
```
1. Zoek impulsieve bullish beweging (grote candle body, weinig wick)
2. Imbalance gevormd? (open price gap tussen wicks)
3. Laatste candle VOOR de impuls = demand zone
4. Zone range: open tot close van die candle (+ eventuele wick eronder)
```

**Supply zone identificatie:**
```
1. Zoek impulsieve bearish beweging
2. Imbalance gevormd?
3. Laatste candle VOOR de impuls = supply zone
4. Zone range: open tot close van die candle (+ eventuele wick erboven)
```

**Zone classificatie:**
```
Extreme zone: verste zone van huidige prijs in huidige leg
Midden zone:  dichter bij huidige prijs
Gevuld:       zone al eerder geraakt → niet meer geldig
```

**Output detectierapport (zones):**
```
{
  "demand_zones": [
    {
      "id": "DZ-001",
      "timeframe": "4H",
      "laag": 92600,
      "hoog": 93000,
      "type": "EXTREME",
      "imbalance": true,
      "geraakt": false,
      "gevormd_op": "2025-04-21 12:00"
    }
  ],
  "supply_zones": [...]
}
```

### 4.3 Imbalance detectie

**Identificatie:**
```
Imbalance bestaat als:
  wick_hoog van candle N < wick_laag van candle N+2
  (er is een open price gap tussen twee candles)

Gevuld als:
  een latere candle heeft wick of body die de gap overbrugt
```

**Output detectierapport (imbalances):**
```
{
  "imbalances": [
    {
      "id": "IMB-001",
      "laag": 93000,
      "hoog": 93800,
      "richting": "bullish",
      "status": "OPEN",
      "gevormd_op": "2025-04-22 08:00",
      "gevuld_op": null
    }
  ]
}
```

### 4.4 Liquiditeitsdetectie

**Equal Highs / Equal Lows:**
```
Equal High: 2+ swing highs binnen 0.15% van elkaar
Equal Low:  2+ swing lows binnen 0.15% van elkaar
Tolerance:  0.15% (instelbaar)

Sweep detectie:
  Prijs heeft wick boven equal high → gesweept
  Candle body sluit eronder → confirmed sweep
```

**Output detectierapport (liquiditeit):**
```
{
  "equal_highs": [
    {
      "prijs": 94800,
      "touches": 3,
      "eerste_touch": "2025-04-22 14:00",
      "laatste_touch": "2025-04-23 07:00",
      "gesweept": false
    }
  ],
  "equal_lows": [
    {
      "prijs": 92850,
      "touches": 2,
      "gesweept": true,
      "sweep_tijd": "2025-04-23 06:45"
    }
  ]
}
```

### 4.5 Momentum detectie

**Individuele candle beoordeling:**
```
Hoog momentum:   body > 60% van totale candle range, wicks < 20%
Laag momentum:   body < 30% van totale candle range
Indecisie:       gelijke wicks boven en onder, kleine body
Reversal wick:   wick > 2x body grootte
```

**Multi-candle momentum (laatste 6 candles):**
```
Snelheid:     hoeveel % bewogen per uur
Grootte:      gemiddelde body grootte
Vloeiendheid: aantal tegengestelde candles in beweging
Pushback:     hoe groot zijn de correcties binnen de beweging

Score:
  STERK:   grote bodies, weinig wicks, weinig pushback, snel
  MEDIUM:  gemengd beeld
  ZWAK:    kleine bodies, veel wicks, veel pushback, traag
```

**Output detectierapport (momentum):**
```
{
  "laatste_6_candles": {
    "bullish_count": 2,
    "bearish_count": 4,
    "gem_body_pct": 0.35,
    "grote_wicks": true,
    "pushback_aanwezig": true
  },
  "impuls_beoordeling": "ZWAKKE CORRECTIE",
  "verwachte_richting": "BULLISH CONTINUATIE"
}
```

---

## 5. Beslissingsboom

De beslissingsboom doorloopt 7 stappen. Elke stap heeft een resultaat
(groen/rood/wacht) en een reden. Entry alleen bij 6/7 of 7/7 groen.

```
┌─────────────────────────────────────────────────────────────┐
│ STAP 1 — Trendrichting (4H)                                 │
│                                                             │
│ Check: Is er een duidelijke trend?                          │
│ ✅ UPTREND   → ga door, alleen LONG setups                  │
│ ✅ DOWNTREND → ga door, alleen SHORT setups                 │
│ ❌ CONSOLIDATIE → stop, geen trade                          │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ STAP 2 — Supply/Demand zone (4H + 1H)                       │
│                                                             │
│ Check: Is er een extreme zone in trenddrichting?            │
│ ✅ Zone gevonden + prijs nadert (<2% afstand)               │
│ ⏳ Zone gevonden maar prijs nog ver weg → wachten           │
│ ❌ Geen geldige zone → stop, geen trade                     │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ STAP 3 — Imbalance check                                    │
│                                                             │
│ Check: Is de imbalance naar de zone volledig gevuld?        │
│ ✅ Geen open imbalance boven entry (voor long)              │
│ ⏳ Imbalance nog open → wachten tot gevuld                  │
│ ❌ Imbalance in tegengestelde richting → stop               │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ STAP 4 — Liquiditeitsfilter                                 │
│                                                             │
│ Check: Blokkeren equal highs/lows de entry?                 │
│ ✅ Equal lows gesweept (voor long), geen highs erboven      │
│ ⚠️  Equal highs direct boven entry → punt aftrek            │
│ ❌ Equal highs NIET gesweept, entry eronder → stop          │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ STAP 5 — 1H bevestiging                                     │
│                                                             │
│ Check: Bevestigt 1H structuur de 4H richting?               │
│ ✅ 1H structuurshift zichtbaar (van bearish naar bullish)   │
│ ⚠️  1H nog neutraal → punt aftrek                           │
│ ❌ 1H tegenstrijdig met 4H → stop                           │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ STAP 6 — Momentum bevestiging                               │
│                                                             │
│ Check: Bevestigt momentum de trenddrichting?                │
│ ✅ Impuls sterk, correctie zwak en choppy                   │
│ ⚠️  Neutraal momentum → punt aftrek                         │
│ ❌ Momentum omgekeerd (sterke correctie) → stop             │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ STAP 7 — Order flow                                         │
│                                                             │
│ Check: Bevestigt order flow de trenddrichting?              │
│ ✅ Buy wall onder entry + liquidatiecluster shorts          │
│ ⚠️  Neutraal order book → punt aftrek                       │
│ ❌ Grote sell wall direct boven entry → stop                │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ SESSIE CHECK (bonus, geen veto)                             │
│                                                             │
│ ✅ London open (08:00 UTC) of NY open (13:00 UTC)           │
│ ⚠️  Buiten sessies → lagere kwaliteit, maar niet verboden  │
└─────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ EINDSCORE & BESLISSING                                      │
│                                                             │
│ 7/7 groen → ENTRY (hoog vertrouwen)                        │
│ 6/7 groen → ENTRY (medium vertrouwen)                      │
│ 5/7 groen → GEEN ENTRY, log wel op                         │
│ <5 groen  → GEEN ENTRY                                     │
│                                                             │
│ Hard veto's (altijd stop, ongeacht score):                  │
│ - Geen duidelijke trend                                     │
│ - Imbalance nog open                                        │
│ - Equal highs niet gesweept bij long                        │
└─────────────────────────────────────────────────────────────┘
```

### Entry parameters

```
Entry prijs:  midden van supply/demand zone
Stop-loss:    net buiten de zone (0.1% buffer)
Target:       volgende imbalance of liquiditeitszone
Risk/Reward:  minimum 2R (als dit niet haalbaar is → geen trade)
Leverage:     2x (paper trading fase: instelbaar)
```

---

## 6. Order Flow Analyse

### 6.1 Order Book (L2)

**Wat we zoeken:**
```
Order walls:   prijsniveaus met >200 BTC (of equivalent) aan orders
               dit zijn magneetpunten voor prijs

Buy walls:     grote concentraties buy orders onder huidige prijs
               → potentiële steun / target voor shorts

Sell walls:    grote concentraties sell orders boven huidige prijs
               → potentiële weerstand / target voor longs
```

**Hoe berekend:**
```python
# Aggregeer orderbook per prijsniveau (in buckets van 0.1%)
# Grootste buckets = order walls
# Top 5 boven en onder huidige prijs rapporteren
```

### 6.2 Liquidatieniveaus

**Wat we zoeken:**
```
Open posities met leverage → berekende liquidatieprijs
Clusters van liquidatieprijzen op één niveau → "liquidatiecluster"

Als prijs een cluster nadert:
  → cascade van gedwongen sluitingen verwacht
  → grote prijsbeweging in die richting
  → aantrekkelijk als target
```

### 6.3 Open Interest

```
Stijgend OI bij stijgende prijs  → echte vraag, uptrend bevestigd
Stijgend OI bij dalende prijs    → shorts accumuleren, squeeze mogelijk
Dalend OI bij stijgende prijs    → short squeeze (voorzichtig)
Dalend OI bij dalende prijs      → long liquidaties
```

### 6.4 Funding Rate

```
Positief (>0.03%):  veel longs → duur om long te zijn
Negatief (<-0.01%): veel shorts → squeeze risico
Neutraal (±0.01%):  gebalanceerde markt
```

**Output detectierapport (order flow):**
```
{
  "order_book": {
    "grootste_buy_wall": {"prijs": 92800, "grootte_btc": 420},
    "grootste_sell_wall": {"prijs": 95500, "grootte_btc": 380},
    "top_5_buy_walls": [...],
    "top_5_sell_walls": [...]
  },
  "liquidatie_clusters": [
    {"prijs": 92400, "type": "shorts", "geschatte_grootte": "groot"}
  ],
  "open_interest": {
    "waarde": 1250000000,
    "trend": "STIJGEND",
    "richting_prijs": "DALEND",
    "interpretatie": "SHORTS ACCUMULEREN"
  },
  "funding_rate": {
    "huidig": -0.0017,
    "interpretatie": "NEGATIEF - veel shorts"
  }
}
```

---

## 7. Risk Management

### Parameters per fase

| Parameter | Paper trading | Micro live (€100) | Live (schalen) |
|---|---|---|---|
| Max leverage | 2x | 2x | 2x → later meer |
| Max positie | 5% portfolio | 5% portfolio | 5% portfolio |
| Max open posities | 5-8 | 3 | 3 |
| Dagelijks verliesplafond | Alert bij -10% | -10% → stop | -5% → stop |
| Wekelijks verliesplafond | Alert bij -25% | -25% → stop | -15% → stop |
| Pauze bij verliesreeks | Uitgeschakeld | 5 op rij → 24u | 5 op rij → 24u |
| Max positieduur | 24 uur | 24 uur | 24 uur |

### Stop-loss logica

```
Stop-loss plaatsing:
  Long:  0.1% onder de demand zone
  Short: 0.1% boven de supply zone

Nooit stop-loss in een imbalance plaatsen
Nooit stop-loss aanpassen na entry (behalve naar breakeven na 1R winst)
```

### Positiegrootte berekening

```python
risico_per_trade = portfolio_waarde * 0.01  # 1% risico per trade
afstand_stop = abs(entry_prijs - stop_prijs) / entry_prijs
positiegrootte = risico_per_trade / afstand_stop
```

---

## 8. Trade Logging & Argumentatie

### 8.1 Detectierapport (elk uur, altijd)

Wordt opgeslagen ongeacht of er een trade is. Doel: detectiekwaliteit
achteraf verifiëren door te vergelijken met de echte chart.

```json
{
  "timestamp": "2025-04-23T09:00:00Z",
  "coin": "BTC",
  "prijs": 93500,
  "structuur_4h": { ... },
  "structuur_1h": { ... },
  "supply_zones": [ ... ],
  "demand_zones": [ ... ],
  "imbalances": [ ... ],
  "liquiditeit": { ... },
  "momentum": { ... },
  "order_flow": { ... }
}
```

### 8.2 Beslissingsrapport (elk uur, altijd)

```json
{
  "timestamp": "2025-04-23T09:00:00Z",
  "coin": "BTC",
  "stappen": [
    {
      "stap": 1,
      "naam": "Trendrichting",
      "resultaat": "GROEN",
      "waarde": "UPTREND",
      "bewijs": "HH $95100 > vorige HH $93800, HL $92800 > vorige HL $91200"
    },
    {
      "stap": 2,
      "naam": "Supply/Demand zone",
      "resultaat": "GROEN",
      "waarde": "Demand zone $92600-$93000 gevonden",
      "bewijs": "Extreme zone, imbalance aanwezig, 1.6% van huidige prijs"
    },
    {
      "stap": 3,
      "naam": "Imbalance check",
      "resultaat": "WACHT",
      "waarde": "IMB-001 nog open ($93000-$93800)",
      "bewijs": "Wicks raken niet — open gap aanwezig"
    }
  ],
  "eindscore": "4/7",
  "beslissing": "GEEN TRADE",
  "reden": "Imbalance nog open + 1H bevestiging ontbreekt"
}
```

### 8.3 Trade log (alleen bij trade)

```json
{
  "trade_id": "BTC-2025-04-23-001",
  "timestamp_open": "2025-04-23T10:00:00Z",
  "coin": "BTC",
  "richting": "LONG",
  "entry": 92950,
  "stop_loss": 92700,
  "target": 95500,
  "leverage": 2,
  "positiegrootte_usd": 500,
  "risico_usd": 12.5,
  "verwacht_reward_usd": 125,
  "risk_reward": "10R",
  "vertrouwen": "HOOG",
  "score": "6/7",
  "detectie_snapshot": { ... },
  "beslissing_snapshot": { ... },
  "claude_argumentatie": "De 4H uptrend is intact met een bevestigde hogere low op $92.800. De extreme demand zone op $92.600-$93.000 heeft imbalance en is nog niet eerder geraakt. Equal lows op $92.850 zijn gesweept om 06:45, wat aangeeft dat de sell-side liquiditeit geconsumeerd is. De 1H structuur heeft om 09:00 een shift naar boven getoond met een hogere high. Momentum toont zwakke bearish correctie met grote wicks naar beneden, wat duidt op kopersdruk. De buy wall van 420 BTC op $92.800 bevestigt institutionele interesse. London open om 08:00 heeft extra volume gebracht. De enige zwakte is het lichte totaalvolume, maar alle andere factoren wijzen op een sterk long setup.",
  "sessie": "London",
  "timestamp_close": null,
  "close_prijs": null,
  "resultaat_usd": null,
  "resultaat_r": null,
  "close_reden": null
}
```

---

## 9. Monitoring & Alerts

### Telegram alerts

```
Bij elke trade open:
  🟢 LONG BTC @ $92.950
  SL: $92.700 | Target: $95.500
  Score: 6/7 | Sessie: London
  Vertrouwen: HOOG

Bij trade close:
  ✅ LONG BTC gesloten @ $95.400
  Resultaat: +$123 (+9.8R)
  Reden: Target bereikt

Bij stop-loss:
  🔴 LONG BTC gestopt @ $92.680
  Verlies: -$12.50 (-1R)

Bij dagelijks verliesplafond (paper: -10%):
  ⚠️  ALERT: Dagelijks verlies -10% bereikt
  Bot gecontinueerd (paper fase) — review aanbevolen

Bij slechte detectie (handmatig te triggeren):
  📊 Detectierapport beschikbaar voor review
```

### Wekelijkse review metrics

```
Per coin:
  - Win rate (%)
  - Gemiddeld R per trade
  - Meest voorkomende verliesreden

Per check:
  - Hoe vaak was stap X groen bij winnende trades?
  - Hoe vaak was stap X groen bij verliezende trades?
  - Welke combinatie van checks voorspelt het best?

Detectiekwaliteit:
  - Waren supply/demand zones correct geplaatst?
  - Werden imbalances correct geïdentificeerd?
  - Klopten de liquiditeitssweeps?
```

---

## 10. Testprotocol

### Fase 1 — Backtesting (voor live gaan)

```
Doel:         valideer strategie op historische data
Periode:      minimaal 6 maanden
Data:         Hyperliquid historische OHLCV + orderbook snapshots
Verwachting:  win rate >50%, gemiddeld R >1.5
```

### Fase 2 — Paper trading (4 weken)

```
Doel:         valideer detectie en beslissingen in real-time
Instellingen: geen harde stops, alles loggen
              5-8 posities tegelijk
              dagelijks alert bij -10%

Review na fase 2:
  Zijn de gedetecteerde zones correct? (vergelijk met chart)
  Is de beslissingsboom consistent?
  Wat is de win rate?
  Zijn er patronen in de verliezende trades?
```

### Fase 3 — Micro live (€100 totaal, 2-4 weken)

```
Doel:         test met echt geld, minimaal risico
Instellingen: max positie €20, dagelijks -10% stop
              max 3 posities tegelijk
```

### Fase 4 — Schalen

```
Doel:         vergroot kapitaal stap voor stap
Voorwaarden:  fase 3 winstgevend afgerond
              win rate >50% over 40+ trades
              detectie kwaliteit bewezen
```

---

## 11. Mappenstructuur

```
hyperliquid-bot/
│
├── BLUEPRINT.md                    ← dit document
│
├── config/
│   ├── settings.yaml               ← alle instelbare parameters
│   └── coins.yaml                  ← welke coins actief
│
├── src/
│   ├── main.py                     ← startpunt, start beide loops
│   │
│   ├── data/
│   │   ├── hyperliquid_client.py   ← API communicatie
│   │   ├── candle_fetcher.py       ← OHLCV data ophalen
│   │   └── orderbook_fetcher.py    ← L2 orderbook ophalen
│   │
│   ├── detection/
│   │   ├── market_structure.py     ← HH/HL/LL/LH + BOS detectie
│   │   ├── supply_demand.py        ← zone identificatie
│   │   ├── imbalance.py            ← imbalance detectie
│   │   ├── liquidity.py            ← equal highs/lows + sweeps
│   │   ├── momentum.py             ← candle + multi-candle momentum
│   │   ├── order_flow.py           ← order walls, OI, funding
│   │   └── detector.py             ← combineert alle detecties
│   │
│   ├── decision/
│   │   ├── decision_tree.py        ← 7-stappen beslissingsboom
│   │   ├── entry_calculator.py     ← entry/stop/target berekening
│   │   └── position_sizer.py       ← positiegrootte berekening
│   │
│   ├── execution/
│   │   ├── trade_executor.py       ← orders plaatsen op Hyperliquid
│   │   └── position_manager.py     ← open posities beheren (loop 2)
│   │
│   ├── logging/
│   │   ├── detection_logger.py     ← detectierapporten opslaan
│   │   ├── decision_logger.py      ← beslissingsrapporten opslaan
│   │   ├── trade_logger.py         ← trade logs opslaan
│   │   └── database.py             ← SQLite database interface
│   │
│   ├── ai/
│   │   └── argumentation.py        ← Claude API voor trade redenering
│   │
│   └── alerts/
│       └── telegram_alert.py       ← Telegram notificaties
│
├── logs/
│   ├── detection/                  ← JSON detectierapporten per uur
│   ├── decisions/                  ← JSON beslissingsrapporten per uur
│   └── trades/                     ← JSON trade logs
│
├── database/
│   └── bot.db                      ← SQLite database
│
└── tests/
    ├── test_market_structure.py
    ├── test_supply_demand.py
    ├── test_imbalance.py
    └── test_decision_tree.py
```

---

## 12. Technische Stack

| Component | Technologie | Reden |
|---|---|---|
| Taal | Python 3.11+ | Bekend, grote ecosysteem |
| Hyperliquid data | hyperliquid-python-sdk | Officiële SDK |
| Data verwerking | pandas, numpy | Candle analyse |
| Database | SQLite | Simpel, lokaal, geen server nodig |
| AI argumentatie | Anthropic Python SDK (Claude) | Natuurlijke trade redenering |
| Alerts | python-telegram-bot | Eenvoudige notificaties |
| Configuratie | PyYAML | Leesbare instellingen |
| Scheduling | APScheduler | Loop timing beheren |
| Testing | pytest | Unit tests per detectiemodule |

---

## 13. Fasering

### Fase A — Detectielaag bouwen (eerst)

```
Doel: bot kan markten lezen en detectierapporten genereren
Geen trades, geen API keys nodig voor papier fase

Deliverables:
  ✅ market_structure.py werkt correct
  ✅ supply_demand.py identificeert zones
  ✅ imbalance.py detecteert open gaps
  ✅ liquidity.py vindt equal highs/lows
  ✅ momentum.py beoordeelt candles
  ✅ Detectierapport wordt elk uur gegenereerd
  ✅ Detectie handmatig verifieerbaar tegen echte chart
```

### Fase B — Beslissingsboom bouwen

```
Doel: bot kan op basis van detectie beslissingen nemen

Deliverables:
  ✅ decision_tree.py doorloopt alle 7 stappen
  ✅ Beslissingsrapport wordt gegenereerd
  ✅ Claude argumentatie werkt
  ✅ Geen trades nog — alleen logging
```

### Fase C — Paper trading koppelen

```
Doel: bot simuleert trades zonder echt geld

Deliverables:
  ✅ Virtuele trades worden bijgehouden
  ✅ Stop-loss en target worden gesimuleerd
  ✅ Trade logs compleet
  ✅ Telegram alerts werken
  ✅ 4 weken paper trading draaien
```

### Fase D — Live koppeling

```
Doel: echte orders op Hyperliquid

Deliverables:
  ✅ Hyperliquid API keys geconfigureerd
  ✅ trade_executor.py plaatst echte orders
  ✅ position_manager.py beheert open posities
  ✅ Risk management actief
  ✅ Start met €100
```

---

*Blauwdruk versie 1.0 — April 2025*
*Gebaseerd op Price Action Bootcamp Ep. 1-12 + Hyperliquid order flow data*
