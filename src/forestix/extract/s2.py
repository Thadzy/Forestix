"""Sentinel-2 L2A time-series extraction with Cloud Score+ masking."""

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


def _build_s2_masked_collection(
    bounds: ee.Geometry,
    start_date: str,
    end_date: str,
    datasets: dict[str, Any],
    cs_thresh: float = 0.60,
) -> ee.ImageCollection:
    """Link Sentinel-2 SR Harmonized with Cloud Score+ and compute NDVI, NBR, NDMI, Red-Edge NDVI."""
    s2 = (
        ee.ImageCollection(datasets["s2_sr_harmonized"])
        .filterBounds(bounds)
        .filterDate(start_date, end_date)
    )
    cs_plus = (
        ee.ImageCollection(datasets["cloud_score_plus"])
        .filterBounds(bounds)
        .filterDate(start_date, end_date)
    )
    linked = s2.linkCollection(cs_plus, ["cs_cdf"])

    def _mask_and_indices(img: ee.Image) -> ee.Image:
        clear = img.select("cs_cdf").gte(cs_thresh)
        scaled = img.select(["B4", "B5", "B8", "B8A", "B11", "B12"]).multiply(0.0001)
        ndvi = scaled.normalizedDifference(["B8", "B4"]).rename("ndvi")
        nbr = scaled.normalizedDifference(["B8", "B12"]).rename("nbr")
        ndmi = scaled.normalizedDifference(["B8A", "B11"]).rename("ndmi")
        re_ndvi = scaled.normalizedDifference(["B8A", "B5"]).rename("re_ndvi")
        return (
            ee.Image.cat([ndvi, nbr, ndmi, re_ndvi])
            .updateMask(clear)
            .copyProperties(img, ["system:time_start"])
        )

    return linked.map(_mask_and_indices)


def extract_s2_monthly_batch(
    plots_fc: ee.FeatureCollection,
    year: int,
    datasets: dict[str, Any],
    cs_thresh: float = 0.60,
    scale_m: int = 10,
) -> list[dict[str, Any]]:
    """Extract monthly cloud-masked Sentinel-2 indices for all plots in one calendar year.

    Serves: DS-6, FR-02.
    """
    bounds = plots_fc.geometry().bounds()
    yr_col = _build_s2_masked_collection(
        bounds, f"{year}-01-01", f"{year + 1}-01-01", datasets, cs_thresh=cs_thresh
    )

    def _per_month(m: ee.Number) -> ee.FeatureCollection:
        m_num = ee.Number(m)
        start = ee.Date.fromYMD(year, m_num, 1)
        end = start.advance(1, "month")
        m_col = yr_col.filterDate(start, end)
        # Safe empty-month fallback so band names always exist
        empty_img = ee.Image.constant([0, 0, 0, 0, 0]).rename(
            ["ndvi", "nbr", "ndmi", "re_ndvi", "clear_obs"]
        ).updateMask(ee.Image(0))
        comp = ee.Image(
            ee.Algorithms.If(
                m_col.size().gt(0),
                ee.Image.cat(
                    [
                        m_col.select(["ndvi", "nbr", "ndmi", "re_ndvi"]).median(),
                        m_col.select("ndvi").count().rename("clear_obs"),
                    ]
                ),
                empty_img,
            )
        )
        ym = start.format("YYYY-MM")
        return comp.reduceRegions(
            collection=plots_fc,
            reducer=ee.Reducer.mean(),
            scale=scale_m,
            tileScale=8,
        ).map(lambda f: f.set("ym", ym).setGeometry(None))

    rows: list[dict[str, Any]] = []
    # Process quarterly (3 months per GEE compute call) to stay well within GEE user memory limits.
    for q_start in (1, 4, 7, 10):
        q_months = ee.List.sequence(q_start, q_start + 2)
        q_fc = ee.FeatureCollection(q_months.map(_per_month)).flatten()
        for f in q_fc.getInfo().get("features", []):
            p = f.get("properties") or {}
            rows.append(
                {
                    "plot_id": p.get("plot_id"),
                    "ym": p.get("ym"),
                    "ndvi": p.get("ndvi"),
                    "nbr": p.get("nbr"),
                    "ndmi": p.get("ndmi"),
                    "re_ndvi": p.get("re_ndvi"),
                    "clear_obs": p.get("clear_obs") or 0,
                }
            )
    return rows


def extract_s2_timeseries(
    plot_geom: Any,
    start_date: str,
    end_date: str,
    datasets: dict[str, Any],
    crs: str = "EPSG:4326",
) -> list[dict[str, Any]]:
    """Extract monthly Sentinel-2 L2A time series for a single plot."""
    _ = crs
    fc = ee.FeatureCollection([ee.Feature(_to_ee_geometry(plot_geom), {"plot_id": "single"})])
    start_yr = int(start_date[:4])
    end_yr = int(end_date[:4])
    out: list[dict[str, Any]] = []
    for yr in range(start_yr, end_yr + 1):
        out.extend(extract_s2_monthly_batch(fc, yr, datasets))
    return out
