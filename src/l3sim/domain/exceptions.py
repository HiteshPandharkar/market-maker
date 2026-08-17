"""Exceptions for invalid domain state or instructions."""


class DomainError(ValueError):
    """Base class for invalid simulator-domain values."""


class InvalidOrderError(DomainError):
    """Raised when an order violates fundamental order constraints."""


class InvalidTradeError(DomainError):
    """Raised when a trade violates fundamental trade constraints."""


class InvalidEventError(DomainError):
    """Raised when an event is incomplete or internally inconsistent."""
