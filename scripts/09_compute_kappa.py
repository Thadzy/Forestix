"""DS-4 Helper: Compute Cohen's Kappa between Chai's blind review CSV and LDD-2567 ground truth.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/09_compute_kappa.py \
        --gt /Users/thadzy/Documents/forestix_test_holdout/ground_truth_locked.csv \
        --review /path/to/chai_blind_labels.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute Cohen's Kappa for DS-4 blind set review.")
    parser.add_argument("--gt", required=True, help="Path to ground_truth_locked.csv")
    parser.add_argument("--review", required=True, help="Path to chai_blind_labels.csv")
    args = parser.parse_args()

    gt = pd.read_csv(Path(args.gt))
    rev = pd.read_csv(Path(args.review))
    merged = gt.merge(rev, on="plot_id", how="inner")

    valid = merged[merged["chai_label"].isin(["G1", "G2", "G3", "G4"])]
    unsure = merged[merged["chai_label"] == "UNSURE"]
    missing = len(gt) - len(valid) - len(unsure)

    print(f"Total GT plots: {len(gt)} | Reviewed G1-G4: {len(valid)} | UNSURE: {len(unsure)} | Unlabeled: {missing}")
    if valid.empty:
        return

    labels = ["G1", "G2", "G3", "G4"]
    kappa = cohen_kappa_score(valid["label_class"], valid["chai_label"], labels=labels)
    agree = (valid["label_class"] == valid["chai_label"]).mean() * 100.0
    print(f"\nAgreement: {agree:.1f}% ({int((valid['label_class'] == valid['chai_label']).sum())}/{len(valid)})")
    print(f"Cohen's Kappa (4-class): {kappa:.4f}  ({'PASS >= 0.80' if kappa >= 0.80 else 'BELOW 0.80 - resolve disagreements'})")

    cm = confusion_matrix(valid["label_class"], valid["chai_label"], labels=labels)
    print("\nConfusion Matrix (rows=LDD2567, cols=Chai):")
    print(pd.DataFrame(cm, index=labels, columns=labels))

    diffs = valid[valid["label_class"] != valid["chai_label"]]
    if not diffs.empty:
        print(f"\nDisagreements ({len(diffs)} plots):")
        for _, r in diffs.iterrows():
            print(f"  {r['plot_id']} | LDD={r['label_class']} ({r.get('ldd_lu_code','')}) vs Chai={r['chai_label']} | note={r.get('notes','')}")


if __name__ == "__main__":
    main()
