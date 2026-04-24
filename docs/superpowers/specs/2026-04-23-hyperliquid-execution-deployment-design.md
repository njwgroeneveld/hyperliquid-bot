# Design: Hyperliquid Testnet Execution + K8s Deployment

**Datum:** 2026-04-23
**Fase:** C (positiebeheer) + D (live testnet execution) + deployment

---

## 1. Doel

De bot kan nu markten lezen (Fase A) en beslissingen nemen (Fase B). Dit design voegt toe:

1. **Echte orders plaatsen** op Hyperliquid testnet via de SDK
2. **Open posities bewaken** en automatisch sluiten bij SL/target/timeout
3. **Prometheus metrics** exposen voor monitoring via bestaande Grafana stack
4. **Telegram alerts** bij trade events
5. **Lokaal testen** zonder Docker, daarna via bestaande CI/CD pipeline naar K8s

---

## 2. Architectuur

### Twee loops, één proces

```
python -m src.main
│
├── Thread 1 — Analyseloop (elk uur, bij :00)
│   detectie → beslissing → entry berekening → order plaatsen
│
├── Thread 2 — Positiebeheer loop (elke 30 seconden)
│   open posities checken → SL/target/timeout → sluiten
│
└── Thread 3 — Metrics HTTP server (altijd aan, poort 8080)
    GET /metrics → Prometheus scraping
```

### Omgevingen

| Omgeving | Config | Storage | Secrets |
|---|---|---|---|
| Lokaal | `.env` bestand | `./logs/` + `./database/` | `.env` |
| K8s | ConfigMap | PersistentVolumeClaim | K8s Secret |

De code maakt geen onderscheid — alles via environment variables en instelbare paden.
SQLite thread safety: elke thread opent een eigen connectie (`connect()` per call).
SQLite WAL-mode zorgt dat gelijktijdige reads/writes vanuit meerdere threads werken.

### K8s resources

```
Deployment (replicas: 1)
  └── Pod: hyperliquid-bot
        ├── mount: /data → PersistentVolumeClaim
        └── envFrom: Secret (private key, API keys)

ConfigMap → settings.yaml, coins.yaml
PersistentVolumeClaim → /data/bot.db + /data/logs/
ServiceMonitor → Prometheus scrapt :8080/metrics elke 30s
```

---

## 3. Nieuwe modules

### `src/execution/trade_executor.py`

Plaatst limit orders op Hyperliquid via `hyperliquid-python-sdk`.

- Authenticatie via EVM private key (uit environment variable)
- Testnet/mainnet URL instelbaar via `HYPERLIQUID_TESTNET=true`
- Plaatst limit order op `entry` prijs uit de entry calculator
- Geeft terug: order ID, bevestigingstijd, status
- Meet `bot_order_placement_latency_seconds` (Histogram)

### `src/execution/position_manager.py`

Loop 2 — draait elke 30 seconden.

Voor elke open positie:
1. Haal huidige mark price op via API
2. Stop-loss geraakt? → sluit positie, log resultaat
3. Target bereikt? → sluit positie, log resultaat
4. Positie ouder dan 24 uur? → forceer sluiting
5. Update `bot_open_positions` en `bot_pnl_usd` metrics

### `src/metrics/prometheus_metrics.py`

Centrale registry voor alle Prometheus metrics. Alle andere modules importeren
hier hun metrics objecten. Start HTTP server op poort 8080.

Automatisch via `prometheus_client`:
- `process_cpu_seconds_total`
- `process_resident_memory_bytes`
- `process_open_fds`
- `python_gc_collections_total`

### `src/alerts/telegram_alert.py`

Stuurt berichten via Telegram Bot API.

Events:
- Trade geopend (richting, entry, SL, target, score, sessie)
- Trade gesloten (resultaat in USD en R)
- Stop-loss geraakt
- Dagelijks verliesalert
- Bot-fout (3+ opeenvolgende errors)

### `.env.example`

```env
# Hyperliquid
HYPERLIQUID_PRIVATE_KEY=0x...
HYPERLIQUID_TESTNET=true

# Anthropic (optioneel — voor trade argumentatie)
ANTHROPIC_API_KEY=sk-ant-...

# Telegram (optioneel)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Paden (optioneel — defaults werken lokaal)
LOG_DIR=logs
DATABASE_PATH=database/bot.db
METRICS_PORT=8080
```

---

## 4. Data persistentie

Alle data die de bot schrijft:

| Pad | Inhoud | Kritiek |
|---|---|---|
| `database/bot.db` | SQLite: trades, detections, decisions | Ja |
| `logs/trades/*.json` | Trade log per trade | Ja |
| `logs/detection/*.json` | Detectierapport per coin per uur | Nee |
| `logs/decisions/*.json` | Beslissingsrapport per coin per uur | Nee |
| `logs/bot.log` | Applicatie log | Nee |

In K8s: alles gemount op `/data/` via PVC. PVC overleeft pod crashes en restarts.

---

## 5. Prometheus metrics

### Trading metrics

| Metric | Type | Labels |
|---|---|---|
| `bot_analysis_runs_total` | Counter | `coin` |
| `bot_decision_score` | Gauge | `coin` |
| `bot_step_result_total` | Counter | `coin`, `step`, `result` |
| `bot_open_positions` | Gauge | `coin`, `direction` |
| `bot_trades_total` | Counter | `coin`, `direction`, `outcome` |
| `bot_pnl_usd` | Gauge | `coin` |
| `bot_win_rate` | Gauge | `coin` |
| `bot_funding_rate` | Gauge | `coin` |
| `bot_trend_status` | Gauge | `coin` (1=up, -1=down, 0=consolidatie) |
| `bot_zones_found` | Gauge | `coin`, `type` (demand/supply) |

### Performance & reliability metrics (RED/USE/Golden Signals)

| Metric | Type | Labels |
|---|---|---|
| `bot_api_latency_seconds` | Histogram | `endpoint` |
| `bot_loop_duration_seconds` | Histogram | `loop` (analysis/position) |
| `bot_order_placement_latency_seconds` | Histogram | `coin` |
| `bot_market_data_age_seconds` | Gauge | `coin`, `timeframe` |
| `bot_loop_schedule_jitter_seconds` | Gauge | `loop` |
| `bot_errors_total` | Counter | `type` (api_error/parse_error/order_failed) |
| `bot_consecutive_errors` | Gauge | — |
| `bot_last_successful_run_timestamp` | Gauge | `loop` |

**Histogrammen** geven automatisch p50/p95/p99 buckets — gebruik altijd Histogram
voor latency, nooit een gemiddelde. De staart van de verdeling is wat telt in trading.

---

## 6. Testnet wallet setup (eenmalig, handmatig)

1. Genereer nieuw EVM keypair — **nooit je echte wallet gebruiken**
   ```python
   from eth_account import Account
   acct = Account.create()
   print(acct.address, acct.key.hex())
   ```
2. Ga naar `app.hyperliquid-testnet.xyz`
3. Verbind wallet → claim testfunds (gratis USDC)
4. Zet private key in `.env` als `HYPERLIQUID_PRIVATE_KEY`

---

## 7. Lokaal testen → K8s

### Stap 1: lokaal
```bash
cp .env.example .env
# vul HYPERLIQUID_PRIVATE_KEY in
pip install -r requirements.txt
python -m src.main
```

### Stap 2: CI/CD → K8s
```
git push → GitHub Actions → docker build → registry → K8s rollout
```

De Dockerfile en K8s manifests worden meegeleverd. De bestaande CI/CD pipeline
pakt de Dockerfile op — geen aanpassingen aan de pipeline nodig.

---

## 8. K8s manifests (te leveren)

- `k8s/deployment.yaml` — Deployment met resource limits, liveness probe op `/metrics`
- `k8s/pvc.yaml` — PersistentVolumeClaim voor `/data`
- `k8s/configmap.yaml` — settings.yaml + coins.yaml
- `k8s/secret.yaml` — template (values nooit in git)
- `k8s/servicemonitor.yaml` — Prometheus scraping config

---

## 9. Wat niet in scope is

- PostgreSQL migratie (SQLite voldoet voor testfase)
- Meerdere replicas (bot moet single-instance blijven vanwege order state)
- Backtesting pipeline (apart project)
- Live mainnet trading (na bewezen testnet resultaten)

---

## 10. Volgorde van implementatie

1. `src/metrics/prometheus_metrics.py` — registry opzetten, HTTP server starten
2. `src/execution/trade_executor.py` — orders plaatsen op testnet
3. `src/execution/position_manager.py` — Loop 2, posities bewaken
4. `src/alerts/telegram_alert.py` — notificaties
5. `src/main.py` updaten — drie threads starten, metrics overal toevoegen
6. `.env.example` + `Dockerfile` + `k8s/` manifests
