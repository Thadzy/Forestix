"""Offline unit tests for 04_auto_polygons.py and 05_kml_to_plots.py."""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_script(name: str):
    path = REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_blind_district_guard_blocks_inside_repo(tmp_path: Path) -> None:
    mod = _load_script("04_auto_polygons.py")
    spec = {"blind_districts": ["Wiang Sa", "Santi Suk"]}
    feats = [{"properties": {"district": "Santisuk"}}]
    with pytest.raises(ValueError, match="Gate G2"):
        mod.check_blind_district_guard(
            feats, [REPO_ROOT / "data" / "candidates" / "bad.geojson"], spec, repo_root=REPO_ROOT
        )
    mod.check_blind_district_guard(feats, [tmp_path / "ok.geojson"], spec, repo_root=REPO_ROOT)


def test_suggest_class_rubber_vs_forest() -> None:
    mod = _load_script("04_auto_polygons.py")
    assert mod.suggest_class("LOSS_POST2020", jrc_forest2020=1, rubber_frac=0.65) == "G3_SUGGESTED"
    assert mod.suggest_class("LOSS_POST2020", jrc_forest2020=1, rubber_frac=0.05) == "G1_SUGGESTED"
    assert mod.suggest_class("LOSS_POST2020", jrc_forest2020=0, rubber_frac=0.10) == "LOSS_CHECK_VHR"
    assert mod.suggest_class("G2_EXISTING_CROPLAND", jrc_forest2020=0, rubber_frac=None) == "G2_EXISTING_CROPLAND"


def test_organic_polygon_and_kml_roundtrip(tmp_path: Path) -> None:
    mod04 = _load_script("04_auto_polygons.py")
    mod05 = _load_script("05_kml_to_plots.py")

    ring = mod04.make_organic_ring_wgs84(101.05, 19.00, target_rai=4.0, rng=random.Random(42))
    metrics = mod04.compute_ring_metrics(ring)
    assert 3.8 <= metrics["area_rai"] <= 4.2
    assert metrics["size_bin"] == "medium_3_5rai"
    assert metrics["pure_pixels"] >= 9

    feats = [
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "candidate_id": "LOSS-PUA-001",
                "pool_name": "LOSS_POST2020",
                "district": "Pua",
                "suggested_class": "G1_SUGGESTED",
                "area_rai": metrics["area_rai"],
                "size_bin": metrics["size_bin"],
                "pure_pixels": metrics["pure_pixels"],
                "seed_source": "hansen",
                "lossyear": 23,
                "radd_date": 0,
                "jrc_forest2020": 1,
                "rubber_frac": 0.0,
            },
        },
        {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "candidate_id": "SKIP-LOSS-PUA-002",
                "pool_name": "LOSS_POST2020",
                "district": "Pua",
                "suggested_class": "LOSS_CHECK_VHR",
                "area_rai": metrics["area_rai"],
                "size_bin": metrics["size_bin"],
                "pure_pixels": metrics["pure_pixels"],
                "seed_source": "hansen",
                "lossyear": 23,
                "radd_date": 0,
                "jrc_forest2020": 0,
                "rubber_frac": 0.0,
            },
        },
    ]

    kml_path = tmp_path / "auto.kml"
    kml_path.write_text(mod04.build_auto_polygons_kml(feats), encoding="utf-8")

    out_geojson = tmp_path / "train_plots.geojson"
    parsed = mod05.kml_to_geojson(kml_path, out_geojson)
    assert len(parsed) == 1
    assert parsed[0]["properties"]["plot_id"] == "LOSS-PUA-001"
    assert parsed[0]["properties"]["label_class"] == "G1"
    assert parsed[0]["properties"]["is_small_plot"] is False
