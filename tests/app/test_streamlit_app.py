from pathlib import Path

import pytest


streamlit = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


APP = Path(__file__).parents[2] / "streamlit_app.py"


def _widget_with_label(widgets, label: str):
    return next(widget for widget in widgets if widget.label == label)


def _run_short_scenario(app: AppTest) -> AppTest:
    _widget_with_label(app.number_input, "Generated events").set_value(10)
    _widget_with_label(app.button, "Run simulation").click()
    return app.run(timeout=20)


def test_app_launches_and_runs_default_workflow() -> None:
    app = AppTest.from_file(str(APP)).run(timeout=20)

    assert not app.exception
    assert app.title[0].value == "Liquidity Stress Lab"
    app = _run_short_scenario(app)

    assert not app.exception
    assert any("Simulation complete" in item.value for item in app.success)
    _widget_with_label(app.radio, "Workspace").set_value("Overview")
    app.run(timeout=20)

    assert not app.exception
    assert any("Overview" in item.value for item in app.subheader)
    assert len(app.metric) >= 7
    assert len(app.get("download_button")) == 4


def test_app_empty_views_prompt_for_a_scenario() -> None:
    app = AppTest.from_file(str(APP)).run(timeout=20)
    _widget_with_label(app.radio, "Workspace").set_value("Order-book playback")
    app.run(timeout=20)

    assert not app.exception
    assert any("run a scenario first" in item.value for item in app.info)


def test_app_compares_scenarios_and_opens_playback() -> None:
    app = _run_short_scenario(AppTest.from_file(str(APP)).run(timeout=20))
    _widget_with_label(app.radio, "Workspace").set_value("Compare")
    app.run(timeout=20)
    _widget_with_label(app.button, "Run comparison").click()
    app.run(timeout=20)

    assert not app.exception
    assert app.dataframe

    _widget_with_label(app.radio, "Workspace").set_value("Order-book playback")
    app.run(timeout=20)
    _widget_with_label(app.slider, "Event").set_value(2)
    app.run(timeout=20)

    assert not app.exception
    assert any("Order-book playback" in item.value for item in app.subheader)
    assert app.dataframe
    assert any(widget.label == "▶ Play" for widget in app.button)
    assert any("Asks are red" in item.value and "Last traded price is amber" in item.value for item in app.caption)
    ladder_sides = app.dataframe[0].value["side"].tolist()
    last_trade_index = ladder_sides.index("LAST TRADE")
    assert all(side == "ASK" for side in ladder_sides[:last_trade_index])
    assert all(side == "BID" for side in ladder_sides[last_trade_index + 1:])
    assert ladder_sides.count("ASK") <= 5
    assert ladder_sides.count("BID") <= 5

    full_depth = _widget_with_label(app.toggle, "Show full order book")
    assert full_depth.value is False
    full_depth.set_value(True)
    app.run(timeout=20)

    assert not app.exception
    assert any("Full depth" in item.value for item in app.caption)

    _widget_with_label(app.button, "▶ Play").click()
    app.run(timeout=20)

    assert not app.exception
    assert _widget_with_label(app.slider, "Event").value == 3
    assert any(widget.label == "⏸ Pause" for widget in app.button)


def test_full_order_book_expands_the_ladder_and_persists() -> None:
    app = AppTest.from_file(str(APP)).run(timeout=20)
    _widget_with_label(app.number_input, "Generated events").set_value(100)
    _widget_with_label(app.button, "Run simulation").click()
    app.run(timeout=20)
    _widget_with_label(app.radio, "Workspace").set_value("Order-book playback")
    app.run(timeout=20)
    _widget_with_label(app.slider, "Event").set_value(110)
    app.run(timeout=20)

    compact_rows = len(app.dataframe[0].value)
    assert compact_rows == 11
    _widget_with_label(app.toggle, "Show full order book").set_value(True)
    app.run(timeout=20)

    assert not app.exception
    assert _widget_with_label(app.toggle, "Show full order book").value is True
    assert len(app.dataframe[0].value) > compact_rows
    assert any("Full depth:" in item.value for item in app.caption)

    _widget_with_label(app.slider, "Event").set_value(109)
    app.run(timeout=20)
    assert _widget_with_label(app.toggle, "Show full order book").value is True

    _widget_with_label(app.toggle, "Show full order book").set_value(False)
    app.run(timeout=20)
    assert _widget_with_label(app.toggle, "Show full order book").value is False
    assert len(app.dataframe[0].value) == compact_rows
    assert any("Showing 5 of" in item.value for item in app.caption)


def test_playback_opens_after_the_initial_book_is_seeded() -> None:
    app = _run_short_scenario(AppTest.from_file(str(APP)).run(timeout=20))
    _widget_with_label(app.radio, "Workspace").set_value("Order-book playback")
    app.run(timeout=20)

    # The default scenario has five initial levels on each side, represented by
    # ten seed events. Starting there avoids presenting a one-order book as the
    # initial playback state.
    assert _widget_with_label(app.slider, "Event").value == 10
    assert len(app.dataframe[0].value) == 11
    assert any("Showing 5 of 5 ask + 5 of 5 bid" in item.value for item in app.caption)


def test_app_shows_business_validation_errors() -> None:
    app = AppTest.from_file(str(APP)).run(timeout=20)
    _widget_with_label(app.number_input, "Minimum quantity").set_value(5)
    _widget_with_label(app.number_input, "Maximum quantity").set_value(4)
    _widget_with_label(app.button, "Run simulation").click()
    app.run(timeout=20)

    assert not app.exception
    assert any("quantity bounds" in item.value for item in app.error)
