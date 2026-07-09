#!/usr/bin/env python3
"""Entrypoint for the AI Radar Phase 0 spike.

Usage:
    python run_spike.py            # skips items already seen
    python run_spike.py --force    # re-summarize everything (ignore dedup cache)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from spike.pipeline import run  # noqa: E402

if __name__ == "__main__":
    run(force="--force" in sys.argv)
