"""Evidence generation: time-series charts and before/after satellite chips."""

from pathlib import Path
from typing import Any

import pandas as pd
from shapely.geometry.base import BaseGeometry


def generate_evidence(
    plot_id: str,
    plot_geom: BaseGeometry,
    timeseries: pd.DataFrame,
    module_b_out: dict[str, Any],
    spec: dict[str, Any],
    output_dir: str | Path,
    crs: str = "EPSG:4326",
) -> dict[str, Path]:
    """Generate time-series plot (with cutoff and break markers) and before/after RGB & SWIR chips.

    Serves: FR-04.

    Args:
        plot_id: Unique identifier for the plot.
        plot_geom: Plot polygon geometry in ``crs`` (default ``EPSG:4326``).
        timeseries: Multi-sensor time-series DataFrame for the plot.
        module_b_out: Module B output containing detected ``break_date``.
        spec: Loaded specification dictionary from ``configs/spec_v1.yaml``.
        output_dir: Directory where generated evidence figures/chips are saved.
        crs: Coordinate reference system of ``plot_geom`` (default ``"EPSG:4326"``).

    Returns:
        Dictionary mapping evidence artifact names (e.g., ``"timeseries_plot"``,
        ``"before_chip"``, ``"after_chip"``) to file paths.
    """
    raise NotImplementedError
