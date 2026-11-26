"""Google Earth Engine initialization helper."""

import os

import ee
from dotenv import load_dotenv


def init_ee() -> None:
    """Initialize Google Earth Engine using ``EE_PROJECT`` from environment or ``.env``.

    Serves: FR-02.

    Args:
        None. Reads ``EE_PROJECT`` from environment variables / ``.env`` file.

    Returns:
        None.

    Raises:
        RuntimeError: If ``EE_PROJECT`` is not set or is empty.
    """
    load_dotenv()
    project = os.getenv("EE_PROJECT", "").strip()
    if not project:
        raise RuntimeError(
            "EE_PROJECT is not set. Set EE_PROJECT in your environment or .env file."
        )
    ee.Initialize(project=project)
