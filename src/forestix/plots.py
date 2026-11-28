"""Plot ingestion, UTM 47N area calculation, and FR-01 geometry guard checks."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# WGS84 / UTM Zone 47N constants
_A = 6378137.0
_F = 1.0 / 298.257223563
_E2 = _F * (2.0 - _F)
_EP2 = _E2 / (1.0 - _E2)
_K0 = 0.9996
_LON0_RAD = math.radians(99.0)


def wgs84_to_utm47n(lon_deg: float, lat_deg: float) -> tuple[float, float]:
    """Project WGS84 (lon, lat) degrees to EPSG:32647 (UTM Zone 47N) meters."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat, cos_lat, tan_lat = math.sin(lat), math.cos(lat), math.tan(lat)
    n = _A / math.sqrt(1.0 - _E2 * sin_lat * sin_lat)
    t = tan_lat * tan_lat
    c = _EP2 * cos_lat * cos_lat
    a_term = cos_lat * (lon - _LON0_RAD)
    e4 = _E2 * _E2
    e6 = e4 * _E2
    m = _A * (
        (1.0 - _E2 / 4.0 - 3.0 * e4 / 64.0 - 5.0 * e6 / 256.0) * lat
        - (3.0 * _E2 / 8.0 + 3.0 * e4 / 32.0 + 45.0 * e6 / 1024.0) * math.sin(2.0 * lat)
        + (15.0 * e4 / 256.0 + 45.0 * e6 / 1024.0) * math.sin(4.0 * lat)
        - (35.0 * e6 / 3072.0) * math.sin(6.0 * lat)
    )
    easting = 500000.0 + _K0 * n * (
        a_term
        + (1.0 - t + c) * (a_term**3) / 6.0
        + (5.0 - 18.0 * t + t * t + 72.0 * c - 58.0 * _EP2) * (a_term**5) / 120.0
    )
    northing = _K0 * (
        m
        + n * tan_lat * (
            (a_term**2) / 2.0
            + (5.0 - t + 9.0 * c + 4.0 * c * c) * (a_term**4) / 24.0
            + (61.0 - 58.0 * t + t * t + 600.0 * c - 330.0 * _EP2) * (a_term**6) / 720.0
        )
    )
    return easting, northing


def _extract_outer_ring(geom: Any) -> list[list[float]]:
    if hasattr(geom, "__geo_interface__"):
        geom = geom.__geo_interface__
    if isinstance(geom, dict):
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        if gtype == "Polygon" and coords:
            return coords[0]
        if gtype == "MultiPolygon" and coords:
            return coords[0][0]
    raise ValueError("Expected a GeoJSON Polygon or MultiPolygon geometry.")


def load_plots(path: str | Path) -> list[dict[str, Any]]:
    """Load plot features from a GeoJSON file (EPSG:4326).

    Serves: FR-01.
    """
    with Path(path).open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return list(data.get("features") or [])


def _ring_area_and_perimeter_utm(ring_wgs84: list[list[float]]) -> tuple[float, float]:
    pts = [wgs84_to_utm47n(float(p[0]), float(p[1])) for p in ring_wgs84]
    if len(pts) < 3:
        return 0.0, 0.0
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    area2 = 0.0
    perim = 0.0
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        area2 += x1 * y2 - x2 * y1
        perim += math.hypot(x2 - x1, y2 - y1)
    return abs(area2) * 0.5, perim


def area_rai(geom_wgs84: Any) -> float:
    """Compute plot area in Thai rai (1 rai = 1,600 m^2) via EPSG:32647 projection."""
    ring = _extract_outer_ring(geom_wgs84)
    area_m2, _ = _ring_area_and_perimeter_utm(ring)
    return round(area_m2 / 1600.0, 2)


def count_pure_pixels(
    geom_wgs84: Any,
    buffer_m: float = 10.0,
    pixel_size_m: float = 10.0,
) -> int:
    """Estimate pure 10 m pixels remaining inside a -10 m inward-buffered polygon."""
    ring = _extract_outer_ring(geom_wgs84)
    area_m2, perim_m = _ring_area_and_perimeter_utm(ring)
    inner_m2 = max(0.0, area_m2 - perim_m * buffer_m + math.pi * buffer_m**2)
    if perim_m > 0 and (2.0 * area_m2 / perim_m) <= buffer_m:
        inner_m2 = 0.0
    return int(inner_m2 // (pixel_size_m**2))


def geometry_guard(geom_wgs84: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Run FR-01 geometry guard checks (area in rai, inward buffer, pure pixel count).

    Serves: FR-01, SA-4.
    """
    gcfg = spec.get("plot_geometry", {})
    buf_m = float(gcfg.get("inward_buffer_m", 10.0))
    min_rai = float(gcfg.get("min_area_rai", 3.0))
    min_px = int(gcfg.get("min_pure_pixels", 9))

    rai = area_rai(geom_wgs84)
    px = count_pure_pixels(geom_wgs84, buffer_m=buf_m, pixel_size_m=10.0)
    return {
        "area_rai": rai,
        "pure_pixels": px,
        "is_small_plot": rai < min_rai or px < min_px,
    }
