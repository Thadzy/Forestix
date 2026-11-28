"""End-to-end verification pipeline (FR-01 -> FR-02 -> FR-03 -> FR-04 + Mass Balance Yield Cap)."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import pandas as pd

from forestix.config import load_spec
from forestix.decision import triage
from forestix.evidence import generate_evidence
from forestix.features import build_features
from forestix.module_a import predict as predict_module_a
from forestix.module_b import detect_break
from forestix.plots import geometry_guard, load_plots

# Nan Province maize yield upper-bound cap (OAE avg ~650-800 kg/rai + safety margin)
MAIZE_MAX_YIELD_KG_PER_RAI = 900.0


def estimate_yield_quota_kg(area_rai: float, triage_status: str) -> float | None:
    """Compute Mass-Balance maize yield cap (kg/season) for GREEN plots to deter plot laundering."""
    if triage_status == "GREEN":
        return round(area_rai * MAIZE_MAX_YIELD_KG_PER_RAI, 1)
    if triage_status == "RED":
        return 0.0
    return None  # AMBER pending human verification


def run_batch(
    plots_path: str | Path,
    ts_dir: str | Path,
    model_a_path: str | Path,
    spec: dict[str, Any] | None = None,
    evidence_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Run the deterministic end-to-end Forestix pipeline on a GeoJSON batch + extracted time series.

    Serves: CM-3, FR-01, FR-03, FR-04, NFR-04.
    """
    cfg = spec or load_spec("configs/spec_v1.yaml")
    plot_features = load_plots(plots_path)
    ts_base = Path(ts_dir)

    with Path(model_a_path).open("rb") as fh:
        model_a = pickle.load(fh)

    feats_df = build_features(ts_base)
    mod_a_preds = predict_module_a(model_a, feats_df).set_index("plot_id").to_dict(orient="index")
    s2_df = pd.read_csv(ts_base / "s2_monthly.csv")
    s1_df = pd.read_csv(ts_base / "s1_monthly.csv")

    results: list[dict[str, Any]] = []
    for feat in plot_features:
        props = feat.get("properties") or {}
        pid = str(props.get("plot_id") or props.get("candidate_id"))
        geom_info = geometry_guard(feat["geometry"], cfg)

        mod_a_out = mod_a_preds.get(
            pid,
            {"predicted_class": "UNKNOWN", "confidence": 0.0, "prob_forest": 0.0, "is_forest_2020": False},
        )
        s2_p = s2_df[s2_df["plot_id"] == pid]
        s1_p = s1_df[s1_df["plot_id"] == pid]
        mod_b_out = detect_break(s2_p, s1_p, cfg)

        status = triage(mod_a_out, mod_b_out, geom_info, cfg)
        quota_kg = estimate_yield_quota_kg(geom_info["area_rai"], status)

        ev_paths: dict[str, str] = {}
        if evidence_dir is not None:
            generated = generate_evidence(
                plot_id=pid,
                s2_plot=s2_p,
                s1_plot=s1_p,
                triage_status=status,
                module_a_out=mod_a_out,
                module_b_out=mod_b_out,
                geom_info=geom_info,
                spec=cfg,
                output_dir=evidence_dir,
                max_yield_quota_kg=quota_kg,
            )
            ev_paths = {k: str(v) for k, v in generated.items()}

        results.append(
            {
                "plot_id": pid,
                "district": props.get("district", ""),
                "area_rai": geom_info["area_rai"],
                "pure_pixels": geom_info["pure_pixels"],
                "is_small_plot": geom_info["is_small_plot"],
                "mod_a_class": mod_a_out["predicted_class"],
                "mod_a_conf": mod_a_out["confidence"],
                "mod_a_prob_forest": mod_a_out["prob_forest"],
                "break_date": mod_b_out["break_date"],
                "dndvi": mod_b_out["dndvi"],
                "dnbr": mod_b_out["dnbr"],
                "dvh": mod_b_out["dvh"],
                "trigger_sensor": mod_b_out["trigger_sensor"],
                "persistence_passed": mod_b_out["persistence_passed"],
                "model_status": status,
                "max_yield_quota_kg": quota_kg,
                "evidence_svg": ev_paths.get("timeseries_plot", ""),
            }
        )
    return results
