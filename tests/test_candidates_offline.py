"""Offline unit tests for DS-2 candidate configuration and Gate G2 blind-district guard."""

import importlib.util
from pathlib import Path

import pytest

from forestix.config import load_candidates_config, load_spec

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_find_candidates_module():
    script_path = REPO_ROOT / "scripts" / "01_find_candidates.py"
    spec = importlib.util.spec_from_file_location("find_candidates_cli", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_candidates_config_pool_counts() -> None:
    """load_candidates_config loads candidates_v1.yaml with 180/90/90 pool n_points."""
    cfg = load_candidates_config(REPO_ROOT / "configs" / "candidates_v1.yaml")
    pools = cfg["pools"]
    assert pools["LOSS_POST2020"]["n_points"] == 180
    assert pools["G2_EXISTING_CROPLAND"]["n_points"] == 90
    assert pools["G4_INTACT_FOREST"]["n_points"] == 90


def test_blind_district_guard_rejects_santisuk_in_repo() -> None:
    """Blind-district guard rejects ['Santisuk'] when --out is inside the repository."""
    cli = _load_find_candidates_module()
    spec = load_spec(REPO_ROOT / "configs" / "spec_v1.yaml")
    in_repo_out = REPO_ROOT / "data" / "candidates" / "blind_candidates.geojson"

    with pytest.raises(ValueError, match="Gate G2"):
        cli.check_blind_district_guard(["Santisuk"], in_repo_out, spec, repo_root=REPO_ROOT)


def test_blind_district_guard_allows_outside_repo_and_train_in_repo(tmp_path: Path) -> None:
    """Guard allows blind districts outside repo and train districts inside repo."""
    cli = _load_find_candidates_module()
    spec = load_spec(REPO_ROOT / "configs" / "spec_v1.yaml")

    cli.check_blind_district_guard(
        ["Santisuk"], tmp_path / "blind.geojson", spec, repo_root=REPO_ROOT
    )
    cli.check_blind_district_guard(
        ["Mae Charim", "Pua", "Tha Wang Pha"],
        REPO_ROOT / "data" / "candidates" / "train_candidates.geojson",
        spec,
        repo_root=REPO_ROOT,
    )
