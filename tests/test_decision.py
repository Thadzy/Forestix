"""Unit tests for SA-4 3-color triage decision rules (all 7 cases active)."""

from __future__ import annotations

from forestix.config import load_spec
from forestix.decision import triage

SPEC = load_spec("configs/spec_v1.yaml")
BIG_PLOT = {"area_rai": 5.0, "pure_pixels": 36, "is_small_plot": False}
SMALL_PLOT = {"area_rai": 1.8, "pure_pixels": 6, "is_small_plot": True}


def test_green_old_farm() -> None:
    """Verify existing cropland before cutoff with Conf >= 0.70 returns GREEN."""
    mod_a = {"predicted_class": "NON_FOREST", "confidence": 0.90, "is_forest_2020": False}
    mod_b = {"break_date": None, "persistence_passed": False}
    assert triage(mod_a, mod_b, BIG_PLOT, SPEC) == "GREEN"


def test_red_new_clearing() -> None:
    """Verify forest at cutoff with Conf >= 0.70, post-buffer clearing, and persistence returns RED."""
    mod_a = {"predicted_class": "FOREST", "confidence": 0.88, "is_forest_2020": True}
    mod_b = {"break_date": "2023-03-15", "persistence_passed": True}
    assert triage(mod_a, mod_b, BIG_PLOT, SPEC) == "RED"


def test_amber_low_conf() -> None:
    """Verify Module A confidence < 0.70 returns AMBER."""
    mod_a = {"predicted_class": "FOREST", "confidence": 0.62, "is_forest_2020": True}
    mod_b = {"break_date": "2023-03-15", "persistence_passed": True}
    assert triage(mod_a, mod_b, BIG_PLOT, SPEC) == "AMBER"


def test_amber_small_plot() -> None:
    """Verify plot with area < 3 rai or pure pixels < 9 returns AMBER."""
    mod_a = {"predicted_class": "FOREST", "confidence": 0.95, "is_forest_2020": True}
    mod_b = {"break_date": "2023-03-15", "persistence_passed": True}
    assert triage(mod_a, mod_b, SMALL_PLOT, SPEC) == "AMBER"


def test_amber_break_in_buffer() -> None:
    """Verify break date within +/- 30 days of cutoff (2020-12-31) returns AMBER."""
    mod_a = {"predicted_class": "FOREST", "confidence": 0.92, "is_forest_2020": True}
    mod_b = {"break_date": "2021-01-15", "persistence_passed": True}
    assert triage(mod_a, mod_b, BIG_PLOT, SPEC) == "AMBER"


def test_small_plot_old_farm_conflict() -> None:
    """Geometry guard takes precedence: small plot (< 3 rai) routes to AMBER even if old farm."""
    mod_a = {"predicted_class": "NON_FOREST", "confidence": 0.92, "is_forest_2020": False}
    mod_b = {"break_date": None, "persistence_passed": False}
    assert triage(mod_a, mod_b, SMALL_PLOT, SPEC) == "AMBER"


def test_cleared_but_fails_persistence() -> None:
    """Transient drop failing persistence check (deciduous leaf-off) returns GREEN."""
    mod_a = {"predicted_class": "FOREST", "confidence": 0.90, "is_forest_2020": True}
    mod_b = {"break_date": "2022-03-15", "persistence_passed": False}
    assert triage(mod_a, mod_b, BIG_PLOT, SPEC) == "GREEN"
