"""DS-8 + CM-1 + CM-2 + CM-3 Offline Training & Spatial-CV Evaluation Script.

Builds data/train/features_train.parquet (DS-8), runs Leave-One-District-Out Spatial CV
for Module A (CM-1), runs Module B change detection + persistence check (CM-2), and
evaluates end-to-end 3-color triage (SA-4) on the 92 training plots.
"""

from __future__ import annotations

import json
import pickle
from collections import Counter
from pathlib import Path

import pandas as pd

from forestix.config import load_spec
from forestix.decision import triage
from forestix.features import build_features
from forestix.module_a import map_group_to_baseline, spatial_cv, train
from forestix.module_b import detect_break


def main() -> None:
    spec = load_spec("configs/spec_v1.yaml")
    ts_dir = Path("data/train/timeseries")

    # 1. DS-8 Feature Engineering
    feats = build_features(ts_dir)
    out_parquet = Path("data/train/features_train.parquet")
    out_csv = Path("data/train/features_train.csv")
    feats.to_parquet(out_parquet, index=False)
    feats.to_csv(out_csv, index=False)
    print(f"[DS-8] Wrote {len(feats)} rows x {len(feats.columns)} cols -> {out_parquet}")

    # 2. CM-1 Module A Spatial CV (Leave-One-District-Out)
    y_base = map_group_to_baseline(feats["label_class"])
    cv_res = spatial_cv(feats, y_base, feats["district"], spec)
    print("\n[CM-1] Module A Leave-One-District-Out Spatial CV:")
    for dist, m in cv_res["per_district"].items():
        print(
            f"  {dist:<14}: N={m['n_plots']:>2} | 3-class Acc={m['accuracy_3class']*100:5.1f}% "
            f"| Forest-Binary Acc={m['accuracy_forest_binary']*100:5.1f}%"
        )
    print(
        f"  OVERALL       : 3-class Acc={cv_res['overall_accuracy_3class']*100:5.1f}% "
        f"| Forest-Binary Acc={cv_res['overall_accuracy_forest_binary']*100:5.1f}%"
    )
    print("\nModule A Classification Report (OOF Spatial CV):")
    print(cv_res["classification_report"])

    # Fit final Module A on all 92 train plots and save model artifact
    model_a = train(feats, y_base, spec)
    model_path = Path("data/train/module_a_rf.pkl")
    with model_path.open("wb") as fh:
        pickle.dump(model_a, fh)
    print(f"[CM-1] Saved Module A Random Forest -> {model_path}")

    # 3. CM-2 Module B Change Detection + End-to-End 3-Color Triage (using OOF Module A)
    s2_df = pd.read_csv(ts_dir / "s2_monthly.csv")
    s1_df = pd.read_csv(ts_dir / "s1_monthly.csv")
    plots_gj = json.load(open("data/train/train_plots.geojson", encoding="utf-8"))["features"]
    geom_meta = {f["properties"]["plot_id"]: f["properties"] for f in plots_gj}
    oof_by_id = cv_res["oof_predictions"].set_index("plot_id").to_dict(orient="index")

    triage_counts: dict[str, Counter] = {g: Counter() for g in ("G1", "G2", "G3", "G4")}
    mod_b_detected: dict[str, int] = {g: 0 for g in ("G1", "G2", "G3", "G4")}
    mod_b_persists: dict[str, int] = {g: 0 for g in ("G1", "G2", "G3", "G4")}

    eval_rows = []
    for _, row in feats.iterrows():
        pid = row["plot_id"]
        cls = row["label_class"]
        mod_a_out = oof_by_id[pid]
        mod_b_out = detect_break(
            s2_df[s2_df["plot_id"] == pid],
            s1_df[s1_df["plot_id"] == pid],
            spec,
        )
        if mod_b_out["break_date"]:
            mod_b_detected[cls] += 1
        if mod_b_out["persistence_passed"]:
            mod_b_persists[cls] += 1

        status = triage(mod_a_out, mod_b_out, geom_meta[pid], spec)
        triage_counts[cls][status] += 1
        eval_rows.append(
            {
                "plot_id": pid,
                "true_group": cls,
                "district": row["district"],
                "area_rai": geom_meta[pid]["area_rai"],
                "is_small_plot": geom_meta[pid]["is_small_plot"],
                "mod_a_pred": mod_a_out["predicted_class"],
                "mod_a_conf": mod_a_out["confidence"],
                "break_date": mod_b_out["break_date"],
                "trigger_sensor": mod_b_out["trigger_sensor"],
                "persistence_passed": mod_b_out["persistence_passed"],
                "triage_status": status,
            }
        )

    pd.DataFrame(eval_rows).to_csv("data/train/oof_end_to_end_eval.csv", index=False)

    print("\n[CM-2 + SA-4] End-to-End OOF Triage Breakdown (All 92 plots, incl. 26 small plots):")
    print(f"{'Group':<6} {'N':>3} | {'ModB Break':>10} {'Persist':>8} | {'GREEN':>6} {'AMBER':>6} {'RED':>6}")
    print("-" * 58)
    for g in ("G1", "G2", "G3", "G4"):
        n_g = sum(triage_counts[g].values())
        print(
            f"{g:<6} {n_g:>3} | {mod_b_detected[g]:>10} {mod_b_persists[g]:>8} | "
            f"{triage_counts[g]['GREEN']:>6} {triage_counts[g]['AMBER']:>6} {triage_counts[g]['RED']:>6}"
        )

    # Also show non-small plots (>= 3 rai) where automated GREEN/RED decisions apply
    eval_df = pd.DataFrame(eval_rows)
    auto_df = eval_df[~eval_df["is_small_plot"]]
    print(f"\n[Automated Plots Only (area >= 3 rai, N={len(auto_df)}):]")
    for g in ("G1", "G2", "G3", "G4"):
        sub = auto_df[auto_df["true_group"] == g]
        c = Counter(sub["triage_status"])
        print(f"  {g} (N={len(sub):>2}): GREEN={c['GREEN']:>2}, AMBER={c['AMBER']:>2}, RED={c['RED']:>2}")


if __name__ == "__main__":
    main()
