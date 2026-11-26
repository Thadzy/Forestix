"""Run by Thadzy only for train districts. Blind districts are run by Chai, output kept outside this repo (Gate G2)."""

import argparse
from pathlib import Path
from typing import Any

from forestix.candidates import candidate_points, to_geojson
from forestix.config import load_candidates_config, load_datasets, load_spec
from forestix.ee_init import init_ee

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _normalize_district(name: str) -> str:
    return name.replace(" ", "").lower()


def check_blind_district_guard(
    districts: list[str],
    out_path: str | Path,
    spec: dict[str, Any],
    repo_root: Path | None = None,
) -> None:
    """Reject writing blind-district candidate points to any path inside the repository.

    Serves: DS-2, Gate G2.

    Args:
        districts: Requested district names.
        out_path: Destination GeoJSON file path.
        spec: Loaded specification dictionary containing ``blind_districts``.
        repo_root: Optional repository root path (defaults to parent of ``scripts/``).

    Raises:
        ValueError: If any requested district matches ``spec["blind_districts"]``
            (case-insensitively, ignoring spaces) and ``out_path`` is inside ``repo_root``.
    """
    root = (repo_root or _REPO_ROOT).resolve()
    resolved_out = Path(out_path).resolve()
    if not resolved_out.is_relative_to(root):
        return

    blind_normalized = {_normalize_district(d) for d in spec.get("blind_districts", [])}
    flagged = [d for d in districts if _normalize_district(d) in blind_normalized]
    if flagged:
        raise ValueError(
            f"Gate G2 violation: blind district(s) {flagged} cannot be written inside "
            f"the repository ({resolved_out}). Pass an --out path outside {root}."
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for candidate point generation.

    Serves: DS-2.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="Generate DS-2 candidate seed points for Forestix."
    )
    parser.add_argument(
        "--districts",
        required=True,
        nargs="+",
        help="Nan Province district names (GAUL ADM2_NAME).",
    )
    parser.add_argument(
        "--out",
        default="data/candidates/train_candidates.geojson",
        help="Output GeoJSON path (default: data/candidates/train_candidates.geojson).",
    )
    parser.add_argument(
        "--spec",
        default="configs/spec_v1.yaml",
        help="Path to spec YAML (default: configs/spec_v1.yaml).",
    )
    parser.add_argument(
        "--datasets",
        default="configs/datasets.yaml",
        help="Path to datasets YAML (default: configs/datasets.yaml).",
    )
    parser.add_argument(
        "--candidates-config",
        default="configs/candidates_v1.yaml",
        help="Path to candidates config YAML (default: configs/candidates_v1.yaml).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for candidate point generation calling ``forestix.candidates``.

    Serves: DS-2.

    Returns:
        None.
    """
    args = parse_args()
    spec = load_spec(args.spec)
    try:
        check_blind_district_guard(args.districts, args.out, spec)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    ds = load_datasets(args.datasets)
    cfg = load_candidates_config(args.candidates_config)

    init_ee()
    fc = candidate_points(args.districts, ds, cfg)
    n_written = to_geojson(fc, args.out)
    print(f"Wrote {n_written} candidate points to {args.out}")


if __name__ == "__main__":
    main()
