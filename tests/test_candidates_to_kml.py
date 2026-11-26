"""Unit tests for scripts/03_candidates_to_kml.py (DS-3 KML export & Gate G2 guard)."""

import csv
import importlib.util
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


def _load_kml_module():
    script_path = REPO_ROOT / "scripts" / "03_candidates_to_kml.py"
    spec = importlib.util.spec_from_file_location("candidates_to_kml_cli", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_feature(
    lon: float,
    lat: float,
    pool_name: str,
    district: str,
    lossyear: int = 0,
    radd_date: int = 0,
) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "pool_name": pool_name,
            "district": district,
            "seed_source": "test_seed",
            "lossyear": lossyear,
            "radd_alert": 1 if radd_date else 0,
            "radd_date": radd_date,
            "jrc_forest2020": 1,
            "wc2020": 10,
            "wc2021": 10,
            "treecover2000": 85,
        },
    }


def test_convert_geojson_to_kml_and_csv(tmp_path: Path) -> None:
    """Converts 4-point GeoJSON to valid KML + CSV with unique IDs, drawn folder, and 4 placemarks."""
    mod = _load_kml_module()

    geojson_data = {
        "type": "FeatureCollection",
        "features": [
            _make_feature(101.100001, 18.700001, "LOSS_POST2020", "Mae Charim", lossyear=22, radd_date=23045),
            _make_feature(101.200002, 18.800002, "LOSS_POST2020", "Mae Charim", lossyear=0, radd_date=0),
            _make_feature(100.900003, 19.100003, "G2_EXISTING_CROPLAND", "Pua"),
            _make_feature(100.800004, 19.000004, "G4_INTACT_FOREST", "Tha Wang Pha"),
        ],
    }
    in_path = tmp_path / "train_candidates.geojson"
    out_kml = tmp_path / "train_candidates.kml"
    out_csv = tmp_path / "train_candidates_ids.csv"
    in_path.write_text(json.dumps(geojson_data), encoding="utf-8")

    counts = mod.convert_geojson_to_kml(in_path, out_kml, out_csv, seed=42)
    assert counts == {
        ("LOSS_POST2020", "Mae Charim"): 2,
        ("G2_EXISTING_CROPLAND", "Pua"): 1,
        ("G4_INTACT_FOREST", "Tha Wang Pha"): 1,
    }

    tree = ET.parse(out_kml)
    root = tree.getroot()

    folders = root.findall(".//kml:Folder", KML_NS)
    folder_names = [f.findtext("kml:name", default="", namespaces=KML_NS) for f in folders]
    assert "drawn" in folder_names

    placemarks = root.findall(".//kml:Placemark", KML_NS)
    assert len(placemarks) == 4

    ids = [pm.findtext("kml:name", default="", namespaces=KML_NS) for pm in placemarks]
    assert len(set(ids)) == 4
    pattern = re.compile(r"^(LOSS|G2|G4)-(MC|PUA|TWP)-\d{3}$")
    for cid in ids:
        assert pattern.match(cid), f"Unexpected candidate_id format: {cid}"

    with out_csv.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 4
    assert [r["candidate_id"] for r in rows] == ids


def test_blind_district_santisuk_rejected(tmp_path: Path) -> None:
    """Gate G2 guard rejects any feature in Santisuk (or Wiang Sa)."""
    mod = _load_kml_module()

    geojson_data = {
        "type": "FeatureCollection",
        "features": [
            _make_feature(100.9, 18.8, "G4_INTACT_FOREST", "Santisuk"),
        ],
    }
    in_path = tmp_path / "blind.geojson"
    out_kml = tmp_path / "blind.kml"
    out_csv = tmp_path / "blind.csv"
    in_path.write_text(json.dumps(geojson_data), encoding="utf-8")

    with pytest.raises((SystemExit, ValueError)):
        mod.convert_geojson_to_kml(in_path, out_kml, out_csv, seed=42)
