"""Tests for locked specification configuration."""

from pathlib import Path

import yaml


def test_spec_v1_loads_and_cutoff_date() -> None:
    """Verify spec_v1.yaml loads cleanly and cutoff_date is 2020-12-31."""
    spec_path = Path(__file__).resolve().parents[1] / "configs" / "spec_v1.yaml"
    with spec_path.open("r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    assert spec["cutoff_date"] == "2020-12-31"
