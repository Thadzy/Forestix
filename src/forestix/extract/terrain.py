"""SRTM terrain elevation, slope, and JRC GFC2020 baseline extraction."""

from __future__ import annotations

from typing import Any

import ee


def _to_ee_geometry(plot_geom: Any) -> ee.Geometry:
    """Convert a GeoJSON dict, Shapely geometry, or ee.Geometry into ee.Geometry."""
    if isinstance(plot_geom, ee.Geometry):
        return plot_geom
    if hasattr(plot_geom, "__geo_interface__"):
        return ee.Geometry(plot_geom.__geo_interface__)
    if isinstance(plot_geom, dict):
        return ee.Geometry(plot_geom)
    raise TypeError(f"Unsupported geometry type: {type(plot_geom)}")


def build_terrain_jrc_image(datasets: dict[str, Any]) -> ee.Image:
    """Build a multi-band image with SRTM elevation (m), slope (deg), and JRC forest2020 (0/1)."""
    srtm = ee.Image(datasets["srtm"]).select("elevation").rename("elevation")
    slope = ee.Terrain.slope(srtm).rename("slope")
    jrc = (
        ee.Image(datasets["jrc_gfc_2020"])
        .select("Map")
        .unmask(0)
        .eq(1)
        .toFloat()
        .rename("jrc_forest2020")
    )
    return ee.Image.cat([srtm, slope, jrc])


def extract_terrain_batch(
    plots_fc: ee.FeatureCollection,
    datasets: dict[str, Any],
    scale_m: int = 30,
) -> list[dict[str, Any]]:
    """Extract SRTM elevation, slope (mean/max), and JRC forest fraction for a batch of plots.

    Serves: DS-6, FR-02, SA-2.
    """
    img = build_terrain_jrc_image(datasets)
    reducer = ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True)
    reduced = img.reduceRegions(
        collection=plots_fc,
        reducer=reducer,
        scale=scale_m,
        tileScale=4,
    )
    feats = reduced.getInfo().get("features", [])
    rows: list[dict[str, Any]] = []
    for f in feats:
        p = f.get("properties") or {}
        rows.append(
            {
                "plot_id": p.get("plot_id"),
                "label_class": p.get("label_class"),
                "district": p.get("district"),
                "area_rai": p.get("area_rai"),
                "elevation_mean": p.get("elevation_mean"),
                "slope_mean": p.get("slope_mean"),
                "slope_max": p.get("slope_max"),
                "jrc_forest2020_frac": p.get("jrc_forest2020_mean"),
            }
        )
    return rows


def extract_terrain(
    plot_geom: Any,
    datasets: dict[str, Any],
    crs: str = "EPSG:4326",
) -> dict[str, float]:
    """Extract SRTM elevation and terrain slope summary statistics for a single plot.

    Serves: FR-02, SA-2.
    """
    _ = crs
    geom = _to_ee_geometry(plot_geom)
    fc = ee.FeatureCollection([ee.Feature(geom, {"plot_id": "single"})])
    rows = extract_terrain_batch(fc, datasets)
    if not rows:
        return {}
    r = rows[0]
    return {
        "elevation_mean": float(r["elevation_mean"]) if r["elevation_mean"] is not None else float("nan"),
        "slope_mean": float(r["slope_mean"]) if r["slope_mean"] is not None else float("nan"),
        "slope_max": float(r["slope_max"]) if r["slope_max"] is not None else float("nan"),
        "jrc_forest2020_frac": (
            float(r["jrc_forest2020_frac"]) if r["jrc_forest2020_frac"] is not None else float("nan")
        ),
    }
