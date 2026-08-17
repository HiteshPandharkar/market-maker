"""Deterministic acceptance scenarios and matching-engine invariants."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from l3sim.domain import Order, OrderType, Side
from l3sim.domain.exceptions import InvalidOrderError
from l3sim.matching import MatchingEngine


NOW = datetime(2026, 8, 16, tzinfo=timezone.utc)


def limit(order_id: str, side: Side, price: str, quantity: int) -> Order:
    return Order(order_id, NOW, side, Decimal(price), quantity)


def market(order_id: str, side: Side, quantity: int) -> Order:
    return Order(order_id, NOW, side, None, quantity, OrderType.MARKET)


def test_add_limit_order_sets_best_bid_and_depth() -> None:
    engine = MatchingEngine()

    engine.submit(limit("bid", Side.BUY, "100", 500))

    assert engine.book.best_bid() == Decimal("100")
    assert engine.book.get_price_level(Side.BUY, Decimal("100")).total_quantity == 500


def test_basic_match_reconciles_trade_and_both_orders() -> None:
    engine = MatchingEngine()
    engine.submit(limit("ask", Side.SELL, "101", 500))

    trades = engine.submit(limit("buy", Side.BUY, "101", 300))

    assert [(trade.price, trade.quantity) for trade in trades] == [(Decimal("101"), 300)]
    assert engine.book.get_order("buy") is None
    assert engine.book.get_order("ask").remaining_quantity == 200
    assert 500 == trades[0].quantity + engine.book.get_order("ask").remaining_quantity
    assert 300 == trades[0].quantity


def test_fifo_fills_oldest_order_before_the_next_order() -> None:
    engine = MatchingEngine()
    engine.submit(limit("A", Side.BUY, "100", 500))
    engine.submit(limit("B", Side.BUY, "100", 300))

    trades = engine.process_market_order(market("sell", Side.SELL, 600))

    assert [(trade.buy_order_id, trade.quantity) for trade in trades] == [
        ("A", 500),
        ("B", 100),
    ]
    assert engine.book.get_order("A") is None
    assert engine.book.get_order("B").remaining_quantity == 200


def test_partial_fill_leaves_positive_remainder_and_removes_filled_market_order() -> None:
    engine = MatchingEngine()
    engine.submit(limit("buy", Side.BUY, "100", 500))

    trades = engine.process_market_order(market("sell", Side.SELL, 200))

    assert [trade.quantity for trade in trades] == [200]
    assert engine.book.get_order("buy").remaining_quantity == 300
    assert engine.book.get_order("sell") is None


def test_market_order_walks_price_levels_best_first() -> None:
    engine = MatchingEngine()
    engine.submit(limit("ask-100", Side.SELL, "100", 200))
    engine.submit(limit("ask-101", Side.SELL, "101", 300))

    trades = engine.process_market_order(market("buy", Side.BUY, 400))

    assert [(trade.price, trade.quantity) for trade in trades] == [
        (Decimal("100"), 200),
        (Decimal("101"), 200),
    ]
    assert engine.book.get_order("ask-100") is None
    assert engine.book.get_order("ask-101").remaining_quantity == 100


def test_partial_cancellation_reconciles_submitted_quantity() -> None:
    engine = MatchingEngine()
    engine.submit(limit("buy", Side.BUY, "100", 500))

    engine.cancel("buy", 200)

    assert engine.book.get_order("buy").remaining_quantity == 300
    assert 500 == 200 + engine.book.get_order("buy").remaining_quantity


def test_marketable_limit_executes_at_resting_price_without_crossing_book() -> None:
    engine = MatchingEngine()
    engine.submit(limit("ask", Side.SELL, "100", 500))

    trades = engine.submit(limit("buy", Side.BUY, "101", 300))

    assert [(trade.price, trade.quantity) for trade in trades] == [(Decimal("100"), 300)]
    assert engine.book.get_order("buy") is None
    assert engine.book.best_bid() is None
    assert engine.book.best_ask() == Decimal("100")


def test_queue_ahead_counts_only_earlier_quantity_at_same_price() -> None:
    engine = MatchingEngine()
    engine.submit(limit("better", Side.BUY, "101", 50))
    engine.submit(limit("A", Side.BUY, "100", 500))
    engine.submit(limit("B", Side.BUY, "100", 300))
    engine.submit(limit("C", Side.BUY, "100", 700))
    engine.submit(limit("behind", Side.BUY, "100", 900))

    assert engine.book.queue_ahead("A") == 0
    assert engine.book.queue_ahead("C") == 800

    with pytest.raises(InvalidOrderError, match="not present"):
        engine.book.queue_ahead("missing")


def test_book_is_uncrossed_and_active_ids_are_unique_after_each_submission() -> None:
    engine = MatchingEngine()
    orders = (
        limit("bid-99", Side.BUY, "99", 100),
        limit("ask-101", Side.SELL, "101", 100),
        limit("bid-101", Side.BUY, "101", 150),
    )

    for order in orders:
        engine.submit(order)
        active = [
            resting
            for level in (*engine.book.bid_levels, *engine.book.ask_levels)
            for resting in level.orders
        ]
        assert len(active) == len({resting.order_id for resting in active})
        assert all(resting.remaining_quantity > 0 for resting in active)
        if engine.book.best_bid() is not None and engine.book.best_ask() is not None:
            assert engine.book.best_bid() < engine.book.best_ask()
