"""Order-book imbalance metrics."""

from decimal import Decimal

from l3sim.domain import OrderBook

from .book_metrics import ask_depth, bid_depth


def order_book_imbalance(book: OrderBook, levels: int = 1) -> Decimal | None:
    """Return selected-depth imbalance, or ``None`` when it is undefined.

    The selected levels are counted best-to-worst on each side.  ``None`` is
    returned for an empty selection rather than inventing a value for a zero
    denominator.
    """

    bid_quantity = sum(level.quantity for level in bid_depth(book, levels))
    ask_quantity = sum(level.quantity for level in ask_depth(book, levels))
    total_quantity = bid_quantity + ask_quantity
    if total_quantity == 0:
        return None
    return Decimal(bid_quantity - ask_quantity) / Decimal(total_quantity)


# Short form suitable for charting and interactive use.
imbalance = order_book_imbalance
