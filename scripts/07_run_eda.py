"""DS-7 EDA: Run all 5 Forestix Exploratory Data Analysis checks on exported GEE time series.

Pure Python stdlib (zero extra dependencies). Reads:
  - data/train/train_plots.geojson
  - data/train/timeseries/{terrain_jrc,landsat_yearly,s2_monthly,s1_monthly}.csv

Writes a Markdown summary to docs/eda_report.md and prints key findings.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def _flt(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        v = float(val)
        return None if math.isnan(v) else v
    except ValueError:
        return None


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else float("nan")


def _std(vals: list[float]) -> float:
    return statistics.stdev(vals) if len(vals) >= 2 else float("nan")


def _fmt(v: float, digits: int = 3) -> str:
    return "n/a" if math.isnan(v) else f"{v:.{digits}f}"


def run_eda(
    plots_path: Path = Path("data/train/train_plots.geojson"),
    ts_dir: Path = Path("data/train/timeseries"),
    out_md: Path = Path("docs/eda_report.md"),
) -> str:
    with plots_path.open("r", encoding="utf-8") as fh:
        plots_gj = json.load(fh)["features"]
    meta = {f["properties"]["plot_id"]: f["properties"] for f in plots_gj}

    with (ts_dir / "terrain_jrc.csv").open(encoding="utf-8") as fh:
        terrain_rows = list(csv.DictReader(fh))
    terrain = {r["plot_id"]: r for r in terrain_rows}

    with (ts_dir / "landsat_yearly.csv").open(encoding="utf-8") as fh:
        landsat_rows = list(csv.DictReader(fh))

    with (ts_dir / "s2_monthly.csv").open(encoding="utf-8") as fh:
        s2_rows = list(csv.DictReader(fh))

    with (ts_dir / "s1_monthly.csv").open(encoding="utf-8") as fh:
        s1_rows = list(csv.DictReader(fh))

    lines: list[str] = [
        "# Forestix DS-7: Exploratory Data Analysis (EDA Report)",
        f"**Dataset:** `{plots_path}` ({len(meta)} LDD-2567-verified plots in Mae Charim, Pua, Tha Wang Pha)  ",
        f"**Time Series:** Landsat ({len(landsat_rows)} rows), Sentinel-2 ({len(s2_rows)} rows), Sentinel-1 ({len(s1_rows)} rows), Terrain/JRC ({len(terrain_rows)} rows)",
        "",
    ]

    # --- EDA-1: Cloud-free months (S2 vs S1) ---
    s2_by_m: dict[str, list[float]] = defaultdict(list)
    s2_clear_by_m: dict[str, list[int]] = defaultdict(list)
    for r in s2_rows:
        m = r["ym"].split("-")[1]
        obs = _flt(r["clear_obs"]) or 0.0
        s2_by_m[m].append(obs)
        s2_clear_by_m[m].append(1 if obs > 0 and _flt(r["ndvi"]) is not None else 0)

    s1_clear_by_m: dict[str, list[int]] = defaultdict(list)
    for r in s1_rows:
        m = r["ym"].split("-")[1]
        obs = _flt(r["obs_count"]) or 0.0
        s1_clear_by_m[m].append(1 if obs > 0 and _flt(r["vh"]) is not None else 0)

    lines.append("## EDA-1: Cloud-Free Observation Availability (Sentinel-2 vs Sentinel-1)")
    lines.append("| Month | Season | S2 Clear Plot-Months (%) | S2 Mean Clear Obs | S1 Valid Plot-Months (%) |")
    lines.append("| :---: | :--- | :---: | :---: | :---: |")
    rainy_s2, dry_s2 = [], []
    for m_int in range(1, 13):
        m = f"{m_int:02d}"
        season = "Rainy" if 5 <= m_int <= 10 else "Dry"
        s2_pct = 100.0 * _mean(s2_clear_by_m[m])
        s2_obs = _mean(s2_by_m[m])
        s1_pct = 100.0 * _mean(s1_clear_by_m[m])
        (rainy_s2 if season == "Rainy" else dry_s2).append(s2_pct)
        lines.append(f"| {m} | {season} | {s2_pct:.1f}% | {s2_obs:.2f} | {s1_pct:.1f}% |")
    lines.append(
        f"\n> **Finding:** Dry-season S2 clear availability averages **{_mean(dry_s2):.1f}%** vs Rainy-season (May–Oct) **{_mean(rainy_s2):.1f}%**, confirming SA-2 that Sentinel-1 SAR is essential for rainy-season clearing detection.\n"
    )

    # --- EDA-2: Phenology & Post-Cutoff Drop by Group ---
    s2_pre_dry: dict[str, list[float]] = defaultdict(list)
    s2_pre_rain: dict[str, list[float]] = defaultdict(list)
    ls_pre_ndvi: dict[str, list[float]] = defaultdict(list)
    ls_pre_nbr: dict[str, list[float]] = defaultdict(list)
    # Per-plot pre vs post drop
    plot_s2_pre: dict[str, list[tuple[float, float]]] = defaultdict(list)
    plot_s2_post: dict[str, list[tuple[float, float]]] = defaultdict(list)
    plot_s1_pre: dict[tuple[str, str], list[float]] = defaultdict(list)
    plot_s1_post: dict[tuple[str, str], list[float]] = defaultdict(list)

    for r in landsat_rows:
        pid = r["plot_id"]
        cls = meta[pid]["label_class"]
        ndvi, nbr = _flt(r["ndvi_med"]), _flt(r["nbr_med"])
        if ndvi is not None:
            ls_pre_ndvi[cls].append(ndvi)
        if nbr is not None:
            ls_pre_nbr[cls].append(nbr)

    for r in s2_rows:
        pid = r["plot_id"]
        cls = meta[pid]["label_class"]
        yr, m = int(r["ym"][:4]), int(r["ym"][5:7])
        ndvi, nbr = _flt(r["ndvi"]), _flt(r["nbr"])
        if ndvi is None or nbr is None:
            continue
        if yr <= 2020:
            plot_s2_pre[pid].append((ndvi, nbr))
            if 2 <= m <= 4:
                s2_pre_dry[cls].append(ndvi)
            elif 6 <= m <= 10:
                s2_pre_rain[cls].append(ndvi)
        else:
            plot_s2_post[pid].append((ndvi, nbr))

    for r in s1_rows:
        pid = r["plot_id"]
        yr = int(r["ym"][:4])
        vh = _flt(r["vh"])
        if vh is None:
            continue
        key = (pid, r["orbit"])
        if yr <= 2020:
            plot_s1_pre[key].append(vh)
        else:
            plot_s1_post[key].append(vh)

    dndvi_by_cls: dict[str, list[float]] = defaultdict(list)
    dnbr_by_cls: dict[str, list[float]] = defaultdict(list)
    dvh_by_cls: dict[str, list[float]] = defaultdict(list)
    for pid, p in meta.items():
        cls = p["label_class"]
        if plot_s2_pre[pid] and plot_s2_post[pid]:
            pre_ndvi = statistics.median(x[0] for x in plot_s2_pre[pid])
            pre_nbr = statistics.median(x[1] for x in plot_s2_pre[pid])
            # 10th percentile post-2020 captures sustained clearing troughs robustly
            post_ndvis = sorted(x[0] for x in plot_s2_post[pid])
            post_nbrs = sorted(x[1] for x in plot_s2_post[pid])
            p10_idx = max(0, int(0.10 * len(post_ndvis)))
            dndvi_by_cls[cls].append(post_ndvis[p10_idx] - pre_ndvi)
            dnbr_by_cls[cls].append(post_nbrs[p10_idx] - pre_nbr)
        vh_drops = []
        for orb in ("ASCENDING", "DESCENDING"):
            pre_v = plot_s1_pre[(pid, orb)]
            post_v = plot_s1_post[(pid, orb)]
            if pre_v and post_v:
                pre_med = statistics.median(pre_v)
                post_s = sorted(post_v)
                p10_v = post_s[max(0, int(0.10 * len(post_s)))]
                vh_drops.append(p10_v - pre_med)
        if vh_drops:
            dvh_by_cls[cls].append(min(vh_drops))

    lines.append("## EDA-2: Pre-2020 Phenology & Post-2020 Canopy Drop by Group")
    lines.append(
        "| Group | N | Landsat Pre-2020 NDVI | S2 Pre Dry (Feb–Apr) | S2 Pre Rain (Jun–Oct) | Post-2020 dNDVI (p10-med) | Post-2020 dNBR (p10-med) | Post-2020 dVH (dB) |"
    )
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    for cls in ("G1", "G2", "G3", "G4"):
        n_cls = sum(1 for p in meta.values() if p["label_class"] == cls)
        lines.append(
            f"| **{cls}** | {n_cls} | {_fmt(_mean(ls_pre_ndvi[cls]))} | {_fmt(_mean(s2_pre_dry[cls]))} | "
            f"{_fmt(_mean(s2_pre_rain[cls]))} | {_fmt(_mean(dndvi_by_cls[cls]))} | "
            f"{_fmt(_mean(dnbr_by_cls[cls]))} | {_fmt(_mean(dvh_by_cls[cls]), 2)} |"
        )
    lines.append("")

    # --- EDA-3: SAR Noise & Orbit Offset by Slope ---
    slope_bins: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for pid, tr in terrain.items():
        slp = _flt(tr["slope_mean"])
        if slp is None:
            continue
        sbin = "<15 deg" if slp < 15 else ("15-25 deg" if slp < 25 else ">25 deg")
        asc = plot_s1_pre[(pid, "ASCENDING")] + plot_s1_post[(pid, "ASCENDING")]
        dsc = plot_s1_pre[(pid, "DESCENDING")] + plot_s1_post[(pid, "DESCENDING")]
        if asc and dsc:
            gap = abs(_mean(asc) - _mean(dsc))
            noise = _mean([_std(asc), _std(dsc)])
            if not math.isnan(noise):
                slope_bins[sbin].append((gap, noise))

    lines.append("## EDA-3: Sentinel-1 SAR Orbit Offset & Noise by Terrain Slope")
    lines.append("| Slope Bin | Plots | Mean |VH_Asc - VH_Desc| (dB) | Mean Within-Orbit VH Std (dB) |")
    lines.append("| :--- | :---: | :---: | :---: |")
    for sbin in ("<15 deg", "15-25 deg", ">25 deg"):
        vals = slope_bins[sbin]
        lines.append(
            f"| {sbin} | {len(vals)} | {_fmt(_mean([v[0] for v in vals]), 2)} dB | {_fmt(_mean([v[1] for v in vals]), 2)} dB |"
        )
    lines.append("")

    # --- EDA-4: Pure Pixels vs Plot Size ---
    sz_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in meta.values():
        sz_groups[p["size_bin"]].append(p)

    lines.append("## EDA-4: Geometry Guard (Area & Pure Pixels by Size Bin)")
    lines.append("| Size Bin | Plots | Mean Area (rai) | Mean Pure Pixels | Flagged Small (`<3 rai` or `<9 px`) |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for sbin in ("small_1_2rai", "medium_3_5rai", "mid_6_9rai", "large_10plus_rai"):
        items = sz_groups[sbin]
        if not items:
            continue
        flagged = sum(1 for x in items if x.get("is_small_plot"))
        lines.append(
            f"| {sbin} | {len(items)} | {_mean([x['area_rai'] for x in items]):.2f} | "
            f"{_mean([x['pure_pixels'] for x in items]):.1f} | {flagged}/{len(items)} ({100*flagged/len(items):.0f}%) |"
        )
    lines.append("")

    # --- EDA-5: JRC GFC2020 Commission Error Baseline vs LDD 2567 ---
    lines.append("## EDA-5: JRC GFC2020 Baseline Agreement vs LDD 2567")
    lines.append("| Group | Plots | JRC Marks as Forest (`frac >= 0.5`) | Interpretation |")
    lines.append("| :--- | :---: | :---: | :--- |")
    interp_map = {
        "G1": "Expected high (forest at 2020 before clearing)",
        "G2": "Commission error if > 0% (old cropland falsely called forest)",
        "G3": "Commission error (LDD rubber/teak plantation falsely called natural forest!)",
        "G4": "Expected high (intact deciduous forest)",
    }
    for cls in ("G1", "G2", "G3", "G4"):
        pids = [pid for pid, p in meta.items() if p["label_class"] == cls]
        jrc_pos = sum(1 for pid in pids if (_flt(terrain[pid]["jrc_forest2020_frac"]) or 0.0) >= 0.5)
        pct = 100.0 * jrc_pos / max(len(pids), 1)
        lines.append(f"| **{cls}** | {len(pids)} | {jrc_pos}/{len(pids)} ({pct:.1f}%) | {interp_map[cls]} |")
    lines.append("")

    report = "\n".join(lines)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(report, encoding="utf-8")
    return report


if __name__ == "__main__":
    print(run_eda())
