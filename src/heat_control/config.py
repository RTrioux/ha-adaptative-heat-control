"""Environment and ``.env`` configuration for heat-control."""

from __future__ import annotations

import os
from pathlib import Path

_KEYS = ("HASS_URL", "HASS_TOKEN")

_loaded = False


def _candidate_files() -> list[Path]:
    # cwd first, then the project root (editable install / source checkout)
    return [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]


def ensure_env() -> None:
    """Populate ``HASS_URL`` / ``HASS_TOKEN`` from a ``.env`` file.

    Existing environment variables always win over ``.env`` values.
    """
    global _loaded
    if _loaded:
        return
    _loaded = True
    for path in _candidate_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key in _KEYS and key not in os.environ:
                os.environ[key] = value
