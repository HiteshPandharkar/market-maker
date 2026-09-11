"""Property-based invariants for arbitrary matching-engine operation sequences."""

from datetime import datetime, timezone
from decimal import Decimal

from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from l3sim.analytics import ask_depth, bid_depth
from l3sim.domain import Order, OrderType, Side
from l3sim.matching import MatchingEngine


NOW = datetime(2026, 8, 16, tzinfo=timezone.utc)
SIDES = st.sampled_from(tuple(Side))
PRICES = st.integers(min_value=9_500, max_value=10_500).map(
    lambda cents: Decimal(cents) / 100
)
QUANTITIES = st.integers(min_value=1, max_value=1_000)


class MatchingEngineStateMachine(RuleBasedStateMachine):
    """Exercise every supported operation and validate the book after each one."""

    def __init__(self) -> None:
        super().__init__()
        self.engine = MatchingEngine()
        self._next_order_id = 0
        self._submitted: dict[str, int] = {}
        self._executed: dict[str, int] = {}
        self._cancelled: dict[str, int] = {}

    def _order_id(self, prefix: str) -> str:
        self._next_order_id += 1
        return f"{prefix}-{self._next_order_id}"

    def _active_orders(self) -> tuple[Order, ...]:
        return tuple(
            order
            for level in (*self.engine.book.bid_levels, *self.engine.book.ask_levels)
            for order in level.orders
        )

    def _record_submission(self, order: Order) -> None:
        self._submitted[order.order_id] = order.quantity
        self._executed[order.order_id] = 0
        self._cancelled[order.order_id] = 0

    def _record_trades(self, trades: tuple) -> None:
        for trade in trades:
            self._executed[trade.buy_order_id] += trade.quantity
            self._executed[trade.sell_order_id] += trade.quantity

    @rule(side=SIDES, price=PRICES, quantity=QUANTITIES)
    def add_limit_order(self, side: Side, price: Decimal, quantity: int) -> None:
        order = Order(self._order_id("limit"), NOW, side, price, quantity)
        self._record_submission(order)
        self._record_trades(self.engine.submit(order))

    @rule(side=SIDES, quantity=QUANTITIES)
    def submit_market_order(self, side: Side, quantity: int) -> None:
        order = Order(
            self._order_id("market"),
            NOW,
            side,
            None,
            quantity,
            OrderType.MARKET,
        )
        self._record_submission(order)
        trades = self.engine.process_market_order(order)
        self._record_trades(trades)
        self._cancelled[order.order_id] = quantity - self._executed[order.order_id]
        assert self.engine.book.get_order(order.order_id) is None

    @precondition(lambda self: bool(self._active_orders()))
    @rule(data=st.data(), cancel_all=st.booleans())
    def cancel_order(self, data: st.DataObject, cancel_all: bool) -> None:
        order = data.draw(st.sampled_from(self._active_orders()), label="active order")
        if cancel_all:
            self.engine.cancel(order.order_id)
            self._cancelled[order.order_id] += order.remaining_quantity
            assert self.engine.book.get_order(order.order_id) is None
            return

        quantity = data.draw(
            st.integers(min_value=1, max_value=order.remaining_quantity),
            label="cancel quantity",
        )
        self.engine.cancel(order.order_id, quantity)
        self._cancelled[order.order_id] += quantity

    @precondition(lambda self: bool(self._active_orders()))
    @rule(data=st.data(), change=st.sampled_from(("price", "quantity", "both")))
    def modify_order(self, data: st.DataObject, change: str) -> None:
        order = data.draw(st.sampled_from(self._active_orders()), label="active order")
        price = data.draw(PRICES, label="new price") if change != "quantity" else None
        quantity = (
            data.draw(QUANTITIES, label="new quantity") if change != "price" else None
        )
        new_remaining = order.remaining_quantity if quantity is None else quantity
        difference = new_remaining - order.remaining_quantity
        if difference > 0:
            self._submitted[order.order_id] += difference
        elif difference < 0:
            self._cancelled[order.order_id] -= difference
        self._record_trades(
            self.engine.modify(order.order_id, price=price, quantity=quantity)
        )

    @invariant()
    def book_is_internally_consistent(self) -> None:
        book = self.engine.book
        bids = book.bid_levels
        asks = book.ask_levels

        assert [level.price for level in bids] == sorted(
            (level.price for level in bids), reverse=True
        )
        assert [level.price for level in asks] == sorted(level.price for level in asks)

        active_orders = self._active_orders()
        assert len(book) == len(active_orders)
        assert len({order.order_id for order in active_orders}) == len(active_orders)
        assert book.is_empty == (len(active_orders) == 0)

        for level in (*bids, *asks):
            assert not level.is_empty
            assert level.total_quantity == sum(
                order.remaining_quantity for order in level.orders
            )
            assert level.total_quantity > 0
            for order in level.orders:
                assert order.side is level.side
                assert order.price == level.price
                assert 0 < order.remaining_quantity <= order.quantity
                assert book.get_order(order.order_id) is order
                assert book.get_price_level(order.side, order.price) is level

    @invariant()
    def book_is_uncrossed_and_metrics_match_levels(self) -> None:
        book = self.engine.book
        best_bid = book.best_bid()
        best_ask = book.best_ask()
        if best_bid is not None and best_ask is not None:
            assert best_bid < best_ask
            assert book.spread() == best_ask - best_bid
            assert book.mid_price() == (best_bid + best_ask) / 2
        else:
            assert book.spread() is None
            assert book.mid_price() is None

        for actual, levels in (
            (bid_depth(book, max(1, len(book.bid_levels))), book.bid_levels),
            (ask_depth(book, max(1, len(book.ask_levels))), book.ask_levels),
        ):
            assert len(actual) == len(levels)
            assert [item.price for item in actual] == [level.price for level in levels]
            assert [item.quantity for item in actual] == [
                level.total_quantity for level in levels
            ]
            assert [item.order_count for item in actual] == [
                len(level) for level in levels
            ]

    @invariant()
    def trades_are_valid(self) -> None:
        for expected_id, trade in enumerate(self.engine.trades, start=1):
            assert trade.trade_id == expected_id
            assert trade.price > 0
            assert trade.quantity > 0
            assert trade.buy_order_id != trade.sell_order_id

    @invariant()
    def every_order_reconciles_to_its_accepted_quantity(self) -> None:
        remaining = {
            order.order_id: order.remaining_quantity for order in self._active_orders()
        }
        for order_id, submitted in self._submitted.items():
            assert submitted == (
                remaining.get(order_id, 0)
                + self._executed[order_id]
                + self._cancelled[order_id]
            )


TestMatchingEngineInvariants = MatchingEngineStateMachine.TestCase
TestMatchingEngineInvariants.settings = settings(
    max_examples=100,
    stateful_step_count=50,
    deadline=None,
    derandomize=True,
    database=None,
)
