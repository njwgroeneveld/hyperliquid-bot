# Hyperliquid Execution + K8s Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real testnet order execution, position management, Prometheus metrics, Telegram alerts, and K8s deployment manifests to the Hyperliquid trading bot.

**Architecture:** The bot runs as a single Python process with three concurrent components: an hourly analysis loop (APScheduler BackgroundScheduler), a 30-second position management loop (daemon thread), and a Prometheus HTTP server (started once via prometheus_client). All components share a single SQLite database with WAL mode enabled for thread safety. A `TradeExecutor` is only created when `HYPERLIQUID_PRIVATE_KEY` is set — without it the bot runs in dry-run (paper) mode automatically.

**Tech Stack:** `hyperliquid-python-sdk`, `prometheus-client`, `requests` (Telegram HTTP), `APScheduler`, `sqlite3 WAL`, Docker, Kubernetes

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `src/metrics/__init__.py` | Create | Empty package marker |
| `src/metrics/prometheus_metrics.py` | Create | All metric objects + `start_metrics_server()` |
| `src/execution/__init__.py` | Create | Empty package marker |
| `src/execution/trade_executor.py` | Create | Place + close orders via Hyperliquid SDK |
| `src/execution/position_manager.py` | Create | Check open trades, close on SL/target/timeout |
| `src/alerts/__init__.py` | Create | Empty package marker |
| `src/alerts/telegram_alert.py` | Create | Send Telegram notifications |
| `src/logging/database.py` | Modify | WAL mode + `hl_order_id` column + migration + updated `insert_trade` |
| `src/main.py` | Modify | 3-thread architecture, metrics, real orders, consecutive-error alerts |
| `requirements.txt` | Modify | Add `prometheus-client` |
| `.env.example` | Create | All env-var documentation |
| `Dockerfile` | Create | Production container |
| `k8s/pvc.yaml` | Create | PersistentVolumeClaim |
| `k8s/configmap.yaml` | Create | settings.yaml + coins.yaml |
| `k8s/secret.yaml` | Create | Secret template (no real values) |
| `k8s/deployment.yaml` | Create | Deployment + Service |
| `k8s/servicemonitor.yaml` | Create | Prometheus ServiceMonitor |

---

## Task 1: Prometheus Metrics Registry

**Files:**
- Create: `src/metrics/__init__.py`
- Create: `src/metrics/prometheus_metrics.py`
- Modify: `requirements.txt`
- Test: `tests/test_prometheus_metrics.py`

- [ ] **Step 1: Add prometheus-client to requirements.txt**

Replace the full contents of `requirements.txt`:
```
hyperliquid-python-sdk>=0.9.0
pandas>=2.0.0
numpy>=1.24.0
anthropic>=0.25.0
python-telegram-bot>=20.0
PyYAML>=6.0
APScheduler>=3.10.0
requests>=2.31.0
prometheus-client>=0.17.0
pytest>=7.0.0
```

- [ ] **Step 2: Install the new dependency**

```bash
pip install "prometheus-client>=0.17.0"
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_prometheus_metrics.py`:
```python
import pytest
from prometheus_client import Counter, Gauge, Histogram
from src.metrics import prometheus_metrics as m


class TestPrometheusMetricsTypes:
    def test_trading_counters_exist(self):
        assert isinstance(m.analysis_runs_total, Counter)
        assert isinstance(m.step_result_total, Counter)
        assert isinstance(m.trades_total, Counter)
        assert isinstance(m.errors_total, Counter)

    def test_trading_gauges_exist(self):
        assert isinstance(m.decision_score, Gauge)
        assert isinstance(m.open_positions, Gauge)
        assert isinstance(m.pnl_usd, Gauge)
        assert isinstance(m.win_rate, Gauge)
        assert isinstance(m.funding_rate, Gauge)
        assert isinstance(m.trend_status, Gauge)
        assert isinstance(m.zones_found, Gauge)

    def test_performance_histograms_exist(self):
        assert isinstance(m.api_latency_seconds, Histogram)
        assert isinstance(m.loop_duration_seconds, Histogram)
        assert isinstance(m.order_placement_latency_seconds, Histogram)

    def test_performance_gauges_exist(self):
        assert isinstance(m.market_data_age_seconds, Gauge)
        assert isinstance(m.loop_schedule_jitter_seconds, Gauge)
        assert isinstance(m.consecutive_errors, Gauge)
        assert isinstance(m.last_successful_run_timestamp, Gauge)


class TestPrometheusMetricsRecording:
    def test_counter_increments_without_error(self):
        m.analysis_runs_total.labels(coin="PLANTEST").inc()

    def test_gauge_set_without_error(self):
        m.decision_score.labels(coin="PLANTEST").set(5.0)
        m.trend_status.labels(coin="PLANTEST").set(1)

    def test_histogram_observe_without_error(self):
        m.api_latency_seconds.labels(endpoint="test_endpoint").observe(0.25)
        m.loop_duration_seconds.labels(loop="analysis").observe(45.0)
        m.order_placement_latency_seconds.labels(coin="PLANTEST").observe(0.5)

    def test_start_metrics_server_is_callable(self):
        assert callable(m.start_metrics_server)
```

- [ ] **Step 4: Run test to verify it fails**

```bash
pytest tests/test_prometheus_metrics.py -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'src.metrics'`

- [ ] **Step 5: Create `src/metrics/__init__.py`**

Empty file — just create it:
```python
```

- [ ] **Step 6: Create `src/metrics/prometheus_metrics.py`**

```python
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Trading metrics
analysis_runs_total = Counter(
    "bot_analysis_runs_total",
    "Total analysis runs per coin",
    ["coin"],
)
decision_score = Gauge(
    "bot_decision_score",
    "Decision tree score (0-7)",
    ["coin"],
)
step_result_total = Counter(
    "bot_step_result_total",
    "Decision tree step outcomes",
    ["coin", "step", "result"],
)
open_positions = Gauge(
    "bot_open_positions",
    "Currently open positions",
    ["coin", "direction"],
)
trades_total = Counter(
    "bot_trades_total",
    "Total completed trades",
    ["coin", "direction", "outcome"],
)
pnl_usd = Gauge(
    "bot_pnl_usd",
    "Realised P&L in USD",
    ["coin"],
)
win_rate = Gauge(
    "bot_win_rate",
    "Win rate as fraction (0-1)",
    ["coin"],
)
funding_rate = Gauge(
    "bot_funding_rate",
    "Current funding rate",
    ["coin"],
)
trend_status = Gauge(
    "bot_trend_status",
    "Trend direction (1=up, -1=down, 0=consolidation)",
    ["coin"],
)
zones_found = Gauge(
    "bot_zones_found",
    "Number of valid zones detected",
    ["coin", "type"],
)

# Performance & reliability metrics
api_latency_seconds = Histogram(
    "bot_api_latency_seconds",
    "Hyperliquid API call latency",
    ["endpoint"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)
loop_duration_seconds = Histogram(
    "bot_loop_duration_seconds",
    "End-to-end loop duration",
    ["loop"],
    buckets=[1, 5, 10, 30, 60, 120, 300],
)
order_placement_latency_seconds = Histogram(
    "bot_order_placement_latency_seconds",
    "Time to place an order on Hyperliquid",
    ["coin"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
market_data_age_seconds = Gauge(
    "bot_market_data_age_seconds",
    "Age of cached market data in seconds",
    ["coin", "timeframe"],
)
loop_schedule_jitter_seconds = Gauge(
    "bot_loop_schedule_jitter_seconds",
    "Seconds between scheduled and actual loop start",
    ["loop"],
)
errors_total = Counter(
    "bot_errors_total",
    "Error counts by type",
    ["type"],
)
consecutive_errors = Gauge(
    "bot_consecutive_errors",
    "Number of consecutive errors without a success",
)
last_successful_run_timestamp = Gauge(
    "bot_last_successful_run_timestamp",
    "Unix timestamp of last successful loop run",
    ["loop"],
)


def start_metrics_server(port: int = 8080) -> None:
    start_http_server(port)
```

- [ ] **Step 7: Run test to verify it passes**

```bash
pytest tests/test_prometheus_metrics.py -v
```
Expected: All 8 tests `PASSED`

- [ ] **Step 8: Run full test suite to check for regressions**

```bash
pytest -v
```
Expected: All 56 existing tests + 8 new = 64 tests `PASSED`

- [ ] **Step 9: Commit**

```bash
git add requirements.txt src/metrics/__init__.py src/metrics/prometheus_metrics.py tests/test_prometheus_metrics.py
git commit -m "feat: add Prometheus metrics registry with all bot and performance metrics"
```

---

## Task 2: Trade Executor + Database Migration

**Files:**
- Create: `src/execution/__init__.py`
- Create: `src/execution/trade_executor.py`
- Modify: `src/logging/database.py`
- Test: `tests/test_trade_executor.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_trade_executor.py`:
```python
from unittest.mock import MagicMock, patch
import pytest
from src.execution.trade_executor import TradeExecutor

MOCK_PRIVATE_KEY = "0x4c0883a69102937d6231471b5dbb6e538eba2ef45a05ad8a1bb2bb8ec845dec0"

META_RESPONSE = {
    "universe": [
        {"name": "BTC", "szDecimals": 5},
        {"name": "ETH", "szDecimals": 4},
        {"name": "SOL", "szDecimals": 2},
    ]
}

ORDER_OK = {
    "status": "ok",
    "response": {
        "type": "order",
        "data": {"statuses": [{"resting": {"oid": 42}}]},
    },
}
ORDER_ERR = {"status": "err", "response": "Insufficient margin"}
CLOSE_OK = {
    "status": "ok",
    "response": {
        "type": "order",
        "data": {"statuses": [{"filled": {"oid": 99, "totalSz": "0.01"}}]},
    },
}


@pytest.fixture
def executor():
    with patch("src.execution.trade_executor.Exchange") as MockExchange, \
         patch("src.execution.trade_executor.Info") as MockInfo, \
         patch("src.execution.trade_executor.Account"):
        mock_info = MagicMock()
        mock_info.meta.return_value = META_RESPONSE
        MockInfo.return_value = mock_info

        mock_exchange = MagicMock()
        MockExchange.return_value = mock_exchange

        ex = TradeExecutor(MOCK_PRIVATE_KEY, testnet=True)
        ex._mock_exchange = mock_exchange
        ex._mock_info = mock_info
        yield ex


class TestSzDecimals:
    def test_btc_returns_5(self, executor):
        assert executor.get_sz_decimals("BTC") == 5

    def test_eth_returns_4(self, executor):
        assert executor.get_sz_decimals("ETH") == 4

    def test_unknown_coin_defaults_to_3(self, executor):
        assert executor.get_sz_decimals("UNKNOWN") == 3

    def test_meta_cached_after_first_call(self, executor):
        executor.get_sz_decimals("BTC")
        executor.get_sz_decimals("BTC")
        assert executor._mock_info.meta.call_count == 1


class TestPlaceLimitOrder:
    def test_long_sets_is_buy_true(self, executor):
        executor._mock_exchange.order.return_value = ORDER_OK
        executor.place_limit_order("BTC", "LONG", 95000.0, 1000.0)
        call_args = executor._mock_exchange.order.call_args[0]
        assert call_args[1] is True

    def test_short_sets_is_buy_false(self, executor):
        executor._mock_exchange.order.return_value = ORDER_OK
        executor.place_limit_order("BTC", "SHORT", 97000.0, 500.0)
        call_args = executor._mock_exchange.order.call_args[0]
        assert call_args[1] is False

    def test_success_returns_hl_order_id(self, executor):
        executor._mock_exchange.order.return_value = ORDER_OK
        result = executor.place_limit_order("BTC", "LONG", 95000.0, 1000.0)
        assert result["status"] == "ok"
        assert result["hl_order_id"] == "42"

    def test_api_error_returns_error_dict(self, executor):
        executor._mock_exchange.order.return_value = ORDER_ERR
        result = executor.place_limit_order("BTC", "LONG", 95000.0, 1000.0)
        assert result["status"] == "error"
        assert "reden" in result

    def test_exception_returns_error_dict(self, executor):
        executor._mock_exchange.order.side_effect = RuntimeError("connection timeout")
        result = executor.place_limit_order("BTC", "LONG", 95000.0, 1000.0)
        assert result["status"] == "error"
        assert "connection timeout" in result["reden"]

    def test_sz_calculated_from_usd_and_price(self, executor):
        executor._mock_exchange.order.return_value = ORDER_OK
        executor.place_limit_order("BTC", "LONG", 95000.0, 950.0)
        # 950 / 95000 = 0.01, rounded to 5 decimals = 0.01
        call_args = executor._mock_exchange.order.call_args[0]
        assert call_args[2] == pytest.approx(0.01, abs=0.0001)


class TestClosePositionMarket:
    def test_success_calls_market_close(self, executor):
        executor._mock_exchange.market_close.return_value = CLOSE_OK
        result = executor.close_position_market("BTC", "LONG", 1000.0, 95000.0)
        assert result["status"] == "ok"
        executor._mock_exchange.market_close.assert_called_once()

    def test_api_error_returns_error_dict(self, executor):
        executor._mock_exchange.market_close.return_value = ORDER_ERR
        result = executor.close_position_market("BTC", "LONG", 1000.0, 95000.0)
        assert result["status"] == "error"
        assert "reden" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_trade_executor.py -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'src.execution'`

- [ ] **Step 3: Create `src/execution/__init__.py`**

Empty file — just create it:
```python
```

- [ ] **Step 4: Create `src/execution/trade_executor.py`**

```python
import logging
import time
from datetime import datetime, timezone

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from src.metrics import prometheus_metrics as metrics

log = logging.getLogger(__name__)

TESTNET_URL = "https://api.hyperliquid-testnet.xyz"
MAINNET_URL = "https://api.hyperliquid.xyz"


class TradeExecutor:
    def __init__(self, private_key: str, testnet: bool = True):
        base_url = TESTNET_URL if testnet else MAINNET_URL
        self.account = Account.from_key(private_key)
        self.info = Info(base_url, skip_ws=True)
        self.exchange = Exchange(self.account, base_url)
        self._sz_decimals_cache: dict[str, int] = {}

    def get_sz_decimals(self, coin: str) -> int:
        if coin not in self._sz_decimals_cache:
            meta = self.info.meta()
            for asset in meta.get("universe", []):
                if asset["name"] == coin:
                    self._sz_decimals_cache[coin] = asset["szDecimals"]
                    break
            else:
                self._sz_decimals_cache[coin] = 3
        return self._sz_decimals_cache[coin]

    def place_limit_order(self, coin: str, richting: str, entry: float, sz_usd: float) -> dict:
        start = time.time()
        try:
            sz_decimals = self.get_sz_decimals(coin)
            sz = round(sz_usd / entry, sz_decimals)
            if sz <= 0:
                return {"status": "error", "reden": "Positiegrootte te klein"}

            is_buy = richting == "LONG"
            result = self.exchange.order(
                coin, is_buy, sz, entry,
                {"limit": {"tif": "Gtc"}},
            )
            elapsed = time.time() - start
            metrics.order_placement_latency_seconds.labels(coin=coin).observe(elapsed)

            if result.get("status") == "ok":
                statuses = result["response"]["data"]["statuses"]
                oid = (
                    statuses[0].get("resting", {}).get("oid")
                    or statuses[0].get("filled", {}).get("oid")
                )
                log.info(f"[{coin}] Order geplaatst: OID={oid}, {richting} {sz} @ {entry}")
                return {
                    "status": "ok",
                    "hl_order_id": str(oid),
                    "sz_coin": sz,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            else:
                err = result.get("response", "onbekend")
                log.error(f"[{coin}] Order mislukt: {err}")
                metrics.errors_total.labels(type="order_failed").inc()
                return {"status": "error", "reden": str(err)}

        except Exception as e:
            log.error(f"[{coin}] Order exception: {e}", exc_info=True)
            metrics.errors_total.labels(type="order_failed").inc()
            return {"status": "error", "reden": str(e)}

    def close_position_market(self, coin: str, richting: str, sz_usd: float, entry: float) -> dict:
        try:
            sz_decimals = self.get_sz_decimals(coin)
            sz_coin = round(sz_usd / entry, sz_decimals)
            result = self.exchange.market_close(coin, sz=sz_coin)
            if result.get("status") == "ok":
                log.info(f"[{coin}] Positie gesloten via market_close")
                return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
            else:
                err = result.get("response", "onbekend")
                log.error(f"[{coin}] Sluiting mislukt: {err}")
                return {"status": "error", "reden": str(err)}
        except Exception as e:
            log.error(f"[{coin}] Sluiting exception: {e}", exc_info=True)
            return {"status": "error", "reden": str(e)}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_trade_executor.py -v
```
Expected: All 12 tests `PASSED`

- [ ] **Step 6: Update `src/logging/database.py`**

Four changes: (a) WAL mode in `_init`, (b) `hl_order_id` in `CREATE_TABLES`, (c) add `_migrate` method, (d) add `hl_order_id` to `insert_trade`.

Replace `CREATE_TABLES` constant (add `hl_order_id TEXT` between `sessie` and `status`):
```python
CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS detection_reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    coin        TEXT NOT NULL,
    price       REAL,
    trend_4h    TEXT,
    trend_1h    TEXT,
    raw_json    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    coin        TEXT NOT NULL,
    score       TEXT,
    beslissing  TEXT,
    raw_json    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT UNIQUE NOT NULL,
    timestamp_open  TEXT NOT NULL,
    coin            TEXT NOT NULL,
    richting        TEXT NOT NULL,
    entry           REAL,
    stop_loss       REAL,
    target          REAL,
    leverage        REAL,
    positie_usd     REAL,
    risico_usd      REAL,
    score           TEXT,
    vertrouwen      TEXT,
    sessie          TEXT,
    hl_order_id     TEXT,
    status          TEXT DEFAULT 'OPEN',
    timestamp_close TEXT,
    close_prijs     REAL,
    resultaat_usd   REAL,
    resultaat_r     REAL,
    close_reden     TEXT,
    raw_json        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_detection_coin ON detection_reports(coin, timestamp);
CREATE INDEX IF NOT EXISTS idx_decision_coin ON decision_reports(coin, timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_coin ON trades(coin, status);
"""
```

Replace `_init` method:
```python
def _init(self):
    with self._connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(CREATE_TABLES)
    self._migrate()
```

Add `_migrate` directly after `_init`:
```python
def _migrate(self):
    with self._connect() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
        if "hl_order_id" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN hl_order_id TEXT")
```

Replace `insert_trade` method (adds `hl_order_id` to the INSERT):
```python
def insert_trade(self, trade: dict):
    sql = """
    INSERT INTO trades (
        trade_id, timestamp_open, coin, richting, entry, stop_loss, target,
        leverage, positie_usd, risico_usd, score, vertrouwen, sessie, hl_order_id, raw_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    with self._connect() as conn:
        conn.execute(sql, (
            trade["trade_id"],
            trade["timestamp_open"],
            trade["coin"],
            trade["richting"],
            trade.get("entry"),
            trade.get("stop_loss"),
            trade.get("target"),
            trade.get("leverage"),
            trade.get("positiegrootte_usd"),
            trade.get("risico_usd"),
            trade.get("score"),
            trade.get("vertrouwen"),
            trade.get("sessie"),
            trade.get("hl_order_id"),
            json.dumps(trade, default=str),
        ))
```

- [ ] **Step 7: Run full test suite**

```bash
pytest -v
```
Expected: 64 + 12 = 76 tests `PASSED`

- [ ] **Step 8: Commit**

```bash
git add src/execution/__init__.py src/execution/trade_executor.py src/logging/database.py tests/test_trade_executor.py
git commit -m "feat: add TradeExecutor for Hyperliquid orders + DB WAL mode + hl_order_id migration"
```

---

## Task 3: Position Manager

**Files:**
- Create: `src/execution/position_manager.py`
- Test: `tests/test_position_manager.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_position_manager.py`:
```python
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import pytest
from src.execution.position_manager import PositionManager

SETTINGS = {"risk": {"max_trade_duration_hours": 24}}


def make_trade(**kwargs):
    defaults = {
        "trade_id": "BTC-L-20250101-1200",
        "coin": "BTC",
        "richting": "LONG",
        "entry": 95000.0,
        "stop_loss": 93000.0,
        "target": 99000.0,
        "positie_usd": 1000.0,
        "risico_usd": 100.0,
        "timestamp_open": datetime.now(timezone.utc).isoformat(),
    }
    defaults.update(kwargs)
    return defaults


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_executor():
    ex = MagicMock()
    ex.close_position_market.return_value = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return ex


@pytest.fixture
def manager(mock_db, mock_executor):
    return PositionManager(mock_db, mock_executor, SETTINGS)


class TestRunOnce:
    def test_no_open_trades_does_nothing(self, manager, mock_db, mock_executor):
        mock_db.get_open_trades.return_value = []
        manager.run_once({"BTC": 95000.0})
        mock_executor.close_position_market.assert_not_called()

    def test_missing_price_skips_trade(self, manager, mock_db, mock_executor):
        mock_db.get_open_trades.return_value = [make_trade()]
        manager.run_once({})
        mock_executor.close_position_market.assert_not_called()


class TestClosingConditions:
    def test_long_sl_hit_closes_with_stop_loss_reason(self, manager, mock_db, mock_executor):
        mock_db.get_open_trades.return_value = [
            make_trade(entry=95000.0, stop_loss=93000.0)
        ]
        manager.run_once({"BTC": 92000.0})
        mock_executor.close_position_market.assert_called_once_with("BTC", "LONG", 1000.0, 95000.0)
        args = mock_db.close_trade.call_args[0]
        assert args[0] == "BTC-L-20250101-1200"
        assert args[4] == "STOP_LOSS"

    def test_long_target_hit_closes_with_target_reason(self, manager, mock_db, mock_executor):
        mock_db.get_open_trades.return_value = [make_trade(target=99000.0)]
        manager.run_once({"BTC": 100000.0})
        args = mock_db.close_trade.call_args[0]
        assert args[4] == "TARGET"

    def test_short_sl_hit_closes_trade(self, manager, mock_db, mock_executor):
        mock_db.get_open_trades.return_value = [
            make_trade(richting="SHORT", entry=97000.0, stop_loss=99000.0, target=93000.0)
        ]
        manager.run_once({"BTC": 99500.0})
        args = mock_db.close_trade.call_args[0]
        assert args[4] == "STOP_LOSS"

    def test_short_target_hit_closes_trade(self, manager, mock_db, mock_executor):
        mock_db.get_open_trades.return_value = [
            make_trade(richting="SHORT", entry=97000.0, stop_loss=99000.0, target=93000.0)
        ]
        manager.run_once({"BTC": 92000.0})
        args = mock_db.close_trade.call_args[0]
        assert args[4] == "TARGET"

    def test_timeout_closes_old_trade(self, manager, mock_db, mock_executor):
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        mock_db.get_open_trades.return_value = [make_trade(timestamp_open=old_ts)]
        manager.run_once({"BTC": 96000.0})
        args = mock_db.close_trade.call_args[0]
        assert args[4] == "TIMEOUT"

    def test_price_between_sl_and_target_no_action(self, manager, mock_db, mock_executor):
        mock_db.get_open_trades.return_value = [
            make_trade(stop_loss=93000.0, target=99000.0)
        ]
        manager.run_once({"BTC": 96000.0})
        mock_executor.close_position_market.assert_not_called()

    def test_failed_close_does_not_update_db(self, manager, mock_db, mock_executor):
        mock_executor.close_position_market.return_value = {
            "status": "error", "reden": "API down"
        }
        mock_db.get_open_trades.return_value = [make_trade(stop_loss=93000.0)]
        manager.run_once({"BTC": 92000.0})
        mock_db.close_trade.assert_not_called()


class TestPnlCalculation:
    def test_long_win_pnl_is_positive(self, manager, mock_db, mock_executor):
        # entry=95000, close=99000, positie=1000 → (99000-95000)/95000*1000 ≈ +42.1
        mock_db.get_open_trades.return_value = [
            make_trade(entry=95000.0, target=99000.0, positie_usd=1000.0)
        ]
        manager.run_once({"BTC": 99000.0})
        args = mock_db.close_trade.call_args[0]
        resultaat_usd = args[2]
        assert resultaat_usd == pytest.approx(42.1, abs=1.0)

    def test_short_win_pnl_is_positive(self, manager, mock_db, mock_executor):
        # entry=97000, close=92000, positie=1000 → (97000-92000)/97000*1000 ≈ +51.5
        mock_db.get_open_trades.return_value = [
            make_trade(richting="SHORT", entry=97000.0, stop_loss=99000.0,
                       target=93000.0, positie_usd=1000.0)
        ]
        manager.run_once({"BTC": 92000.0})
        args = mock_db.close_trade.call_args[0]
        assert args[2] > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_position_manager.py -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'src.execution.position_manager'`

- [ ] **Step 3: Create `src/execution/position_manager.py`**

```python
import logging
from datetime import datetime, timezone

from src.logging.database import Database
from src.execution.trade_executor import TradeExecutor
from src.metrics import prometheus_metrics as metrics

log = logging.getLogger(__name__)


class PositionManager:
    def __init__(self, db: Database, executor: TradeExecutor, settings: dict):
        self.db = db
        self.executor = executor
        self.max_duration_hours = settings["risk"]["max_trade_duration_hours"]

    def run_once(self, all_mids: dict[str, float]) -> None:
        for trade in self.db.get_open_trades():
            coin = trade["coin"]
            current_price = all_mids.get(coin)
            if current_price is None:
                log.warning(f"[{coin}] Geen prijs beschikbaar — sla over")
                continue
            self._check_trade(trade, float(current_price))

    def _check_trade(self, trade: dict, current_price: float) -> None:
        richting = trade["richting"]
        stop_loss = float(trade["stop_loss"])
        target = float(trade["target"])
        timestamp_open = trade["timestamp_open"]

        open_dt = datetime.fromisoformat(timestamp_open.replace("Z", "+00:00"))
        hours_open = (datetime.now(timezone.utc) - open_dt).total_seconds() / 3600
        if hours_open >= self.max_duration_hours:
            self._close_trade(trade, current_price, "TIMEOUT")
            return

        if richting == "LONG":
            if current_price <= stop_loss:
                self._close_trade(trade, current_price, "STOP_LOSS")
            elif current_price >= target:
                self._close_trade(trade, current_price, "TARGET")
        else:
            if current_price >= stop_loss:
                self._close_trade(trade, current_price, "STOP_LOSS")
            elif current_price <= target:
                self._close_trade(trade, current_price, "TARGET")

    def _close_trade(self, trade: dict, close_prijs: float, reden: str) -> None:
        coin = trade["coin"]
        richting = trade["richting"]
        entry = float(trade["entry"])
        positie_usd = float(trade.get("positie_usd") or 0)
        risico_usd = float(trade.get("risico_usd") or 0)

        result = self.executor.close_position_market(coin, richting, positie_usd, entry)
        if result["status"] != "ok":
            log.error(f"[{coin}] Sluiting mislukt: {result.get('reden')}")
            return

        if richting == "LONG":
            resultaat_usd = round((close_prijs - entry) / entry * positie_usd, 2)
        else:
            resultaat_usd = round((entry - close_prijs) / entry * positie_usd, 2)

        resultaat_r = round(resultaat_usd / risico_usd, 2) if risico_usd > 0 else 0.0
        timestamp_close = datetime.now(timezone.utc).isoformat()

        self.db.close_trade(
            trade["trade_id"],
            close_prijs,
            resultaat_usd,
            resultaat_r,
            reden,
            timestamp_close,
        )

        direction = richting.lower()
        outcome = "win" if resultaat_usd >= 0 else "loss"
        metrics.trades_total.labels(coin=coin, direction=direction, outcome=outcome).inc()
        metrics.pnl_usd.labels(coin=coin).set(resultaat_usd)
        metrics.open_positions.labels(coin=coin, direction=direction).set(0)

        log.info(
            f"[{coin}] Trade gesloten: {reden} | "
            f"Resultaat: ${resultaat_usd:+.2f} ({resultaat_r:+.2f}R)"
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_position_manager.py -v
```
Expected: All 11 tests `PASSED`

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```
Expected: 76 + 11 = 87 tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add src/execution/position_manager.py tests/test_position_manager.py
git commit -m "feat: add PositionManager — SL/target/timeout enforcement every 30 seconds"
```

---

## Task 4: Telegram Alert

**Files:**
- Create: `src/alerts/__init__.py`
- Create: `src/alerts/telegram_alert.py`
- Test: `tests/test_telegram_alert.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_telegram_alert.py`:
```python
from unittest.mock import patch, MagicMock
import src.alerts.telegram_alert as tg


class TestSend:
    def test_send_without_token_returns_false(self):
        tg._BOT_TOKEN = None
        tg._CHAT_ID = None
        assert tg._send("test message") is False

    def test_send_network_error_returns_false(self):
        tg._BOT_TOKEN = "fake_token"
        tg._CHAT_ID = "12345"
        with patch("src.alerts.telegram_alert.requests.post") as mock_post:
            mock_post.side_effect = Exception("Network error")
            assert tg._send("test message") is False


class TestAlertMessages:
    def test_trade_opened_contains_coin_and_direction(self):
        trade = {
            "coin": "BTC", "richting": "LONG", "entry": 95000.0,
            "stop_loss": 93000.0, "target": 99000.0,
            "risk_reward": "2.5R", "score": "6/7", "sessie": "London",
        }
        with patch.object(tg, "_send", return_value=True) as mock_send:
            result = tg.alert_trade_opened(trade)
            assert result is True
            msg = mock_send.call_args[0][0]
            assert "BTC" in msg
            assert "LONG" in msg

    def test_trade_closed_win_shows_positive_result(self):
        with patch.object(tg, "_send", return_value=True) as mock_send:
            tg.alert_trade_closed("BTC-L-001", "BTC", "TARGET", 200.0, 2.0)
            msg = mock_send.call_args[0][0]
            assert "TARGET" in msg
            assert "+200.00" in msg

    def test_trade_closed_loss_shows_negative_result(self):
        with patch.object(tg, "_send", return_value=True) as mock_send:
            tg.alert_trade_closed("BTC-L-001", "BTC", "STOP_LOSS", -100.0, -1.0)
            msg = mock_send.call_args[0][0]
            assert "STOP_LOSS" in msg
            assert "-100.00" in msg

    def test_bot_error_includes_consecutive_count(self):
        with patch.object(tg, "_send", return_value=True) as mock_send:
            tg.alert_bot_error("Connection refused", 3)
            msg = mock_send.call_args[0][0]
            assert "3" in msg

    def test_daily_loss_includes_percentage(self):
        with patch.object(tg, "_send", return_value=True) as mock_send:
            tg.alert_daily_loss(12.5)
            msg = mock_send.call_args[0][0]
            assert "12.5" in msg
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_telegram_alert.py -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'src.alerts'`

- [ ] **Step 3: Create `src/alerts/__init__.py`**

Empty file — just create it:
```python
```

- [ ] **Step 4: Create `src/alerts/telegram_alert.py`**

```python
import logging
import os

import requests

log = logging.getLogger(__name__)

_BOT_TOKEN: str | None = None
_CHAT_ID: str | None = None


def _init() -> None:
    global _BOT_TOKEN, _CHAT_ID
    _BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    _CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


_init()


def _send(text: str) -> bool:
    if not _BOT_TOKEN or not _CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": _CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=5,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        log.warning(f"Telegram send mislukt: {e}")
        return False


def alert_trade_opened(trade: dict) -> bool:
    msg = (
        f"<b>TRADE GEOPEND</b> — {trade.get('coin', '?')}\n"
        f"Richting: {trade.get('richting', '?')}\n"
        f"Entry: ${trade.get('entry', 0):,.2f}\n"
        f"Stop-loss: ${trade.get('stop_loss', 0):,.2f}\n"
        f"Target: ${trade.get('target', 0):,.2f}\n"
        f"R/R: {trade.get('risk_reward', '?')} | Score: {trade.get('score', '?')} | "
        f"Sessie: {trade.get('sessie', '?')}"
    )
    return _send(msg)


def alert_trade_closed(
    trade_id: str, coin: str, reden: str, resultaat_usd: float, resultaat_r: float
) -> bool:
    emoji = "✅" if resultaat_usd >= 0 else "❌"
    msg = (
        f"{emoji} <b>TRADE GESLOTEN</b> — {coin}\n"
        f"Reden: {reden}\n"
        f"Resultaat: ${resultaat_usd:+.2f} ({resultaat_r:+.2f}R)\n"
        f"Trade ID: {trade_id}"
    )
    return _send(msg)


def alert_bot_error(error_msg: str, consecutive_count: int) -> bool:
    msg = (
        f"⚠️ <b>BOT FOUT</b>\n"
        f"Opeenvolgende fouten: {consecutive_count}\n"
        f"Fout: {error_msg}"
    )
    return _send(msg)


def alert_daily_loss(loss_pct: float) -> bool:
    msg = (
        f"🚨 <b>DAGELIJKS VERLIESALERT</b>\n"
        f"Verlies: {loss_pct:.1f}%"
    )
    return _send(msg)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_telegram_alert.py -v
```
Expected: All 7 tests `PASSED`

- [ ] **Step 6: Run full test suite**

```bash
pytest -v
```
Expected: 87 + 7 = 94 tests `PASSED`

- [ ] **Step 7: Commit**

```bash
git add src/alerts/__init__.py src/alerts/telegram_alert.py tests/test_telegram_alert.py
git commit -m "feat: add Telegram alert module for trade open/close/error events"
```

---

## Task 5: Update main.py — Three Threads + Metrics + Real Orders

This task rewrites `src/main.py`. The analysis logic is unchanged; the additions are: `BackgroundScheduler`, `make_executor()`, `executor` parameter on `AnalysisLoop`, Prometheus metrics throughout, real order placement in `_handle_entry`, consecutive-error tracking, and the position management daemon thread.

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_main_execution.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_main_execution.py`:
```python
import os
from unittest.mock import MagicMock, patch
import pytest
from src.main import make_executor, AnalysisLoop

SETTINGS = {
    "strategy": {
        "zone_proximity_pct": 0.02, "swing_n": 3, "swing_lookback": 3,
        "equal_tolerance": 0.0015, "impulse_min_body_pct": 0.60,
        "impulse_min_move_pct": 0.003, "impulse_volume_multiplier": 1.5,
        "order_wall_threshold_btc": 200, "order_wall_buckets": 0.001,
        "momentum_strong_body_pct": 0.60, "momentum_weak_body_pct": 0.30,
    },
    "risk": {
        "risk_per_trade": 0.01, "max_leverage": 2, "min_risk_reward": 2.0,
        "stop_buffer_pct": 0.001, "atr_period": 14, "atr_stop_multiplier": 1.5,
        "avg_trade_duration_hours": 12, "max_trade_duration_hours": 24,
        "max_positions": 5, "max_correlated_positions": 3,
        "daily_loss_alert_pct": 0.10, "weekly_loss_alert_pct": 0.25,
    },
    "timeframes": {"trend": "4h", "entry": "1h", "candle_lookback": 200},
    "session_hours_utc": {
        "london_open": 8, "london_close": 12, "ny_open": 13, "ny_close": 17,
    },
    "logging": {"log_dir": "logs", "database_path": "database/test_main.db"},
}


class TestMakeExecutor:
    def test_returns_none_when_no_key(self):
        with patch.dict(os.environ, {}, clear=True):
            assert make_executor() is None

    def test_returns_executor_when_key_set(self):
        with patch.dict(os.environ, {"HYPERLIQUID_PRIVATE_KEY": "0xdeadbeef"}), \
             patch("src.main.TradeExecutor") as MockExecutor:
            MockExecutor.return_value = MagicMock()
            result = make_executor()
            assert result is not None
            MockExecutor.assert_called_once_with("0xdeadbeef", testnet=True)

    def test_mainnet_when_testnet_false(self):
        with patch.dict(os.environ, {
            "HYPERLIQUID_PRIVATE_KEY": "0xdeadbeef",
            "HYPERLIQUID_TESTNET": "false",
        }), patch("src.main.TradeExecutor") as MockExecutor:
            MockExecutor.return_value = MagicMock()
            make_executor()
            MockExecutor.assert_called_once_with("0xdeadbeef", testnet=False)


class TestAnalysisLoopExecutorParam:
    def _make_loop(self, executor=None):
        with patch("src.main.Database"), \
             patch("src.main.HyperliquidClient"), \
             patch("src.main.CandleFetcher"), \
             patch("src.main.OrderbookFetcher"), \
             patch("src.main.Detector"), \
             patch("src.main.DetectionLogger"), \
             patch("src.main.DecisionLogger"), \
             patch("src.main.TradeLogger"):
            return AnalysisLoop(SETTINGS, ["BTC"], executor=executor)

    def test_executor_is_none_by_default(self):
        loop = self._make_loop()
        assert loop.executor is None

    def test_executor_stored_when_provided(self):
        mock_ex = MagicMock()
        loop = self._make_loop(executor=mock_ex)
        assert loop.executor is mock_ex
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_main_execution.py -v
```
Expected: `FAILED` — `make_executor` and `executor` kwarg don't exist yet

- [ ] **Step 3: Replace the full contents of `src/main.py`**

```python
"""
Hyperliquid Trading Bot — startpunt.

Fase C/D: Testnet execution + positiebeheer + Prometheus metrics + Telegram alerts.

Gebruik: python -m src.main
         HYPERLIQUID_PRIVATE_KEY=0x... HYPERLIQUID_TESTNET=true python -m src.main
"""

import logging
import os
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml
from apscheduler.schedulers.background import BackgroundScheduler

from src.data.hyperliquid_client import HyperliquidClient
from src.data.candle_fetcher import CandleFetcher
from src.data.orderbook_fetcher import OrderbookFetcher
from src.detection.detector import Detector
from src.decision import decision_tree
from src.decision.entry_calculator import calculate_entry, find_target
from src.decision.position_sizer import calculate, validate_position
from src.ai.argumentation import generate_trade_argumentation, generate_no_trade_summary
from src.logging.detection_logger import DetectionLogger
from src.logging.decision_logger import DecisionLogger
from src.logging.trade_logger import TradeLogger
from src.logging.database import Database
from src.execution.trade_executor import TradeExecutor
from src.execution.position_manager import PositionManager
from src.alerts import telegram_alert as telegram
from src.metrics import prometheus_metrics as metrics


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

PAPER_PORTFOLIO_USD = 10_000
CORRELATED_GROUP = {"BTC", "ETH", "SOL"}


def load_config() -> tuple[dict, list[str]]:
    with open("config/settings.yaml", encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    with open("config/coins.yaml", encoding="utf-8") as f:
        coins_cfg = yaml.safe_load(f)
    active_coins = [c["symbol"] for c in coins_cfg["active_coins"] if c.get("active")]
    settings["logging"]["log_dir"] = os.getenv("LOG_DIR", settings["logging"]["log_dir"])
    settings["logging"]["database_path"] = os.getenv(
        "DATABASE_PATH", settings["logging"]["database_path"]
    )
    return settings, active_coins


def make_executor() -> "TradeExecutor | None":
    private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY")
    if not private_key:
        log.warning("HYPERLIQUID_PRIVATE_KEY niet ingesteld — dry-run modus (geen echte orders)")
        return None
    testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"
    return TradeExecutor(private_key, testnet=testnet)


def make_trade_id(coin: str, richting: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return f"{coin}-{richting[:1]}-{ts}"


class AnalysisLoop:
    def __init__(
        self,
        settings: dict,
        coins: list[str],
        executor: "TradeExecutor | None" = None,
    ):
        self.settings = settings
        self.coins = coins
        self.executor = executor
        self.lookback = settings["timeframes"]["candle_lookback"]
        self.risk_pct = settings["risk"]["risk_per_trade"]
        self.leverage = settings["risk"]["max_leverage"]
        self.min_rr = settings["risk"]["min_risk_reward"]
        self.stop_buffer = settings["risk"]["stop_buffer_pct"]

        self.client = HyperliquidClient()
        self.candle_fetcher = CandleFetcher(self.client)
        self.orderbook_fetcher = OrderbookFetcher(self.client)
        self.detector = Detector(settings)

        log_dir = settings["logging"]["log_dir"]
        self.detection_logger = DetectionLogger(f"{log_dir}/detection")
        self.decision_logger = DecisionLogger(f"{log_dir}/decisions")
        self.trade_logger = TradeLogger(f"{log_dir}/trades")
        self.db = Database(settings["logging"]["database_path"])

        self._prev_meta: dict[str, dict] = {}
        self._open_paper_trades: dict[str, str] = {}
        self._consecutive_errors: int = 0

    def run_for_coin(self, coin: str):
        log.info(f"[{coin}] Analyse gestart")
        metrics.analysis_runs_total.labels(coin=coin).inc()
        start = time.time()

        try:
            df_4h = self.candle_fetcher.fetch(coin, "4h", self.lookback)
            df_1h = self.candle_fetcher.fetch(coin, "1h", self.lookback)

            if df_4h.empty or df_1h.empty:
                log.warning(f"[{coin}] Geen candle data — sla over")
                return

            orderbook = self.orderbook_fetcher.fetch(coin)
            meta = self.orderbook_fetcher.fetch_meta(coin)
            meta_prev = self._prev_meta.get(coin)
            self._prev_meta[coin] = meta

            detection = self.detector.run(coin, df_4h, df_1h, orderbook, meta, meta_prev)
            self.detection_logger.save(detection)
            self.db.insert_detection(detection)

            trend_map = {"UPTREND": 1, "DOWNTREND": -1, "CONSOLIDATIE": 0}
            trend_val = trend_map.get(detection.get("structuur_4h", {}).get("trend", ""), 0)
            metrics.trend_status.labels(coin=coin).set(trend_val)
            metrics.zones_found.labels(coin=coin, type="demand").set(
                len(detection.get("zones_4h", {}).get("demand_zones", []))
            )
            metrics.zones_found.labels(coin=coin, type="supply").set(
                len(detection.get("zones_4h", {}).get("supply_zones", []))
            )
            metrics.funding_rate.labels(coin=coin).set(
                detection.get("order_flow", {}).get("funding_rate", {}).get("huidig", 0)
            )

            beslissing = decision_tree.evaluate(detection, self.settings)
            self.decision_logger.save(beslissing)
            self.db.insert_decision(beslissing)

            score = beslissing["eindscore"]
            is_entry = beslissing["is_entry"]
            richting = beslissing.get("richting")
            prijs = detection["huidige_prijs"]

            metrics.decision_score.labels(coin=coin).set(score)

            log.info(
                f"[{coin}] Score {score} | Beslissing: {beslissing['beslissing']} | "
                f"Richting: {richting} | Prijs: ${prijs:,.2f}"
            )

            if is_entry and richting and beslissing.get("geselecteerde_zone"):
                if self._correlatie_geblokkeerd(coin, richting):
                    log.info(
                        f"[{coin}] Entry geblokkeerd — al een {richting} positie open "
                        f"in gecorreleerde crypto groep"
                    )
                else:
                    self._handle_entry(coin, detection, beslissing, prijs, df_1h=df_1h)
            else:
                samenvatting = generate_no_trade_summary(beslissing)
                log.info(f"[{coin}] {samenvatting}")

            self._consecutive_errors = 0
            metrics.consecutive_errors.set(0)

        except Exception as e:
            self._consecutive_errors += 1
            metrics.errors_total.labels(type="api_error").inc()
            metrics.consecutive_errors.set(self._consecutive_errors)
            log.error(f"[{coin}] Fout tijdens analyse: {e}", exc_info=True)
            if self._consecutive_errors >= 3:
                telegram.alert_bot_error(str(e), self._consecutive_errors)
        finally:
            elapsed = time.time() - start
            metrics.loop_duration_seconds.labels(loop="analysis").observe(elapsed)

    def _correlatie_geblokkeerd(self, coin: str, richting: str) -> bool:
        max_correlated = self.settings["risk"].get("max_correlated_positions", 99)
        if max_correlated >= len(CORRELATED_GROUP):
            return False
        if coin not in CORRELATED_GROUP:
            return False
        actief = sum(
            1 for c, r in self._open_paper_trades.items()
            if c in CORRELATED_GROUP and r == richting
        )
        return actief >= max_correlated

    def _handle_entry(
        self, coin: str, detection: dict, beslissing: dict, prijs: float, df_1h=None
    ):
        richting = beslissing["richting"]
        zone = beslissing["geselecteerde_zone"]
        vertrouwen = beslissing["vertrouwen"]

        atr_period = self.settings["risk"]["atr_period"]
        atr_multiplier = self.settings["risk"]["atr_stop_multiplier"]
        avg_trade_hours = self.settings["risk"]["avg_trade_duration_hours"]

        entry_params = calculate_entry(
            zone, richting, df_1h,
            atr_period=atr_period,
            atr_multiplier=atr_multiplier,
            stop_buffer_pct=self.settings["risk"]["stop_buffer_pct"],
        )
        if not entry_params:
            log.warning(f"[{coin}] Entry berekening mislukt")
            return

        entry = entry_params["entry"]
        stop_loss = entry_params["stop_loss"]

        target_info = find_target(
            detection, richting, entry, stop_loss, self.min_rr,
            leverage=self.leverage,
            avg_trade_hours=avg_trade_hours,
        )
        if not target_info["haalbaar"]:
            log.info(f"[{coin}] Geen haalbaar target: {target_info['reden']}")
            return

        target = target_info["target"]
        rr = target_info["rr"]

        positie = calculate(PAPER_PORTFOLIO_USD, entry, stop_loss, self.risk_pct, self.leverage)

        trade_params = {"entry": entry, "stop_loss": stop_loss, "target": target, "rr": rr}
        argumentatie = generate_trade_argumentation(detection, beslissing, trade_params)

        sessie_info = beslissing.get("sessie") or {}
        trade_id = make_trade_id(coin, richting)

        hl_order_id = None
        status = "OPEN_PAPER"
        if self.executor is not None:
            order_result = self.executor.place_limit_order(
                coin, richting, entry, positie.get("positiegrootte_usd", 0)
            )
            if order_result["status"] == "ok":
                hl_order_id = order_result["hl_order_id"]
                status = "OPEN"
                log.info(f"[{coin}] Testnet order geplaatst: OID={hl_order_id}")
            else:
                log.error(f"[{coin}] Order plaatsing mislukt: {order_result.get('reden')}")
                return

        trade_log = {
            "trade_id": trade_id,
            "timestamp_open": datetime.now(timezone.utc).isoformat(),
            "coin": coin,
            "richting": richting,
            "entry": entry,
            "stop_loss": stop_loss,
            "target": target,
            "leverage": self.leverage,
            "positiegrootte_usd": positie.get("positiegrootte_usd"),
            "margin_usd": positie.get("margin_usd"),
            "risico_usd": positie.get("risico_usd"),
            "verwacht_reward_usd": round(positie.get("risico_usd", 0) * rr, 2) if rr else None,
            "risk_reward": f"{rr}R",
            "vertrouwen": vertrouwen,
            "score": beslissing["eindscore"],
            "sessie": sessie_info.get("sessie", "?"),
            "detectie_snapshot": detection,
            "beslissing_snapshot": beslissing,
            "claude_argumentatie": argumentatie,
            "status": status,
            "hl_order_id": hl_order_id,
            "timestamp_close": None,
            "close_prijs": None,
            "resultaat_usd": None,
            "resultaat_r": None,
            "close_reden": None,
        }

        self.trade_logger.save(trade_log)
        self.db.insert_trade(trade_log)
        self._open_paper_trades[coin] = richting

        metrics.open_positions.labels(coin=coin, direction=richting.lower()).set(1)
        telegram.alert_trade_opened(trade_log)

        label = "TESTNET TRADE" if self.executor else "PAPER TRADE"
        log.info(
            f"\n{'='*60}\n"
            f"[{coin}] {label} GESIGNALEERD\n"
            f"  Richting:  {richting}\n"
            f"  Entry:     ${entry:,.2f}\n"
            f"  Stop-loss: ${stop_loss:,.2f} ({entry_params['stop_afstand_pct']:.2f}%)\n"
            f"  Target:    ${target:,.2f} ({rr}R)\n"
            f"  Positie:   ${positie.get('positiegrootte_usd', '?'):,.0f}"
            f" (margin ${positie.get('margin_usd', '?'):,.0f})\n"
            f"  Risico:    ${positie.get('risico_usd', '?'):,.2f}\n"
            f"  Score:     {beslissing['eindscore']} | Vertrouwen: {vertrouwen}\n"
            f"  Sessie:    {sessie_info.get('sessie', '?')}\n"
            f"\n  Argumentatie:\n  {argumentatie}\n"
            f"{'='*60}"
        )

    def run_all(self):
        now = datetime.now(timezone.utc)
        log.info(f"=== Analyseloop gestart: {now.isoformat()} ===")
        for coin in self.coins:
            self.run_for_coin(coin)
            time.sleep(1)
        metrics.last_successful_run_timestamp.labels(loop="analysis").set(time.time())


def main():
    log_dir = os.getenv("LOG_DIR", "logs")
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    port = int(os.getenv("METRICS_PORT", "8080"))
    metrics.start_metrics_server(port)
    log.info(f"Metrics server gestart op poort {port}")
    log.info("Hyperliquid Trading Bot opgestart (Fase C/D — Testnet Execution)")

    settings, coins = load_config()

    executor = make_executor()
    client = HyperliquidClient()
    analysis_loop = AnalysisLoop(settings, coins, executor=executor)

    stop_event = threading.Event()

    if executor is not None:
        db = analysis_loop.db
        pos_manager = PositionManager(db, executor, settings)

        def _position_loop():
            while not stop_event.is_set():
                start = time.time()
                try:
                    all_mids = client.get_all_mids()
                    pos_manager.run_once(all_mids)
                    metrics.last_successful_run_timestamp.labels(loop="position").set(
                        time.time()
                    )
                except Exception as e:
                    log.error(f"Positiebeheer fout: {e}", exc_info=True)
                    metrics.errors_total.labels(type="api_error").inc()
                finally:
                    elapsed = time.time() - start
                    metrics.loop_duration_seconds.labels(loop="position").observe(elapsed)
                stop_event.wait(30)

        threading.Thread(
            target=_position_loop, daemon=True, name="position-loop"
        ).start()
        log.info("Positiebeheer loop gestart (interval: 30s)")
    else:
        log.info("Dry-run modus — positiebeheer uitgeschakeld")

    analysis_loop.run_all()

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(analysis_loop.run_all, "cron", minute=0, id="analysis_loop")
    scheduler.start()
    log.info(f"Scheduler actief — analyseloop draait elk uur voor: {coins}")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("Bot gestopt door gebruiker")
        scheduler.shutdown()
        stop_event.set()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_main_execution.py -v
```
Expected: All 5 tests `PASSED`

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```
Expected: 94 + 5 = 99 tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/test_main_execution.py
git commit -m "feat: update main.py — 3-thread architecture, real testnet orders, Prometheus metrics throughout"
```

---

## Task 6: Deployment Files

No automated tests — these are infrastructure files. Verify by building the Docker image locally.

**Files:**
- Create: `.env.example`
- Create: `Dockerfile`
- Create: `k8s/pvc.yaml`
- Create: `k8s/secret.yaml`
- Create: `k8s/configmap.yaml`
- Create: `k8s/deployment.yaml`
- Create: `k8s/servicemonitor.yaml`

- [ ] **Step 1: Create `.env.example`**

```
# Hyperliquid — vereist
HYPERLIQUID_PRIVATE_KEY=0x_your_testnet_private_key_here
HYPERLIQUID_TESTNET=true

# Anthropic — optioneel (voor trade argumentatie via Claude)
ANTHROPIC_API_KEY=sk-ant-...

# Telegram — optioneel (voor trade alerts)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# Paden — optioneel, onderstaande defaults werken lokaal
LOG_DIR=logs
DATABASE_PATH=database/bot.db
METRICS_PORT=8080
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/logs /data/database

ENV LOG_DIR=/data/logs
ENV DATABASE_PATH=/data/bot.db
ENV METRICS_PORT=8080

EXPOSE 8080

CMD ["python", "-m", "src.main"]
```

- [ ] **Step 3: Build and verify the image**

```bash
docker build -t hyperliquid-bot:local .
```
Expected: `Successfully built ...` (no errors)

- [ ] **Step 4: Create `k8s/pvc.yaml`**

```bash
mkdir -p k8s
```

`k8s/pvc.yaml`:
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: hyperliquid-bot-pvc
  namespace: trading
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
```

- [ ] **Step 5: Create `k8s/secret.yaml`**

```yaml
# TEMPLATE — nooit echte waarden committen naar git.
# Maak de secret aan via:
#   kubectl create secret generic hyperliquid-secrets \
#     --namespace=trading \
#     --from-literal=private_key=0x... \
#     --from-literal=anthropic_api_key=sk-ant-... \
#     --from-literal=telegram_bot_token=... \
#     --from-literal=telegram_chat_id=...
apiVersion: v1
kind: Secret
metadata:
  name: hyperliquid-secrets
  namespace: trading
type: Opaque
stringData:
  private_key: "CHANGE_ME_0x..."
  anthropic_api_key: "CHANGE_ME_sk-ant-..."
  telegram_bot_token: "CHANGE_ME_..."
  telegram_chat_id: "CHANGE_ME_..."
```

- [ ] **Step 6: Create `k8s/configmap.yaml`**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: hyperliquid-bot-config
  namespace: trading
data:
  settings.yaml: |
    strategy:
      swing_n: 3
      swing_lookback: 3
      equal_tolerance: 0.0015
      impulse_min_body_pct: 0.60
      impulse_min_move_pct: 0.003
      impulse_volume_multiplier: 1.5
      zone_proximity_pct: 0.02
      momentum_strong_body_pct: 0.60
      momentum_weak_body_pct: 0.30
      order_wall_threshold_btc: 200
      order_wall_buckets: 0.001

    risk:
      risk_per_trade: 0.01
      max_leverage: 2
      max_positions: 5
      max_correlated_positions: 3
      min_risk_reward: 2.0
      stop_buffer_pct: 0.001
      atr_period: 14
      atr_stop_multiplier: 1.5
      max_trade_duration_hours: 24
      avg_trade_duration_hours: 12
      daily_loss_alert_pct: 0.10
      weekly_loss_alert_pct: 0.25

    timeframes:
      trend: "4h"
      entry: "1h"
      candle_lookback: 200

    session_hours_utc:
      london_open: 8
      london_close: 12
      ny_open: 13
      ny_close: 17

    logging:
      log_dir: "logs"
      database_path: "database/bot.db"

  coins.yaml: |
    active_coins:
      - symbol: BTC
        min_daily_volume_usd: 50000000
        active: true
      - symbol: ETH
        min_daily_volume_usd: 50000000
        active: true
      - symbol: SOL
        min_daily_volume_usd: 50000000
        active: true
```

- [ ] **Step 7: Create `k8s/deployment.yaml`**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: hyperliquid-bot
  namespace: trading
  labels:
    app: hyperliquid-bot
spec:
  selector:
    app: hyperliquid-bot
  ports:
    - name: metrics
      port: 8080
      targetPort: 8080
  type: ClusterIP
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hyperliquid-bot
  namespace: trading
spec:
  replicas: 1
  selector:
    matchLabels:
      app: hyperliquid-bot
  template:
    metadata:
      labels:
        app: hyperliquid-bot
    spec:
      containers:
        - name: bot
          image: your-registry/hyperliquid-bot:latest
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          ports:
            - containerPort: 8080
              name: metrics
          env:
            - name: HYPERLIQUID_TESTNET
              value: "true"
            - name: LOG_DIR
              value: "/data/logs"
            - name: DATABASE_PATH
              value: "/data/bot.db"
            - name: METRICS_PORT
              value: "8080"
            - name: HYPERLIQUID_PRIVATE_KEY
              valueFrom:
                secretKeyRef:
                  name: hyperliquid-secrets
                  key: private_key
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: hyperliquid-secrets
                  key: anthropic_api_key
                  optional: true
            - name: TELEGRAM_BOT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: hyperliquid-secrets
                  key: telegram_bot_token
                  optional: true
            - name: TELEGRAM_CHAT_ID
              valueFrom:
                secretKeyRef:
                  name: hyperliquid-secrets
                  key: telegram_chat_id
                  optional: true
          volumeMounts:
            - name: data
              mountPath: /data
            - name: config
              mountPath: /app/config
          livenessProbe:
            httpGet:
              path: /metrics
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 60
            failureThreshold: 3
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: hyperliquid-bot-pvc
        - name: config
          configMap:
            name: hyperliquid-bot-config
```

- [ ] **Step 8: Create `k8s/servicemonitor.yaml`**

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: hyperliquid-bot
  namespace: trading
  labels:
    app: hyperliquid-bot
spec:
  selector:
    matchLabels:
      app: hyperliquid-bot
  endpoints:
    - port: metrics
      interval: 30s
      path: /metrics
```

- [ ] **Step 9: Final test suite run**

```bash
pytest -v
```
Expected: 99 tests `PASSED`

- [ ] **Step 10: Commit**

```bash
git add .env.example Dockerfile k8s/
git commit -m "feat: add Dockerfile and K8s manifests for production deployment"
```

---

## Testnet Wallet Setup (manual, one-time)

Before running with real orders, complete these steps:

**1. Generate a dedicated testnet keypair** — never use your real wallet:
```python
from eth_account import Account
acct = Account.create()
print("Address:", acct.address)
print("Key:", acct.key.hex())
```

**2. Claim testnet funds:**
- Go to `app.hyperliquid-testnet.xyz`
- Connect the address from step 1
- Claim free USDC

**3. Configure `.env`:**
```bash
cp .env.example .env
# Edit .env: set HYPERLIQUID_PRIVATE_KEY=0x<key from step 1>
```

**4. Run locally:**
```bash
python -m src.main
```
Expected logs: `Metrics server gestart op poort 8080`, analysis loop runs for BTC/ETH/SOL, first order attempted within the hour.

**5. Verify metrics endpoint:**
```bash
curl http://localhost:8080/metrics | grep bot_
```
Expected: All `bot_*` metrics visible.

---

## Spec Coverage Self-Review

| Spec requirement | Task |
|---|---|
| `src/metrics/prometheus_metrics.py` — registry + HTTP server | Task 1 |
| All metrics from spec section 5 (trading + RED/USE/Golden Signals) | Task 1 |
| `src/execution/trade_executor.py` — limit orders via SDK | Task 2 |
| SQLite WAL mode for thread safety | Task 2 (database.py) |
| `src/execution/position_manager.py` — Loop 2, 30s, SL/target/timeout | Task 3 |
| `src/alerts/telegram_alert.py` — trade open/close/error/daily-loss | Task 4 |
| `src/main.py` — 3 threads, metrics throughout | Task 5 |
| `bot_consecutive_errors` gauge + Telegram alert at 3+ errors | Task 5 |
| LOG_DIR / DATABASE_PATH env var overrides | Task 5 |
| `.env.example` | Task 6 |
| `Dockerfile` | Task 6 |
| `k8s/deployment.yaml` — liveness probe on `/metrics` | Task 6 |
| `k8s/pvc.yaml` — data survives pod restarts | Task 6 |
| `k8s/configmap.yaml` — settings + coins | Task 6 |
| `k8s/secret.yaml` — template, no real values | Task 6 |
| `k8s/servicemonitor.yaml` — Prometheus scrape every 30s | Task 6 |
