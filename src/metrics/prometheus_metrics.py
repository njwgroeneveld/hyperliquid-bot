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
