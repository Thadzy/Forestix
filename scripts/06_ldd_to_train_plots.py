"""Join LDD Nan 2567 Land Use Shapefile (LU_NAN_2567.shp) with DS-2 train_candidates.geojson.

Pure Python stdlib (zero external GIS libraries required):
- Exact WGS84 <-> UTM Zone 47N (EPSG:32647) Transverse Mercator projection
- Direct .shp/.dbf parser with bounding-box pruning + ray-casting point-in-polygon
- Enforces Gate G2 (never writes blind districts inside this repo)
- Builds a clean, balanced, LDD-verified data/train/train_plots.geojson + label_progress.json

Usage:
    PYTHONPATH=src .venv/bin/python scripts/06_ldd_to_train_plots.py \
        --ldd /Users/thadzy/Documents/Landuse_nan/น่าน2567/การใช้ที่ดิน/LU_NAN_2567.shp
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BLIND_DISTRICTS = {"wiangsa", "santisuk"}

# WGS84 / UTM Zone 47N constants
_A = 6378137.0
_F = 1.0 / 298.257223563
_E2 = _F * (2.0 - _F)
_EP2 = _E2 / (1.0 - _E2)
_K0 = 0.9996
_LON0_RAD = math.radians(99.0)  # UTM Zone 47N central meridian


def wgs84_to_utm47n(lon_deg: float, lat_deg: float) -> tuple[float, float]:
    """Convert WGS84 (lon, lat) in degrees to UTM Zone 47N (easting, northing) in meters."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    tan_lat = math.tan(lat)

    n = _A / math.sqrt(1.0 - _E2 * sin_lat * sin_lat)
    t = tan_lat * tan_lat
    c = _EP2 * cos_lat * cos_lat
    a_term = cos_lat * (lon - _LON0_RAD)

    e4 = _E2 * _E2
    e6 = e4 * _E2
    m = _A * (
        (1.0 - _E2 / 4.0 - 3.0 * e4 / 64.0 - 5.0 * e6 / 256.0) * lat
        - (3.0 * _E2 / 8.0 + 3.0 * e4 / 32.0 + 45.0 * e6 / 1024.0) * math.sin(2.0 * lat)
        + (15.0 * e4 / 256.0 + 45.0 * e6 / 1024.0) * math.sin(4.0 * lat)
        - (35.0 * e6 / 3072.0) * math.sin(6.0 * lat)
    )

    easting = 500000.0 + _K0 * n * (
        a_term
        + (1.0 - t + c) * (a_term**3) / 6.0
        + (5.0 - 18.0 * t + t * t + 72.0 * c - 58.0 * _EP2) * (a_term**5) / 120.0
    )
    northing = _K0 * (
        m
        + n * tan_lat * (
            (a_term**2) / 2.0
            + (5.0 - t + 9.0 * c + 4.0 * c * c) * (a_term**4) / 24.0
            + (61.0 - 58.0 * t + t * t + 600.0 * c - 330.0 * _EP2) * (a_term**6) / 720.0
        )
    )
    return easting, northing


def utm47n_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """Convert UTM Zone 47N (easting, northing) in meters to WGS84 (lon, lat) in degrees."""
    x = easting - 500000.0
    y = northing
    m = y / _K0
    e4 = _E2 * _E2
    e6 = e4 * _E2
    mu = m / (_A * (1.0 - _E2 / 4.0 - 3.0 * e4 / 64.0 - 5.0 * e6 / 256.0))
    e1 = (1.0 - math.sqrt(1.0 - _E2)) / (1.0 + math.sqrt(1.0 - _E2))

    phi1 = (
        mu
        + (3.0 * e1 / 2.0 - 27.0 * (e1**3) / 32.0) * math.sin(2.0 * mu)
        + (21.0 * (e1**2) / 16.0 - 55.0 * (e1**4) / 32.0) * math.sin(4.0 * mu)
        + (151.0 * (e1**3) / 96.0) * math.sin(6.0 * mu)
        + (1097.0 * (e1**4) / 512.0) * math.sin(8.0 * mu)
    )

    sin_p = math.sin(phi1)
    cos_p = math.cos(phi1)
    tan_p = math.tan(phi1)
    n1 = _A / math.sqrt(1.0 - _E2 * sin_p * sin_p)
    t1 = tan_p * tan_p
    c1 = _EP2 * cos_p * cos_p
    r1 = _A * (1.0 - _E2) / ((1.0 - _E2 * sin_p * sin_p) ** 1.5)
    d = x / (n1 * _K0)

    lat = phi1 - (n1 * tan_p / r1) * (
        (d**2) / 2.0
        - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1 * c1 - 9.0 * _EP2) * (d**4) / 24.0
        + (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * t1 * t1 - 252.0 * _EP2 - 3.0 * c1 * c1)
        * (d**6) / 720.0
    )
    lon = _LON0_RAD + (
        d
        - (1.0 + 2.0 * t1 + c1) * (d**3) / 6.0
        + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * c1 * c1 + 8.0 * _EP2 + 24.0 * t1 * t1)
        * (d**5) / 120.0
    ) / cos_p
    return math.degrees(lon), math.degrees(lat)


def _point_in_ring(px: float, py: float, ring: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-18) + xi):
            inside = not inside
        j = i
    return inside


def _simplify_ring_utm(ring: list[tuple[float, float]], tol_m: float = 4.0) -> list[tuple[float, float]]:
    """Lightweight Ramer-Douglas-Peucker simplification for a closed UTM ring."""
    if len(ring) <= 12:
        return ring
    pts = ring[:-1] if ring[0] == ring[-1] else list(ring)

    def _rdp(seq: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(seq) <= 2:
            return seq
        x1, y1 = seq[0]
        x2, y2 = seq[-1]
        dx, dy = x2 - x1, y2 - y1
        denom = math.hypot(dx, dy)
        max_d = -1.0
        idx = 0
        for i in range(1, len(seq) - 1):
            px, py = seq[i]
            if denom < 1e-9:
                d = math.hypot(px - x1, py - y1)
            else:
                d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / denom
            if d > max_d:
                max_d = d
                idx = i
        if max_d > tol_m:
            left = _rdp(seq[: idx + 1])
            right = _rdp(seq[idx:])
            return left[:-1] + right
        return [seq[0], seq[-1]]

    simplified = _rdp(pts)
    if len(simplified) < 3:
        return ring
    simplified.append(simplified[0])
    return simplified


def _ring_area_utm(ring: list[tuple[float, float]]) -> float:
    area2 = 0.0
    for i in range(len(ring) - 1):
        area2 += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(area2) * 0.5


def spatial_join_ldd(
    shp_path: Path,
    candidates: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Join candidate points (WGS84) with LDD Shapefile polygons (UTM 47N)."""
    dbf_path = shp_path.with_suffix(".dbf")
    if not shp_path.exists() or not dbf_path.exists():
        raise FileNotFoundError(f"Missing .shp or .dbf at {shp_path}")

    # Pre-project candidate points to UTM 47N
    cand_utm = []
    for c in candidates:
        ex, ny = wgs84_to_utm47n(c["lon"], c["lat"])
        cand_utm.append((c["candidate_id"], ex, ny))

    # Parse DBF header
    with dbf_path.open("rb") as fdbf, shp_path.open("rb") as fshp:
        hdr = fdbf.read(32)
        numrec, hdrlen, reclen = struct.unpack("<IHH", hdr[4:12])
        fields: list[tuple[str, str, int]] = []
        while True:
            b = fdbf.read(1)
            if not b or b == b"\r":
                break
            desc = b + fdbf.read(31)
            fields.append((desc[:11].split(b"\x00")[0].decode("latin1"), chr(desc[11]), desc[16]))
        fdbf.seek(hdrlen)

        # Skip 100-byte SHP file header
        fshp.seek(100)

        matched: dict[str, dict[str, Any]] = {}
        remaining = {cid: (ex, ny) for cid, ex, ny in cand_utm}

        for rec_idx in range(numrec):
            rec_hdr = fshp.read(8)
            if len(rec_hdr) < 8:
                break
            _, content_words = struct.unpack(">II", rec_hdr)
            content = fshp.read(content_words * 2)
            dbf_rec = fdbf.read(reclen)
            if not remaining:
                break

            shape_type = struct.unpack("<I", content[:4])[0]
            if shape_type not in (5, 15, 25):  # Polygon / PolygonZ / PolygonM
                continue

            xmin, ymin, xmax, ymax = struct.unpack("<4d", content[4:36])
            # Fast bounding-box filter against remaining candidate points
            hits = [
                (cid, ex, ny)
                for cid, (ex, ny) in remaining.items()
                if xmin <= ex <= xmax and ymin <= ny <= ymax
            ]
            if not hits:
                continue

            num_parts, num_points = struct.unpack("<II", content[36:44])
            parts = list(struct.unpack(f"<{num_parts}I", content[44 : 44 + 4 * num_parts]))
            pts_off = 44 + 4 * num_parts
            raw_pts = struct.unpack(f"<{num_points * 2}d", content[pts_off : pts_off + 16 * num_points])
            rings: list[list[tuple[float, float]]] = []
            for p_i in range(num_parts):
                start = parts[p_i]
                end = parts[p_i + 1] if p_i + 1 < num_parts else num_points
                ring = [(raw_pts[2 * k], raw_pts[2 * k + 1]) for k in range(start, end)]
                if ring:
                    rings.append(ring)

            # Parse DBF attributes only when bbox matched
            pos = 1
            attrs: dict[str, str] = {}
            for fname, _, flen in fields:
                if fname in ("LU_CODE", "LU_DES_TH", "LU_DES_EN", "LUL1_CODE", "LUL2_CODE", "Area_Rai"):
                    attrs[fname] = dbf_rec[pos : pos + flen].decode("utf-8", errors="ignore").strip()
                pos += flen

            for cid, ex, ny in hits:
                # Odd-even across rings handles holes properly
                inside_count = sum(1 for r in rings if _point_in_ring(ex, ny, r))
                if inside_count % 2 == 1:
                    # Pick the containing outer ring (largest ring containing the point)
                    containing = [r for r in rings if _point_in_ring(ex, ny, r)]
                    best_ring = max(containing, key=_ring_area_utm)
                    matched[cid] = {
                        "rec_idx": rec_idx,
                        "lu_code": attrs.get("LU_CODE", ""),
                        "lu_des_en": attrs.get("LU_DES_EN", ""),
                        "lu_des_th": attrs.get("LU_DES_TH", ""),
                        "lul1_code": attrs.get("LUL1_CODE", ""),
                        "ldd_area_rai": attrs.get("Area_Rai", ""),
                        "ring_utm": best_ring,
                    }
                    remaining.pop(cid, None)

    return matched


def _load_mod(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_candidates_any_zone(
    candidates_path: Path,
    csv_path: Path | None,
    out_paths: list[Path],
) -> list[dict[str, Any]]:
    """Load candidates while enforcing Gate G2 (blind districts only allowed outside repo)."""
    import csv as _csv
    import datetime as _dt

    with candidates_path.open("r", encoding="utf-8") as fh:
        features = json.load(fh).get("features") or []

    root = _REPO_ROOT.resolve()
    writing_inside_repo = any(p.resolve().is_relative_to(root) for p in out_paths)
    if writing_inside_repo:
        for feat in features:
            dist = str((feat.get("properties") or {}).get("district", ""))
            if dist.replace(" ", "").lower() in _BLIND_DISTRICTS:
                raise ValueError(
                    f"Gate G2 violation: blind district '{dist}' cannot be written inside {root}."
                )

    id_by_coord: dict[tuple[float, float, str], str] = {}
    if csv_path and csv_path.exists():
        with csv_path.open("r", encoding="utf-8") as fh:
            for row in _csv.DictReader(fh):
                key = (round(float(row["lon"]), 5), round(float(row["lat"]), 5), row["pool_name"])
                id_by_coord[key] = row["candidate_id"]

    pool_codes = {"LOSS_POST2020": "LOSS", "G2_EXISTING_CROPLAND": "G2", "G4_INTACT_FOREST": "G4"}
    seq_counters: dict[tuple[str, str], int] = {}
    items: list[dict[str, Any]] = []
    for feat in features:
        props = dict(feat.get("properties") or {})
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        lon, lat = float(geom["coordinates"][0]), float(geom["coordinates"][1])
        pool_name = str(props.get("pool_name", "UNKNOWN"))
        district = str(props.get("district", "UNKNOWN"))
        cid = props.get("candidate_id") or id_by_coord.get((round(lon, 5), round(lat, 5), pool_name))
        if not cid:
            k = (pool_name, district)
            seq_counters[k] = seq_counters.get(k, 0) + 1
            words = district.strip().split()
            dcode = words[0][:3].upper() if len(words) == 1 else "".join(w[0].upper() for w in words)
            cid = f"{pool_codes.get(pool_name, 'UNK')}-{dcode}-{seq_counters[k]:03d}"

        ly = props.get("lossyear")
        lossyear = "none" if (ly is None or ly == "" or int(ly) == 0) else str(2000 + int(ly) if int(ly) < 100 else int(ly))
        rd = props.get("radd_date")
        radd_date = "none"
        if rd not in (None, "", 0, "0", "none"):
            iv = int(rd)
            yy, doy = iv // 1000, iv % 1000
            radd_date = (_dt.date(2000 + yy, 1, 1) + _dt.timedelta(days=doy - 1)).isoformat() if 1 <= doy <= 366 else str(rd)

        items.append(
            {
                "candidate_id": str(cid),
                "pool_name": pool_name,
                "district": district,
                "lon": round(lon, 6),
                "lat": round(lat, 6),
                "seed_source": str(props.get("seed_source", "none")),
                "lossyear": lossyear,
                "radd_date": radd_date,
                "jrc_forest2020": int(props.get("jrc_forest2020", 0)),
                "treecover2000": int(props.get("treecover2000", 0)),
                "wc2020": int(props.get("wc2020", 0)),
            }
        )
    items.sort(key=lambda x: x["candidate_id"])
    return items


def build_ldd_train_plots(
    ldd_shp: Path,
    candidates_path: Path,
    csv_path: Path | None,
    progress_path: Path,
    out_geojson: Path,
    per_class: int = 25,
    max_parcel_rai: float = 30.0,
    seed: int = 42,
) -> list[dict[str, Any]]:
    ui = _load_mod(_REPO_ROOT / "scripts" / "label_ui.py")
    auto = _load_mod(_REPO_ROOT / "scripts" / "04_auto_polygons.py")

    cands = _load_candidates_any_zone(candidates_path, csv_path, [progress_path, out_geojson])
    print(f"Spatial-joining {len(cands)} candidates against {ldd_shp.name}...")
    joined = spatial_join_ldd(ldd_shp, cands)
    print(f"Matched {len(joined)}/{len(cands)} candidates to LDD polygons.")

    # Diagnostic summary of Pool x LDD LU_CODE
    diag = Counter((c["pool_name"], joined[c["candidate_id"]]["lu_code"]) for c in cands if c["candidate_id"] in joined)
    print("\nTop Pool x LDD LU_CODE matches:")
    for (pool, code), cnt in diag.most_common(18):
        print(f"  {pool:<22} | {code:<6} : {cnt}")

    # Classify cleanly using LDD 2567 + 2020 baseline
    plantation_codes = {"A302", "A305", "A303", "A315"}  # Rubber, Teak, Oil palm, Bamboo
    corn_crop_codes = {"A202", "A602", "A200", "A600", "A101", "A001"}  # Corn, shifting corn, field crops
    forest_codes = {"F201", "F101", "F200", "F100"}

    pools: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {
        "G1": [],
        "G2": [],
        "G3": [],
        "G4": [],
    }

    for c in cands:
        cid = c["candidate_id"]
        if cid not in joined:
            continue
        ldd = joined[cid]
        code = ldd["lu_code"]
        pool = c["pool_name"]

        if pool == "LOSS_POST2020":
            if code in plantation_codes:
                pools["G3"].append((c, ldd))
            elif c["jrc_forest2020"] == 1 and code in (corn_crop_codes | {"M102", "F200", "F201"}):
                pools["G1"].append((c, ldd))
        elif pool == "G2_EXISTING_CROPLAND":
            if code in corn_crop_codes:
                pools["G2"].append((c, ldd))
        elif pool == "G4_INTACT_FOREST":
            if code in forest_codes:
                pools["G4"].append((c, ldd))

    print("\nAvailable LDD-verified candidates per class:")
    for k, v in pools.items():
        print(f"  {k}: {len(v)}")

    rng = random.Random(seed)
    all_dists = sorted({c["district"] for c in cands})

    def _pick(cls_name: str, items: list[tuple[dict[str, Any], dict[str, Any]]], target_n: int):
        dists = all_dists
        preferred_codes = {
            "G1": {"A202": 0, "A602": 1, "A200": 2, "A600": 3},
            "G2": {"A202": 0, "A602": 1, "A101": 2},
            "G3": {"A302": 0, "A305": 1},
            "G4": {"F201": 0, "F101": 1, "F200": 2},
        }[cls_name]
        src_rank = {"both": 0, "hansen": 1, "radd": 2, "none": 3}

        def _score(pair):
            c, ldd = pair
            area_rai = _ring_area_utm(ldd["ring_utm"]) / 1600.0
            nice_parcel = 0 if (0.8 <= area_rai <= max_parcel_rai) else 1
            return (
                preferred_codes.get(ldd["lu_code"], 9),
                nice_parcel,
                src_rank.get(c["seed_source"], 9),
                c["candidate_id"],
            )

        selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
        base_q = target_n // max(len(dists), 1)
        rem = target_n % max(len(dists), 1)
        used_ids: set[str] = set()
        for idx, d in enumerate(dists):
            q = base_q + (1 if idx < rem else 0)
            sub = [p for p in items if p[0]["district"] == d]
            sub.sort(key=_score)
            for p in sub[:q]:
                selected.append(p)
                used_ids.add(p[0]["candidate_id"])

        if len(selected) < target_n:
            rest = [p for p in items if p[0]["candidate_id"] not in used_ids]
            rest.sort(key=_score)
            selected.extend(rest[: target_n - len(selected)])
        return selected

    size_cycle = [1.6, 2.0, 2.3, 3.8, 4.5, 5.2, 11.0, 12.5, 14.0]

    store = ui.LabelStore(cands, progress_path, out_geojson)
    store.saved = {}
    used_real_ldd = Counter()

    for cls_name in ("G1", "G2", "G3", "G4"):
        picked = _pick(cls_name, pools[cls_name], per_class)
        for idx, (c, ldd) in enumerate(picked):
            ring_utm = ldd["ring_utm"]
            parcel_rai = _ring_area_utm(ring_utm) / 1600.0

            if 0.8 <= parcel_rai <= max_parcel_rai:
                simp_utm = _simplify_ring_utm(ring_utm, tol_m=4.0)
                ring_wgs = [
                    [round(lon, 6), round(lat, 6)]
                    for lon, lat in (utm47n_to_wgs84(x, y) for x, y in simp_utm)
                ]
                if ring_wgs[0] != ring_wgs[-1]:
                    ring_wgs.append(ring_wgs[0])
                poly_src = "ldd_2567_parcel"
                used_real_ldd[cls_name] += 1
            else:
                # LDD polygon is a giant continuous forest/hillside -> place realistic plot inside it
                target_rai = size_cycle[idx % len(size_cycle)]
                ring_wgs = auto.make_organic_ring_wgs84(c["lon"], c["lat"], target_rai=target_rai, rng=rng)
                poly_src = "ldd_2567_stratified_subparcel"

            cdate = c["radd_date"] if c["radd_date"] != "none" else (c["lossyear"] if c["lossyear"] != "none" else "")
            note = f"LDD2567:{ldd['lu_code']} ({ldd['lu_des_en']}) | {poly_src}"
            store.save_item(
                {
                    "candidate_id": c["candidate_id"],
                    "status": "labeled",
                    "label_class": cls_name,
                    "clearing_date": cdate,
                    "notes": note,
                    "polygon_ring": ring_wgs,
                }
            )

    # Enrich train_plots.geojson with explicit LDD metadata columns
    with out_geojson.open("r", encoding="utf-8") as fh:
        gj = json.load(fh)
    for feat in gj["features"]:
        cid = feat["properties"]["candidate_id"]
        if cid in joined:
            feat["properties"]["ldd_lu_code"] = joined[cid]["lu_code"]
            feat["properties"]["ldd_lu_des_en"] = joined[cid]["lu_des_en"]
            feat["properties"]["ldd_lu_des_th"] = joined[cid]["lu_des_th"]
    with out_geojson.open("w", encoding="utf-8") as fh:
        json.dump(gj, fh, indent=2, ensure_ascii=False)

    print(f"\nReal LDD parcel polygons used directly (vs stratified sub-parcel): {dict(used_real_ldd)}")
    return gj["features"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build LDD-verified train_plots.geojson.")
    parser.add_argument(
        "--ldd",
        required=True,
        help="Path to LU_NAN_2567.shp",
    )
    parser.add_argument("--candidates", default="data/candidates/train_candidates.geojson")
    parser.add_argument("--csv", default="data/candidates/train_candidates_ids.csv")
    parser.add_argument("--progress", default="data/train/label_progress.json")
    parser.add_argument("--out", default="data/train/train_plots.geojson")
    parser.add_argument("--per-class", type=int, default=25, help="Target plots per class (default: 25 -> 100 total).")
    parser.add_argument("--max-parcel-rai", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    feats = build_ldd_train_plots(
        ldd_shp=Path(args.ldd),
        candidates_path=Path(args.candidates),
        csv_path=Path(args.csv) if args.csv else None,
        progress_path=Path(args.progress),
        out_geojson=Path(args.out),
        per_class=args.per_class,
        max_parcel_rai=args.max_parcel_rai,
    )
    print(f"\nWrote {len(feats)} LDD-verified plots to {args.out}")
    print("By class:   ", dict(sorted(Counter(f["properties"]["label_class"] for f in feats).items())))
    print("By size_bin:", dict(sorted(Counter(f["properties"]["size_bin"] for f in feats).items())))
    print("By district:", dict(sorted(Counter(f["properties"]["district"] for f in feats).items())))
    print("By LDD code:", dict(sorted(Counter(f["properties"].get("ldd_lu_code") for f in feats).items())))


if __name__ == "__main__":
    main()
