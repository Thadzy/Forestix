"""Forestix DS-3 Visual Labeling Studio (local web UI, zero extra dependencies).

Serves a synchronized dual-map Before (2020) vs After (Latest) labeling interface
using Python's built-in http.server, saving directly to data/train/train_plots.geojson.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/label_ui.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HTML_PATH = Path(__file__).resolve().parent / "label_ui.html"
_BLIND_DISTRICTS = {"wiangsa", "santisuk"}


def _meters_per_degree(lat_deg: float) -> tuple[float, float]:
    lat_rad = math.radians(lat_deg)
    m_lat = 111132.92 - 559.82 * math.cos(2 * lat_rad) + 1.175 * math.cos(4 * lat_rad)
    m_lon = 111412.84 * math.cos(lat_rad) - 93.5 * math.cos(3 * lat_rad)
    return m_lon, m_lat


def compute_ring_metrics(ring: list[list[float]], inward_buffer_m: float = 10.0) -> dict[str, Any]:
    """Compute area_rai, pure_pixels, size_bin, and is_small_plot for a WGS84 ring."""
    if not ring or len(ring) < 4:
        return {"area_rai": 0.0, "pure_pixels": 0, "size_bin": "none", "is_small_plot": True}
    n = len(ring) - 1 if ring[0] == ring[-1] else len(ring)
    lon0 = sum(p[0] for p in ring[:n]) / max(n, 1)
    lat0 = sum(p[1] for p in ring[:n]) / max(n, 1)
    m_lon, m_lat = _meters_per_degree(lat0)
    pts_m = [((p[0] - lon0) * m_lon, (p[1] - lat0) * m_lat) for p in ring]
    if pts_m[0] != pts_m[-1]:
        pts_m.append(pts_m[0])

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
    pure_pixels = int(inner_m2 // 100.0)

    if area_rai < 3.0:
        size_bin = "small_1_2rai"
    elif area_rai < 6.0:
        size_bin = "medium_3_5rai"
    elif area_rai < 10.0:
        size_bin = "mid_6_9rai"
    else:
        size_bin = "large_10plus_rai"

    return {
        "area_rai": area_rai,
        "pure_pixels": pure_pixels,
        "size_bin": size_bin,
        "is_small_plot": area_rai < 3.0 or pure_pixels < 9,
    }


def _decode_lossyear(val: Any) -> str:
    if val is None or val == "" or int(val) == 0:
        return "none"
    v = int(val)
    return str(2000 + v) if v < 100 else str(v)


def _decode_radd(val: Any) -> str:
    if val is None or val == "" or str(val) == "none":
        return "none"
    try:
        iv = int(val)
    except ValueError:
        return str(val)
    if iv == 0:
        return "none"
    yy, doy = iv // 1000, iv % 1000
    import datetime

    if 1 <= doy <= 366:
        return (datetime.date(2000 + yy, 1, 1) + datetime.timedelta(days=doy - 1)).isoformat()
    return str(val)


def _load_candidates(candidates_path: Path, csv_path: Path | None) -> list[dict[str, Any]]:
    """Load candidate points or auto-polygons and assign deterministic candidate_ids."""
    with candidates_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    features = data.get("features") or []

    # Check Gate G2
    for feat in features:
        dist = str((feat.get("properties") or {}).get("district", ""))
        if dist.replace(" ", "").lower() in _BLIND_DISTRICTS:
            raise ValueError(
                f"Gate G2 violation: blind district '{dist}' cannot be opened in the train UI."
            )

    # Optional ID lookup from train_candidates_ids.csv (matches Google Earth Pro IDs!)
    id_by_coord: dict[tuple[float, float, str], str] = {}
    if csv_path and csv_path.exists():
        with csv_path.open("r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                key = (round(float(row["lon"]), 5), round(float(row["lat"]), 5), row["pool_name"])
                id_by_coord[key] = row["candidate_id"]

    pool_codes = {
        "LOSS_POST2020": "LOSS",
        "G2_EXISTING_CROPLAND": "G2",
        "G4_INTACT_FOREST": "G4",
    }
    seq_counters: dict[tuple[str, str], int] = {}
    items: list[dict[str, Any]] = []

    for feat in features:
        props = dict(feat.get("properties") or {})
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        starter_ring: list[list[float]] | None = None

        if gtype == "Point":
            lon, lat = float(geom["coordinates"][0]), float(geom["coordinates"][1])
        elif gtype == "Polygon" and geom.get("coordinates"):
            starter_ring = geom["coordinates"][0]
            n = len(starter_ring) - 1 if starter_ring[0] == starter_ring[-1] else len(starter_ring)
            lon = sum(p[0] for p in starter_ring[:n]) / max(n, 1)
            lat = sum(p[1] for p in starter_ring[:n]) / max(n, 1)
        else:
            continue

        pool_name = str(props.get("pool_name", "UNKNOWN"))
        district = str(props.get("district", "UNKNOWN"))
        cid = props.get("candidate_id")
        if not cid:
            cid = id_by_coord.get((round(lon, 5), round(lat, 5), pool_name))
        if not cid:
            k = (pool_name, district)
            seq_counters[k] = seq_counters.get(k, 0) + 1
            words = district.strip().split()
            dcode = words[0][:3].upper() if len(words) == 1 else "".join(w[0].upper() for w in words)
            cid = f"{pool_codes.get(pool_name, 'UNK')}-{dcode}-{seq_counters[k]:03d}"

        items.append(
            {
                "candidate_id": str(cid),
                "pool_name": pool_name,
                "district": district,
                "lon": round(lon, 6),
                "lat": round(lat, 6),
                "seed_source": str(props.get("seed_source", "none")),
                "lossyear": _decode_lossyear(props.get("lossyear")),
                "radd_date": _decode_radd(props.get("radd_date")),
                "jrc_forest2020": int(props.get("jrc_forest2020", 0)),
                "treecover2000": int(props.get("treecover2000", 0)),
                "wc2020": int(props.get("wc2020", 0)),
                "rubber_frac": props.get("rubber_frac"),
                "suggested_class": props.get("suggested_class"),
                "starter_ring": starter_ring,
            }
        )

    # Sort nicely by candidate_id so order is deterministic and easy to navigate
    items.sort(key=lambda x: x["candidate_id"])
    return items


class LabelStore:
    """Manages candidate list, saved progress JSON, and live export to train_plots.geojson."""

    def __init__(
        self,
        candidates: list[dict[str, Any]],
        progress_path: Path,
        out_geojson_path: Path,
    ) -> None:
        self.candidates = candidates
        self.by_id = {c["candidate_id"]: c for c in candidates}
        self.progress_path = progress_path
        self.out_geojson_path = out_geojson_path
        self.saved: dict[str, dict[str, Any]] = {}
        self._load_progress()

    def _load_progress(self) -> None:
        if self.progress_path.exists():
            with self.progress_path.open("r", encoding="utf-8") as fh:
                self.saved = json.load(fh)

    def _flush(self) -> None:
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        with self.progress_path.open("w", encoding="utf-8") as fh:
            json.dump(self.saved, fh, indent=2, ensure_ascii=False)

        features: list[dict[str, Any]] = []
        for cid, rec in sorted(self.saved.items()):
            if rec.get("status") != "labeled":
                continue
            ring = rec.get("polygon_ring")
            if not ring or len(ring) < 4:
                continue
            base = self.by_id.get(cid, {})
            metrics = compute_ring_metrics(ring)
            props = {
                "plot_id": cid,
                "candidate_id": cid,
                "label_class": rec.get("label_class"),
                "clearing_date": rec.get("clearing_date") or "",
                "notes": rec.get("notes") or "",
                "pool_name": base.get("pool_name"),
                "district": base.get("district"),
                "seed_source": base.get("seed_source"),
                "lossyear": base.get("lossyear"),
                "radd_date": base.get("radd_date"),
                "jrc_forest2020": base.get("jrc_forest2020"),
                "treecover2000": base.get("treecover2000"),
                **metrics,
            }
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": props,
                }
            )

        self.out_geojson_path.parent.mkdir(parents=True, exist_ok=True)
        with self.out_geojson_path.open("w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": features}, fh, indent=2, ensure_ascii=False)

    def save_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        cid = str(payload["candidate_id"])
        status = str(payload.get("status", "labeled"))
        ring = payload.get("polygon_ring")
        if ring and len(ring) >= 3 and ring[0] != ring[-1]:
            ring = [*ring, ring[0]]
        metrics = compute_ring_metrics(ring) if ring else {}
        self.saved[cid] = {
            "candidate_id": cid,
            "status": status,
            "label_class": payload.get("label_class"),
            "clearing_date": str(payload.get("clearing_date") or "").strip(),
            "notes": str(payload.get("notes") or "").strip(),
            "polygon_ring": ring,
            **metrics,
        }
        self._flush()
        return self.saved[cid]

    def reset_item(self, cid: str) -> None:
        self.saved.pop(cid, None)
        self._flush()

    def payload(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "saved": self.saved,
            "out_geojson": str(self.out_geojson_path),
        }


def make_handler(store: LabelStore, html_bytes: bytes):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return  # keep terminal clean

        def _send_json(self, obj: Any, status: int = 200) -> None:
            raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.end_headers()
                self.wfile.write(html_bytes)
                return
            if self.path == "/api/data":
                self._send_json(store.payload())
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, status=400)
                return

            if self.path == "/api/save":
                if not data.get("candidate_id"):
                    self._send_json({"error": "candidate_id required"}, status=400)
                    return
                saved = store.save_item(data)
                self._send_json({"ok": True, "item": saved})
                return

            if self.path == "/api/reset":
                cid = str(data.get("candidate_id") or "")
                if cid:
                    store.reset_item(cid)
                self._send_json({"ok": True})
                return

            self.send_error(HTTPStatus.NOT_FOUND)

    return Handler


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch Forestix DS-3 Visual Labeling Studio.")
    parser.add_argument(
        "--candidates",
        default=None,
        help="Input GeoJSON (auto-uses auto_train_polygons.geojson if present, else train_candidates.geojson).",
    )
    parser.add_argument(
        "--csv",
        default="data/candidates/train_candidates_ids.csv",
        help="Optional CSV for matching candidate_ids.",
    )
    parser.add_argument(
        "--progress",
        default="data/train/label_progress.json",
        help="Progress JSON file for resumable labeling.",
    )
    parser.add_argument(
        "--out",
        default="data/train/train_plots.geojson",
        help="Live output GeoJSON path.",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.candidates:
        cand_path = Path(args.candidates)
    else:
        auto_p = Path("data/candidates/auto_train_polygons.geojson")
        cand_path = auto_p if auto_p.exists() else Path("data/candidates/train_candidates.geojson")

    if not cand_path.exists():
        print(f"ERROR: Candidate file not found: {cand_path}", file=sys.stderr)
        raise SystemExit(1)

    csv_path = Path(args.csv) if args.csv else None
    candidates = _load_candidates(cand_path, csv_path)
    store = LabelStore(candidates, Path(args.progress), Path(args.out))
    html_bytes = _HTML_PATH.read_bytes()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store, html_bytes))
    url = f"http://127.0.0.1:{args.port}"
    print(f"Forestix DS-3 Labeling Studio running at: {url}")
    print(f"Loaded {len(candidates)} candidates from: {cand_path}")
    print(f"Auto-saving labeled plots to: {args.out}")
    print("Press Ctrl+C to stop.")

    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
