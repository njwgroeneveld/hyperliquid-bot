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
