"""Business-level scenarios and presentation-ready simulation results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
import csv
import io
from statistics import mean

from l3sim.domain import (
    AddOrderEvent,
    CancelOrderEvent,
    MarketOrderEvent,
    ModifyOrderEvent,
    Side,
)
from l3sim.generator import Generator, GeneratorConfig
from l3sim.simulation import Runner, Snapshot


class ScenarioPreset(str, Enum):
    """Stable identifiers for the built-in business scenarios."""

    NORMAL = "normal"
    THIN_LIQUIDITY = "thin_liquidity"
    BUY_PRESSURE = "buy_pressure"
    SELL_PRESSURE = "sell_pressure"
    LIQUIDITY_WITHDRAWAL = "liquidity_withdrawal"

    @property
    def label(self) -> str:
        return {
            self.NORMAL: "Normal market",
            self.THIN_LIQUIDITY: "Thin liquidity",
            self.BUY_PRESSURE: "Buy-pressure stress",
            self.SELL_PRESSURE: "Sell-pressure stress",
            self.LIQUIDITY_WITHDRAWAL: "Liquidity withdrawal",
        }[self]


class ActivityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def label(self) -> str:
        return self.value.title()


class LiquidityLevel(str, Enum):
    THIN = "thin"
    NORMAL = "normal"
    DEEP = "deep"

    @property
    def label(self) -> str:
        return self.value.title()


@dataclass(frozen=True, slots=True)
class PresetProfile:
    description: str
    activity_level: ActivityLevel
    starting_liquidity: LiquidityLevel
    buy_sell_pressure: int
    limit_order_rate: float
    market_order_rate: float
    cancel_rate: float
    modify_rate: float
    mean_price_distance_ticks: float


_PRESETS = {
    ScenarioPreset.NORMAL: PresetProfile(
        "Balanced order flow and ordinary liquidity provision: the baseline for comparisons.",
        ActivityLevel.MEDIUM, LiquidityLevel.NORMAL, 0, 4.0, 1.0, 1.0, 0.5, 5.0,
    ),
    ScenarioPreset.THIN_LIQUIDITY: PresetProfile(
        "A shallow, dispersed book where aggressive orders can move execution conditions quickly.",
        ActivityLevel.MEDIUM, LiquidityLevel.THIN, 0, 3.0, 1.5, 2.0, 0.5, 8.0,
    ),
    ScenarioPreset.BUY_PRESSURE: PresetProfile(
        "Directional demand is biased toward buys, testing ask-side resilience.",
        ActivityLevel.HIGH, LiquidityLevel.NORMAL, 40, 4.0, 2.0, 1.0, 0.5, 5.0,
    ),
    ScenarioPreset.SELL_PRESSURE: PresetProfile(
        "Directional demand is biased toward sells, testing bid-side resilience.",
        ActivityLevel.HIGH, LiquidityLevel.NORMAL, -40, 4.0, 2.0, 1.0, 0.5, 5.0,
    ),
    ScenarioPreset.LIQUIDITY_WITHDRAWAL: PresetProfile(
        "Cancellations dominate replenishment, modelling deteriorating displayed liquidity.",
        ActivityLevel.HIGH, LiquidityLevel.THIN, 0, 2.0, 1.5, 4.0, 1.0, 9.0,
    ),
}


def preset_profile(preset: ScenarioPreset) -> PresetProfile:
    """Return the immutable defaults for a built-in preset."""

    if not isinstance(preset, ScenarioPreset):
        raise ValueError("preset must be a ScenarioPreset")
    return _PRESETS[preset]


def preset_description(preset: ScenarioPreset) -> str:
    return preset_profile(preset).description


@dataclass(frozen=True, slots=True)
class ScenarioConfig:
    """Validated business inputs, with optional expert generator overrides."""

    preset: ScenarioPreset = ScenarioPreset.NORMAL
    event_count: int = 1_000
    seed: int = 7
    starting_price: Decimal = Decimal("100.00")
    activity_level: ActivityLevel | None = None
    starting_liquidity: LiquidityLevel | None = None
    buy_sell_pressure: int | None = None
    tick_size: Decimal = Decimal("0.01")
    limit_order_rate: float | None = None
    market_order_rate: float | None = None
    cancel_rate: float | None = None
    modify_rate: float | None = None
    quantity_min: int = 1
    quantity_max: int = 1_000
    quantity_log_mean: float = 4.0
    quantity_log_stddev: float = 0.75
    mean_price_distance_ticks: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.preset, ScenarioPreset):
            raise ValueError("preset must be a ScenarioPreset")
        if not isinstance(self.event_count, int) or isinstance(self.event_count, bool) or not 1 <= self.event_count <= 100_000:
            raise ValueError("event_count must be an integer between 1 and 100000")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("seed must be an integer")
        if not isinstance(self.starting_price, Decimal) or self.starting_price <= 0:
            raise ValueError("starting_price must be a positive Decimal")
        if not isinstance(self.tick_size, Decimal) or self.tick_size <= 0:
            raise ValueError("tick_size must be a positive Decimal")
        if self.activity_level is not None and not isinstance(self.activity_level, ActivityLevel):
            raise ValueError("activity_level must be an ActivityLevel")
        if self.starting_liquidity is not None and not isinstance(self.starting_liquidity, LiquidityLevel):
            raise ValueError("starting_liquidity must be a LiquidityLevel")
        if self.buy_sell_pressure is not None and (
            not isinstance(self.buy_sell_pressure, int)
            or isinstance(self.buy_sell_pressure, bool)
            or not -100 <= self.buy_sell_pressure <= 100
        ):
            raise ValueError("buy_sell_pressure must be an integer between -100 and 100")
        for name in ("limit_order_rate", "market_order_rate", "cancel_rate", "modify_rate"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.quantity_min <= 0 or self.quantity_max < self.quantity_min:
            raise ValueError("quantity bounds must be positive and ordered")
        if self.quantity_log_stddev < 0:
            raise ValueError("quantity_log_stddev cannot be negative")
        if self.mean_price_distance_ticks is not None and self.mean_price_distance_ticks <= 0:
            raise ValueError("mean_price_distance_ticks must be positive")

    @property
    def resolved_activity_level(self) -> ActivityLevel:
        return self.activity_level or preset_profile(self.preset).activity_level

    @property
    def resolved_starting_liquidity(self) -> LiquidityLevel:
        return self.starting_liquidity or preset_profile(self.preset).starting_liquidity

    @property
    def resolved_buy_sell_pressure(self) -> int:
        return self.buy_sell_pressure if self.buy_sell_pressure is not None else preset_profile(self.preset).buy_sell_pressure

    @property
    def initial_levels(self) -> int:
        return {LiquidityLevel.THIN: 2, LiquidityLevel.NORMAL: 5, LiquidityLevel.DEEP: 8}[self.resolved_starting_liquidity]

    def to_generator_config(self) -> GeneratorConfig:
        """Compile business inputs into the existing technical generator configuration."""

        profile = preset_profile(self.preset)
        scale = {ActivityLevel.LOW: 0.6, ActivityLevel.MEDIUM: 1.0, ActivityLevel.HIGH: 1.6}[self.resolved_activity_level]

        def rate(override: float | None, base: float) -> float:
            return override if override is not None else base * scale

        pressure = self.resolved_buy_sell_pressure
        return GeneratorConfig(
            initial_mid_price=self.starting_price,
            tick_size=self.tick_size,
            limit_order_rate=rate(self.limit_order_rate, profile.limit_order_rate),
            market_order_rate=rate(self.market_order_rate, profile.market_order_rate),
            cancel_rate=rate(self.cancel_rate, profile.cancel_rate),
            modify_rate=rate(self.modify_rate, profile.modify_rate),
            buy_probability=0.5 + pressure * 0.004,
            quantity_min=self.quantity_min,
            quantity_max=self.quantity_max,
            quantity_log_mean=self.quantity_log_mean,
            quantity_log_stddev=self.quantity_log_stddev,
            mean_price_distance_ticks=self.mean_price_distance_ticks or profile.mean_price_distance_ticks,
        )


@dataclass(frozen=True, slots=True)
class SimulationSummary:
    trade_count: int
    executed_volume: int
    final_price: Decimal | None
    price_change: Decimal | None
    average_spread: Decimal | None
    maximum_spread: Decimal | None
    average_depth: float
    final_imbalance: Decimal | None


@dataclass(frozen=True, slots=True)
class TimeSeriesRow:
    event_number: int
    timestamp: datetime
    event_type: str
    best_bid: Decimal | None
    best_ask: Decimal | None
    mid_price: Decimal | None
    spread: Decimal | None
    bid_depth: int
    ask_depth: int
    total_depth: int
    imbalance: Decimal | None
    cumulative_trades: int
    cumulative_volume: int


@dataclass(frozen=True, slots=True)
class EventRow:
    event_number: int
    timestamp: datetime
    event_type: str
    description: str
    trades: int
    executed_volume: int


@dataclass(frozen=True, slots=True)
class LadderRow:
    side: str
    order_id: str
    price: Decimal
    quantity: int
    order_count: int


@dataclass(frozen=True, slots=True)
class TradeRow:
    price: Decimal
    quantity: int
    buy_order_id: str
    sell_order_id: str


@dataclass(frozen=True, slots=True)
class PlaybackFrame:
    event_number: int
    timestamp: datetime
    event_type: str
    description: str
    previous_best_bid: Decimal | None
    previous_best_ask: Decimal | None
    best_bid: Decimal | None
    best_ask: Decimal | None
    mid_price: Decimal | None
    spread: Decimal | None
    trades: tuple[TradeRow, ...]
    ladder: tuple[LadderRow, ...]


@dataclass(frozen=True, slots=True)
class SimulationResult:
    config: ScenarioConfig
    summary: SimulationSummary
    time_series: tuple[TimeSeriesRow, ...]
    events: tuple[EventRow, ...]
    final_ladder: tuple[LadderRow, ...]
    _snapshots: tuple[Snapshot, ...] = field(repr=False, compare=True)

    def playback_frame(self, event_number: int) -> PlaybackFrame:
        if not isinstance(event_number, int) or isinstance(event_number, bool) or not 1 <= event_number <= len(self._snapshots):
            raise IndexError("event_number is outside the simulation")
        snapshot = self._snapshots[event_number - 1]
        previous = self._snapshots[event_number - 2] if event_number > 1 else None
        event = self.events[event_number - 1]
        return PlaybackFrame(
            event_number=event_number,
            timestamp=snapshot.timestamp,
            event_type=event.event_type,
            description=event.description,
            previous_best_bid=previous.best_bid if previous else None,
            previous_best_ask=previous.best_ask if previous else None,
            best_bid=snapshot.best_bid,
            best_ask=snapshot.best_ask,
            mid_price=snapshot.mid_price,
            spread=snapshot.spread,
            trades=tuple(
                TradeRow(trade.price, trade.quantity, str(trade.buy_order_id), str(trade.sell_order_id))
                for trade in snapshot.trades
            ),
            ladder=_ladder(snapshot),
        )

    def summary_csv(self) -> str:
        return _csv((asdict(self.summary),))

    def time_series_csv(self) -> str:
        return _csv(tuple(asdict(row) for row in self.time_series))

    def events_csv(self) -> str:
        return _csv(tuple(asdict(row) for row in self.events))

    def final_ladder_csv(self) -> str:
        return _csv(tuple(asdict(row) for row in self.final_ladder))

    def interpretation(self) -> str:
        """Return a concise, deterministic business reading of the run."""

        summary = self.summary
        if summary.final_price is None:
            return "The market finished without a two-sided midpoint, indicating severely depleted displayed liquidity."
        direction = "unchanged"
        if summary.price_change is not None and summary.price_change > 0:
            direction = "higher"
        elif summary.price_change is not None and summary.price_change < 0:
            direction = "lower"
        imbalance_text = "balanced"
        if summary.final_imbalance is not None and summary.final_imbalance > Decimal("0.2"):
            imbalance_text = "bid-heavy"
        elif summary.final_imbalance is not None and summary.final_imbalance < Decimal("-0.2"):
            imbalance_text = "ask-heavy"
        return (
            f"The midpoint finished {direction}; displayed liquidity ended {imbalance_text}. "
            f"The run generated {summary.trade_count} trades with {summary.executed_volume:,} units executed."
        )


def run_scenario(config: ScenarioConfig) -> SimulationResult:
    """Run one deterministic scenario and return presentation-ready records."""

    if not isinstance(config, ScenarioConfig):
        raise TypeError("config must be a ScenarioConfig")
    runner = Runner()
    generator = Generator(config.to_generator_config(), seed=config.seed, book=runner.engine.book)
    runner.run(generator.initial_book_events(levels=config.initial_levels))
    for _ in range(config.event_count):
        runner.process(generator.next_event())

    return _result_from_runner(config, runner)


def _result_from_runner(config: ScenarioConfig, runner: Runner) -> SimulationResult:
    """Aggregate a completed runner; separated for focused KPI testing."""

    snapshots = runner.snapshots
    if not snapshots:
        raise ValueError("cannot build a result from a runner without snapshots")
    time_series = _time_series(snapshots)
    events = tuple(_event_row(number, snapshot) for number, snapshot in enumerate(snapshots, 1))
    spreads = [snapshot.spread for snapshot in snapshots if snapshot.spread is not None]
    final = snapshots[-1]
    final_price = final.mid_price
    summary = SimulationSummary(
        trade_count=len(runner.engine.trades),
        executed_volume=sum(trade.quantity for trade in runner.engine.trades),
        final_price=final_price,
        price_change=final_price - config.starting_price if final_price is not None else None,
        average_spread=sum(spreads, Decimal(0)) / len(spreads) if spreads else None,
        maximum_spread=max(spreads) if spreads else None,
        average_depth=mean(snapshot.total_book_quantity for snapshot in snapshots),
        final_imbalance=_snapshot_imbalance(final),
    )
    return SimulationResult(config, summary, time_series, events, _ladder(final), snapshots)


def _time_series(snapshots: tuple[Snapshot, ...]) -> tuple[TimeSeriesRow, ...]:
    rows: list[TimeSeriesRow] = []
    trade_count = 0
    volume = 0
    for number, snapshot in enumerate(snapshots, 1):
        trade_count += len(snapshot.trades)
        volume += sum(trade.quantity for trade in snapshot.trades)
        rows.append(TimeSeriesRow(
            number, snapshot.timestamp, snapshot.event.event_type.value,
            snapshot.best_bid, snapshot.best_ask, snapshot.mid_price, snapshot.spread,
            snapshot.bid_depth, snapshot.ask_depth, snapshot.total_book_quantity,
            _snapshot_imbalance(snapshot), trade_count, volume,
        ))
    return tuple(rows)


def _snapshot_imbalance(snapshot: Snapshot, levels: int = 3) -> Decimal | None:
    bid = sum(level.total_quantity for level in snapshot.bids[:levels])
    ask = sum(level.total_quantity for level in snapshot.asks[:levels])
    total = bid + ask
    return Decimal(bid - ask) / Decimal(total) if total else None


def _ladder(snapshot: Snapshot) -> tuple[LadderRow, ...]:
    asks = tuple(
        LadderRow(
            "ASK",
            ", ".join(str(order.order_id) for order in level.orders),
            level.price,
            level.total_quantity,
            level.order_count,
        )
        for level in reversed(snapshot.asks)
    )
    bids = tuple(
        LadderRow(
            "BID",
            ", ".join(str(order.order_id) for order in level.orders),
            level.price,
            level.total_quantity,
            level.order_count,
        )
        for level in snapshot.bids
    )
    return asks + bids


def _event_row(number: int, snapshot: Snapshot) -> EventRow:
    event = snapshot.event
    if isinstance(event, AddOrderEvent):
        description = f"Added {event.order.side.value.lower()} limit order for {event.order.quantity} at {event.order.price}."
    elif isinstance(event, MarketOrderEvent):
        description = f"Submitted {event.order.side.value.lower()} market order for {event.order.quantity}."
    elif isinstance(event, CancelOrderEvent):
        amount = "all remaining quantity" if event.quantity is None else str(event.quantity)
        description = f"Cancelled {amount} from order {event.order_id}."
    elif isinstance(event, ModifyOrderEvent):
        changes = []
        if event.price is not None:
            changes.append(f"price to {event.price}")
        if event.quantity is not None:
            changes.append(f"quantity to {event.quantity}")
        description = f"Modified order {event.order_id}: {' and '.join(changes)}."
    else:
        description = event.event_type.value.replace("_", " ").title()
    return EventRow(
        number, snapshot.timestamp, event.event_type.value, description,
        len(snapshot.trades), sum(trade.quantity for trade in snapshot.trades),
    )


def _csv(rows: tuple[dict, ...]) -> str:
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys(), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if value is None else value for key, value in row.items()})
    return output.getvalue()
