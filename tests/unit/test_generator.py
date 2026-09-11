from datetime import datetime, timezone
from decimal import Decimal

from l3sim.domain import (
    AddOrderEvent,
    CancelOrderEvent,
    MarketOrderEvent,
    ModifyOrderEvent,
    Order,
    Side,
)
from l3sim.generator import Generator, GeneratorConfig
from l3sim.matching import MatchingEngine


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def resting_order(order_id: str, side: Side, price: str, quantity: int = 10) -> Order:
    return Order(order_id, NOW, side, Decimal(price), quantity)


def populated_engine() -> MatchingEngine:
    engine = MatchingEngine()
    engine.submit(resting_order("bid", Side.BUY, "99.99"))
    engine.submit(resting_order("ask", Side.SELL, "100.01"))
    return engine


def test_same_seed_and_config_produce_the_same_events() -> None:
    config = GeneratorConfig(start_time=NOW)
    first = Generator(config, seed=42)
    second = Generator(config, seed=42)

    assert [first.next_event() for _ in range(20)] == [second.next_event() for _ in range(20)]


def test_event_timestamps_are_strictly_increasing() -> None:
    generator = Generator(GeneratorConfig(start_time=NOW), seed=10)

    timestamps = [generator.next_event().timestamp for _ in range(10)]

    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)


def test_limit_order_generation_respects_quantity_bounds_and_tick_size() -> None:
    config = GeneratorConfig(
        start_time=NOW,
        limit_order_rate=1,
        market_order_rate=0,
        cancel_rate=0,
        modify_rate=0,
        quantity_min=17,
        quantity_max=17,
    )
    event = Generator(config, seed=2).next_event()

    assert isinstance(event, AddOrderEvent)
    assert event.order.quantity == 17
    assert event.order.price is not None
    assert event.order.price % config.tick_size == 0


def test_generated_limit_orders_do_not_cross_a_live_book() -> None:
    engine = populated_engine()
    config = GeneratorConfig(
        start_time=NOW,
        limit_order_rate=1,
        market_order_rate=0,
        cancel_rate=0,
        modify_rate=0,
    )
    generator = Generator(config, seed=3, book=engine.book)

    events = [generator.next_event() for _ in range(20)]

    for event in events:
        assert isinstance(event, AddOrderEvent)
        assert event.order.price is not None
        if event.order.side is Side.BUY:
            assert event.order.price < engine.book.best_ask()
        else:
            assert event.order.price > engine.book.best_bid()


def test_market_only_configuration_generates_market_orders() -> None:
    config = GeneratorConfig(
        start_time=NOW,
        limit_order_rate=0,
        market_order_rate=1,
        cancel_rate=0,
        modify_rate=0,
    )

    event = Generator(config, seed=4).next_event()

    assert isinstance(event, MarketOrderEvent)
    assert event.order.price is None


def test_cancellation_selects_a_live_order_and_valid_quantity() -> None:
    engine = populated_engine()
    config = GeneratorConfig(
        start_time=NOW,
        limit_order_rate=0,
        market_order_rate=0,
        cancel_rate=1,
        modify_rate=0,
    )

    event = Generator(config, seed=5, book=engine.book).next_event()

    assert isinstance(event, CancelOrderEvent)
    order = engine.book.get_order(event.order_id)
    assert order is not None
    assert event.quantity is not None
    assert 1 <= event.quantity <= order.remaining_quantity


def test_modification_selects_a_live_order_with_a_valid_change() -> None:
    engine = populated_engine()
    config = GeneratorConfig(
        start_time=NOW,
        limit_order_rate=0,
        market_order_rate=0,
        cancel_rate=0,
        modify_rate=1,
    )

    event = Generator(config, seed=6, book=engine.book).next_event()

    assert isinstance(event, ModifyOrderEvent)
    assert engine.book.get_order(event.order_id) is not None
    assert event.price is not None or event.quantity is not None


def test_initial_book_has_configured_depth_and_a_positive_spread() -> None:
    config = GeneratorConfig(start_time=NOW, quantity_min=10, quantity_max=10)
    events = Generator(config, seed=7).initial_book_events(levels=3)

    assert len(events) == 6
    bids = [event.order.price for event in events if event.order.side is Side.BUY]
    asks = [event.order.price for event in events if event.order.side is Side.SELL]
    assert max(bids) == Decimal("99.99")
    assert min(asks) == Decimal("100.01")
    assert all(event.order.quantity == 10 for event in events)