from datetime import datetime, timezone
from decimal import Decimal

import pytest

from l3sim.analytics import ask_depth, bid_depth, imbalance, microprice
from l3sim.domain import Order, OrderBook, Side


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def add(book: OrderBook, order_id: str, side: Side, price: str, quantity: int) -> None:
    book.add_order(Order(order_id, NOW, side, Decimal(price), quantity))


def test_depth_is_best_to_worst_and_retains_l3_order_counts() -> None:
    book = OrderBook()
    add(book, "b-1", Side.BUY, "100", 4)
    add(book, "b-2", Side.BUY, "100", 6)
    add(book, "b-3", Side.BUY, "99", 9)
    add(book, "a-1", Side.SELL, "101", 3)

    assert [(level.price, level.quantity, level.order_count) for level in bid_depth(book, 2)] == [
        (Decimal("100"), 10, 2),
        (Decimal("99"), 9, 1),
    ]
    assert [(level.price, level.quantity) for level in ask_depth(book)] == [(Decimal("101"), 3)]


def test_imbalance_and_microprice_use_requested_and_top_depth() -> None:
    book = OrderBook()
    add(book, "b-1", Side.BUY, "100", 6)
    add(book, "b-2", Side.BUY, "99", 100)
    add(book, "a-1", Side.SELL, "101", 4)
    add(book, "a-2", Side.SELL, "102", 100)

    assert imbalance(book) == Decimal("0.2")
    assert microprice(book) == Decimal("100.6")
    assert imbalance(book, 2) == Decimal("0.009523809523809523809523809524")


def test_metrics_are_undefined_without_both_sides() -> None:
    book = OrderBook()
    add(book, "b-1", Side.BUY, "100", 1)

    assert microprice(book) is None
    assert imbalance(OrderBook()) is None
    with pytest.raises(ValueError, match="positive"):
        bid_depth(book, 0)
