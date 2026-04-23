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
