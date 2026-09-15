#!/usr/bin/env python3
"""Compatibility entry point for the shared documentation checker."""

import runpy
from pathlib import Path


CHECKER = (
    Path(__file__).resolve().parents[4]
    / ".agents"
    / "skills"
    / "odubook-i18n"
    / "scripts"
    / "check_docs.py"
)


if __name__ == "__main__":
    runpy.run_path(str(CHECKER), run_name="__main__")
