"""Sentinel-1 GRD SAR time-series extraction (ascending and descending kept separate)."""

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


def extract_s1_monthly_batch(
    plots_fc: ee.FeatureCollection,
    year: int,
    datasets: dict[str, Any],
    scale_m: int = 10,
) -> list[dict[str, Any]]:
    """Extract monthly Sentinel-1 VV/VH/VH-VV (dB) with ASCENDING and DESCENDING kept strictly separate.

    Serves: DS-6, FR-02, SA-2 (late fusion on steep Nan terrain).
    """
    bounds = plots_fc.geometry().bounds()
    base_col = (
        ee.ImageCollection(datasets["s1_grd"])
        .filterBounds(bounds)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .select(["VV", "VH"])
    )

    rows: list[dict[str, Any]] = []
    for orbit in ("ASCENDING", "DESCENDING"):
        orbit_col = base_col.filter(ee.Filter.eq("orbitProperties_pass", orbit))

        def _per_month(m: ee.Number) -> ee.FeatureCollection:
            m_num = ee.Number(m)
            start = ee.Date.fromYMD(year, m_num, 1)
            end = start.advance(1, "month")
            m_col = orbit_col.filterDate(start, end)
            empty_img = ee.Image.constant([0, 0, 0, 0]).rename(
                ["vv", "vh", "vh_minus_vv", "obs_count"]
            ).updateMask(ee.Image(0))

            def _make_comp() -> ee.Image:
                med = m_col.median()
                vv = med.select("VV").rename("vv")
                vh = med.select("VH").rename("vh")
                ratio = vh.subtract(vv).rename("vh_minus_vv")
                cnt = m_col.select("VH").count().rename("obs_count")
                return ee.Image.cat([vv, vh, ratio, cnt])

            comp = ee.Image(ee.Algorithms.If(m_col.size().gt(0), _make_comp(), empty_img))
            ym = start.format("YYYY-MM")
            return comp.reduceRegions(
                collection=plots_fc,
                reducer=ee.Reducer.mean(),
                scale=scale_m,
                tileScale=8,
            ).map(lambda f: f.set({"ym": ym, "orbit": orbit}).setGeometry(None))

        for half_start in (1, 7):
            h_fc = ee.FeatureCollection(ee.List.sequence(half_start, half_start + 5).map(_per_month)).flatten()
            for f in h_fc.getInfo().get("features", []):
                p = f.get("properties") or {}
                rows.append(
                    {
                        "plot_id": p.get("plot_id"),
                        "ym": p.get("ym"),
                        "orbit": p.get("orbit"),
                        "vv": p.get("vv"),
                        "vh": p.get("vh"),
                        "vh_minus_vv": p.get("vh_minus_vv"),
                        "obs_count": p.get("obs_count") or 0,
                    }
                )
    return rows


def extract_s1_timeseries(
    plot_geom: Any,
    start_date: str,
    end_date: str,
    datasets: dict[str, Any],
    crs: str = "EPSG:4326",
) -> list[dict[str, Any]]:
    """Extract monthly Sentinel-1 VV/VH time series for a single plot, keeping orbits separate."""
    _ = crs
    fc = ee.FeatureCollection([ee.Feature(_to_ee_geometry(plot_geom), {"plot_id": "single"})])
    start_yr = int(start_date[:4])
    end_yr = int(end_date[:4])
    out: list[dict[str, Any]] = []
    for yr in range(start_yr, end_yr + 1):
        out.extend(extract_s1_monthly_batch(fc, yr, datasets))
    return out
