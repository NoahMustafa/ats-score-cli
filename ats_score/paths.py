"""Resolve bundled data files in both dev and frozen (PyInstaller) runs.

Every read of a bundled data file (model weights, wordlists) goes through
`bundled_path`. In a normal checkout it points at the package dir; inside a
PyInstaller --onefile binary it points at the unpacked _MEIPASS temp dir.

Keep in sync with the PyInstaller spec: data must be added with dest
"ats_score/data" so the frozen layout matches the dev layout.
"""

import sys
from pathlib import Path


def _base() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller unpacks --add-data here; we add it under ats_score/.
        return Path(sys._MEIPASS) / "ats_score"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent  # the ats_score package dir


def bundled_path(rel: str) -> Path:
    """Path to a bundled data file, e.g. bundled_path("data/potion-8M")."""
    return _base() / rel
