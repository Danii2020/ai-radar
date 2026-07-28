#!/usr/bin/env python3
"""AgentCore Runtime entrypoint for the curation pipeline (Spec 04).

Wraps the UNCHANGED compiled curation graph (Spec 01) in a BedrockAgentCoreApp
handler. Constructs DynamoCardStore (Spec 03) + a composite RSS+Tavily
Discoverer (Specs 01-02) from env only - same wiring as run_curation.py, minus
CLI/rich. The Tavily API key is resolved from Secrets Manager at invocation
time (never baked into the image); on failure the run degrades to RSS-only.

Portability: `bedrock_agentcore` and the Secrets Manager boto3 client are
imported ONLY here (the composition root / infra edge) - never in src/curation/
graph/node/state code, which stays byte-for-byte unchanged from Spec 01.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))   # same as run_curation.py

from bedrock_agentcore import BedrockAgentCoreApp

from curation import config as curation_config
from curation.composite import CompositeDiscoverer
from curation.dynamo import DynamoCardStore
from curation.graph import build_graph
from curation.interfaces import Discoverer
from curation.local import RssDiscoverer
from curation.tavily import TavilyDiscoverer
from spike import config

app = BedrockAgentCoreApp()


def _resolve_tavily_key(secret_name: str) -> str:
    """Fetch the Tavily API key from Secrets Manager. Returns "" on any
    failure, empty secret, OR the CDK-provisioned "not yet populated" sentinel
    (curation.config.TAVILY_SECRET_UNSET_SENTINEL) - the caller then degrades
    to RSS-only (mirrors run_curation.py). A freshly-`cdk deploy`'d secret is
    pinned to that sentinel until a human `put-secret-value`s the real key
    (Task 3.5); without this check it would resolve as a truthy-but-useless
    "key" and wrongly report tavily_enabled=True. boto3 is imported lazily
    here so pytest can patch this function without a real client. NEVER logs
    the secret value."""
    import boto3

    try:
        client = boto3.client("secretsmanager", region_name=config.AWS_REGION)
        response = client.get_secret_value(SecretId=secret_name)
    except Exception:  # missing secret, denied, throttled, etc. - degrade quietly
        return ""

    value = response.get("SecretString") or ""
    if value == curation_config.TAVILY_SECRET_UNSET_SENTINEL:
        return ""
    return value


def _build_store() -> DynamoCardStore:
    """DynamoCardStore() unconditionally - the Runtime is cloud-only (no JSON
    backend). Table name from curation.config.CARD_TABLE_NAME."""
    return DynamoCardStore()


def _build_discoverer() -> CompositeDiscoverer:
    """RssDiscoverer always; add TavilyDiscoverer.from_config() iff a key
    resolves from Secrets Manager. Resolves the secret, injects it into
    curation.config.TAVILY_API_KEY so from_config() (Spec 02, unchanged) sees
    it, then appends the Tavily source. Degrades to RSS-only otherwise."""
    key = _resolve_tavily_key(curation_config.TAVILY_SECRET_NAME)
    curation_config.TAVILY_API_KEY = key

    sources: list[Discoverer] = [RssDiscoverer()]
    if key:
        sources.append(TavilyDiscoverer.from_config())
    return CompositeDiscoverer(sources)


@app.entrypoint
def handler(payload) -> dict:
    """AgentCore entrypoint. `payload` is accepted (SDK signature) but ignored -
    all config is env-driven. Builds store + discoverer + the UNCHANGED graph,
    invokes it with max_items=spike.config.MAX_ITEMS, and returns a run summary
    (counts). Never raises for a single bad item/source (inherited per-item
    try/except from Specs 01-03)."""
    store = _build_store()
    discoverer = _build_discoverer()
    graph = build_graph(store, discoverer)

    final = graph.invoke({"max_items": config.MAX_ITEMS})

    return {
        "discovered": final.get("discovered", 0),
        "deduped": final.get("deduped", 0),
        "summarized": final.get("summarized", 0),
        "failed": final.get("failed", 0),
        "persisted": len(final.get("cards", [])),
        "discoverer_failures": discoverer.failures(),
        "store_failures": store.failures(),
        "tavily_enabled": bool(curation_config.TAVILY_API_KEY),
    }


if __name__ == "__main__":
    app.run()
