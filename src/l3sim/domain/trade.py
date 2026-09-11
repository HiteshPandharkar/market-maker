"""Trade representation produced by the matching engine."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .exceptions import InvalidTradeError
from .order import OrderId


@dataclass(frozen=True, slots=True)
class Trade:
    """A single execution between one buy order and one sell order."""

    trade_id: str | int
    timestamp: datetime
    buy_order_id: OrderId
    sell_order_id: OrderId
    price: Decimal
    quantity: int

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise InvalidTradeError("timestamp must be a datetime")
        if not isinstance(self.price, Decimal) or self.price <= 0:
            raise InvalidTradeError("price must be a positive Decimal")
        if not isinstance(self.quantity, int) or isinstance(self.quantity, bool) or self.quantity <= 0:
            raise InvalidTradeError("quantity must be a positive integer")
