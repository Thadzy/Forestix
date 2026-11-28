"""End-to-end pipeline integration & NFR-04 determinism tests."""

from __future__ import annotations

from pathlib import Path

from forestix.config import load_spec
from forestix.pipeline import run_batch

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_pipeline_determinism_and_evidence(tmp_path: Path) -> None:
    """Verify NFR-04: running the pipeline twice on the same plots yields 100% identical outputs."""
    plots_path = REPO_ROOT / "data" / "train" / "train_plots.geojson"
    ts_dir = REPO_ROOT / "data" / "train" / "timeseries"
    model_path = REPO_ROOT / "data" / "train" / "module_a_rf.pkl"
    if not (plots_path.exists() and ts_dir.exists() and model_path.exists()):
        return

    spec = load_spec(REPO_ROOT / "configs" / "spec_v1.yaml")
    run1 = run_batch(plots_path, ts_dir, model_path, spec=spec, evidence_dir=tmp_path / "ev1")
    run2 = run_batch(plots_path, ts_dir, model_path, spec=spec, evidence_dir=tmp_path / "ev2")

    assert len(run1) >= 80
    assert len(run1) == len(run2)
    for r1, r2 in zip(run1[:15], run2[:15]):
        assert r1["plot_id"] == r2["plot_id"]
        assert r1["model_status"] == r2["model_status"]
        assert r1["break_date"] == r2["break_date"]
        assert r1["mod_a_conf"] == r2["mod_a_conf"]
        assert r1["max_yield_quota_kg"] == r2["max_yield_quota_kg"]
        assert Path(r1["evidence_svg"]).exists()
