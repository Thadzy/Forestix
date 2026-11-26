"""Convert reviewed Google Earth Pro KML polygons into data/train/train_plots.geojson.

Pure Python stdlib (zero extra dependencies). Supports both:
- Auto-generated KML reviewed by Keep/Delete in Google Earth Pro (from 04_auto_polygons.py)
- Hand-drawn polygons placed in the 'drawn' folder (from 03_candidates_to_kml.py)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

FOLDER_TO_CLASS: dict[str, str] = {
    "G1": "G1",
    "G1_SUGGESTED": "G1",
    "G1_NEW_DEFORESTATION": "G1",
    "G2": "G2",
    "G2_EXISTING_CROPLAND": "G2",
    "G3": "G3",
    "G3_SUGGESTED": "G3",
    "G3_PLANTATION_HARVEST": "G3",
    "G4": "G4",
    "G4_INTACT_FOREST": "G4",
}


def _parse_coordinates(coord_text: str) -> list[list[float]]:
    pts: list[list[float]] = []
    for token in coord_text.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            pts.append([float(parts[0]), float(parts[1])])
    if len(pts) >= 3 and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def _compute_ring_metrics(ring: list[list[float]], inward_buffer_m: float = 10.0) -> tuple[float, int]:
    n = len(ring) - 1 if len(ring) > 1 and ring[0] == ring[-1] else len(ring)
    lon0 = sum(p[0] for p in ring[:n]) / max(n, 1)
    lat0 = sum(p[1] for p in ring[:n]) / max(n, 1)
    lat_rad = math.radians(lat0)
    m_lat = 111132.92 - 559.82 * math.cos(2 * lat_rad) + 1.175 * math.cos(4 * lat_rad)
    m_lon = 111412.84 * math.cos(lat_rad) - 93.5 * math.cos(3 * lat_rad)
    pts_m = [((lon - lon0) * m_lon, (lat - lat0) * m_lat) for lon, lat in ring]

    area2 = 0.0
    perim = 0.0
    for i in range(len(pts_m) - 1):
        x1, y1 = pts_m[i]
        x2, y2 = pts_m[i + 1]
        area2 += x1 * y2 - x2 * y1
        perim += math.hypot(x2 - x1, y2 - y1)
    area_m2 = abs(area2) * 0.5
    area_rai = round(area_m2 / 1600.0, 2)
    inner_m2 = max(0.0, area_m2 - perim * inward_buffer_m + math.pi * inward_buffer_m**2)
    if perim > 0 and (2.0 * area_m2 / perim) <= inward_buffer_m:
        inner_m2 = 0.0
    return area_rai, int(inner_m2 // 100.0)


def _infer_class(folder_name: str, description: str, cid: str) -> str:
    upper_desc = description.upper()
    for code in ("G1", "G2", "G3", "G4"):
        if upper_desc.startswith(code) or f"SUGGESTED_CLASS: {code}" in upper_desc:
            return code
    base_folder = folder_name.split("(")[0].strip().upper()
    if base_folder in FOLDER_TO_CLASS:
        return FOLDER_TO_CLASS[base_folder]
    for code in ("G2", "G4"):
        if cid.upper().startswith(f"{code}-"):
            return code
    return "UNLABELED"


def _classify_size_bin(area_rai: float) -> str:
    if area_rai < 3.0:
        return "small_1_2rai"
    if area_rai < 6.0:
        return "medium_3_5rai"
    if area_rai < 10.0:
        return "mid_6_9rai"
    return "large_10plus_rai"


def kml_to_geojson(
    kml_path: Path,
    out_geojson: Path,
    meta_geojson: Path | None = None,
    inward_buffer_m: float = 10.0,
) -> list[dict[str, Any]]:
    """Parse polygons from a KML file, attach metadata + area/pure_pixels, and write GeoJSON."""
    meta_by_id: dict[str, dict[str, Any]] = {}
    if meta_geojson and meta_geojson.exists():
        with meta_geojson.open("r", encoding="utf-8") as fh:
            for feat in json.load(fh).get("features", []):
                props = feat.get("properties") or {}
                cid = props.get("candidate_id")
                if cid:
                    meta_by_id[str(cid)] = props

    tree = ET.parse(kml_path)
    root = tree.getroot()

    features: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _walk(elem: ET.Element, folder_name: str = "") -> None:
        tag = elem.tag.split("}")[-1]
        if tag == "Folder":
            name_el = elem.find("kml:name", KML_NS)
            cur_folder = (name_el.text or "").strip() if name_el is not None else folder_name
            for child in elem:
                _walk(child, cur_folder)
            return

        if tag == "Placemark":
            poly_el = elem.find(
                ".//kml:Polygon//kml:outerBoundaryIs//kml:LinearRing//kml:coordinates", KML_NS
            )
            if poly_el is None or not poly_el.text:
                return
            name_el = elem.find("kml:name", KML_NS)
            desc_el = elem.find("kml:description", KML_NS)
            cid = (name_el.text or "").strip() if name_el is not None else ""
            if not cid or cid.upper().startswith("SKIP-"):
                return
            if cid in seen_ids:
                return
            seen_ids.add(cid)

            ring = _parse_coordinates(poly_el.text)
            if len(ring) < 4:
                return

            area_rai, pure_pixels = _compute_ring_metrics(ring, inward_buffer_m=inward_buffer_m)
            desc = (desc_el.text or "").strip() if desc_el is not None else ""
            label_class = _infer_class(folder_name, desc, cid)
            base_meta = dict(meta_by_id.get(cid, {}))
            props = {
                **base_meta,
                "plot_id": cid,
                "candidate_id": cid,
                "label_class": label_class,
                "area_rai": area_rai,
                "pure_pixels": pure_pixels,
                "size_bin": _classify_size_bin(area_rai),
                "is_small_plot": area_rai < 3.0 or pure_pixels < 9,
                "qa_notes": desc,
            }
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": props,
                }
            )
            return

        for child in elem:
            _walk(child, folder_name)

    _walk(root)

    out_geojson.parent.mkdir(parents=True, exist_ok=True)
    with out_geojson.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, indent=2)
    return features


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert reviewed Google Earth Pro KML polygons to train_plots.geojson."
    )
    parser.add_argument("--in", "--input", dest="kml_path", required=True, help="Reviewed KML file.")
    parser.add_argument(
        "--out",
        default="data/train/train_plots.geojson",
        help="Output GeoJSON path (default: data/train/train_plots.geojson).",
    )
    parser.add_argument(
        "--meta",
        default="data/candidates/auto_train_polygons.geojson",
        help="Optional auto-polygons GeoJSON to carry over metadata attributes.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    kml_path = Path(args.kml_path)
    if not kml_path.exists():
        print(f"ERROR: KML file not found: {kml_path}", file=sys.stderr)
        raise SystemExit(1)

    meta_path = Path(args.meta) if args.meta else None
    feats = kml_to_geojson(kml_path, Path(args.out), meta_geojson=meta_path)

    counts: dict[tuple[str, str], int] = {}
    for f in feats:
        p = f["properties"]
        key = (str(p["label_class"]), str(p["size_bin"]))
        counts[key] = counts.get(key, 0) + 1

    print(f"Wrote {len(feats)} plots to {args.out}")
    for (cls_name, sbin), cnt in sorted(counts.items()):
        print(f"  {cls_name:<10} | {sbin:<16} : {cnt}")


if __name__ == "__main__":
    main()
