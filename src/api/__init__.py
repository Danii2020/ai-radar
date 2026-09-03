"""Plane B (serving) — the read-only feed API (Phase 2, spec `feed-api`).

Does not import `src/curation/` (Plane A internals); `boto3` is confined to
`src/api/dynamo.py`.
"""
