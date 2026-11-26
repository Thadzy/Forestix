"""SA-4 3-Color Triage Decision Rules (pure function, no Earth Engine imports)."""

from __future__ import annotations

import datetime
from typing import Any, Literal

TriageStatus = Literal["GREEN", "AMBER", "RED"]


def _days_after_cutoff(break_date: str | None, cutoff_date: str) -> int | None:
    if not break_date:
        return None
    b = datetime.date.fromisoformat(break_date[:10])
    c = datetime.date.fromisoformat(cutoff_date[:10])
    return (b - c).days


def triage(
    module_a_out: dict[str, Any],
    module_b_out: dict[str, Any],
    plot_geom_info: dict[str, Any],
    spec: dict[str, Any],
) -> TriageStatus:
    """Assign 3-color triage status (GREEN, AMBER, or RED) from Module A, Module B, and geometry.

    Implements SA-4 rules from ``docs/requirements.md``:
      1. AMBER if small plot (area < 3 rai or pure_pixels < 9), OR Module A conf < 0.70,
         OR break_date falls within +/- 30 days of cutoff_date.
      2. GREEN if Module A predicts non-forest/plantation (conf >= 0.70), OR forest with no
         persistent post-cutoff clearing.
      3. RED if Module A confirms forest (conf >= 0.70) AND Module B detects clearing past
         the +30-day buffer that passes persistence_check.

    Serves: SA-4, FR-04.
    """
    geom_cfg = spec.get("plot_geometry", {})
    triage_cfg = spec.get("triage_thresholds", {})
    min_rai = float(geom_cfg.get("min_area_rai", 3.0))
    min_px = int(geom_cfg.get("min_pure_pixels", 9))
    conf_thresh = float(triage_cfg.get("module_a_conf", 0.70))
    buf_days = int(triage_cfg.get("cutoff_buffer_days", 30))
    cutoff_date = str(spec.get("cutoff_date", "2020-12-31"))

    area_rai = float(plot_geom_info.get("area_rai", 0.0))
    pure_pixels = int(plot_geom_info.get("pure_pixels", 0))
    is_small = bool(plot_geom_info.get("is_small_plot", area_rai < min_rai or pure_pixels < min_px))

    conf = float(module_a_out.get("confidence", 0.0))
    is_forest = bool(module_a_out.get("is_forest_2020", module_a_out.get("predicted_class") == "FOREST"))

    break_date = module_b_out.get("break_date")
    persists = bool(module_b_out.get("persistence_passed", False))
    delta_days = _days_after_cutoff(break_date, cutoff_date)

    # Geometry guard & low-confidence guard always route to human review (AMBER)
    if is_small or conf < conf_thresh:
        return "AMBER"

    # Non-forest / plantation at cutoff with high confidence -> GREEN
    if not is_forest:
        return "GREEN"

    # Forest at cutoff: check post-cutoff clearing & buffer window
    if break_date is None or delta_days is None:
        return "GREEN"
    if abs(delta_days) <= buf_days:
        return "AMBER"
    if delta_days > buf_days and persists:
        return "RED"
    return "GREEN"
