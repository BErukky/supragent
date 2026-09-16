import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "execution"))

import trade_tracker


@pytest.fixture(autouse=True)
def isolated_trades_env(tmp_path, monkeypatch):
    """Isolate trades and history JSON files for each test."""
    trades_path = str(tmp_path / "trades.json")
    history_path = str(tmp_path / "trade_history.json")
    monkeypatch.setattr(trade_tracker, "TRADES_FILE", trades_path)
    monkeypatch.setattr(trade_tracker, "HISTORY_FILE", history_path)
    yield


def test_register_and_filter_trades_by_chat_id():
    # User 1 registers a trade
    t1 = trade_tracker.register_trade(
        symbol="EUR/USD",
        direction="LONG",
        entry=1.0850,
        sl=1.0800,
        tps=[1.0900, 1.0950],
        size_units=10000,
        risk_usd=50.0,
        chat_id="user_123"
    )
    assert t1["chat_id"] == "user_123"

    # User 2 registers a trade on the same symbol with different entry/SL
    t2 = trade_tracker.register_trade(
        symbol="EUR/USD",
        direction="LONG",
        entry=1.0860,
        sl=1.0810,
        tps=[1.0920],
        size_units=5000,
        risk_usd=25.0,
        chat_id="user_456"
    )
    assert t2["chat_id"] == "user_456"

    # All open trades (admin view)
    all_open = trade_tracker.get_open_trades()
    assert len(all_open) == 2

    # Filtered by chat_id
    user1_trades = trade_tracker.get_open_trades(chat_id="user_123")
    assert len(user1_trades) == 1
    assert user1_trades[0]["entry"] == 1.0850

    user2_trades = trade_tracker.get_open_trades(chat_id="user_456")
    assert len(user2_trades) == 1
    assert user2_trades[0]["entry"] == 1.0860

    # User 3 (no trades)
    user3_trades = trade_tracker.get_open_trades(chat_id="user_789")
    assert len(user3_trades) == 0


def test_format_open_trades_user_isolation():
    trade_tracker.register_trade(
        symbol="XAU/USD",
        direction="LONG",
        entry=2500.0,
        sl=2480.0,
        tps=[2540.0],
        size_units=1,
        risk_usd=20.0,
        chat_id="user_1"
    )
    trade_tracker.register_trade(
        symbol="BTC/USD",
        direction="SHORT",
        entry=60000.0,
        sl=61000.0,
        tps=[58000.0],
        size_units=0.1,
        risk_usd=100.0,
        chat_id="user_2"
    )

    fmt_user1 = trade_tracker.format_open_trades(chat_id="user_1")
    assert "XAU/USD" in fmt_user1
    assert "BTC/USD" not in fmt_user1

    fmt_user2 = trade_tracker.format_open_trades(chat_id="user_2")
    assert "BTC/USD" in fmt_user2
    assert "XAU/USD" not in fmt_user2

    fmt_user3 = trade_tracker.format_open_trades(chat_id="user_3")
    assert "No open trades" in fmt_user3


def test_close_trade_user_isolation():
    t1 = trade_tracker.register_trade(
        symbol="GBP/USD",
        direction="LONG",
        entry=1.3000,
        sl=1.2950,
        tps=[1.3100],
        size_units=10000,
        risk_usd=50.0,
        chat_id="user_1"
    )

    # User 2 tries to close User 1's trade by ID
    closed = trade_tracker.close_trade(t1["id"], exit_price=1.3050, chat_id="user_2")
    assert closed is None
    assert len(trade_tracker.get_open_trades(chat_id="user_1")) == 1

    # User 1 closes their own trade
    closed = trade_tracker.close_trade(t1["id"], exit_price=1.3050, chat_id="user_1")
    assert closed is not None
    assert closed["pnl_usd"] == 50.0
    assert len(trade_tracker.get_open_trades(chat_id="user_1")) == 0


def test_stats_and_history_user_isolation():
    t1 = trade_tracker.register_trade(
        symbol="EUR/USD",
        direction="LONG",
        entry=1.0800,
        sl=1.0750,
        tps=[1.0900],
        size_units=10000,
        risk_usd=50.0,
        chat_id="user_A"
    )
    t2 = trade_tracker.register_trade(
        symbol="USD/JPY",
        direction="SHORT",
        entry=150.0,
        sl=151.0,
        tps=[148.0],
        size_units=100,
        risk_usd=100.0,
        chat_id="user_B"
    )

    trade_tracker.close_trade(t1["id"], exit_price=1.0900, chat_id="user_A")
    trade_tracker.close_trade(t2["id"], exit_price=151.0, chat_id="user_B")

    # User A stats
    stats_a = trade_tracker.get_stats(chat_id="user_A")
    assert stats_a["total"] == 1
    assert stats_a["wins"] == 1
    assert stats_a["losses"] == 0
    assert stats_a["net_pnl"] == 100.0

    # User B stats
    stats_b = trade_tracker.get_stats(chat_id="user_B")
    assert stats_b["total"] == 1
    assert stats_b["wins"] == 0
    assert stats_b["losses"] == 1
    assert stats_b["net_pnl"] == -100.0

    # Formatted history
    hist_a = trade_tracker.format_history(chat_id="user_A")
    assert "EUR/USD" in hist_a
    assert "USD/JPY" not in hist_a


def test_check_trades_symbol_caching_and_sl():
    # Register 2 trades for same symbol with different SLs
    t1 = trade_tracker.register_trade(
        symbol="XAU/USD",
        direction="LONG",
        entry=2500.0,
        sl=2480.0,
        tps=[2550.0],
        size_units=1,
        risk_usd=20.0,
        chat_id="user_1"
    )
    t2 = trade_tracker.register_trade(
        symbol="XAU/USD",
        direction="LONG",
        entry=2510.0,
        sl=2490.0,
        tps=[2550.0],
        size_units=1,
        risk_usd=20.0,
        chat_id="user_2"
    )

    send_messages = []
    def mock_send(cid, msg):
        send_messages.append((cid, msg))

    # Mock _get_live_price to verify it is called only ONCE for XAU/USD per cycle
    # Price is 2485.0 -> t2 is stopped out (SL 2490.0), t1 is still open (SL 2480.0)
    with patch.object(trade_tracker, "_get_live_price", return_value=2485.0) as mock_price:
        trade_tracker._check_trades(mock_send)
        assert mock_price.call_count == 1

    # Check alert was sent to user_2 only
    assert len(send_messages) == 1
    assert send_messages[0][0] == "user_2"
    assert "STOPPED OUT" in send_messages[0][1]

    # Verify open trades state
    open_trades_u1 = trade_tracker.get_open_trades("user_1")
    open_trades_u2 = trade_tracker.get_open_trades("user_2")
    assert len(open_trades_u1) == 1
    assert len(open_trades_u2) == 0
