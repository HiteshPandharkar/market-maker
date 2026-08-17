"""Configuration for the synthetic L3 event generator."""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    """Parameters controlling synthetic order-flow generation.

    Rates are events per unit of simulated time.  Their relative values select
    the next event type and their sum determines the exponential inter-arrival
    time.  Quantity samples are log-normal and clamped to the configured
    inclusive bounds.
    """

    initial_mid_price: Decimal = Decimal("100.00")
    tick_size: Decimal = Decimal("0.01")
    limit_order_rate: float = 4.0
    market_order_rate: float = 1.0
    cancel_rate: float = 1.0
    modify_rate: float = 0.5
    buy_probability: float = 0.5
    quantity_min: int = 1
    quantity_max: int = 1_000
    quantity_log_mean: float = 4.0
    quantity_log_stddev: float = 0.75
    mean_price_distance_ticks: float = 5.0
    start_time: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __post_init__(self) -> None:
        if not isinstance(self.initial_mid_price, Decimal) or self.initial_mid_price <= 0:
            raise ValueError("initial_mid_price must be a positive Decimal")
        if not isinstance(self.tick_size, Decimal) or self.tick_size <= 0:
            raise ValueError("tick_size must be a positive Decimal")
        for name in ("limit_order_rate", "market_order_rate", "cancel_rate", "modify_rate"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.total_rate <= 0:
            raise ValueError("at least one event rate must be positive")
        if not 0 <= self.buy_probability <= 1:
            raise ValueError("buy_probability must be between zero and one")
        if self.quantity_min <= 0 or self.quantity_max < self.quantity_min:
            raise ValueError("quantity bounds must be positive and ordered")
        if self.quantity_log_stddev < 0 or self.mean_price_distance_ticks <= 0:
            raise ValueError("distribution parameters must be non-negative")
        if not isinstance(self.start_time, datetime):
            raise ValueError("start_time must be a datetime")

    @property
    def total_rate(self) -> float:
        return self.limit_order_rate + self.market_order_rate + self.cancel_rate + self.modify_rate
