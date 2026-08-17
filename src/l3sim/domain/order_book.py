"""Price-priority collection of resting L3 limit orders."""

from decimal import Decimal

from .enums import OrderType, Side
from .exceptions import InvalidOrderError
from .order import Order, OrderId
from .price_level import PriceLevel


class OrderBook:
    """A two-sided book of resting limit orders.

    The book owns price-level selection and active-order lookup; each
    :class:`PriceLevel` owns FIFO priority among orders at its price.  Matching
    is deliberately left to the matching engine, so ``add_order`` simply adds
    a valid resting limit order even if it would cross the opposite side.
    """

    __slots__ = ("_bids", "_asks", "_order_locations")

    def __init__(self) -> None:
        self._bids: dict[Decimal, PriceLevel] = {}
        self._asks: dict[Decimal, PriceLevel] = {}
        self._order_locations: dict[OrderId, tuple[Side, Decimal]] = {}

    @property
    def bid_levels(self) -> tuple[PriceLevel, ...]:
        """Bid levels from highest to lowest price."""

        return tuple(self._bids[price] for price in sorted(self._bids, reverse=True))

    @property
    def ask_levels(self) -> tuple[PriceLevel, ...]:
        """Ask levels from lowest to highest price."""

        return tuple(self._asks[price] for price in sorted(self._asks))

    @property
    def is_empty(self) -> bool:
        """Whether no orders are resting in the book."""

        return not self._order_locations

    def __len__(self) -> int:
        """Return the number of active resting orders."""

        return len(self._order_locations)

    def best_bid(self) -> Decimal | None:
        """Return the highest resting bid price, if any."""

        return max(self._bids, default=None)

    def best_ask(self) -> Decimal | None:
        """Return the lowest resting ask price, if any."""

        return min(self._asks, default=None)

    def mid_price(self) -> Decimal | None:
        """Return the midpoint of the best bid and ask, if both exist."""

        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid is None or best_ask is None:
            return None
        return (best_bid + best_ask) / Decimal(2)

    def spread(self) -> Decimal | None:
        """Return the best-ask/best-bid spread, if both sides exist."""

        best_bid = self.best_bid()
        best_ask = self.best_ask()
        if best_bid is None or best_ask is None:
            return None
        return best_ask - best_bid

    def get_price_level(self, side: Side, price: Decimal) -> PriceLevel | None:
        """Return a price level by side and price, if it exists."""

        self._validate_side_and_price(side, price)
        return self._levels_for(side).get(price)

    def get_order(self, order_id: OrderId) -> Order | None:
        """Return an active order by ID, if present."""

        location = self._order_locations.get(order_id)
        if location is None:
            return None
        side, price = location
        # The index and price levels are maintained together by this class.
        return self._levels_for(side)[price].get_order(order_id)

    def queue_ahead(self, order_id: OrderId) -> int:
        """Return the resting quantity ahead of an order at its price level.

        Only earlier orders on the same side and at the same price contribute
        to queue position.  Orders at better prices are deliberately excluded:
        this is position within the order's own FIFO queue.
        """

        location = self._order_locations.get(order_id)
        if location is None:
            raise InvalidOrderError(f"order ID is not present in book: {order_id!r}")

        side, price = location
        quantity = 0
        for order in self._levels_for(side)[price].orders:
            if order.order_id == order_id:
                return quantity
            quantity += order.remaining_quantity

        # The location index and price level are maintained atomically.
        raise InvalidOrderError(f"order ID is not present at indexed price level: {order_id!r}")

    def add_order(self, order: Order) -> None:
        """Add a resting limit order, preserving FIFO at its price level."""

        self._validate_resting_order(order)
        if order.order_id in self._order_locations:
            raise InvalidOrderError(f"duplicate active order ID: {order.order_id!r}")

        assert order.price is not None  # guaranteed by _validate_resting_order
        levels = self._levels_for(order.side)
        level = levels.setdefault(order.price, PriceLevel(order.side, order.price))
        level.add_order(order)
        self._order_locations[order.order_id] = (order.side, order.price)

    def remove_order(self, order_id: OrderId) -> Order | None:
        """Remove and return an active order, deleting an empty price level."""

        location = self._order_locations.pop(order_id, None)
        if location is None:
            return None

        side, price = location
        levels = self._levels_for(side)
        level = levels[price]
        order = level.remove_order(order_id)
        if level.is_empty:
            del levels[price]
        return order

    def replace_order(self, order: Order) -> None:
        """Replace an order snapshot without changing its FIFO priority.

        Replacement is only valid for the same active order at the same side
        and price.  A price or side change must be modelled as cancel/re-add,
        which correctly gives the order new queue priority.
        """

        self._validate_resting_order(order)
        location = self._order_locations.get(order.order_id)
        if location is None:
            raise InvalidOrderError(f"order ID is not present in book: {order.order_id!r}")

        assert order.price is not None
        if location != (order.side, order.price):
            raise InvalidOrderError("replacement order side and price must not change")
        self._levels_for(order.side)[order.price].replace_order(order)

    def _levels_for(self, side: Side) -> dict[Decimal, PriceLevel]:
        return self._bids if side is Side.BUY else self._asks

    @staticmethod
    def _validate_side_and_price(side: Side, price: Decimal) -> None:
        if not isinstance(side, Side):
            raise InvalidOrderError("book side must be a Side")
        if not isinstance(price, Decimal) or price <= 0:
            raise InvalidOrderError("book price must be a positive Decimal")

    @classmethod
    def _validate_resting_order(cls, order: Order) -> None:
        if not isinstance(order, Order):
            raise InvalidOrderError("order book can contain only Order instances")
        if order.order_type is not OrderType.LIMIT:
            raise InvalidOrderError("market orders cannot rest in the order book")
        if order.is_filled:
            raise InvalidOrderError("filled orders cannot rest in the order book")
        assert order.price is not None
        cls._validate_side_and_price(order.side, order.price)
