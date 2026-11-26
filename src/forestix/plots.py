"""Plot ingestion, CRS conversion, and geometry guard checks."""

from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry.base import BaseGeometry


def load_plots(path: str | Path, crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """Load plot polygons from a GeoJSON or Shapefile.

    Serves: FR-01.

    Args:
        path: Path to the vector file (GeoJSON or SHP).
        crs: Expected/storage CRS string (default ``"EPSG:4326"``).

    Returns:
        GeoDataFrame of plot polygons in the storage CRS.
    """
    raise NotImplementedError


def to_metric_crs(gdf: gpd.GeoDataFrame, metric_crs: str = "EPSG:32647") -> gpd.GeoDataFrame:
    """Reproject plot geometries to the metric CRS for area and buffer calculations.

    Serves: FR-01.

    Args:
        gdf: Input GeoDataFrame (typically in ``EPSG:4326``).
        metric_crs: Target projected CRS in meters (default ``"EPSG:32647"``, UTM Zone 47N).

    Returns:
        Reprojected GeoDataFrame in ``metric_crs`` (units: meters).
    """
    raise NotImplementedError


def area_rai(geom_metric: BaseGeometry) -> float:
    """Compute plot area in Thai rai (1 rai = 1,600 m^2).

    Serves: FR-01.

    Args:
        geom_metric: Plot geometry in metric CRS (``EPSG:32647``, units: meters).

    Returns:
        Plot area in rai (float).
    """
    raise NotImplementedError


def inward_buffer(geom_metric: BaseGeometry, buffer_m: float = 10.0) -> BaseGeometry:
    """Shrink plot polygon inward to exclude edge mixed pixels.

    Serves: FR-01, SA-2.

    Args:
        geom_metric: Plot geometry in metric CRS (``EPSG:32647``, units: meters).
        buffer_m: Inward buffer distance in meters (default ``10.0`` m).

    Returns:
        Inward-buffered geometry in metric CRS (``EPSG:32647``; may be empty if plot is too narrow).
    """
    raise NotImplementedError


def count_pure_pixels(geom_metric: BaseGeometry, pixel_size_m: float = 10.0) -> int:
    """Estimate the number of pure 10 m pixels inside an inward-buffered plot geometry.

    Serves: FR-01, SA-2.

    Args:
        geom_metric: Buffered plot geometry in metric CRS (``EPSG:32647``, units: meters).
        pixel_size_m: Reference pixel size in meters (default ``10.0`` m for Sentinel-2).

    Returns:
        Estimated count of pure pixels (int).
    """
    raise NotImplementedError


def geometry_guard(geom_metric: BaseGeometry, spec: dict[str, Any]) -> dict[str, Any]:
    """Run FR-01 geometry guard checks (area in rai, inward buffer, pure pixel count).

    Serves: FR-01, SA-4.

    Args:
        geom_metric: Plot geometry in metric CRS (``EPSG:32647``, units: meters).
        spec: Loaded specification dictionary from ``configs/spec_v1.yaml``.

    Returns:
        Dictionary containing ``area_rai`` (float), ``pure_pixels`` (int),
        ``buffered_geom`` (BaseGeometry in ``EPSG:32647``), and ``is_small_plot`` (bool).
    """
    raise NotImplementedError
