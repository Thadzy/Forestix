"""Configuration loaders for Forestix."""

from pathlib import Path
from typing import Any

import yaml


def _load_yaml_dict(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and ensure the root value is a mapping."""
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping in {file_path}, got {type(data).__name__}")
    return data


def load_spec(path: str | Path) -> dict[str, Any]:
    """Load the locked Forestix specification YAML file.

    Serves: SA-3, Gate G1 (spec_v1.yaml).

    Args:
        path: Path to the specification YAML file (e.g., ``configs/spec_v1.yaml``).

    Returns:
        Dictionary containing locked spatial, temporal, geometry, and triage parameters.
    """
    return _load_yaml_dict(path)


def load_datasets(path: str | Path) -> dict[str, Any]:
    """Load the Earth Engine dataset asset IDs YAML file.

    Serves: FR-02, DS-5.

    Args:
        path: Path to the datasets YAML file (e.g., ``configs/datasets.yaml``).

    Returns:
        Dictionary mapping dataset keys to Earth Engine asset IDs (or ``None`` if unconfirmed).
    """
    return _load_yaml_dict(path)


def load_candidates_config(path: str | Path) -> dict[str, Any]:
    """Load the DS-2 candidate-seed configuration YAML file.

    Serves: DS-2.

    Args:
        path: Path to the candidates config YAML file (e.g., ``configs/candidates_v1.yaml``).

    Returns:
        Dictionary containing seed, scale, pool sizes, and threshold parameters.
    """
    return _load_yaml_dict(path)
