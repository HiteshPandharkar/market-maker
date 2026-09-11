"""Individual L3 order representation."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .enums import OrderType, Side
from .exceptions import InvalidOrderError

OrderId = str | int


@dataclass(frozen=True, slots=True)
class Order:
    """An immutable order snapshot.

    ``remaining_quantity`` is the outstanding quantity represented by this
    snapshot. Matching code must create a replacement via ``with_remaining``
    instead of mutating an order already held by the book.
    """

    order_id: OrderId
    timestamp: datetime
    side: Side
    price: Decimal | None
    quantity: int
    order_type: OrderType = OrderType.LIMIT
    remaining_quantity: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise InvalidOrderError("timestamp must be a datetime")
        if not isinstance(self.side, Side):
            raise InvalidOrderError("side must be a Side")
        if not isinstance(self.order_type, OrderType):
            raise InvalidOrderError("order_type must be an OrderType")
        if not isinstance(self.quantity, int) or isinstance(self.quantity, bool) or self.quantity <= 0:
            raise InvalidOrderError("quantity must be a positive integer")

        remaining = self.quantity if self.remaining_quantity is None else self.remaining_quantity
        if not isinstance(remaining, int) or isinstance(remaining, bool) or not 0 <= remaining <= self.quantity:
            raise InvalidOrderError("remaining_quantity must be between zero and quantity")
        object.__setattr__(self, "remaining_quantity", remaining)

        if self.order_type is OrderType.LIMIT:
            if not isinstance(self.price, Decimal) or self.price <= 0:
                raise InvalidOrderError("a limit order requires a positive Decimal price")
        elif self.price is not None:
            raise InvalidOrderError("a market order must not have a price")

    @property
    def is_filled(self) -> bool:
        """Whether the order has no outstanding quantity."""

        return self.remaining_quantity == 0

    def with_remaining(self, remaining_quantity: int) -> "Order":
        """Return a new snapshot with the requested outstanding quantity."""

        return Order(
            order_id=self.order_id,
            timestamp=self.timestamp,
            side=self.side,
            price=self.price,
            quantity=self.quantity,
            order_type=self.order_type,
            remaining_quantity=remaining_quantity,
        )
