"""Read-only top-of-book and depth metrics."""

from dataclasses import dataclass
from decimal import Decimal

from l3sim.domain import OrderBook, Side


@dataclass(frozen=True, slots=True)
class DepthLevel:
    """Aggregate state for one price level in an order book."""

    side: Side
    price: Decimal
    quantity: int
    order_count: int


def _validate_levels(levels: int) -> None:
    if isinstance(levels, bool) or not isinstance(levels, int) or levels < 1:
        raise ValueError("levels must be a positive integer")


def best_bid(book: OrderBook) -> Decimal | None:
    """Return the highest resting bid price, if present."""

    return book.best_bid()


def best_ask(book: OrderBook) -> Decimal | None:
    """Return the lowest resting ask price, if present."""

    return book.best_ask()


def mid_price(book: OrderBook) -> Decimal | None:
    """Return the midpoint of the best bid and ask, if both exist."""

    return book.mid_price()


def spread(book: OrderBook) -> Decimal | None:
    """Return the best-ask minus best-bid spread, if both exist."""

    return book.spread()


def depth(book: OrderBook, side: Side, levels: int = 1) -> tuple[DepthLevel, ...]:
    """Return up to ``levels`` price levels, ordered best-to-worst.

    Each result keeps both L3 order count and the outstanding aggregate
    quantity, so callers need not inspect individual orders for common depth
    calculations.
    """

    _validate_levels(levels)
    if not isinstance(side, Side):
        raise ValueError("side must be a Side")
    source_levels = book.bid_levels if side is Side.BUY else book.ask_levels
    return tuple(
        DepthLevel(level.side, level.price, level.total_quantity, len(level))
        for level in source_levels[:levels]
    )


def bid_depth(book: OrderBook, levels: int = 1) -> tuple[DepthLevel, ...]:
    """Return the selected best bid levels."""

    return depth(book, Side.BUY, levels)


def ask_depth(book: OrderBook, levels: int = 1) -> tuple[DepthLevel, ...]:
    """Return the selected best ask levels."""

    return depth(book, Side.SELL, levels)


class BookMetrics:
    """Convenient namespaced access to standard order-book metrics."""

    best_bid = staticmethod(best_bid)
    best_ask = staticmethod(best_ask)
    mid_price = staticmethod(mid_price)
    spread = staticmethod(spread)
    depth = staticmethod(depth)
    bid_depth = staticmethod(bid_depth)
    ask_depth = staticmethod(ask_depth)
