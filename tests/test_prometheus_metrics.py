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
