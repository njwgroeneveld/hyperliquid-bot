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
