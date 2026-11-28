"""CM-3 CLI: Run the end-to-end Forestix verification pipeline on a plot GeoJSON + time series.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/run_pipeline.py \
        --plots data/train/train_plots.geojson \
        --ts-dir data/train/timeseries \
        --model data/train/module_a_rf.pkl \
        --out-dir data/train/pipeline_out \
        --evidence
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from forestix.config import load_spec
from forestix.pipeline import run_batch


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Forestix end-to-end verification pipeline (CM-3).")
    parser.add_argument("--plots", required=True, help="Input plot polygons GeoJSON.")
    parser.add_argument("--ts-dir", required=True, help="Directory with terrain/landsat/s2/s1 CSVs.")
    parser.add_argument("--model", default="data/train/module_a_rf.pkl", help="Trained Module A pickle.")
    parser.add_argument("--spec", default="configs/spec_v1.yaml", help="Locked spec YAML.")
    parser.add_argument("--out-dir", default="data/train/pipeline_out", help="Output directory.")
    parser.add_argument("--evidence", action="store_true", help="Generate SVG evidence charts per plot.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    spec = load_spec(args.spec)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ev_dir = (out_dir / "evidence") if args.evidence else None

    results = run_batch(
        plots_path=args.plots,
        ts_dir=args.ts_dir,
        model_a_path=args.model,
        spec=spec,
        evidence_dir=ev_dir,
    )

    df = pd.DataFrame(results)
    csv_path = out_dir / "predictions.csv"
    json_path = out_dir / "predictions.json"
    df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    counts = Counter(r["model_status"] for r in results)
    print(f"Processed {len(results)} plots -> {csv_path}")
    print(f"Status summary: GREEN={counts['GREEN']}, AMBER={counts['AMBER']}, RED={counts['RED']}")
    if ev_dir:
        print(f"Evidence SVGs written to: {ev_dir}")


if __name__ == "__main__":
    main()
