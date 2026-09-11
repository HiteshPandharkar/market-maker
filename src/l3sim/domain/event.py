"""Input events and engine-generated output events."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from .enums import EventType, OrderType
from .exceptions import InvalidEventError
from .order import Order, OrderId
from .trade import Trade

EventId = str | int


@dataclass(frozen=True, slots=True)
class Event:
    event_id: EventId
    timestamp: datetime
    event_type: EventType = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise InvalidEventError("timestamp must be a datetime")


@dataclass(frozen=True, slots=True)
class AddOrderEvent(Event):
    order: Order
    event_type: EventType = field(init=False, default=EventType.ADD_ORDER)

    def __post_init__(self) -> None:
        Event.__post_init__(self)
        if self.order.order_type is not OrderType.LIMIT:
            raise InvalidEventError("AddOrderEvent requires a limit order")


@dataclass(frozen=True, slots=True)
class MarketOrderEvent(Event):
    order: Order
    event_type: EventType = field(init=False, default=EventType.MARKET_ORDER)

    def __post_init__(self) -> None:
        Event.__post_init__(self)
        if self.order.order_type is not OrderType.MARKET:
            raise InvalidEventError("MarketOrderEvent requires a market order")


@dataclass(frozen=True, slots=True)
class CancelOrderEvent(Event):
    order_id: OrderId
    quantity: int | None = None
    event_type: EventType = field(init=False, default=EventType.CANCEL_ORDER)

    def __post_init__(self) -> None:
        Event.__post_init__(self)
        if self.quantity is not None and (not isinstance(self.quantity, int) or isinstance(self.quantity, bool) or self.quantity <= 0):
            raise InvalidEventError("cancel quantity must be a positive integer when supplied")


@dataclass(frozen=True, slots=True)
class ModifyOrderEvent(Event):
    order_id: OrderId
    price: Decimal | None = None
    quantity: int | None = None
    event_type: EventType = field(init=False, default=EventType.MODIFY_ORDER)

    def __post_init__(self) -> None:
        Event.__post_init__(self)
        if self.price is None and self.quantity is None:
            raise InvalidEventError("a modification must include a price or quantity")
        if self.price is not None and (not isinstance(self.price, Decimal) or self.price <= 0):
            raise InvalidEventError("modified price must be a positive Decimal")
        if self.quantity is not None and (not isinstance(self.quantity, int) or isinstance(self.quantity, bool) or self.quantity <= 0):
            raise InvalidEventError("modified quantity must be a positive integer")


@dataclass(frozen=True, slots=True)
class TradeEvent(Event):
    trade: Trade
    event_type: EventType = field(init=False, default=EventType.TRADE)


@dataclass(frozen=True, slots=True)
class OrderAcceptedEvent(Event):
    order_id: OrderId
    event_type: EventType = field(init=False, default=EventType.ORDER_ACCEPTED)


@dataclass(frozen=True, slots=True)
class OrderCancelledEvent(Event):
    order_id: OrderId
    cancelled_quantity: int
    event_type: EventType = field(init=False, default=EventType.ORDER_CANCELLED)

    def __post_init__(self) -> None:
        Event.__post_init__(self)
        if not isinstance(self.cancelled_quantity, int) or isinstance(self.cancelled_quantity, bool) or self.cancelled_quantity <= 0:
            raise InvalidEventError("cancelled_quantity must be a positive integer")


@dataclass(frozen=True, slots=True)
class OrderModifiedEvent(Event):
    order_id: OrderId
    event_type: EventType = field(init=False, default=EventType.ORDER_MODIFIED)


@dataclass(frozen=True, slots=True)
class OrderFilledEvent(Event):
    order_id: OrderId
    event_type: EventType = field(init=False, default=EventType.ORDER_FILLED)


@dataclass(frozen=True, slots=True)
class OrderPartiallyFilledEvent(Event):
    order_id: OrderId
    remaining_quantity: int
    event_type: EventType = field(init=False, default=EventType.ORDER_PARTIALLY_FILLED)

    def __post_init__(self) -> None:
        Event.__post_init__(self)
        if not isinstance(self.remaining_quantity, int) or isinstance(self.remaining_quantity, bool) or self.remaining_quantity <= 0:
            raise InvalidEventError("remaining_quantity must be a positive integer")
