"""Skipped test stubs for SA-4 3-color triage decision rules."""

import pytest


@pytest.mark.skip(reason="SA-4 rules not final")
def test_green_old_farm() -> None:
    """Verify existing cropland before cutoff with Conf >= 0.70 returns GREEN.

    Serves: SA-4, G2.
    """
    raise NotImplementedError


@pytest.mark.skip(reason="SA-4 rules not final")
def test_red_new_clearing() -> None:
    """Verify forest at cutoff with Conf >= 0.70, post-buffer clearing, and persistence returns RED.

    Serves: SA-4, G1.
    """
    raise NotImplementedError


@pytest.mark.skip(reason="SA-4 rules not final")
def test_amber_low_conf() -> None:
    """Verify Module A confidence < 0.70 returns AMBER.

    Serves: SA-4.
    """
    raise NotImplementedError


@pytest.mark.skip(reason="SA-4 rules not final")
def test_amber_small_plot() -> None:
    """Verify plot with area < 3 rai or pure pixels < 9 returns AMBER.

    Serves: SA-4, FR-01.
    """
    raise NotImplementedError


@pytest.mark.skip(reason="SA-4 rules not final")
def test_amber_break_in_buffer() -> None:
    """Verify break date within +/- 30 days of cutoff returns AMBER.

    Serves: SA-4.
    """
    raise NotImplementedError


@pytest.mark.skip(reason="SA-4 rules not final")
def test_small_plot_old_farm_conflict() -> None:
    """Verify precedence when a plot is both small (< 3 rai) and old farm (Conf >= 0.70).

    Serves: SA-4 (open precedence item).
    """
    raise NotImplementedError


@pytest.mark.skip(reason="SA-4 rules not final")
def test_cleared_but_fails_persistence() -> None:
    """Verify behavior when Module B detects a drop that fails the persistence check.

    Serves: SA-4, CM-2 (open uncovered case).
    """
    raise NotImplementedError
