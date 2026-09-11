"""Top-of-book microprice calculation."""

from decimal import Decimal

from l3sim.domain import OrderBook, Side


def microprice(book: OrderBook) -> Decimal | None:
    """Return the queue-size weighted top-of-book price.

    A microprice needs a non-empty best bid and best ask.  It is therefore
    undefined for a one-sided or empty book.
    """

    best_bid = book.best_bid()
    best_ask = book.best_ask()
    if best_bid is None or best_ask is None:
        return None

    bid_level = book.get_price_level(Side.BUY, best_bid)
    ask_level = book.get_price_level(Side.SELL, best_ask)
    assert bid_level is not None and ask_level is not None
    total_quantity = bid_level.total_quantity + ask_level.total_quantity
    if total_quantity == 0:
        return None
    return (
        best_ask * bid_level.total_quantity + best_bid * ask_level.total_quantity
    ) / Decimal(total_quantity)
