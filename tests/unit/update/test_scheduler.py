"""Tests for the periodic update-check timer (spec §8.1)."""
import pytest

from locksmith.update.scheduler import (
    UpdateScheduler, INITIAL_DELAY_MS, CADENCE_MS,
)


def test_initial_delay_is_30_seconds():
    assert INITIAL_DELAY_MS == 30_000


def test_cadence_is_4_hours():
    assert CADENCE_MS == 4 * 60 * 60 * 1000


def test_start_emits_check_requested_after_initial_delay(qtbot):
    scheduler = UpdateScheduler()
    with qtbot.waitSignal(scheduler.check_requested, timeout=2000):
        scheduler.start(initial_delay_ms_override=100)


def test_stop_prevents_further_checks(qtbot):
    scheduler = UpdateScheduler()
    scheduler.start(initial_delay_ms_override=50)
    qtbot.wait(150)  # let initial fire
    scheduler.stop()
    received = []
    scheduler.check_requested.connect(lambda: received.append(1))
    qtbot.wait(200)
    assert received == []


def test_trigger_now_emits_check_requested(qtbot):
    scheduler = UpdateScheduler()
    with qtbot.waitSignal(scheduler.check_requested, timeout=500):
        scheduler.trigger_now()


def test_is_enabled_reflects_running_state():
    scheduler = UpdateScheduler()
    assert scheduler.is_enabled is False
    scheduler.start(initial_delay_ms_override=10_000_000)  # huge delay; won't fire
    assert scheduler.is_enabled is True
    scheduler.stop()
    assert scheduler.is_enabled is False
