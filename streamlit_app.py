"""Local business interface for the l3sim Liquidity Stress Lab."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

import altair as alt
import pandas as pd
import streamlit as st

from l3sim.lab import (
    ActivityLevel,
    LiquidityLevel,
    ScenarioConfig,
    ScenarioPreset,
    SimulationResult,
    preset_description,
    preset_profile,
    run_scenario,
)


st.set_page_config(page_title="Liquidity Stress Lab", page_icon="📊", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem;}
    [data-testid="stMetricValue"] {font-size: 1.55rem;}
    .lab-note {padding: .75rem 1rem; border-radius: .5rem; background: #f2f6fb; color: #27405e;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _enum_index(values: list, selected) -> int:
    return values.index(selected)


def _decimal(value: float | str) -> Decimal:
    return Decimal(str(value))


def _display(value, digits: int = 4) -> str:
    if value is None:
        return "Not defined"
    if isinstance(value, (Decimal, float)):
        return f"{float(value):,.{digits}f}"
    return f"{value:,}" if isinstance(value, int) else str(value)


def _records(rows) -> list[dict]:
    records = []
    for row in rows:
        record = asdict(row)
        records.append({key: float(value) if isinstance(value, Decimal) else value for key, value in record.items()})
    return records


def _ladder_records(result: SimulationResult, frame) -> list[dict]:
    """Return ladder rows with IDs, including for results kept from an older app run."""

    snapshot = result._snapshots[frame.event_number - 1]
    order_ids = {
        ("BID", level.price): ", ".join(str(order.order_id) for order in level.orders)
        for level in snapshot.bids
    }
    order_ids.update({
        ("ASK", level.price): ", ".join(str(order.order_id) for order in level.orders)
        for level in snapshot.asks
    })

    records = []
    for row in frame.ladder:
        record = asdict(row)
        record["order_id"] = record.get("order_id") or order_ids.get((row.side, row.price), "")
        records.append({key: float(value) if isinstance(value, Decimal) else value for key, value in record.items()})

    bid_start = next((index for index, record in enumerate(records) if record["side"] == "BID"), len(records))
    last_trade_price = getattr(snapshot, "last_trade_price", None)
    records.insert(
        bid_start,
        {
            "side": "LAST TRADE",
            "order_id": "Most recent execution" if last_trade_price is not None else "No trades yet",
            "price": float(last_trade_price) if last_trade_price is not None else None,
            "quantity": getattr(snapshot, "last_trade_quantity", None),
            "order_count": None,
        },
    )
    return records


def _top_ladder_records(records: list[dict], levels: int = 5) -> list[dict]:
    """Return the best N aggregated price levels on each side of the market."""

    asks = [record for record in records if record["side"] == "ASK"]
    bids = [record for record in records if record["side"] == "BID"]
    last_trade = [record for record in records if record["side"] == "LAST TRADE"]
    return asks[-levels:] + last_trade + bids[:levels]


def _style_ladder(ladder: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Apply the bid/ask colour convention used by trading ladders."""

    def side_colours(row: pd.Series) -> list[str]:
        if row["side"] == "BID":
            colour = "color: #16a34a"
        elif row["side"] == "ASK":
            colour = "color: #dc2626"
        else:
            colour = "color: #d97706"
        return [colour] * len(row)

    return (
        ladder.style.apply(side_colours, axis=1)
        .format({"price": "{:.2f}", "quantity": "{:,.0f}", "order_count": "{:,.0f}"}, na_rep="—")
        .set_properties(subset=["side", "price"], **{"font-weight": "700"})
    )


def _price_spread_chart(frame: pd.DataFrame) -> alt.LayerChart:
    """Show the quoted range, midpoint, and spread without visual competition."""

    chart_frame = frame.reset_index()
    price_values = chart_frame[["mid_price", "best_bid", "best_ask"]]
    price_min = float(price_values.min().min())
    price_max = float(price_values.max().max())
    price_padding = max((price_max - price_min) * 0.08, 0.001)
    price_scale = alt.Scale(
        domain=[price_min - price_padding, price_max + price_padding],
        zero=False,
    )
    spread_bars = (
        alt.Chart(chart_frame)
        .mark_bar(color="#a178df", opacity=0.16)
        .encode(
            x=alt.X("event_number:Q", title="Event"),
            y=alt.Y(
                "spread:Q",
                title="Spread (purple bars)",
                axis=alt.Axis(orient="right", titleColor="#a178df", labelColor="#a178df"),
                scale=alt.Scale(zero=True),
            ),
            tooltip=[
                alt.Tooltip("event_number:Q", title="Event"),
                alt.Tooltip("mid_price:Q", title="Midpoint", format=".4f"),
                alt.Tooltip("best_bid:Q", title="Best bid", format=".4f"),
                alt.Tooltip("best_ask:Q", title="Best ask", format=".4f"),
                alt.Tooltip("spread:Q", title="Spread", format=".4f"),
            ],
        )
    )
    quote_band = (
        alt.Chart(chart_frame)
        .mark_area(color="#5b8fd1", opacity=0.18, interpolate="step-after")
        .encode(
            x=alt.X("event_number:Q", title="Event"),
            y=alt.Y("best_bid:Q", title="Quoted price", scale=price_scale),
            y2="best_ask:Q",
        )
    )
    bid = alt.Chart(chart_frame).mark_line(color="#2e8b57", strokeWidth=1.2, interpolate="step-after").encode(
        x="event_number:Q",
        y=alt.Y("best_bid:Q", scale=price_scale, axis=None),
    )
    ask = alt.Chart(chart_frame).mark_line(color="#e56645", strokeWidth=1.2, interpolate="step-after").encode(
        x="event_number:Q",
        y=alt.Y("best_ask:Q", scale=price_scale, axis=None),
    )
    midpoint = alt.Chart(chart_frame).mark_line(color="#63a7ff", strokeWidth=2.8, interpolate="step-after").encode(
        x="event_number:Q",
        y=alt.Y("mid_price:Q", scale=price_scale, axis=None),
    )
    return (
        alt.layer(spread_bars, quote_band, bid, ask, midpoint)
        .resolve_scale(y="independent")
        .properties(height=360)
        .interactive(bind_y=False)
    )


def _midpoint_comparison_chart(frame: pd.DataFrame) -> alt.Chart:
    """Compare midpoint paths on a price-focused, non-zero scale."""

    chart_frame = frame.reset_index().melt(
        id_vars="generated_event",
        var_name="scenario",
        value_name="mid_price",
    )
    return (
        alt.Chart(chart_frame)
        .mark_line(strokeWidth=2, interpolate="step-after")
        .encode(
            x=alt.X("generated_event:Q", title="Generated event"),
            y=alt.Y(
                "mid_price:Q",
                title="Midpoint",
                scale=alt.Scale(zero=False),
            ),
            color=alt.Color("scenario:N", title="Scenario"),
            tooltip=[
                alt.Tooltip("generated_event:Q", title="Generated event"),
                alt.Tooltip("scenario:N", title="Scenario"),
                alt.Tooltip("mid_price:Q", title="Midpoint", format=".4f"),
            ],
        )
        .properties(height=360)
        .interactive(bind_y=False)
    )


def _scenario_form() -> ScenarioConfig | None:
    preset = st.selectbox(
        "Market scenario",
        list(ScenarioPreset),
        format_func=lambda item: item.label,
        help="A documented set of order-flow and liquidity assumptions.",
    )
    profile = preset_profile(preset)
    st.caption(preset_description(preset))

    with st.form("scenario_config"):
        left, middle, right = st.columns(3)
        with left:
            starting_price = st.number_input("Starting price", min_value=0.01, value=100.0, step=1.0)
            event_count = st.number_input("Generated events", min_value=1, max_value=100_000, value=1_000, step=100)
            seed = st.number_input("Reproducible run ID", value=7, step=1, help="Use the same ID to reproduce an identical run.")
        with middle:
            activities = list(ActivityLevel)
            activity = st.selectbox(
                "Market activity",
                activities,
                index=_enum_index(activities, profile.activity_level),
                format_func=lambda item: item.label,
                help="Scales the frequency of all order-book events.",
                key=f"activity_{preset.value}",
            )
            liquidity_levels = list(LiquidityLevel)
            liquidity = st.selectbox(
                "Starting liquidity",
                liquidity_levels,
                index=_enum_index(liquidity_levels, profile.starting_liquidity),
                format_func=lambda item: item.label,
                help="Controls how many price levels initially appear on each side.",
                key=f"liquidity_{preset.value}",
            )
        with right:
            pressure = st.slider(
                "Buy / sell pressure",
                min_value=-100,
                max_value=100,
                value=profile.buy_sell_pressure,
                help="Negative values favour sells; positive values favour buys.",
                key=f"pressure_{preset.value}",
            )
            st.caption("Business inputs override the selected preset without changing its documented baseline.")

        with st.expander("Advanced generator assumptions"):
            override_rates = st.checkbox(
                "Override preset event rates",
                help="Exact rates replace both the preset rates and the market-activity multiplier.",
            )
            rate_cols = st.columns(4)
            limit_rate = rate_cols[0].number_input("Limit rate", min_value=0.0, value=profile.limit_order_rate)
            market_rate = rate_cols[1].number_input("Market rate", min_value=0.0, value=profile.market_order_rate)
            cancel_rate = rate_cols[2].number_input("Cancel rate", min_value=0.0, value=profile.cancel_rate)
            modify_rate = rate_cols[3].number_input("Modify rate", min_value=0.0, value=profile.modify_rate)
            dist_cols = st.columns(3)
            tick_size = dist_cols[0].number_input("Tick size", min_value=0.0001, value=0.01, format="%.4f")
            quantity_min = dist_cols[1].number_input("Minimum quantity", min_value=1, value=1)
            quantity_max = dist_cols[2].number_input("Maximum quantity", min_value=1, value=1_000)
            shape_cols = st.columns(3)
            log_mean = shape_cols[0].number_input("Quantity log mean", value=4.0)
            log_stddev = shape_cols[1].number_input("Quantity log deviation", min_value=0.0, value=0.75)
            distance = shape_cols[2].number_input(
                "Mean quote distance (ticks)", min_value=0.1, value=profile.mean_price_distance_ticks,
            )

        submitted = st.form_submit_button("Run simulation", type="primary", use_container_width=True)
        if not submitted:
            return None
        return ScenarioConfig(
            preset=preset,
            event_count=int(event_count),
            seed=int(seed),
            starting_price=_decimal(starting_price),
            activity_level=activity,
            starting_liquidity=liquidity,
            buy_sell_pressure=pressure,
            tick_size=_decimal(tick_size),
            limit_order_rate=limit_rate if override_rates else None,
            market_order_rate=market_rate if override_rates else None,
            cancel_rate=cancel_rate if override_rates else None,
            modify_rate=modify_rate if override_rates else None,
            quantity_min=int(quantity_min),
            quantity_max=int(quantity_max),
            quantity_log_mean=log_mean,
            quantity_log_stddev=log_stddev,
            mean_price_distance_ticks=distance,
        )


def _require_result() -> SimulationResult | None:
    result = st.session_state.get("scenario_result")
    if result is None:
        st.info("Configure and run a scenario first.")
    return result


def _overview(result: SimulationResult) -> None:
    st.subheader(f"Overview · {result.config.preset.label}")
    st.markdown(f"<div class='lab-note'>{result.interpretation()}</div>", unsafe_allow_html=True)
    summary = result.summary
    metrics = st.columns(4)
    metrics[0].metric("Trades", _display(summary.trade_count, 0), help="Individual executions generated by matching orders.")
    metrics[1].metric("Executed volume", _display(summary.executed_volume, 0))
    metrics[2].metric("Final midpoint", _display(summary.final_price, 2), delta=_display(summary.price_change, 2))
    metrics[3].metric("Average spread", _display(summary.average_spread, 4), help="Average best ask minus best bid.")
    secondary = st.columns(3)
    secondary[0].metric("Maximum spread", _display(summary.maximum_spread, 4))
    secondary[1].metric("Average displayed depth", _display(summary.average_depth, 0))
    secondary[2].metric("Final imbalance", _display(summary.final_imbalance, 3), help="Positive is bid-heavy; negative is ask-heavy.")

    frame = pd.DataFrame(_records(result.time_series)).set_index("event_number")
    left, right = st.columns(2)
    left.markdown("#### Price and spread")
    left.altair_chart(
        _price_spread_chart(frame),
        use_container_width=True,
    )
    left.caption(
        "Blue line: midpoint · Shaded band: best bid to best ask · "
        "Purple bars: spread (right axis)"
    )
    right.markdown("#### Displayed liquidity")
    right.line_chart(frame[["bid_depth", "ask_depth"]], color=["#2e8b57", "#c84b31"])
    st.markdown("#### Three-level order-book imbalance")
    st.line_chart(frame[["imbalance"]], color=["#7b61a8"])

    st.markdown("#### Download results")
    downloads = st.columns(4)
    downloads[0].download_button("Summary CSV", result.summary_csv(), "summary.csv", "text/csv", use_container_width=True)
    downloads[1].download_button("Time series CSV", result.time_series_csv(), "time_series.csv", "text/csv", use_container_width=True)
    downloads[2].download_button("Events CSV", result.events_csv(), "events.csv", "text/csv", use_container_width=True)
    downloads[3].download_button("Final book CSV", result.final_ladder_csv(), "final_book.csv", "text/csv", use_container_width=True)


def _compare(result: SimulationResult) -> None:
    st.subheader("Compare market conditions")
    alternatives = [preset for preset in ScenarioPreset if preset is not result.config.preset]
    comparison_preset = st.selectbox("Comparison scenario", alternatives, format_func=lambda item: item.label)
    st.caption(preset_description(comparison_preset))
    if st.button("Run comparison", type="primary"):
        comparison_config = ScenarioConfig(
            preset=comparison_preset,
            event_count=result.config.event_count,
            seed=result.config.seed,
            starting_price=result.config.starting_price,
            tick_size=result.config.tick_size,
        )
        with st.spinner("Running comparable scenario with the same run ID…"):
            st.session_state.comparison_result = run_scenario(comparison_config)
    comparison = st.session_state.get("comparison_result")
    if (
        comparison is None
        or comparison.config.seed != result.config.seed
        or comparison.config.preset is not comparison_preset
    ):
        st.info("Run the comparison to see side-by-side results using the same reproducible run ID.")
        return

    metric_names = ["trade_count", "executed_volume", "final_price", "price_change", "average_spread", "maximum_spread", "average_depth", "final_imbalance"]
    rows = []
    for name in metric_names:
        first = getattr(result.summary, name)
        second = getattr(comparison.summary, name)
        delta = second - first if first is not None and second is not None else None
        rows.append({"Metric": name.replace("_", " ").title(), result.config.preset.label: first, comparison.config.preset.label: second, "Difference": delta})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    def comparison_frame(scenario: SimulationResult) -> pd.DataFrame:
        frame = pd.DataFrame(_records(scenario.time_series))[["event_number", "mid_price", "spread", "total_depth"]]
        seed_events = 2 * scenario.config.initial_levels
        frame = frame[frame["event_number"] >= seed_events].copy()
        frame["generated_event"] = frame["event_number"] - seed_events
        return frame.drop(columns="event_number")

    first = comparison_frame(result)
    second = comparison_frame(comparison)
    combined = first.merge(second, on="generated_event", suffixes=(f" · {result.config.preset.label}", f" · {comparison.config.preset.label}")).set_index("generated_event")
    st.markdown("#### Midpoint comparison")
    st.altair_chart(
        _midpoint_comparison_chart(combined.filter(like="mid_price")),
        use_container_width=True,
    )
    st.caption("The midpoint axis is zoomed to the observed price range; it does not start at zero.")
    st.markdown("#### Spread comparison")
    st.line_chart(combined.filter(like="spread"))
    st.markdown("#### Displayed-depth comparison")
    st.line_chart(combined.filter(like="total_depth"))


def _playback(result: SimulationResult) -> None:
    st.subheader("Order-book playback")
    trade_events = [row for row in result.events if row.trades]
    # The first events seed one bid and one ask at a time. Opening playback at
    # event 1 therefore looks like a broken/empty ladder and makes the full-book
    # toggle appear ineffective because only one price level exists. Start at
    # the first fully seeded book while still allowing the user to scrub back.
    initial_playback_event = min(2 * result.config.initial_levels, len(result.events))
    playback_key = "playback_event_number"
    running_key = "playback_running"
    full_book_key = "playback_show_full_book"
    st.session_state.setdefault(playback_key, initial_playback_event)
    st.session_state.setdefault(running_key, False)
    st.session_state.setdefault(full_book_key, False)
    st.session_state[playback_key] = min(max(1, int(st.session_state[playback_key])), len(result.events))

    if trade_events:
        executions = {row.event_number: row.description for row in trade_events}

        def jump_to_execution() -> None:
            selected_event = st.session_state.get("playback_execution_jump")
            if selected_event is not None:
                st.session_state[playback_key] = selected_event
                st.session_state[running_key] = False

        st.selectbox(
            "Jump to an execution",
            [None, *executions],
            format_func=lambda event: "Choose an event" if event is None else f"Event {event}: {executions[event]}",
            key="playback_execution_jump",
            on_change=jump_to_execution,
        )

    # Keep display controls outside the auto-refreshing fragment. A widget in a
    # timed fragment can briefly render frontend state from one fragment run
    # while the table below it comes from another, leaving the switch and book
    # visibly out of sync.
    show_full_depth = st.toggle(
        "Show full order book",
        key=full_book_key,
        help=(
            "Off shows the five best aggregated price levels per side. On shows every price level "
            "that exists at the selected event."
        ),
    )

    # speed = st.slider(
    #     "Playback speed",
    #     min_value=1.0,
    #     max_value=10.0,
    #     value=4.0,
    #     step=1.0,
    #     format="%.1f events / second",
    # )

    # @st.fragment(run_every=(1 / speed if st.session_state[running_key] else None))
    @st.fragment(run_every=(1 if st.session_state[running_key] else None))
    def playback_ladder() -> None:
        if st.session_state[running_key]:
            if st.session_state[playback_key] < len(result.events):
                st.session_state[playback_key] += 1
            else:
                st.session_state[running_key] = False
                st.rerun()

        control, progress = st.columns([0.22, 0.78], vertical_alignment="bottom")
        with control:
            button_label = "⏸ Pause" if st.session_state[running_key] else "▶ Play"
            if st.button(button_label, type="primary", use_container_width=True):
                if st.session_state[playback_key] >= len(result.events):
                    st.session_state[playback_key] = 1
                st.session_state[running_key] = not st.session_state[running_key]
                st.rerun()

        with progress:
            event_number = st.slider(
                "Event",
                1,
                len(result.events),
                key=playback_key,
                disabled=st.session_state[running_key],
            )

        frame = result.playback_frame(event_number)
        st.caption(
            f"Event {event_number} of {len(result.events)} · "
            f"{frame.timestamp.isoformat()} · {frame.event_type.replace('_', ' ').title()}"
        )
        st.write(frame.description)

        before, after, spread = st.columns(3)
        before.metric("Previous best bid / ask", f"{_display(frame.previous_best_bid, 2)} / {_display(frame.previous_best_ask, 2)}")
        after.metric("New best bid / ask", f"{_display(frame.best_bid, 2)} / {_display(frame.best_ask, 2)}")
        spread.metric("New spread", _display(frame.spread, 4))
        left, right = st.columns([1.15, 0.85])
        with left:
            st.markdown("#### Order-book ladder")
            all_ladder_records = _ladder_records(result, frame)
            ask_levels = sum(record["side"] == "ASK" for record in all_ladder_records)
            bid_levels = sum(record["side"] == "BID" for record in all_ladder_records)
            if show_full_depth:
                ladder_records = all_ladder_records
                depth_label = f"Full depth: {ask_levels} ask + {bid_levels} bid price levels"
            else:
                ladder_records = _top_ladder_records(all_ladder_records)
                shown_asks = min(ask_levels, 5)
                shown_bids = min(bid_levels, 5)
                depth_label = (
                    f"Showing {shown_asks} of {ask_levels} ask + "
                    f"{shown_bids} of {bid_levels} bid price levels"
                )
            st.caption(
                f"{depth_label} · Asks are red · Last traded price is amber · "
                "Bids are green · Quantity is stacked at each price"
            )
            ladder = pd.DataFrame(
                ladder_records,
                columns=["side", "order_id", "price", "quantity", "order_count"],
            )
            st.dataframe(
                _style_ladder(ladder),
                hide_index=True,
                use_container_width=True,
                height="auto",
                column_config={
                    "side": "Side",
                    "order_id": "Orders / status",
                    "price": st.column_config.NumberColumn("Price", format="%.2f"),
                    "quantity": st.column_config.NumberColumn("Stacked quantity", format="%d"),
                    "order_count": st.column_config.NumberColumn("Orders", format="%d"),
                },
            )
        with right:
            st.markdown("#### Executions caused by this event")
            if frame.trades:
                st.dataframe(pd.DataFrame(_records(frame.trades)), hide_index=True, use_container_width=True)
            else:
                st.info("This event did not execute a trade.")

    playback_ladder()


st.title("Liquidity Stress Lab")
st.caption("Explore how order flow and liquidity affect spreads, depth, prices, and execution conditions.")
st.warning("Educational synthetic simulation only — results are not calibrated to a real instrument or venue and are not financial advice.")

view = st.sidebar.radio("Workspace", ["Configure", "Overview", "Compare", "Order-book playback"])
st.sidebar.markdown("---")
st.sidebar.caption("Deterministic Level 3 simulation · price-time priority")

if view == "Configure":
    st.subheader("Configure a market scenario")
    try:
        config = _scenario_form()
        if config is not None:
            with st.spinner("Running deterministic market simulation…"):
                st.session_state.scenario_result = run_scenario(config)
                st.session_state.pop("comparison_result", None)
                st.session_state.pop("playback_event_number", None)
                st.session_state.pop("playback_running", None)
                st.session_state.pop("playback_execution_jump", None)
                st.session_state.pop("playback_show_full_book", None)
            st.success("Simulation complete. Open Overview, Compare, or Order-book playback.")
    except ValueError as exc:
        st.error(str(exc))
elif view == "Overview":
    if result := _require_result():
        _overview(result)
elif view == "Compare":
    if result := _require_result():
        _compare(result)
else:
    if result := _require_result():
        _playback(result)
