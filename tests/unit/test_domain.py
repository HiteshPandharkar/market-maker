from datetime import datetime, timezone
from decimal import Decimal

import pytest

from l3sim.domain import (
    AddOrderEvent,
    CancelOrderEvent,
    EventType,
    MarketOrderEvent,
    ModifyOrderEvent,
    Order,
    OrderType,
    PriceLevel,
    Side,
    Trade,
)
from l3sim.domain.exceptions import InvalidEventError, InvalidOrderError, InvalidTradeError


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def test_limit_order_defaults_remaining_quantity_and_is_immutable() -> None:
    order = Order("o-1", NOW, Side.BUY, Decimal("100.00"), 500)

    assert order.remaining_quantity == 500
    assert order.with_remaining(200).remaining_quantity == 200
    assert order.remaining_quantity == 500


@pytest.mark.parametrize(
    ("order_type", "price"),
    [(OrderType.LIMIT, None), (OrderType.MARKET, Decimal("100"))],
)

def test_order_requires_price_consistent_with_type(order_type: OrderType, price: Decimal | None) -> None:
    with pytest.raises(InvalidOrderError):
        Order("o-1", NOW, Side.BUY, price, 1, order_type)


def test_order_rejects_remaining_quantity_outside_submitted_quantity() -> None:
    with pytest.raises(InvalidOrderError):
        Order("o-1", NOW, Side.BUY, Decimal("100"), 10, remaining_quantity=11)


def test_trade_requires_positive_decimal_price_and_quantity() -> None:
    with pytest.raises(InvalidTradeError):
        Trade("t-1", NOW, "buy", "sell", Decimal("0"), 5)


def test_input_events_are_classified() -> None:
    limit = Order("l-1", NOW, Side.SELL, Decimal("101"), 10)
    market = Order("m-1", NOW, Side.BUY, None, 10, OrderType.MARKET)

    assert AddOrderEvent("e-1", NOW, limit).event_type is EventType.ADD_ORDER
    assert MarketOrderEvent("e-2", NOW, market).event_type is EventType.MARKET_ORDER
    assert CancelOrderEvent("e-3", NOW, "l-1", 2).event_type is EventType.CANCEL_ORDER


def test_input_event_type_must_match_order_instruction() -> None:
    limit = Order("l-1", NOW, Side.SELL, Decimal("101"), 10)
    market = Order("m-1", NOW, Side.BUY, None, 10, OrderType.MARKET)

    with pytest.raises(InvalidEventError):
        MarketOrderEvent("e-1", NOW, limit)
    with pytest.raises(InvalidEventError):
        AddOrderEvent("e-2", NOW, market)


def test_modify_event_requires_a_valid_change() -> None:
    with pytest.raises(InvalidEventError):
        ModifyOrderEvent("e-1", NOW, "o-1")
    with pytest.raises(InvalidEventError):
        ModifyOrderEvent("e-2", NOW, "o-1", quantity=0)


@pytest.mark.parametrize(
    ("side", "price"),
    [("BUY", Decimal("100")), (Side.BUY, 100), (Side.BUY, Decimal("0"))],
)
def test_price_level_requires_side_and_positive_decimal_price(side: object, price: object) -> None:
    with pytest.raises(InvalidOrderError):
        PriceLevel(side, price)  # type: ignore[arg-type]


def test_price_level_maintains_fifo_and_aggregate_quantity() -> None:
    level = PriceLevel(Side.BUY, Decimal("100"))
    first = Order("o-1", NOW, Side.BUY, Decimal("100"), 10)
    second = Order("o-2", NOW, Side.BUY, Decimal("100"), 20)

    level.add_order(first)
    level.add_order(second)

    assert level.orders == (first, second)
    assert level.oldest_order() is first
    assert level.get_order("o-2") is second
    assert level.total_quantity == 30
    assert len(level) == 2
    assert not level.is_empty


def test_price_level_removal_updates_queue_and_empty_state() -> None:
    level = PriceLevel(Side.BUY, Decimal("100"))
    first = Order("o-1", NOW, Side.BUY, Decimal("100"), 10)
    second = Order("o-2", NOW, Side.BUY, Decimal("100"), 20)
    level.add_order(first)
    level.add_order(second)

    assert level.remove_order("missing") is None
    assert level.remove_order("o-1") is first
    assert level.orders == (second,)
    assert level.oldest_order() is second
    assert level.total_quantity == 20

    assert level.remove_order("o-2") is second
    assert level.is_empty
    assert level.oldest_order() is None
    assert level.total_quantity == 0


def test_price_level_replacement_preserves_fifo_priority() -> None:
    level = PriceLevel(Side.BUY, Decimal("100"))
    first = Order("o-1", NOW, Side.BUY, Decimal("100"), 10)
    second = Order("o-2", NOW, Side.BUY, Decimal("100"), 20)
    level.add_order(first)
    level.add_order(second)

    replacement = first.with_remaining(4)
    level.replace_order(replacement)

    assert level.orders == (replacement, second)
    assert level.oldest_order() is replacement
    assert level.total_quantity == 24


def test_price_level_rejects_invalid_resting_orders_and_replacements() -> None:
    level = PriceLevel(Side.BUY, Decimal("100"))
    valid = Order("o-1", NOW, Side.BUY, Decimal("100"), 10)
    level.add_order(valid)

    invalid_orders = (
        "not an order",
        Order("market", NOW, Side.BUY, None, 10, OrderType.MARKET),
        Order("sell", NOW, Side.SELL, Decimal("100"), 10),
        Order("other-price", NOW, Side.BUY, Decimal("101"), 10),
        valid.with_remaining(0),
    )
    for order in invalid_orders:
        with pytest.raises(InvalidOrderError):
            level.add_order(order)  # type: ignore[arg-type]

    with pytest.raises(InvalidOrderError, match="duplicate"):
        level.add_order(valid)
    with pytest.raises(InvalidOrderError, match="not present"):
        level.replace_order(Order("missing", NOW, Side.BUY, Decimal("100"), 10))
