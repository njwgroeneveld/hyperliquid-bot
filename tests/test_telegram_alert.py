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
