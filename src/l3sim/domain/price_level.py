"""FIFO queue of resting limit orders at a single price."""

from collections import OrderedDict
from decimal import Decimal

from .enums import OrderType, Side
from .exceptions import InvalidOrderError
from .order import Order, OrderId


class PriceLevel:
    """Orders resting at one ``side`` and ``price``, ordered by arrival time.

    Orders are stored by ID in insertion order.  This provides FIFO access to
    the oldest order and constant-time lookup/removal by order ID.
    """

    __slots__ = ("side", "price", "_orders")

    def __init__(self, side: Side, price: Decimal) -> None:
        if not isinstance(side, Side):
            raise InvalidOrderError("price level side must be a Side")
        if not isinstance(price, Decimal) or price <= 0:
            raise InvalidOrderError("price level price must be a positive Decimal")

        self.side = side
        self.price = price
        self._orders: OrderedDict[OrderId, Order] = OrderedDict()

    @property
    def orders(self) -> tuple[Order, ...]:
        """Resting orders in price-time priority order."""

        return tuple(self._orders.values())

    @property
    def total_quantity(self) -> int:
        """Aggregate outstanding quantity at this price level."""

        return sum(order.remaining_quantity for order in self._orders.values())

    @property
    def is_empty(self) -> bool:
        """Whether the level contains no resting orders."""

        return not self._orders

    def __len__(self) -> int:
        return len(self._orders)

    def add_order(self, order: Order) -> None:
        """Append a compatible resting limit order to the end of the queue."""

        self._validate_order(order)
        if order.order_id in self._orders:
            raise InvalidOrderError(f"duplicate order ID at price level: {order.order_id!r}")
        self._orders[order.order_id] = order

    def get_order(self, order_id: OrderId) -> Order | None:
        """Return an order at this level, if present."""

        return self._orders.get(order_id)

    def oldest_order(self) -> Order | None:
        """Return the next order eligible to trade without removing it."""

        return next(iter(self._orders.values()), None)

    def remove_order(self, order_id: OrderId) -> Order | None:
        """Remove and return an order, preserving the queue of other orders."""

        return self._orders.pop(order_id, None)

    def replace_order(self, order: Order) -> None:
        """Replace an existing order snapshot without changing FIFO priority."""

        self._validate_order(order)
        if order.order_id not in self._orders:
            raise InvalidOrderError(f"order ID is not present at price level: {order.order_id!r}")
        self._orders[order.order_id] = order

    def _validate_order(self, order: Order) -> None:
        if not isinstance(order, Order):
            raise InvalidOrderError("price level can contain only Order instances")
        if order.order_type is not OrderType.LIMIT:
            raise InvalidOrderError("price level can contain only limit orders")
        if order.side is not self.side or order.price != self.price:
            raise InvalidOrderError("order side and price must match the price level")
        if order.is_filled:
            raise InvalidOrderError("filled orders cannot rest at a price level")
