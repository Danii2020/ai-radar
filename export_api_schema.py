#!/usr/bin/env python3
"""Write the published feed-API JSON Schema artifact.

    uv run export_api_schema.py     # -> docs/api/feed-api.v1.schema.json

Spec 02 (`web-feed-ui`) generates its TypeScript types from that file.
`tests/test_feed_api_contract.py` fails if the committed file drifts from
`contracts.card.json_schema()`, so regenerating is a required step whenever
CardOut/FeedResponse changes (which is a BREAKING API change — bump
CARD_SCHEMA_VERSION and the route/artifact version).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from contracts.card import json_schema  # noqa: E402

OUTPUT_PATH = Path(__file__).parent / "docs" / "api" / "feed-api.v1.schema.json"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(json_schema(), indent=2) + "\n")
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
