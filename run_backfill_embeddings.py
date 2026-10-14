#!/usr/bin/env python3
"""One-time (idempotent) catch-up: embed every curated card that lacks a vector.

Usage:
    uv run run_backfill_embeddings.py

Uses your local AWS credentials; prints the account id and table it will write
to before writing, so a wrong profile is caught early.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import boto3

from curation.backfill import backfill_embeddings
from curation.dynamo import DynamoCardStore


def _account_id() -> str:
    try:
        return boto3.client("sts").get_caller_identity()["Account"]
    except Exception:  # noqa: BLE001 - informational only
        return "unknown"


def main() -> None:
    store = DynamoCardStore()
    print(f"account={_account_id()} table={store.table_name}")
    result = backfill_embeddings(store)
    print(
        f"embedded={result.embedded} skipped={result.skipped} failed={result.failed}"
    )


if __name__ == "__main__":
    main()
