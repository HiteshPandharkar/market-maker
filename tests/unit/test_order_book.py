from datetime import datetime, timezone
from decimal import Decimal

import pytest

from l3sim.domain import Order, OrderBook, OrderType, Side
from l3sim.domain.exceptions import InvalidOrderError


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def test_order_book_uses_price_time_priority_and_tracks_top_of_book() -> None:
    book = OrderBook()
    bid = Order("bid", NOW, Side.BUY, Decimal("100"), 10)
    better_bid = Order("better-bid", NOW, Side.BUY, Decimal("101"), 20)
    ask = Order("ask", NOW, Side.SELL, Decimal("102"), 30)
    book.add_order(bid)
    book.add_order(better_bid)
    book.add_order(ask)

    assert book.bid_levels == (book.get_price_level(Side.BUY, Decimal("101")), book.get_price_level(Side.BUY, Decimal("100")))
    assert book.ask_levels == (book.get_price_level(Side.SELL, Decimal("102")),)
    assert book.best_bid() == Decimal("101")
    assert book.best_ask() == Decimal("102")
    assert book.mid_price() == Decimal("101.5")
    assert book.spread() == Decimal("1")
    assert book.get_order("bid") is bid
    assert len(book) == 3


def test_order_book_removes_empty_levels_and_rejects_invalid_orders() -> None:
    book = OrderBook()
    bid = Order("bid", NOW, Side.BUY, Decimal("100"), 10)
    book.add_order(bid)

    assert book.remove_order("missing") is None
    assert book.remove_order("bid") is bid
    assert book.get_price_level(Side.BUY, Decimal("100")) is None
    assert book.best_bid() is None
    assert book.is_empty

    with pytest.raises(InvalidOrderError, match="market"):
        book.add_order(Order("market", NOW, Side.BUY, None, 10, OrderType.MARKET))


def test_order_book_replacement_preserves_priority() -> None:
    book = OrderBook()
    first = Order("first", NOW, Side.BUY, Decimal("100"), 10)
    second = Order("second", NOW, Side.BUY, Decimal("100"), 20)
    book.add_order(first)
    book.add_order(second)

    replacement = first.with_remaining(4)
    book.replace_order(replacement)

    assert book.get_price_level(Side.BUY, Decimal("100")).orders == (replacement, second)
