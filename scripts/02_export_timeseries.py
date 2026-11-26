"""DS-6 CLI: Export multi-sensor satellite time series from GEE for Forestix plots.

Extracts 4 tables into --out-dir (default: data/train/timeseries):
  - terrain_jrc.csv   : SRTM elevation, slope (mean/max), JRC GFC2020 forest fraction
  - landsat_yearly.csv: Landsat 8/9 C2 L2 yearly NDVI/NBR (2015-2020 pre-cutoff baseline)
  - s2_monthly.csv    : Sentinel-2 L2A + Cloud Score+ (>=0.60) monthly NDVI/NBR/NDMI/RE-NDVI (2018-2025)
  - s1_monthly.csv    : Sentinel-1 GRD monthly VV/VH/VH-VV kept separate by ASCENDING/DESCENDING (2018-2025)

Applies the FR-01 10 m inward buffer on polygons before sampling (with automatic fallback to
unbuffered geometry for very narrow plots whose -10 m buffer is empty). Enforces Gate G2.

Usage:
    EE_PROJECT=<your-project> PYTHONPATH=src .venv/bin/python scripts/02_export_timeseries.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import ee

from forestix.config import load_datasets, load_spec
from forestix.ee_init import init_ee
from forestix.extract.landsat import extract_landsat_batch
from forestix.extract.s1 import extract_s1_monthly_batch
from forestix.extract.s2 import extract_s2_monthly_batch
from forestix.extract.terrain import extract_terrain_batch

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _normalize_district(name: str) -> str:
    return name.replace(" ", "").lower()


def check_blind_district_guard(
    features: list[dict[str, Any]],
    out_dir: Path,
    spec: dict[str, Any],
    repo_root: Path | None = None,
) -> None:
    """Reject writing blind-district time series inside the repository (Gate G2)."""
    root = (repo_root or _REPO_ROOT).resolve()
    if not out_dir.resolve().is_relative_to(root):
        return
    blind_norm = {_normalize_district(d) for d in spec.get("blind_districts", [])}
    flagged = {
        str((f.get("properties") or {}).get("district", ""))
        for f in features
        if _normalize_district(str((f.get("properties") or {}).get("district", ""))) in blind_norm
    }
    if flagged:
        raise ValueError(
            f"Gate G2 violation: blind district(s) {sorted(flagged)} cannot be exported inside "
            f"the repository ({out_dir.resolve()}). Pass an --out-dir outside {root}."
        )


def _write_csv(rows: list[dict[str, Any]], path: Path, append: bool = False) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    mode = "a" if (append and path.exists()) else "w"
    with path.open(mode, encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()
        writer.writerows(rows)


def _build_ee_plots_fc(
    features: list[dict[str, Any]],
    inward_buffer_m: float = 10.0,
) -> ee.FeatureCollection:
    """Convert GeoJSON polygon features to ee.FeatureCollection with safe -10 m inward buffer."""
    ee_feats = []
    for f in features:
        props = f.get("properties") or {}
        geom = ee.Geometry(f["geometry"])
        shrunk = geom.buffer(-inward_buffer_m)
        safe_geom = ee.Geometry(ee.Algorithms.If(shrunk.area(1).gt(100), shrunk, geom))
        ee_feats.append(
            ee.Feature(
                safe_geom,
                {
                    "plot_id": str(props.get("plot_id") or props.get("candidate_id")),
                    "label_class": str(props.get("label_class", "")),
                    "district": str(props.get("district", "")),
                    "area_rai": float(props.get("area_rai", 0.0)),
                },
            )
        )
    return ee.FeatureCollection(ee_feats)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export multi-sensor GEE time series for Forestix plots (DS-6 / FR-02)."
    )
    parser.add_argument(
        "--plots",
        default="data/train/train_plots.geojson",
        help="Input plots GeoJSON (default: data/train/train_plots.geojson).",
    )
    parser.add_argument(
        "--out-dir",
        default="data/train/timeseries",
        help="Output directory for CSV tables (default: data/train/timeseries).",
    )
    parser.add_argument("--spec", default="configs/spec_v1.yaml")
    parser.add_argument("--datasets", default="configs/datasets.yaml")
    parser.add_argument("--landsat-start", type=int, default=2015)
    parser.add_argument("--landsat-end", type=int, default=2020)
    parser.add_argument("--s2-start", type=int, default=2018)
    parser.add_argument("--s2-end", type=int, default=2025)
    parser.add_argument("--s1-start", type=int, default=2018)
    parser.add_argument("--s1-end", type=int, default=2025)
    parser.add_argument("--limit", type=int, default=None, help="Optional plot limit for quick smoke test.")
    parser.add_argument(
        "--only",
        nargs="+",
        choices=["terrain", "landsat", "s2", "s1"],
        default=["terrain", "landsat", "s2", "s1"],
        help="Subset of sensors to export.",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing s2_monthly.csv / s1_monthly.csv instead of overwriting.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    spec = load_spec(args.spec)
    ds = load_datasets(args.datasets)

    plots_path = Path(args.plots)
    if not plots_path.exists():
        print(f"ERROR: Plots file not found: {plots_path}", file=sys.stderr)
        raise SystemExit(1)

    with plots_path.open("r", encoding="utf-8") as fh:
        features = json.load(fh).get("features") or []
    if args.limit:
        features = features[: args.limit]

    out_dir = Path(args.out_dir)
    try:
        check_blind_district_guard(features, out_dir, spec)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    init_ee()
    inward_m = float(spec.get("plot_geometry", {}).get("inward_buffer_m", 10.0))
    plots_fc = _build_ee_plots_fc(features, inward_buffer_m=inward_m)
    print(f"Exporting GEE time series for {len(features)} plots -> {out_dir}")

    if "terrain" in args.only:
        print("[1/4] Extracting SRTM terrain + JRC GFC2020...")
        rows = extract_terrain_batch(plots_fc, ds)
        _write_csv(rows, out_dir / "terrain_jrc.csv")
        print(f"      -> {len(rows)} rows written to terrain_jrc.csv")

    if "landsat" in args.only:
        print(f"[2/4] Extracting Landsat 8/9 yearly ({args.landsat_start}-{args.landsat_end})...")
        rows = extract_landsat_batch(plots_fc, args.landsat_start, args.landsat_end, ds)
        _write_csv(rows, out_dir / "landsat_yearly.csv")
        print(f"      -> {len(rows)} rows written to landsat_yearly.csv")

    if "s2" in args.only:
        s2_path = out_dir / "s2_monthly.csv"
        if s2_path.exists() and not args.append:
            s2_path.unlink()
        total_s2 = 0
        for yr in range(args.s2_start, args.s2_end + 1):
            print(f"[3/4] Extracting Sentinel-2 monthly ({yr})...")
            rows = extract_s2_monthly_batch(plots_fc, yr, ds)
            _write_csv(rows, s2_path, append=(args.append or yr > args.s2_start))
            total_s2 += len(rows)
        print(f"      -> {total_s2} rows written to s2_monthly.csv")

    if "s1" in args.only:
        s1_path = out_dir / "s1_monthly.csv"
        if s1_path.exists() and not args.append:
            s1_path.unlink()
        total_s1 = 0
        for yr in range(args.s1_start, args.s1_end + 1):
            print(f"[4/4] Extracting Sentinel-1 monthly Asc/Desc ({yr})...")
            rows = extract_s1_monthly_batch(plots_fc, yr, ds)
            _write_csv(rows, s1_path, append=(args.append or yr > args.s1_start))
            total_s1 += len(rows)
        print(f"      -> {total_s1} rows written to s1_monthly.csv")

    print("Done! Ready for DS-7 (EDA) and Module A/B training.")


if __name__ == "__main__":
    main()
