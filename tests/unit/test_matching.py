import os, sys
sys.path.append(os.getcwd())

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from l3sim.domain import Order, OrderType, Side
from l3sim.domain.exceptions import InvalidOrderError
from l3sim.matching import MatchingEngine


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def limit(order_id: str, side: Side, price: str, quantity: int) -> Order:
    return Order(order_id, NOW, side, Decimal(price), quantity)


def test_marketable_limit_uses_resting_price_and_rests_residual() -> None:
    engine = MatchingEngine()
    engine.submit(limit("ask", Side.SELL, "100", 10))

    trades = engine.submit(limit("buy", Side.BUY, "101", 15))

    assert [(trade.price, trade.quantity) for trade in trades] == [(Decimal("100"), 10)]
    assert engine.book.get_order("ask") is None
    assert engine.book.get_order("buy") == limit("buy", Side.BUY, "101", 15).with_remaining(5)


def test_market_order_consumes_best_prices_then_fifo() -> None:
    engine = MatchingEngine()
    engine.submit(limit("first", Side.SELL, "100", 3))
    engine.submit(limit("second", Side.SELL, "100", 4))
    engine.submit(limit("worse", Side.SELL, "101", 5))
    market_buy = Order("market", NOW, Side.BUY, None, 10, OrderType.MARKET)

    trades = engine.process_market_order(market_buy)

    assert [(trade.sell_order_id, trade.price, trade.quantity) for trade in trades] == [
        ("first", Decimal("100"), 3),
        ("second", Decimal("100"), 4),
        ("worse", Decimal("101"), 3),
    ]
    assert engine.book.get_order("worse").remaining_quantity == 2
    assert engine.book.get_order("market") is None

def test_non_marketable_limit_rests_without_trades() -> None:
    engine = MatchingEngine()
    engine.submit(limit("ask", Side.SELL, "101", 10))

    assert engine.submit(limit("buy", Side.BUY, "100", 10)) == ()
    assert engine.book.get_order("buy") == limit("buy", Side.BUY, "100", 10)


def test_rejects_duplicate_active_and_filled_incoming_orders() -> None:
    engine = MatchingEngine()
    engine.submit(limit("bid", Side.BUY, "100", 10))

    with pytest.raises(InvalidOrderError, match="duplicate"):
        engine.submit(limit("bid", Side.BUY, "99", 10))
    with pytest.raises(InvalidOrderError, match="filled"):
        engine.submit(limit("filled", Side.BUY, "99", 10).with_remaining(0))


def test_cancel_removes_an_order_or_reduces_it_without_changing_priority() -> None:
    engine = MatchingEngine()
    engine.submit(limit("first", Side.BUY, "100", 10))
    engine.submit(limit("second", Side.BUY, "100", 10))

    assert engine.cancel("first", 4).remaining_quantity == 6
    assert engine.book.get_price_level(Side.BUY, Decimal("100")).orders[0].order_id == "first"
    assert engine.cancel("second").order_id == "second"
    assert engine.book.get_order("second") is None


def test_cancel_rejects_unknown_orders_and_excessive_quantities() -> None:
    engine = MatchingEngine()
    engine.submit(limit("bid", Side.BUY, "100", 10))

    with pytest.raises(InvalidOrderError, match="not present"):
        engine.cancel("missing")
    with pytest.raises(InvalidOrderError, match="cannot exceed"):
        engine.cancel("bid", 11)


def test_modify_quantity_reduction_preserves_priority_but_increase_loses_it() -> None:
    engine = MatchingEngine()
    engine.submit(limit("first", Side.BUY, "100", 10))
    engine.submit(limit("second", Side.BUY, "100", 10))

    assert engine.modify("first", quantity=6) == ()
    assert [order.order_id for order in engine.book.get_price_level(Side.BUY, Decimal("100")).orders] == ["first", "second"]

    assert engine.modify("first", quantity=12) == ()
    assert [order.order_id for order in engine.book.get_price_level(Side.BUY, Decimal("100")).orders] == ["second", "first"]
    assert engine.book.get_order("first") == limit("first", Side.BUY, "100", 12)


def test_modify_price_loses_priority_and_can_match_immediately() -> None:
    engine = MatchingEngine()
    engine.submit(limit("ask", Side.SELL, "101", 10))
    engine.submit(limit("bid", Side.BUY, "100", 10))

    trades = engine.modify("bid", price=Decimal("101"))

    assert [(trade.price, trade.quantity) for trade in trades] == [(Decimal("101"), 10)]
    assert engine.book.get_order("bid") is None
    assert engine.book.get_order("ask") is None
