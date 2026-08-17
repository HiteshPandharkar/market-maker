"""Chronological event processing and immutable market-state recording."""

from collections.abc import Iterable
from datetime import datetime

from l3sim.domain import AddOrderEvent, CancelOrderEvent, MarketOrderEvent, ModifyOrderEvent
from l3sim.domain.event import Event
from l3sim.domain.exceptions import InvalidEventError
from l3sim.matching import MatchingEngine

from .state import PriceLevelSnapshot, Snapshot


class Runner:
    """Run input events through a matching engine and retain their snapshots.

    The runner never changes input events.  It only reads each event, applies
    it to its engine, then records an immutable copy of the resulting L3 book.
    Events with equal timestamps retain caller order; an earlier timestamp is
    rejected to prevent accidental time travel.
    """

    __slots__ = ("_engine", "_last_timestamp", "_snapshots")

    def __init__(self, engine: MatchingEngine | None = None) -> None:
        self._engine = engine if engine is not None else MatchingEngine()
        self._last_timestamp: datetime | None = None
        self._snapshots: list[Snapshot] = []

    @property
    def engine(self) -> MatchingEngine:
        """The live matching engine used by this run."""

        return self._engine

    @property
    def snapshots(self) -> tuple[Snapshot, ...]:
        """All recorded states, in processing order."""

        return tuple(self._snapshots)

    @property
    def last_snapshot(self) -> Snapshot | None:
        """The most recently recorded state, if an event was processed."""

        return self._snapshots[-1] if self._snapshots else None

    def process(self, event: Event) -> Snapshot:
        """Process one chronological input event and return its snapshot."""

        if not isinstance(event, Event):
            raise InvalidEventError("runner can process only input Event instances")
        if self._last_timestamp is not None and event.timestamp < self._last_timestamp:
            raise InvalidEventError("events must be processed in chronological order")

        trades = self._dispatch(event)
        snapshot = self._snapshot(event, trades)
        self._last_timestamp = event.timestamp
        self._snapshots.append(snapshot)
        return snapshot

    process_event = process

    def run(self, events: Iterable[Event]) -> tuple[Snapshot, ...]:
        """Process an iterable of events and return the snapshots produced."""

        return tuple(self.process(event) for event in events)

    def _dispatch(self, event: Event):
        if isinstance(event, AddOrderEvent):
            return self._engine.submit(event.order)
        if isinstance(event, MarketOrderEvent):
            return self._engine.process_market_order(event.order)
        if isinstance(event, CancelOrderEvent):
            self._engine.cancel(event.order_id, event.quantity)
            return ()
        if isinstance(event, ModifyOrderEvent):
            return self._engine.modify(event.order_id, price=event.price, quantity=event.quantity)
        raise InvalidEventError(f"unsupported input event type: {type(event).__name__}")

    def _snapshot(self, event: Event, trades: tuple) -> Snapshot:
        book = self._engine.book
        bids = tuple(
            PriceLevelSnapshot(level.side, level.price, level.orders)
            for level in book.bid_levels
        )
        asks = tuple(
            PriceLevelSnapshot(level.side, level.price, level.orders)
            for level in book.ask_levels
        )
        bid_depth = sum(level.total_quantity for level in bids)
        ask_depth = sum(level.total_quantity for level in asks)
        last_trade = self._engine.trades[-1] if self._engine.trades else None
        return Snapshot(
            timestamp=event.timestamp,
            event=event,
            trades=trades,
            best_bid=book.best_bid(),
            best_ask=book.best_ask(),
            mid_price=book.mid_price(),
            spread=book.spread(),
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            total_book_quantity=bid_depth + ask_depth,
            last_trade_price=last_trade.price if last_trade is not None else None,
            last_trade_quantity=last_trade.quantity if last_trade is not None else None,
            bids=bids,
            asks=asks,
        )


SimulationRunner = Runner
