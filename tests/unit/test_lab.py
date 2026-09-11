from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from l3sim.domain import AddOrderEvent, CancelOrderEvent, Order, Side
from l3sim.lab import (
    ActivityLevel,
    LiquidityLevel,
    ScenarioConfig,
    ScenarioPreset,
    run_scenario,
)
from l3sim.lab.scenario import _result_from_runner
from l3sim.simulation import Runner


NOW = datetime(2026, 8, 16, tzinfo=timezone.utc)


def test_every_preset_runs_and_finishes_with_a_non_crossed_book() -> None:
    for preset in ScenarioPreset:
        result = run_scenario(ScenarioConfig(preset=preset, event_count=50))
        frame = result.playback_frame(len(result.events))

        if frame.best_bid is not None and frame.best_ask is not None:
            assert frame.best_bid < frame.best_ask
        assert len(result.time_series) == 50 + 2 * result.config.initial_levels


def test_identical_configurations_are_fully_deterministic() -> None:
    config = ScenarioConfig(preset=ScenarioPreset.THIN_LIQUIDITY, event_count=75, seed=91)

    assert run_scenario(config) == run_scenario(config)


def test_business_controls_and_expert_overrides_compile_to_generator_config() -> None:
    config = ScenarioConfig(
        preset=ScenarioPreset.BUY_PRESSURE,
        activity_level=ActivityLevel.LOW,
        starting_liquidity=LiquidityLevel.DEEP,
        buy_sell_pressure=-25,
        limit_order_rate=9.0,
    )

    generated = config.to_generator_config()

    assert config.initial_levels == 8
    assert generated.buy_probability == pytest.approx(0.4)
    assert generated.limit_order_rate == 9.0
    assert generated.market_order_rate == pytest.approx(1.2)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"event_count": 0}, "event_count"),
        ({"starting_price": Decimal("0")}, "starting_price"),
        ({"buy_sell_pressure": 101}, "buy_sell_pressure"),
        ({"quantity_min": 5, "quantity_max": 4}, "quantity bounds"),
        ({"cancel_rate": -1.0}, "cancel_rate"),
    ],
)
def test_scenario_config_rejects_invalid_business_inputs(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ScenarioConfig(**kwargs)


def test_kpis_handle_one_sided_and_undefined_market_state() -> None:
    runner = Runner()
    runner.process(
        AddOrderEvent(
            "event-1",
            NOW,
            Order("bid-1", NOW, Side.BUY, Decimal("99"), 10),
        )
    )

    result = _result_from_runner(ScenarioConfig(event_count=1), runner)

    assert result.summary.trade_count == 0
    assert result.summary.executed_volume == 0
    assert result.summary.final_price is None
    assert result.summary.average_spread is None
    assert result.summary.maximum_spread is None
    assert result.summary.average_depth == 10
    assert result.summary.final_imbalance == Decimal("1")
    assert "without a two-sided midpoint" in result.interpretation()


def test_kpis_and_event_descriptions_match_a_hand_built_run() -> None:
    runner = Runner()
    runner.process(AddOrderEvent("e-1", NOW, Order("bid", NOW, Side.BUY, Decimal("99"), 10)))
    runner.process(AddOrderEvent("e-2", NOW, Order("ask", NOW, Side.SELL, Decimal("101"), 30)))
    runner.process(CancelOrderEvent("e-3", NOW + timedelta(seconds=1), "ask", 10))

    result = _result_from_runner(ScenarioConfig(event_count=1), runner)

    assert result.summary.final_price == Decimal("100")
    assert result.summary.price_change == Decimal("0")
    assert result.summary.average_spread == Decimal("2")
    assert result.summary.maximum_spread == Decimal("2")
    assert result.summary.average_depth == pytest.approx(80 / 3)
    assert result.summary.final_imbalance == Decimal("-1") / Decimal("3")
    assert result.events[-1].description == "Cancelled 10 from order ask."


def test_playback_reports_before_and_after_values_and_validates_bounds() -> None:
    result = run_scenario(ScenarioConfig(event_count=5))
    frame = result.playback_frame(2)

    assert frame.previous_best_bid == result.time_series[0].best_bid
    assert frame.best_bid == result.time_series[1].best_bid
    assert frame.ladder
    assert all(row.order_id for row in frame.ladder)
    with pytest.raises(IndexError):
        result.playback_frame(0)


def test_all_csv_exports_have_headers_and_rows() -> None:
    result = run_scenario(ScenarioConfig(event_count=5))

    assert result.summary_csv().startswith("trade_count,executed_volume")
    assert result.time_series_csv().count("\n") == len(result.time_series) + 1
    assert "description" in result.events_csv().splitlines()[0]
    assert result.final_ladder_csv().startswith("side,order_id,price,quantity,order_count")
