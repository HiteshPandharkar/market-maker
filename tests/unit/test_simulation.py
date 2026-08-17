from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from l3sim.domain import AddOrderEvent, CancelOrderEvent, MarketOrderEvent, Order, OrderType, Side
from l3sim.domain.exceptions import InvalidEventError
from l3sim.simulation import Runner


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def limit(order_id: str, side: Side, price: str, quantity: int) -> Order:
    return Order(order_id, NOW, side, Decimal(price), quantity)


def test_runner_records_an_immutable_l3_state_after_each_event() -> None:
    runner = Runner()
    first = runner.process(AddOrderEvent("e-1", NOW, limit("bid", Side.BUY, "100", 10)))
    second = runner.process(AddOrderEvent("e-2", NOW + timedelta(seconds=1), limit("ask", Side.SELL, "101", 7)))
    runner.process(CancelOrderEvent("e-3", NOW + timedelta(seconds=2), "bid", 4))

    assert first.bid_depth == 10
    assert first.total_book_quantity == 10
    assert first.bids[0].orders[0].remaining_quantity == 10
    assert second.best_bid == Decimal("100")
    assert second.best_ask == Decimal("101")
    assert second.mid_price == Decimal("100.5")
    assert second.spread == Decimal("1")
    assert runner.last_snapshot is not second
    assert runner.last_snapshot.bid_depth == 6


def test_runner_records_trades_and_persists_last_trade_metrics() -> None:
    runner = Runner()
    runner.process(AddOrderEvent("e-1", NOW, limit("ask", Side.SELL, "100", 5)))
    trade_snapshot = runner.process(
        MarketOrderEvent(
            "e-2",
            NOW + timedelta(seconds=1),
            Order("buy", NOW, Side.BUY, None, 3, OrderType.MARKET),
        )
    )
    cancel_snapshot = runner.process(CancelOrderEvent("e-3", NOW + timedelta(seconds=2), "ask"))

    assert [(trade.price, trade.quantity) for trade in trade_snapshot.trades] == [(Decimal("100"), 3)]
    assert trade_snapshot.last_trade_price == Decimal("100")
    assert trade_snapshot.last_trade_quantity == 3
    assert cancel_snapshot.last_trade_price == Decimal("100")
    assert cancel_snapshot.last_trade_quantity == 3


def test_runner_rejects_events_that_go_backwards_in_time() -> None:
    runner = Runner()
    runner.process(AddOrderEvent("e-1", NOW, limit("bid", Side.BUY, "100", 1)))

    with pytest.raises(InvalidEventError, match="chronological"):
        runner.process(AddOrderEvent("e-2", NOW - timedelta(seconds=1), limit("ask", Side.SELL, "101", 1)))
