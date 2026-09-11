"""A reproducible, book-aware source of synthetic input events."""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import random

from l3sim.domain import (
    AddOrderEvent,
    CancelOrderEvent,
    MarketOrderEvent,
    ModifyOrderEvent,
    Order,
    OrderBook,
    OrderType,
    Side,
)
from l3sim.domain.event import Event

from .config import GeneratorConfig


class Generator:
    """Generate stochastic, valid input events without changing an engine.

    Supply the engine's current :class:`OrderBook` to :meth:`next_event` (or
    at construction).  The caller remains responsible for processing events;
    this separation makes the generator usable in tests and simulations alike.
    """

    __slots__ = ("config", "_book", "_rng", "_timestamp", "_event_sequence", "_order_sequence")

    def __init__(self, config: GeneratorConfig | None = None, *, seed: int | None = None, book: OrderBook | None = None) -> None:
        self.config = config or GeneratorConfig()
        self._book = book
        self._rng = random.Random(seed)
        self._timestamp = self.config.start_time
        self._event_sequence = 0
        self._order_sequence = 0

    @property
    def timestamp(self):
        """Timestamp of the most recently produced event."""

        return self._timestamp

    def next_event(self, book: OrderBook | None = None) -> Event:
        """Return the next event, advancing simulated time.

        Cancellation and modification requests fall back to a limit order when
        no live order exists, so every normal generated event is processable.
        """

        active_book = book if book is not None else self._book
        self._timestamp += timedelta(seconds=self._rng.expovariate(self.config.total_rate))
        event_type = self._event_type(active_book)
        if event_type == "limit":
            return self._limit_event(active_book)
        if event_type == "market":
            return self._market_event()
        order = self._select_order(active_book)
        if order is None:
            return self._limit_event(active_book)
        if event_type == "cancel":
            return CancelOrderEvent(self._event_id(), self._timestamp, order.order_id, self._rng.randint(1, order.remaining_quantity))
        return self._modify_event(order, active_book)

    generate_event = next_event

    def initial_book_events(self, levels: int = 4) -> tuple[AddOrderEvent, ...]:
        """Generate a symmetric, non-crossing initial book around the mid."""

        if not isinstance(levels, int) or isinstance(levels, bool) or levels <= 0:
            raise ValueError("levels must be a positive integer")
        events: list[AddOrderEvent] = []
        for offset in range(1, levels + 1):
            for side in (Side.BUY, Side.SELL):
                price = self.config.initial_mid_price + (self.config.tick_size * offset * (1 if side is Side.SELL else -1))
                events.append(AddOrderEvent(self._event_id(), self._timestamp, self._limit_order(side, price)))
        return tuple(events)

    def _event_type(self, book: OrderBook | None) -> str:
        weights = (("limit", self.config.limit_order_rate), ("market", self.config.market_order_rate), ("cancel", self.config.cancel_rate), ("modify", self.config.modify_rate))
        eligible = [(name, weight) for name, weight in weights if weight > 0 and (name in {"limit", "market"} or book is not None and len(book) > 0)]
        # A cancellation-only or modification-only configuration has no valid
        # event while the book is empty. Seed it with a passive limit order.
        if not eligible:
            return "limit"
        total = sum(weight for _, weight in eligible)
        mark = self._rng.random() * total
        for name, weight in eligible:
            mark -= weight
            if mark <= 0:
                return name
        return eligible[-1][0]

    def _limit_event(self, book: OrderBook | None) -> AddOrderEvent:
        side = self._side()
        mid = book.mid_price() if book is not None else None
        reference = mid or self.config.initial_mid_price
        distance = max(1, int(self._rng.expovariate(1 / self.config.mean_price_distance_ticks)) + 1)
        price = self._tick(reference + self.config.tick_size * distance * (1 if side is Side.SELL else -1))
        if book is not None:
            # Keep ordinary synthetic limits passive; marketable limits are an
            # explicit future policy rather than an accidental crossed book.
            if side is Side.BUY and book.best_ask() is not None:
                price = max(self.config.tick_size, min(price, book.best_ask() - self.config.tick_size))
            elif side is Side.SELL and book.best_bid() is not None:
                price = max(price, book.best_bid() + self.config.tick_size)
        return AddOrderEvent(self._event_id(), self._timestamp, self._limit_order(side, price))

    def _market_event(self) -> MarketOrderEvent:
        order = Order(self._order_id(), self._timestamp, self._side(), None, self._quantity(), OrderType.MARKET)
        return MarketOrderEvent(self._event_id(), self._timestamp, order)

    def _modify_event(self, order: Order, book: OrderBook | None) -> ModifyOrderEvent:
        if self._rng.random() < 0.5:
            return ModifyOrderEvent(self._event_id(), self._timestamp, order.order_id, quantity=self._quantity())
        # A one-tick outward price change remains passive and intentionally
        # loses queue priority under the matching engine's documented rules.
        assert order.price is not None
        direction = -1 if order.side is Side.BUY else 1
        new_price = self._tick(order.price + direction * self.config.tick_size)
        return ModifyOrderEvent(
            self._event_id(),
            self._timestamp,
            order.order_id,
            price=max(self.config.tick_size, new_price),
        )

    def _limit_order(self, side: Side, price: Decimal) -> Order:
        return Order(self._order_id(), self._timestamp, side, price, self._quantity())

    def _select_order(self, book: OrderBook | None) -> Order | None:
        if book is None or book.is_empty:
            return None
        orders = [order for level in (*book.bid_levels, *book.ask_levels) for order in level.orders]
        return self._rng.choice(orders)

    def _quantity(self) -> int:
        sampled = round(self._rng.lognormvariate(self.config.quantity_log_mean, self.config.quantity_log_stddev))
        return max(self.config.quantity_min, min(self.config.quantity_max, sampled))

    def _side(self) -> Side:
        return Side.BUY if self._rng.random() < self.config.buy_probability else Side.SELL

    def _tick(self, price: Decimal) -> Decimal:
        # Decimal quantization by a non-power-of-ten tick does not enforce a
        # tick multiple, hence divide, round, then multiply.
        units = (price / self.config.tick_size).to_integral_value(rounding=ROUND_HALF_UP)
        return units * self.config.tick_size

    def _event_id(self) -> str:
        self._event_sequence += 1
        return f"event-{self._event_sequence}"

    def _order_id(self) -> str:
        self._order_sequence += 1
        return f"order-{self._order_sequence}"


SyntheticEventGenerator = Generator
