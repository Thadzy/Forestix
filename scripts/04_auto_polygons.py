"""DS-3 Auto-Polygon Generator: auto-vectorize candidate plots from GEE for fast QA in Google Earth Pro.

Zero external geometry dependencies beyond earthengine-api + Python stdlib so it runs directly
in the existing Forestix .venv.

Workflow:
1. Reads candidate seed points (default: data/candidates/train_candidates.geojson).
2. Enforces the Gate G2 blind-district guard (never writes blind districts inside this repo).
3. In Google Earth Engine, auto-extracts polygon boundaries around each seed:
   - LOSS_POST2020: connected component of Hansen/RADD loss around the seed + optional Wang et al. (2023)
     10m rubber map fraction to help separate G1 (natural forest clearing) vs G3 (rubber harvest).
   - G2_EXISTING_CROPLAND: connected WorldCover cropland patch (clipped to realistic plot size if huge).
   - G4_INTACT_FOREST: stratified realistic-sized polygon (small/medium/large) around intact-forest seeds.
4. Simplifies pixel staircases, computes area_rai & pure_pixels (FR-01), and writes both GeoJSON
   and an Outlined KML for rapid Keep/Delete QA in Google Earth Pro.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import ee

from forestix.candidates import build_pool_image
from forestix.config import load_candidates_config, load_datasets, load_spec
from forestix.ee_init import init_ee

_REPO_ROOT = Path(__file__).resolve().parent.parent

KML_NS = "http://www.opengis.net/kml/2.2"
RUBBER_ASSET_DEFAULT = "projects/rubber-499107/assets/rubber_SEA_2020"

# KML colors are aabbggrr (outlined polygons with faint fill for clear VHR inspection).
CLASS_STYLES: dict[str, tuple[str, str]] = {
    "G1_SUGGESTED": ("ff0000ff", "220000ff"),         # red outline
    "G3_SUGGESTED": ("ffff00ff", "22ff00ff"),         # magenta outline (rubber)
    "LOSS_CHECK_VHR": ("ff0088ff", "220088ff"),       # orange outline (needs quick look)
    "G2_EXISTING_CROPLAND": ("ff00ffff", "2200ffff"), # yellow outline
    "G4_INTACT_FOREST": ("ff00ff00", "2200ff00"),     # green outline
}

FOLDER_ORDER: list[str] = [
    "G1_SUGGESTED",
    "G3_SUGGESTED",
    "LOSS_CHECK_VHR",
    "G2_EXISTING_CROPLAND",
    "G4_INTACT_FOREST",
]

# Stratified target sizes (in rai) for G4 intact forest polygons & clipping huge cropland blobs.
G4_TARGET_RAI_CYCLE: list[float] = [1.5, 2.0, 4.0, 5.0, 12.0, 15.0]


def _normalize_district(name: str) -> str:
    return name.replace(" ", "").lower()


def check_blind_district_guard(
    features: list[dict[str, Any]],
    out_paths: list[Path],
    spec: dict[str, Any],
    repo_root: Path | None = None,
) -> None:
    """Reject writing blind-district outputs inside the repository (Gate G2)."""
    root = (repo_root or _REPO_ROOT).resolve()
    inside_repo = [p.resolve() for p in out_paths if p.resolve().is_relative_to(root)]
    if not inside_repo:
        return

    blind_norm = {_normalize_district(d) for d in spec.get("blind_districts", [])}
    flagged: set[str] = set()
    for feat in features:
        dist = str((feat.get("properties") or {}).get("district", ""))
        if _normalize_district(dist) in blind_norm:
            flagged.add(dist)

    if flagged:
        raise ValueError(
            f"Gate G2 violation: blind district(s) {sorted(flagged)} cannot be written inside "
            f"the repository ({inside_repo[0]}). Pass output paths outside {root}."
        )


def classify_size_bin(area_rai: float) -> str:
    """Bucket plot area (in Thai rai) into spec.md size bins."""
    if area_rai < 3.0:
        return "small_1_2rai"
    if area_rai < 6.0:
        return "medium_3_5rai"
    if area_rai < 10.0:
        return "mid_6_9rai"
    return "large_10plus_rai"


def suggest_class(
    pool_name: str,
    jrc_forest2020: int,
    rubber_frac: float | None,
) -> str:
    """Assign an initial suggested class folder for rapid human QA."""
    if pool_name == "G2_EXISTING_CROPLAND":
        return "G2_EXISTING_CROPLAND"
    if pool_name == "G4_INTACT_FOREST":
        return "G4_INTACT_FOREST"
    if rubber_frac is not None and rubber_frac >= 0.40:
        return "G3_SUGGESTED"
    if jrc_forest2020 == 1 and (rubber_frac is None or rubber_frac < 0.20):
        return "G1_SUGGESTED"
    return "LOSS_CHECK_VHR"


def _meters_per_degree(lat_deg: float) -> tuple[float, float]:
    """Return (meters_per_deg_lon, meters_per_deg_lat) at the given latitude."""
    lat_rad = math.radians(lat_deg)
    m_lat = 111132.92 - 559.82 * math.cos(2 * lat_rad) + 1.175 * math.cos(4 * lat_rad)
    m_lon = 111412.84 * math.cos(lat_rad) - 93.5 * math.cos(3 * lat_rad)
    return m_lon, m_lat


def _ring_to_local_m(ring: list[list[float]] | list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Project a closed WGS84 ring to local tangent-plane meters around its centroid."""
    pts = [(float(p[0]), float(p[1])) for p in ring]
    n = len(pts) - 1 if len(pts) > 1 and pts[0] == pts[-1] else len(pts)
    lon0 = sum(p[0] for p in pts[:n]) / max(n, 1)
    lat0 = sum(p[1] for p in pts[:n]) / max(n, 1)
    m_lon, m_lat = _meters_per_degree(lat0)
    return [((lon - lon0) * m_lon, (lat - lat0) * m_lat) for lon, lat in pts]


def _shoelace_area_and_perimeter_m(pts_m: list[tuple[float, float]]) -> tuple[float, float]:
    """Return (area_m2, perimeter_m) for a closed ring in meters."""
    if len(pts_m) < 4:
        return 0.0, 0.0
    area2 = 0.0
    perim = 0.0
    for i in range(len(pts_m) - 1):
        x1, y1 = pts_m[i]
        x2, y2 = pts_m[i + 1]
        area2 += x1 * y2 - x2 * y1
        perim += math.hypot(x2 - x1, y2 - y1)
    return abs(area2) * 0.5, perim


def compute_ring_metrics(
    ring_wgs84: list[list[float]] | list[tuple[float, float]],
    inward_buffer_m: float = 10.0,
) -> dict[str, Any]:
    """Compute area_rai, pure_pixels estimate, and size_bin for a WGS84 outer ring."""
    pts_m = _ring_to_local_m(ring_wgs84)
    area_m2, perim_m = _shoelace_area_and_perimeter_m(pts_m)
    area_rai = round(area_m2 / 1600.0, 2)
    # Steiner-style inward offset estimate: A_in = max(0, A - P*b + pi*b^2)
    inner_area_m2 = max(0.0, area_m2 - perim_m * inward_buffer_m + math.pi * inward_buffer_m**2)
    if perim_m > 0 and (2.0 * area_m2 / perim_m) <= inward_buffer_m:
        inner_area_m2 = 0.0
    pure_pixels = int(inner_area_m2 // 100.0)
    return {
        "area_m2": area_m2,
        "area_rai": area_rai,
        "pure_pixels": pure_pixels,
        "size_bin": classify_size_bin(area_rai),
    }


def make_organic_ring_wgs84(
    lon: float,
    lat: float,
    target_rai: float,
    rng: random.Random,
    n_vertices: int = 8,
) -> list[list[float]]:
    """Create a realistic slightly irregular closed WGS84 polygon ring around (lon, lat)."""
    target_area_m2 = target_rai * 1600.0
    base_r = math.sqrt(target_area_m2 / math.pi)
    step = 2.0 * math.pi / n_vertices
    angles = [i * step + rng.uniform(-0.22 * step, 0.22 * step) for i in range(n_vertices)]
    aspect = rng.uniform(0.75, 1.35)
    rot = rng.uniform(0.0, math.pi)
    cos_r, sin_r = math.cos(rot), math.sin(rot)

    pts_m: list[tuple[float, float]] = []
    for a in angles:
        r = base_r * rng.uniform(0.85, 1.15)
        lx = r * math.cos(a) * aspect
        ly = r * math.sin(a) / aspect
        pts_m.append((lx * cos_r - ly * sin_r, lx * sin_r + ly * cos_r))
    pts_m.append(pts_m[0])

    cur_area, _ = _shoelace_area_and_perimeter_m(pts_m)
    scale = math.sqrt(target_area_m2 / cur_area) if cur_area > 0 else 1.0
    m_lon, m_lat = _meters_per_degree(lat)
    ring = [
        [round(lon + (x * scale) / m_lon, 6), round(lat + (y * scale) / m_lat, 6)]
        for x, y in pts_m
    ]
    ring[-1] = ring[0]
    return ring


def _largest_ring_from_geojson_geom(geom: dict[str, Any]) -> list[list[float]] | None:
    """Extract the largest outer ring from a GeoJSON Polygon or MultiPolygon."""
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "Polygon" and coords:
        return coords[0]
    if gtype == "MultiPolygon" and coords:
        best_ring: list[list[float]] | None = None
        best_area = -1.0
        for poly in coords:
            if not poly:
                continue
            ring = poly[0]
            area_m2, _ = _shoelace_area_and_perimeter_m(_ring_to_local_m(ring))
            if area_m2 > best_area:
                best_area = area_m2
                best_ring = ring
        return best_ring
    return None


def _try_load_rubber_image(asset_id: str | None) -> ee.Image | None:
    """Attempt to load Wang et al. (2023) 10m SE Asia rubber map; return None if inaccessible."""
    if not asset_id:
        return None
    try:
        img = ee.Image(asset_id)
        bands = img.bandNames().getInfo()
        if not bands:
            return None
        return img.select(0).gt(0).unmask(0).toInt8().rename("rubber2020")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Could not load rubber map '{asset_id}' ({exc}); proceeding without it.")
        return None


def _build_masks(ds: dict[str, Any], cfg: dict[str, Any]) -> tuple[ee.Image, ee.Image]:
    """Build binary masks for LOSS_POST2020 and G2_EXISTING_CROPLAND."""
    pool_img = build_pool_image(ds, cfg)
    pool = pool_img.select("pool")
    loss_mask = pool.eq(1).selfMask().rename("mask")
    g2_mask = pool.eq(2).selfMask().rename("mask")
    return loss_mask, g2_mask


def _vectorize_seed_batch(
    batch: list[dict[str, Any]],
    mask_img: ee.Image,
    rubber_img: ee.Image | None,
    buffer_m: int,
    scale_m: int,
) -> list[dict[str, Any]]:
    """Vectorize connected mask patches around a batch of candidate points in one GEE call."""
    ee_features = [
        ee.Feature(
            ee.Geometry.Point([item["lon"], item["lat"]]),
            {"candidate_id": item["candidate_id"]},
        )
        for item in batch
    ]
    fc = ee.FeatureCollection(ee_features)

    def _extract_one(pt_feat: ee.Feature) -> ee.Feature:
        pt = pt_feat.geometry()
        region = pt.buffer(buffer_m)
        vecs = mask_img.reduceToVectors(
            geometry=region,
            scale=scale_m,
            geometryType="polygon",
            eightConnected=True,
            bestEffort=True,
            maxPixels=1_000_000,
        )
        hitting = vecs.filterBounds(pt.buffer(max(scale_m, 15)))
        best = ee.Feature(
            ee.Algorithms.If(
                hitting.size().gt(0),
                hitting.first(),
                ee.Feature(pt.buffer(1), {"empty": 1}),
            )
        )
        # Simplify pixel staircases server-side (5 m tolerance)
        clean_geom = best.geometry().simplify(5)
        out = ee.Feature(clean_geom, pt_feat.toDictionary()).set(
            "found", hitting.size().gt(0)
        )
        if rubber_img is not None:
            stats = rubber_img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=clean_geom,
                scale=10,
                maxPixels=1_000_000,
                bestEffort=True,
            )
            out = out.set("rubber_frac", stats.get("rubber2020"))
        return out

    return fc.map(_extract_one).getInfo().get("features", [])


def build_auto_polygons_kml(features: list[dict[str, Any]]) -> str:
    """Build a Google Earth Pro KML with outlined polygons organized by suggested class."""
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<kml xmlns="{KML_NS}">',
        "  <Document>",
        "    <name>Forestix DS-3 Auto-Polygons (Keep/Delete QA)</name>",
        "    <description>Auto-vectorized polygons from GEE. Review in Google Earth Pro, "
        "delete bad polygons, adjust edges if needed, then right-click this Document "
        "-&gt; Save Place As... (.kml).</description>",
    ]

    for cls_name, (line_col, poly_col) in CLASS_STYLES.items():
        lines.extend(
            [
                f'    <Style id="style-{cls_name}">',
                "      <LineStyle>",
                f"        <color>{line_col}</color>",
                "        <width>2.5</width>",
                "      </LineStyle>",
                "      <PolyStyle>",
                f"        <color>{poly_col}</color>",
                "        <fill>1</fill>",
                "        <outline>1</outline>",
                "      </PolyStyle>",
                "    </Style>",
            ]
        )

    by_folder: dict[str, list[dict[str, Any]]] = {}
    for feat in features:
        folder = str(feat["properties"].get("suggested_class", "LOSS_CHECK_VHR"))
        by_folder.setdefault(folder, []).append(feat)

    for folder_name in FOLDER_ORDER:
        items = by_folder.get(folder_name, [])
        if not items:
            continue
        lines.append("    <Folder>")
        lines.append(f"      <name>{escape(folder_name)} ({len(items)})</name>")
        for feat in items:
            props = feat["properties"]
            coords = feat["geometry"]["coordinates"][0]
            coord_str = " ".join(f"{lon:.6f},{lat:.6f},0" for lon, lat in coords)
            cid = str(props["candidate_id"])
            desc_lines = [
                f"suggested_class: {props.get('suggested_class')}",
                f"pool_name: {props.get('pool_name')}",
                f"district: {props.get('district')}",
                f"area_rai: {props.get('area_rai')} ({props.get('size_bin')})",
                f"pure_pixels: {props.get('pure_pixels')}",
                f"seed_source: {props.get('seed_source')}",
                f"lossyear: {props.get('lossyear')}",
                f"radd_date: {props.get('radd_date')}",
                f"jrc_forest2020: {props.get('jrc_forest2020')}",
                f"rubber_frac: {props.get('rubber_frac')}",
            ]
            desc = escape("\n".join(desc_lines))
            lines.extend(
                [
                    "      <Placemark>",
                    f"        <name>{escape(cid)}</name>",
                    f"        <styleUrl>#style-{folder_name}</styleUrl>",
                    f"        <description>{desc}</description>",
                    "        <Polygon>",
                    "          <tessellate>1</tessellate>",
                    "          <outerBoundaryIs>",
                    "            <LinearRing>",
                    f"              <coordinates>{coord_str}</coordinates>",
                    "            </LinearRing>",
                    "          </outerBoundaryIs>",
                    "        </Polygon>",
                    "      </Placemark>",
                ]
            )
        lines.append("    </Folder>")

    lines.extend(["  </Document>", "</kml>", ""])
    return "\n".join(lines)


def _assign_ids_if_missing(features: list[dict[str, Any]], seed: int = 42) -> list[dict[str, Any]]:
    """Reuse candidate_id from properties or assign deterministic IDs matching 03_candidates_to_kml.py."""
    pool_codes = {
        "LOSS_POST2020": "LOSS",
        "G2_EXISTING_CROPLAND": "G2",
        "G4_INTACT_FOREST": "G4",
    }
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for feat in features:
        props = feat.get("properties") or {}
        key = (str(props.get("pool_name", "")), str(props.get("district", "")))
        groups.setdefault(key, []).append(feat)

    rng = random.Random(seed)
    records: list[dict[str, Any]] = []
    for (pool_name, district), group_feats in sorted(groups.items()):
        shuffled = list(group_feats)
        rng.shuffle(shuffled)
        words = district.strip().split()
        dcode = words[0][:3].upper() if len(words) == 1 else "".join(w[0].upper() for w in words)
        pcode = pool_codes.get(pool_name, "UNK")
        for seq, feat in enumerate(shuffled, start=1):
            props = dict(feat.get("properties") or {})
            lon, lat = feat["geometry"]["coordinates"][:2]
            cid = props.get("candidate_id") or f"{pcode}-{dcode}-{seq:03d}"
            props["candidate_id"] = cid
            props["lon"] = float(lon)
            props["lat"] = float(lat)
            records.append(props)
    return records


def generate_auto_polygons(
    in_path: Path,
    out_geojson: Path,
    out_kml: Path,
    spec_path: Path,
    datasets_path: Path,
    candidates_cfg_path: Path,
    rubber_asset: str | None = RUBBER_ASSET_DEFAULT,
    max_per_pool: int | None = None,
    min_rai: float = 0.8,
    max_rai: float = 40.0,
    batch_size: int = 25,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Run GEE auto-vectorization on candidate points and write GeoJSON + KML."""
    spec = load_spec(spec_path)
    ds = load_datasets(datasets_path)
    cfg = load_candidates_config(candidates_cfg_path)

    with in_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    raw_features = raw.get("features") or []
    check_blind_district_guard(raw_features, [out_geojson, out_kml], spec)

    records = _assign_ids_if_missing(raw_features, seed=seed)
    if max_per_pool is not None:
        capped: list[dict[str, Any]] = []
        counts_per_pool: dict[str, int] = {}
        for rec in records:
            p = rec["pool_name"]
            if counts_per_pool.get(p, 0) < max_per_pool:
                capped.append(rec)
                counts_per_pool[p] = counts_per_pool.get(p, 0) + 1
        records = capped

    init_ee()
    loss_mask, g2_mask = _build_masks(ds, cfg)
    rubber_img = _try_load_rubber_image(rubber_asset)

    rng = random.Random(seed)
    inward_m = float(spec.get("plot_geometry", {}).get("inward_buffer_m", 10.0))

    rec_by_id = {r["candidate_id"]: r for r in records}
    loss_recs = [r for r in records if r["pool_name"] == "LOSS_POST2020"]
    g2_recs = [r for r in records if r["pool_name"] == "G2_EXISTING_CROPLAND"]
    g4_recs = [r for r in records if r["pool_name"] == "G4_INTACT_FOREST"]

    out_features: list[dict[str, Any]] = []

    def _process_vectorized(
        pool_recs: list[dict[str, Any]],
        mask: ee.Image,
        use_rubber: bool,
        buffer_m: int,
        scale_m: int,
        fallback_organic_if_huge: bool,
    ) -> None:
        for i in range(0, len(pool_recs), batch_size):
            chunk = pool_recs[i : i + batch_size]
            print(
                f"Vectorizing {chunk[0]['pool_name']} [{i + 1}-{i + len(chunk)}/{len(pool_recs)}]..."
            )
            ee_feats = _vectorize_seed_batch(
                chunk,
                mask_img=mask,
                rubber_img=rubber_img if use_rubber else None,
                buffer_m=buffer_m,
                scale_m=scale_m,
            )
            for ef in ee_feats:
                eprops = ef.get("properties") or {}
                if not eprops.get("found"):
                    continue
                cid = str(eprops["candidate_id"])
                rec = rec_by_id[cid]
                ring = _largest_ring_from_geojson_geom(ef.get("geometry") or {})
                if not ring or len(ring) < 4:
                    continue

                metrics = compute_ring_metrics(ring, inward_buffer_m=inward_m)
                source_tag = "gee_auto_vector"
                if fallback_organic_if_huge and metrics["area_rai"] > max_rai:
                    target_rai = G4_TARGET_RAI_CYCLE[len(out_features) % len(G4_TARGET_RAI_CYCLE)]
                    ring = make_organic_ring_wgs84(rec["lon"], rec["lat"], target_rai, rng)
                    metrics = compute_ring_metrics(ring, inward_buffer_m=inward_m)
                    source_tag = "stratified_cropland_parcel"

                if metrics["area_rai"] < min_rai or metrics["area_rai"] > max_rai:
                    continue

                rfrac_raw = eprops.get("rubber_frac")
                rfrac = round(float(rfrac_raw), 3) if rfrac_raw is not None else None
                jrc_val = int(rec.get("jrc_forest2020", 0))
                s_cls = suggest_class(rec["pool_name"], jrc_val, rfrac)

                props = {
                    **rec,
                    "suggested_class": s_cls,
                    "area_rai": metrics["area_rai"],
                    "pure_pixels": metrics["pure_pixels"],
                    "size_bin": metrics["size_bin"],
                    "rubber_frac": rfrac,
                    "polygon_source": source_tag,
                }
                out_features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                        "properties": props,
                    }
                )

    _process_vectorized(
        loss_recs, loss_mask, use_rubber=True, buffer_m=250, scale_m=20, fallback_organic_if_huge=False
    )
    _process_vectorized(
        g2_recs, g2_mask, use_rubber=False, buffer_m=200, scale_m=10, fallback_organic_if_huge=True
    )

    print(f"Generating stratified polygons for G4_INTACT_FOREST ({len(g4_recs)} seeds)...")
    for idx, rec in enumerate(g4_recs):
        target_rai = G4_TARGET_RAI_CYCLE[idx % len(G4_TARGET_RAI_CYCLE)]
        ring = make_organic_ring_wgs84(rec["lon"], rec["lat"], target_rai, rng)
        metrics = compute_ring_metrics(ring, inward_buffer_m=inward_m)
        props = {
            **rec,
            "suggested_class": "G4_INTACT_FOREST",
            "area_rai": metrics["area_rai"],
            "pure_pixels": metrics["pure_pixels"],
            "size_bin": metrics["size_bin"],
            "rubber_frac": None,
            "polygon_source": "stratified_intact_forest",
        }
        out_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": props,
            }
        )

    out_geojson.parent.mkdir(parents=True, exist_ok=True)
    with out_geojson.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": out_features}, fh, indent=2)

    out_kml.parent.mkdir(parents=True, exist_ok=True)
    out_kml.write_text(build_auto_polygons_kml(out_features), encoding="utf-8")
    return out_features


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-generate DS-3 plot polygons from GEE for fast Keep/Delete QA in Google Earth Pro."
    )
    parser.add_argument(
        "--in",
        "--input",
        dest="input_path",
        default="data/candidates/train_candidates.geojson",
        help="Input candidate points GeoJSON (default: data/candidates/train_candidates.geojson).",
    )
    parser.add_argument(
        "--out-geojson",
        default="data/candidates/auto_train_polygons.geojson",
        help="Output auto-polygons GeoJSON path.",
    )
    parser.add_argument(
        "--out-kml",
        default="data/candidates/auto_train_polygons.kml",
        help="Output Google Earth Pro KML path for rapid Keep/Delete QA.",
    )
    parser.add_argument("--spec", default="configs/spec_v1.yaml")
    parser.add_argument("--datasets", default="configs/datasets.yaml")
    parser.add_argument("--candidates-config", default="configs/candidates_v1.yaml")
    parser.add_argument(
        "--rubber-asset",
        default=RUBBER_ASSET_DEFAULT,
        help="Optional GEE rubber map asset ID (pass '' to disable).",
    )
    parser.add_argument(
        "--max-per-pool",
        type=int,
        default=None,
        help="Optional cap per pool for quick dry runs (e.g. --max-per-pool 30).",
    )
    parser.add_argument("--min-rai", type=float, default=0.8)
    parser.add_argument("--max-rai", type=float, default=40.0)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        feats = generate_auto_polygons(
            in_path=Path(args.input_path),
            out_geojson=Path(args.out_geojson),
            out_kml=Path(args.out_kml),
            spec_path=Path(args.spec),
            datasets_path=Path(args.datasets),
            candidates_cfg_path=Path(args.candidates_config),
            rubber_asset=args.rubber_asset or None,
            max_per_pool=args.max_per_pool,
            min_rai=args.min_rai,
            max_rai=args.max_rai,
            batch_size=args.batch_size,
            seed=args.seed,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    summary: dict[tuple[str, str], int] = {}
    for f in feats:
        p = f["properties"]
        key = (str(p["suggested_class"]), str(p["size_bin"]))
        summary[key] = summary.get(key, 0) + 1

    print(f"\nGenerated {len(feats)} auto-polygons:")
    for (cls_name, sbin), cnt in sorted(summary.items()):
        print(f"  {cls_name:<22} | {sbin:<16} : {cnt}")
    print(f"\nGeoJSON: {args.out_geojson}")
    print(f"KML:     {args.out_kml}")


if __name__ == "__main__":
    main()
