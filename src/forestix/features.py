"""DS-8 Feature engineering from multi-sensor time series (strictly pre-cutoff for Module A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FEATURE_COLUMNS: list[str] = [
    # Landsat 2015-2020 (long-term pre-cutoff history)
    "ls_ndvi_med",
    "ls_ndvi_min",
    "ls_ndvi_std",
    "ls_nbr_med",
    "ls_nbr_min",
    "ls_ndvi_2020",
    # Sentinel-2 2018-2020 (phenology: dry vs rainy season)
    "s2_ndvi_dry",
    "s2_ndvi_rain",
    "s2_ndvi_amp",
    "s2_nbr_dry",
    "s2_nbr_rain",
    "s2_ndmi_dry",
    "s2_re_ndvi_med",
    # Sentinel-1 2018-2020 (SAR structure, Asc & Desc kept separate)
    "s1_vh_asc_med",
    "s1_vh_dsc_med",
    "s1_vv_asc_med",
    "s1_vv_dsc_med",
    "s1_ratio_asc_med",
    "s1_ratio_dsc_med",
    "s1_vh_asc_std",
    "s1_vh_dsc_std",
    # SRTM Terrain
    "elevation_mean",
    "slope_mean",
    "slope_max",
]


def _safe_stat(series: pd.Series, fn: str) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return float("nan")
    if fn == "median":
        return float(clean.median())
    if fn == "min":
        return float(clean.min())
    if fn == "std":
        return float(clean.std(ddof=0))
    return float(clean.mean())


def build_features_from_tables(
    terrain_df: pd.DataFrame,
    landsat_df: pd.DataFrame,
    s2_df: pd.DataFrame,
    s1_df: pd.DataFrame,
    cutoff_year: int = 2020,
) -> pd.DataFrame:
    """Build per-plot pre-cutoff feature table from the 4 DS-5 exported CSV tables.

    Strictly uses observations <= ``cutoff_year`` (zero post-2020 leakage into Module A).
    Deliberately excludes JRC GFC2020 from input features so Module A can be benchmarked
    independently against JRC in TR-4.

    Serves: DS-8, FR-03.
    """
    ls = landsat_df.copy()
    ls["year"] = pd.to_numeric(ls["year"], errors="coerce")
    ls_pre = ls[ls["year"] <= cutoff_year]

    s2 = s2_df.copy()
    s2["year"] = s2["ym"].str[:4].astype(int)
    s2["month"] = s2["ym"].str[5:7].astype(int)
    s2_pre = s2[s2["year"] <= cutoff_year]

    s1 = s1_df.copy()
    s1["year"] = s1["ym"].str[:4].astype(int)
    s1_pre = s1[s1["year"] <= cutoff_year]

    rows: list[dict[str, Any]] = []
    for _, tr in terrain_df.iterrows():
        pid = tr["plot_id"]
        ls_p = ls_pre[ls_pre["plot_id"] == pid]
        s2_p = s2_pre[s2_pre["plot_id"] == pid]
        s1_p = s1_pre[s1_pre["plot_id"] == pid]

        s2_dry = s2_p[s2_p["month"].isin([2, 3, 4])]
        s2_rain = s2_p[s2_p["month"].isin([6, 7, 8, 9, 10])]
        s1_asc = s1_p[s1_p["orbit"] == "ASCENDING"]
        s1_dsc = s1_p[s1_p["orbit"] == "DESCENDING"]

        ndvi_dry = _safe_stat(s2_dry["ndvi"], "median")
        ndvi_rain = _safe_stat(s2_rain["ndvi"], "median")
        ndvi_amp = (
            ndvi_rain - ndvi_dry
            if not (np.isnan(ndvi_rain) or np.isnan(ndvi_dry))
            else float("nan")
        )

        ls_2020 = ls_p[ls_p["year"] == cutoff_year]
        rows.append(
            {
                "plot_id": pid,
                "label_class": tr.get("label_class", ""),
                "district": tr.get("district", ""),
                "area_rai": float(tr["area_rai"]) if pd.notna(tr.get("area_rai")) else float("nan"),
                "jrc_forest2020_frac": (
                    float(tr["jrc_forest2020_frac"])
                    if pd.notna(tr.get("jrc_forest2020_frac"))
                    else float("nan")
                ),
                "ls_ndvi_med": _safe_stat(ls_p["ndvi_med"], "median"),
                "ls_ndvi_min": _safe_stat(ls_p["ndvi_p10"], "min"),
                "ls_ndvi_std": _safe_stat(ls_p["ndvi_med"], "std"),
                "ls_nbr_med": _safe_stat(ls_p["nbr_med"], "median"),
                "ls_nbr_min": _safe_stat(ls_p["nbr_p10"], "min"),
                "ls_ndvi_2020": _safe_stat(ls_2020["ndvi_med"], "median"),
                "s2_ndvi_dry": ndvi_dry,
                "s2_ndvi_rain": ndvi_rain,
                "s2_ndvi_amp": ndvi_amp,
                "s2_nbr_dry": _safe_stat(s2_dry["nbr"], "median"),
                "s2_nbr_rain": _safe_stat(s2_rain["nbr"], "median"),
                "s2_ndmi_dry": _safe_stat(s2_dry["ndmi"], "median"),
                "s2_re_ndvi_med": _safe_stat(s2_p["re_ndvi"], "median"),
                "s1_vh_asc_med": _safe_stat(s1_asc["vh"], "median"),
                "s1_vh_dsc_med": _safe_stat(s1_dsc["vh"], "median"),
                "s1_vv_asc_med": _safe_stat(s1_asc["vv"], "median"),
                "s1_vv_dsc_med": _safe_stat(s1_dsc["vv"], "median"),
                "s1_ratio_asc_med": _safe_stat(s1_asc["vh_minus_vv"], "median"),
                "s1_ratio_dsc_med": _safe_stat(s1_dsc["vh_minus_vv"], "median"),
                "s1_vh_asc_std": _safe_stat(s1_asc["vh"], "std"),
                "s1_vh_dsc_std": _safe_stat(s1_dsc["vh"], "std"),
                "elevation_mean": _safe_stat(pd.Series([tr.get("elevation_mean")]), "mean"),
                "slope_mean": _safe_stat(pd.Series([tr.get("slope_mean")]), "mean"),
                "slope_max": _safe_stat(pd.Series([tr.get("slope_max")]), "mean"),
            }
        )
    return pd.DataFrame(rows)


def build_features(ts_dir: str | Path) -> pd.DataFrame:
    """Load the 4 DS-5 CSV tables from ``ts_dir`` and return the DS-8 feature DataFrame."""
    base = Path(ts_dir)
    return build_features_from_tables(
        terrain_df=pd.read_csv(base / "terrain_jrc.csv"),
        landsat_df=pd.read_csv(base / "landsat_yearly.csv"),
        s2_df=pd.read_csv(base / "s2_monthly.csv"),
        s1_df=pd.read_csv(base / "s1_monthly.csv"),
    )
