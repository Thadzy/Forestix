"""Offline unit tests for DS-6 time-series extraction CLI and Gate G2 guard."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_export_script():
    path = REPO_ROOT / "scripts" / "02_export_timeseries.py"
    spec = importlib.util.spec_from_file_location("export_ts", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_export_blind_district_guard(tmp_path: Path) -> None:
    mod = _load_export_script()
    spec = {"blind_districts": ["Wiang Sa", "Santi Suk"]}
    feats = [{"properties": {"district": "Wiang Sa"}}]
    with pytest.raises(ValueError, match="Gate G2"):
        mod.check_blind_district_guard(
            feats, REPO_ROOT / "data" / "train" / "timeseries", spec, repo_root=REPO_ROOT
        )
    # Outside repo is permitted for Chai's blind run
    mod.check_blind_district_guard(feats, tmp_path / "blind_ts", spec, repo_root=REPO_ROOT)


def test_export_parse_args_defaults() -> None:
    mod = _load_export_script()
    args = mod.parse_args([])
    assert args.plots == "data/train/train_plots.geojson"
    assert args.landsat_start == 2015
    assert args.landsat_end == 2020
    assert args.s2_start == 2018
    assert args.s2_end == 2025
    assert set(args.only) == {"terrain", "landsat", "s2", "s1"}
