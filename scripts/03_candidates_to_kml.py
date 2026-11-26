"""DS-3 helper. Train zone only; never run on blind districts inside this repo (Gate G2)."""

import argparse
import csv
import datetime
import json
import random
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

KML_NS = "http://www.opengis.net/kml/2.2"
PUSHPIN_URL = "http://maps.google.com/mapfiles/kml/pushpin/wht-pushpin.png"

POOL_CODES: dict[str, str] = {
    "LOSS_POST2020": "LOSS",
    "G2_EXISTING_CROPLAND": "G2",
    "G4_INTACT_FOREST": "G4",
}

POOL_ORDER: list[str] = [
    "LOSS_POST2020",
    "G2_EXISTING_CROPLAND",
    "G4_INTACT_FOREST",
]

POOL_FOLDER_NAMES: dict[str, str] = {
    "LOSS_POST2020": "LOSS_POST2020 (G1+G3)",
    "G2_EXISTING_CROPLAND": "G2_EXISTING_CROPLAND",
    "G4_INTACT_FOREST": "G4_INTACT_FOREST",
}

# KML color format is aabbggrr.
POOL_COLORS: dict[str, str] = {
    "LOSS": "ff0000ff",  # red
    "G2": "ff00ffff",    # yellow
    "G4": "ff00ff00",    # green
}

BLIND_DISTRICTS_NORMALIZED: set[str] = {"wiangsa", "santisuk"}

CSV_COLUMNS: list[str] = [
    "candidate_id",
    "pool_name",
    "district",
    "lon",
    "lat",
    "seed_source",
    "lossyear",
    "radd_date",
    "jrc_forest2020",
]


def normalize_district(name: str) -> str:
    """Normalize a district name by removing spaces and lowercasing."""
    return name.replace(" ", "").lower()


def district_code(district: str) -> str:
    """Return uppercase initials for multi-word districts or first 3 letters for one word."""
    words = district.strip().split()
    if not words:
        raise ValueError("District name cannot be empty.")
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(w[0].upper() for w in words)


def decode_lossyear(lossyear: Any) -> str:
    """Format Hansen lossyear (0 or 1-25) as calendar year or 'none'."""
    if lossyear is None or lossyear == "" or int(lossyear) == 0:
        return "none"
    return str(2000 + int(lossyear))


def decode_radd_date(radd_date: Any) -> str:
    """Decode YYDOY integer into YYYY-MM-DD, or 'none' if 0/empty."""
    if radd_date is None or radd_date == "" or int(radd_date) == 0:
        return "none"
    val = int(radd_date)
    yy = val // 1000
    doy = val % 1000
    if doy < 1 or doy > 366:
        return str(val)
    dt = datetime.date(2000 + yy, 1, 1) + datetime.timedelta(days=doy - 1)
    return dt.isoformat()


def check_no_blind_districts(features: list[dict[str, Any]]) -> None:
    """Raise ValueError if any feature belongs to a Gate G2 blind district."""
    for feat in features:
        props = feat.get("properties") or {}
        district = str(props.get("district", ""))
        if normalize_district(district) in BLIND_DISTRICTS_NORMALIZED:
            raise ValueError(
                f"Gate G2 violation: blind district '{district}' is not allowed in DS-3 KML export."
            )


def assign_candidate_ids(
    features: list[dict[str, Any]],
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Assign deterministic, spatially shuffled candidate_ids per pool x district.

    Features are sorted by (pool_name, district, original_index) before shuffling
    within each (pool_name, district) group using random.Random(seed).
    """
    check_no_blind_districts(features)

    indexed: list[tuple[str, str, int, dict[str, Any]]] = []
    for idx, feat in enumerate(features):
        props = feat.get("properties") or {}
        pool_name = str(props.get("pool_name", ""))
        district = str(props.get("district", ""))
        if pool_name not in POOL_CODES:
            raise ValueError(f"Unknown pool_name '{pool_name}' at feature index {idx}.")
        indexed.append((pool_name, district, idx, feat))

    indexed.sort(key=lambda item: (item[0], item[1], item[2]))

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for pool_name, district, _, feat in indexed:
        groups.setdefault((pool_name, district), []).append(feat)

    rng = random.Random(seed)
    records: list[dict[str, Any]] = []

    ordered_pools = [p for p in POOL_ORDER if any(k[0] == p for k in groups)]
    for pool_name in ordered_pools:
        pool_code = POOL_CODES[pool_name]
        districts = sorted(d for (p, d) in groups if p == pool_name)
        for district in districts:
            dist_code = district_code(district)
            group = list(groups[(pool_name, district)])
            rng.shuffle(group)
            for n, feat in enumerate(group, start=1):
                props = feat.get("properties") or {}
                coords = (feat.get("geometry") or {}).get("coordinates") or []
                if len(coords) < 2:
                    raise ValueError(f"Feature in {pool_name}/{district} missing Point coordinates.")
                lon = float(coords[0])
                lat = float(coords[1])
                candidate_id = f"{pool_code}-{dist_code}-{n:03d}"
                records.append(
                    {
                        "candidate_id": candidate_id,
                        "pool_name": pool_name,
                        "pool_code": pool_code,
                        "district": district,
                        "lon": lon,
                        "lat": lat,
                        "seed_source": props.get("seed_source", ""),
                        "lossyear": props.get("lossyear", 0),
                        "radd_alert": props.get("radd_alert", 0),
                        "radd_date": props.get("radd_date", 0),
                        "jrc_forest2020": props.get("jrc_forest2020", ""),
                        "wc2020": props.get("wc2020", ""),
                        "wc2021": props.get("wc2021", ""),
                        "treecover2000": props.get("treecover2000", ""),
                    }
                )
    return records


def format_description(rec: dict[str, Any]) -> str:
    """Format plain-text Placemark description lines for a candidate record."""
    lines = [
        f"pool_name: {rec['pool_name']}",
        f"district: {rec['district']}",
        f"seed_source: {rec['seed_source']}",
        f"lossyear: {decode_lossyear(rec['lossyear'])}",
        f"radd_date: {decode_radd_date(rec['radd_date'])}",
        f"jrc_forest2020: {rec['jrc_forest2020']}",
        f"wc2020: {rec['wc2020']}",
        f"wc2021: {rec['wc2021']}",
        f"treecover2000: {rec['treecover2000']}",
        f"lon/lat: {rec['lon']:.6f}, {rec['lat']:.6f}",
    ]
    return "\n".join(lines)


def build_kml(records: list[dict[str, Any]]) -> str:
    """Build KML document string with styles, pool/district folders, and drawn folder."""
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<kml xmlns="{KML_NS}">',
        "  <Document>",
        "    <name>Forestix DS-3 train candidates</name>",
    ]

    for pool_code, color in POOL_COLORS.items():
        lines.extend(
            [
                f'    <Style id="style-{pool_code}">',
                "      <IconStyle>",
                f"        <color>{color}</color>",
                "        <scale>1.1</scale>",
                "        <Icon>",
                f"          <href>{PUSHPIN_URL}</href>",
                "        </Icon>",
                "      </IconStyle>",
                "    </Style>",
            ]
        )

    drawn_desc = escape(
        "Put your polygons here. Name each polygon with the pin's candidate_id; "
        "use SKIP-<id> for rejected pins."
    )
    lines.extend(
        [
            "    <Folder>",
            "      <name>drawn</name>",
            f"      <description>{drawn_desc}</description>",
            "    </Folder>",
        ]
    )

    by_pool: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for rec in records:
        by_pool.setdefault(rec["pool_name"], {}).setdefault(rec["district"], []).append(rec)

    for pool_name in POOL_ORDER:
        if pool_name not in by_pool:
            continue
        folder_name = escape(POOL_FOLDER_NAMES[pool_name])
        lines.append("    <Folder>")
        lines.append(f"      <name>{folder_name}</name>")

        for district in sorted(by_pool[pool_name]):
            lines.append("      <Folder>")
            lines.append(f"        <name>{escape(district)}</name>")
            for rec in by_pool[pool_name][district]:
                desc = escape(format_description(rec))
                lines.extend(
                    [
                        "        <Placemark>",
                        f"          <name>{escape(rec['candidate_id'])}</name>",
                        f"          <styleUrl>#style-{rec['pool_code']}</styleUrl>",
                        f"          <description>{desc}</description>",
                        "          <Point>",
                        f"            <coordinates>{rec['lon']},{rec['lat']},0</coordinates>",
                        "          </Point>",
                        "        </Placemark>",
                    ]
                )
            lines.append("      </Folder>")
        lines.append("    </Folder>")

    lines.extend(["  </Document>", "</kml>", ""])
    return "\n".join(lines)


def write_csv(records: list[dict[str, Any]], csv_path: Path) -> None:
    """Write candidate ID lookup CSV."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for rec in records:
            writer.writerow({col: rec[col] for col in CSV_COLUMNS})


def convert_geojson_to_kml(
    geojson_path: Path,
    kml_path: Path,
    csv_path: Path,
    seed: int = 42,
) -> dict[tuple[str, str], int]:
    """Load candidate GeoJSON, assign IDs, and write KML + CSV outputs.

    Returns:
        Mapping of (pool_name, district) to candidate count.
    """
    with geojson_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    features = data.get("features") or []
    records = assign_candidate_ids(features, seed=seed)

    kml_text = build_kml(records)
    kml_path.parent.mkdir(parents=True, exist_ok=True)
    kml_path.write_text(kml_text, encoding="utf-8")

    write_csv(records, csv_path)

    counts: dict[tuple[str, str], int] = {}
    for rec in records:
        key = (rec["pool_name"], rec["district"])
        counts[key] = counts.get(key, 0) + 1
    return counts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for DS-3 GeoJSON-to-KML conversion."""
    parser = argparse.ArgumentParser(
        description="Convert DS-2 train_candidates.geojson to Google Earth Pro KML + ID CSV."
    )
    parser.add_argument(
        "--in",
        "--input",
        dest="input_path",
        default="data/candidates/train_candidates.geojson",
        help="Input GeoJSON path (default: data/candidates/train_candidates.geojson).",
    )
    parser.add_argument(
        "--out",
        default="data/candidates/train_candidates.kml",
        help="Output KML path (default: data/candidates/train_candidates.kml).",
    )
    parser.add_argument(
        "--csv",
        default="data/candidates/train_candidates_ids.csv",
        help="Output CSV path (default: data/candidates/train_candidates_ids.csv).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for per-pool/district shuffling (default: 42).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    args = parse_args(argv)
    in_path = Path(args.input_path)
    out_path = Path(args.out)
    csv_path = Path(args.csv)

    try:
        counts = convert_geojson_to_kml(in_path, out_path, csv_path, seed=args.seed)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("Candidate counts (pool x district):")
    for (pool_name, district), count in counts.items():
        print(f"  {pool_name} | {district}: {count}")
    print(f"KML written to: {out_path}")
    print(f"CSV written to: {csv_path}")


if __name__ == "__main__":
    main()
