"""Immutable views of a simulation's market state."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from l3sim.domain import Order, Side, Trade
from l3sim.domain.event import Event


@dataclass(frozen=True, slots=True)
class PriceLevelSnapshot:
    """The L3 orders and aggregate quantity at one price level."""

    side: Side
    price: Decimal
    orders: tuple[Order, ...]

    @property
    def total_quantity(self) -> int:
        """Outstanding quantity represented by the orders at this level."""

        return sum(order.remaining_quantity for order in self.orders)

    @property
    def order_count(self) -> int:
        """Number of individual resting orders at this price."""

        return len(self.orders)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """The complete observable market state after one input event.

    ``bids`` and ``asks`` are ordered best-to-worst and contain immutable
    :class:`~l3sim.domain.Order` snapshots.  They make historic snapshots
    independent of subsequent mutations to the live order book.
    """

    timestamp: datetime
    event: Event
    trades: tuple[Trade, ...]
    best_bid: Decimal | None
    best_ask: Decimal | None
    mid_price: Decimal | None
    spread: Decimal | None
    bid_depth: int
    ask_depth: int
    total_book_quantity: int
    last_trade_price: Decimal | None
    last_trade_quantity: int | None
    bids: tuple[PriceLevelSnapshot, ...]
    asks: tuple[PriceLevelSnapshot, ...]

    @property
    def book_orders(self) -> tuple[Order, ...]:
        """All resting orders in deterministic book order."""

        return tuple(order for level in (*self.bids, *self.asks) for order in level.orders)


# A descriptive name for callers that prefer not to use the generic term.
MarketSnapshot = Snapshot
