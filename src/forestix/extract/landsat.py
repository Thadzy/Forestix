"""Landsat 8/9 Collection 2 Level-2 yearly NDVI and NBR extraction (pre-2020 history)."""

from __future__ import annotations

from typing import Any

import ee


def _to_ee_geometry(plot_geom: Any) -> ee.Geometry:
    if isinstance(plot_geom, ee.Geometry):
        return plot_geom
    if hasattr(plot_geom, "__geo_interface__"):
        return ee.Geometry(plot_geom.__geo_interface__)
    if isinstance(plot_geom, dict):
        return ee.Geometry(plot_geom)
    raise TypeError(f"Unsupported geometry type: {type(plot_geom)}")


def _prep_landsat_c2(img: ee.Image) -> ee.Image:
    """Apply QA_PIXEL cloud/shadow mask and Collection 2 L2 reflectance scaling, then add NDVI/NBR."""
    qa = img.select("QA_PIXEL")
    # Bits 1 (dilated cloud), 2 (cirrus), 3 (cloud), 4 (cloud shadow) must be 0
    clear = (
        qa.bitwiseAnd(1 << 1).eq(0)
        .And(qa.bitwiseAnd(1 << 2).eq(0))
        .And(qa.bitwiseAnd(1 << 3).eq(0))
        .And(qa.bitwiseAnd(1 << 4).eq(0))
    )
    sr = img.select(["SR_B4", "SR_B5", "SR_B7"]).multiply(0.0000275).add(-0.2)
    ndvi = sr.normalizedDifference(["SR_B5", "SR_B4"]).rename("ndvi")
    nbr = sr.normalizedDifference(["SR_B5", "SR_B7"]).rename("nbr")
    return ee.Image.cat([ndvi, nbr]).updateMask(clear)


def extract_landsat_batch(
    plots_fc: ee.FeatureCollection,
    start_year: int,
    end_year: int,
    datasets: dict[str, Any],
    scale_m: int = 30,
) -> list[dict[str, Any]]:
    """Extract yearly Landsat 8/9 NDVI and NBR (median, p10, p90) for a batch of plots.

    Serves: DS-6, FR-02.
    """
    bounds = plots_fc.geometry().bounds()
    l8 = ee.ImageCollection(datasets["landsat_8"]).filterBounds(bounds)
    l9_id = datasets.get("landsat_9")
    if l9_id:
        col = l8.merge(ee.ImageCollection(l9_id).filterBounds(bounds))
    else:
        col = l8

    rows: list[dict[str, Any]] = []
    for year in range(start_year, end_year + 1):
        yr_col = col.filterDate(f"{year}-01-01", f"{year + 1}-01-01").map(_prep_landsat_c2)
        composite = ee.Image.cat(
            [
                yr_col.select("ndvi").median().rename("ndvi_med"),
                yr_col.select("ndvi").reduce(ee.Reducer.percentile([10])).rename("ndvi_p10"),
                yr_col.select("ndvi").reduce(ee.Reducer.percentile([90])).rename("ndvi_p90"),
                yr_col.select("nbr").median().rename("nbr_med"),
                yr_col.select("nbr").reduce(ee.Reducer.percentile([10])).rename("nbr_p10"),
                yr_col.select("ndvi").count().rename("obs_count"),
            ]
        )
        reduced = composite.reduceRegions(
            collection=plots_fc,
            reducer=ee.Reducer.mean(),
            scale=scale_m,
            tileScale=4,
        )
        for f in reduced.getInfo().get("features", []):
            p = f.get("properties") or {}
            rows.append(
                {
                    "plot_id": p.get("plot_id"),
                    "year": year,
                    "ndvi_med": p.get("ndvi_med"),
                    "ndvi_p10": p.get("ndvi_p10"),
                    "ndvi_p90": p.get("ndvi_p90"),
                    "nbr_med": p.get("nbr_med"),
                    "nbr_p10": p.get("nbr_p10"),
                    "obs_count": p.get("obs_count"),
                }
            )
    return rows


def extract_landsat_yearly(
    plot_geom: Any,
    start_year: int,
    end_year: int,
    datasets: dict[str, Any],
    crs: str = "EPSG:4326",
) -> list[dict[str, Any]]:
    """Extract Landsat 8/9 C2 L2 yearly NDVI and NBR composites for a single plot."""
    _ = crs
    fc = ee.FeatureCollection([ee.Feature(_to_ee_geometry(plot_geom), {"plot_id": "single"})])
    return extract_landsat_batch(fc, start_year, end_year, datasets)
