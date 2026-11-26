"""Module B: Post-cutoff canopy change detection and persistence verification."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# Default EDA-informed thresholds (derived from Forestix DS-7 eda_report.md)
DEFAULT_DNBR_THRESH = -0.20
DEFAULT_DNDVI_THRESH = -0.15
DEFAULT_DVH_THRESH_DB = -2.20
DEFAULT_PERSIST_DNBR = -0.10
DEFAULT_PERSIST_DNDVI = -0.08
DEFAULT_PERSIST_DVH_DB = -1.20


def detect_break(
    s2_plot: pd.DataFrame,
    s1_plot: pd.DataFrame,
    spec: dict[str, Any] | None = None,
    dnbr_thresh: float = DEFAULT_DNBR_THRESH,
    dndvi_thresh: float = DEFAULT_DNDVI_THRESH,
    dvh_thresh: float = DEFAULT_DVH_THRESH_DB,
) -> dict[str, Any]:
    """Detect canopy structural break date and change magnitudes (dNDVI, dNBR, dVH).

    Uses late fusion of Sentinel-2 optical indices and Sentinel-1 SAR (ASCENDING and
    DESCENDING orbits evaluated strictly against their own pre-2020 baselines).

    Serves: CM-2, FR-03, SA-2.
    """
    cutoff = str((spec or {}).get("cutoff_date", "2020-12-31"))
    cutoff_ym = cutoff[:7]

    s2 = s2_plot.copy()
    s2["ndvi"] = pd.to_numeric(s2["ndvi"], errors="coerce")
    s2["nbr"] = pd.to_numeric(s2["nbr"], errors="coerce")
    s2_pre = s2[s2["ym"] <= cutoff_ym].dropna(subset=["ndvi", "nbr"])
    s2_post = s2[s2["ym"] > cutoff_ym].dropna(subset=["ndvi", "nbr"]).sort_values("ym")

    pre_ndvi = float(s2_pre["ndvi"].median()) if not s2_pre.empty else float("nan")
    pre_nbr = float(s2_pre["nbr"].median()) if not s2_pre.empty else float("nan")

    # Compute optical drops per post-cutoff month
    opt_break_ym: str | None = None
    min_dndvi = 0.0
    min_dnbr = 0.0
    if not s2_post.empty and not np.isnan(pre_nbr):
        dndvis = s2_post["ndvi"] - pre_ndvi
        dnbrs = s2_post["nbr"] - pre_nbr
        min_dndvi = float(dndvis.quantile(0.10))
        min_dnbr = float(dnbrs.quantile(0.10))
        triggered = s2_post[(dnbrs <= dnbr_thresh) & (dndvis <= dndvi_thresh)]
        if not triggered.empty:
            opt_break_ym = str(triggered.iloc[0]["ym"])

    # Compute SAR drops per orbit separately (SA-2 Late Fusion)
    s1 = s1_plot.copy()
    s1["vh"] = pd.to_numeric(s1["vh"], errors="coerce")
    sar_break_yms: list[str] = []
    min_dvh = 0.0
    for orbit in ("ASCENDING", "DESCENDING"):
        orb = s1[s1["orbit"] == orbit].dropna(subset=["vh"])
        orb_pre = orb[orb["ym"] <= cutoff_ym]
        orb_post = orb[orb["ym"] > cutoff_ym].sort_values("ym")
        if orb_pre.empty or orb_post.empty:
            continue
        pre_vh = float(orb_pre["vh"].median())
        dvhs = orb_post["vh"] - pre_vh
        q10 = float(dvhs.quantile(0.10))
        if q10 < min_dvh:
            min_dvh = q10
        # Require 2 consecutive months below threshold to avoid single-pass speckle false alarms
        below = (dvhs <= dvh_thresh).values
        for i in range(len(below) - 1):
            if below[i] and below[i + 1]:
                sar_break_yms.append(str(orb_post.iloc[i]["ym"]))
                break

    sar_break_ym = min(sar_break_yms) if sar_break_yms else None

    if opt_break_ym and sar_break_ym:
        chosen_ym = min(opt_break_ym, sar_break_ym)
        sensor = "both"
    elif opt_break_ym:
        chosen_ym = opt_break_ym
        sensor = "optical"
    elif sar_break_ym:
        chosen_ym = sar_break_ym
        sensor = "radar"
    else:
        chosen_ym = None
        sensor = "none"

    break_date = f"{chosen_ym}-15" if chosen_ym else None
    persists = persistence_check(s2_plot, s1_plot, break_date, spec)

    return {
        "break_date": break_date,
        "dndvi": round(min_dndvi, 4),
        "dnbr": round(min_dnbr, 4),
        "dvh": round(min_dvh, 2),
        "trigger_sensor": sensor,
        "persistence_passed": persists,
    }


def persistence_check(
    s2_plot: pd.DataFrame,
    s1_plot: pd.DataFrame,
    break_date: str | None,
    spec: dict[str, Any] | None = None,
) -> bool:
    """Verify whether a detected canopy drop persists into the following rainy season (Jun-Oct).

    Distinguishes true clearing from dry-season deciduous leaf-off phenology.
    Serves: CM-2, FR-03, SA-2.
    """
    if not break_date:
        return False
    cutoff_ym = str((spec or {}).get("cutoff_date", "2020-12-31"))[:7]
    b_yr = int(break_date[:4])
    b_mo = int(break_date[5:7])
    # Next rainy season (Jun-Oct): same year if cleared Jan-May, else next year
    target_rain_yr = b_yr if b_mo <= 5 else b_yr + 1

    s2 = s2_plot.copy()
    s2["ndvi"] = pd.to_numeric(s2["ndvi"], errors="coerce")
    s2["nbr"] = pd.to_numeric(s2["nbr"], errors="coerce")
    s2["year"] = s2["ym"].str[:4].astype(int)
    s2["month"] = s2["ym"].str[5:7].astype(int)

    pre_rain = s2[(s2["ym"] <= cutoff_ym) & (s2["month"].isin([6, 7, 8, 9, 10]))].dropna(subset=["nbr", "ndvi"])
    post_rain = s2[(s2["year"] >= target_rain_yr) & (s2["month"].isin([6, 7, 8, 9, 10]))].dropna(
        subset=["nbr", "ndvi"]
    )
    if not pre_rain.empty and not post_rain.empty:
        # Look at first available rainy season at/after target_rain_yr
        first_yr = int(post_rain["year"].min())
        pr = post_rain[post_rain["year"] == first_yr]
        dnbr_rain = float(pr["nbr"].median()) - float(pre_rain["nbr"].median())
        dndvi_rain = float(pr["ndvi"].median()) - float(pre_rain["ndvi"].median())
        if dnbr_rain <= DEFAULT_PERSIST_DNBR or dndvi_rain <= DEFAULT_PERSIST_DNDVI:
            return True

    # Fallback / rainy-season confirmation via Sentinel-1 VH (separate per orbit)
    s1 = s1_plot.copy()
    s1["vh"] = pd.to_numeric(s1["vh"], errors="coerce")
    s1["year"] = s1["ym"].str[:4].astype(int)
    s1["month"] = s1["ym"].str[5:7].astype(int)
    for orbit in ("ASCENDING", "DESCENDING"):
        orb = s1[s1["orbit"] == orbit].dropna(subset=["vh"])
        pre_r = orb[(orb["ym"] <= cutoff_ym) & (orb["month"].isin([6, 7, 8, 9, 10]))]
        post_r = orb[(orb["year"] >= target_rain_yr) & (orb["month"].isin([6, 7, 8, 9, 10]))]
        if not pre_r.empty and not post_r.empty:
            first_yr = int(post_r["year"].min())
            dvh_r = float(post_r[post_r["year"] == first_yr]["vh"].median()) - float(pre_r["vh"].median())
            if dvh_r <= DEFAULT_PERSIST_DVH_DB:
                return True

    return False
