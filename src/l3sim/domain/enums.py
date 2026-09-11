"""Enumerations shared by domain objects."""

from enum import Enum


class Side(str, Enum):
    """The direction of an order from its submitter's perspective."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Supported order instructions."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"


class EventType(str, Enum):
    """Input and engine-generated event classifications."""

    ADD_ORDER = "ADD_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    MODIFY_ORDER = "MODIFY_ORDER"
    MARKET_ORDER = "MARKET_ORDER"
    TRADE = "TRADE"
    ORDER_ACCEPTED = "ORDER_ACCEPTED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_MODIFIED = "ORDER_MODIFIED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_PARTIALLY_FILLED = "ORDER_PARTIALLY_FILLED"
