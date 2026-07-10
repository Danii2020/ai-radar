"""Tests for `src/curation/local.py` — `JsonFileCardStore` + `RssDiscoverer`.

Spec: specs/curation-graph/contract.md ("Local default implementations",
Behavior Guarantee 8), specs/curation-graph/audit.md T7-T10.

RED phase: `src/curation/` does not exist yet. Every test in this file is
expected to fail at collection with `ModuleNotFoundError: No module named
'curation'` until the implementation lands.
"""
from __future__ import annotations

import hashlib
import json

from spike.cards import Card

from curation.local import JsonFileCardStore, RssDiscoverer


def _url_hash(url: str) -> str:
    """Mirror the Card.url -> seen-key rule from contract.md Guarantee 8, used
    here only to seed/assert fixture state — not a re-implementation under test."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


# T7 — dedup_filter drops seen url_hashes, preserving input order.
def test_dedup_filter_drops_seen_items_and_preserves_order(tmp_path, make_raw_item):
    seen_path = tmp_path / "seen.json"
    cards_path = tmp_path / "cards.json"
    a = make_raw_item(url="https://example.com/a", title="A")
    b = make_raw_item(url="https://example.com/b", title="B")
    c = make_raw_item(url="https://example.com/c", title="C")
    seen_path.write_text(json.dumps([_url_hash(b.url)]))

    store = JsonFileCardStore(seen_path=seen_path, cards_path=cards_path)
    result = store.dedup_filter([a, b, c])

    assert [item.url for item in result] == [a.url, c.url]


# T7 — force=True bypasses the seen set entirely.
def test_dedup_filter_force_true_bypasses_seen_set(tmp_path, make_raw_item):
    seen_path = tmp_path / "seen.json"
    cards_path = tmp_path / "cards.json"
    a = make_raw_item(url="https://example.com/a")
    seen_path.write_text(json.dumps([_url_hash(a.url)]))

    store = JsonFileCardStore(seen_path=seen_path, cards_path=cards_path, force=True)
    result = store.dedup_filter([a])

    assert result == [a]


# T7 — with no seen.json on disk yet, nothing is dropped.
def test_dedup_filter_with_no_prior_seen_file_returns_all_items(tmp_path, make_raw_item):
    seen_path = tmp_path / "seen.json"
    cards_path = tmp_path / "cards.json"
    a = make_raw_item(url="https://example.com/a")
    b = make_raw_item(url="https://example.com/b")

    store = JsonFileCardStore(seen_path=seen_path, cards_path=cards_path)
    result = store.dedup_filter([a, b])

    assert result == [a, b]


# T8 — upsert -> dedup_filter idempotency bridge (Guarantee 8: Card.url -> sha256[:16]).
def test_upsert_then_dedup_filter_excludes_persisted_items(
    tmp_path, make_raw_item, make_model_out
):
    seen_path = tmp_path / "seen.json"
    cards_path = tmp_path / "cards.json"
    item = make_raw_item(url="https://example.com/a")
    card = Card.from_model(item, make_model_out())

    store = JsonFileCardStore(seen_path=seen_path, cards_path=cards_path)
    store.upsert([card])
    result = store.dedup_filter([item])

    assert result == []


# T8 — seen accumulates across multiple upsert calls (does not clobber prior entries).
def test_upsert_accumulates_seen_across_multiple_calls(
    tmp_path, make_raw_item, make_model_out
):
    seen_path = tmp_path / "seen.json"
    cards_path = tmp_path / "cards.json"
    item1 = make_raw_item(url="https://example.com/a")
    item2 = make_raw_item(url="https://example.com/b")
    card1 = Card.from_model(item1, make_model_out())
    card2 = Card.from_model(item2, make_model_out())

    store = JsonFileCardStore(seen_path=seen_path, cards_path=cards_path)
    store.upsert([card1])
    store.upsert([card2])

    seen_on_disk = set(json.loads(seen_path.read_text()))
    assert seen_on_disk == {_url_hash(item1.url), _url_hash(item2.url)}


# T9 — upsert writes seen.json (sorted) + cards.json (full batch, indent=2),
# creating parent dirs, matching spike.pipeline._save's shape exactly.
def test_upsert_writes_seen_sorted_and_cards_batch_matching_spike_save_shape(
    tmp_path, make_raw_item, make_model_out
):
    seen_path = tmp_path / "nested" / "seen.json"
    cards_path = tmp_path / "nested" / "cards.json"
    item_z = make_raw_item(url="https://example.com/z", title="Z")
    item_a = make_raw_item(url="https://example.com/a", title="A")
    card_z = Card.from_model(item_z, make_model_out(title="Z"))
    card_a = Card.from_model(item_a, make_model_out(title="A"))

    store = JsonFileCardStore(seen_path=seen_path, cards_path=cards_path)
    store.upsert([card_z, card_a])

    expected_seen = sorted([_url_hash(item_z.url), _url_hash(item_a.url)])
    assert seen_path.read_text() == json.dumps(expected_seen, indent=2)

    expected_cards = [card_z.to_dict(), card_a.to_dict()]
    assert cards_path.read_text() == json.dumps(expected_cards, indent=2)


# T9 — cards.json reflects only the batch passed to THIS upsert call (not an
# accumulation like seen.json), matching the spike's "save the run's ranked cards".
def test_upsert_cards_json_reflects_latest_batch_only(
    tmp_path, make_raw_item, make_model_out
):
    seen_path = tmp_path / "seen.json"
    cards_path = tmp_path / "cards.json"
    item1 = make_raw_item(url="https://example.com/a")
    item2 = make_raw_item(url="https://example.com/b")
    card1 = Card.from_model(item1, make_model_out(title="First batch"))
    card2 = Card.from_model(item2, make_model_out(title="Second batch"))

    store = JsonFileCardStore(seen_path=seen_path, cards_path=cards_path)
    store.upsert([card1])
    store.upsert([card2])

    cards_on_disk = json.loads(cards_path.read_text())
    assert cards_on_disk == [card2.to_dict()]


# T10 — RssDiscoverer.discover delegates to spike.feeds.discover with the
# configured feeds/per_feed (monkeypatched — asserts the call shape, no network).
def test_rss_discoverer_delegates_to_feeds_discover_with_configured_args(
    monkeypatch, make_raw_item
):
    import curation.local as local_module

    captured = {}
    expected_items = [make_raw_item(url="https://example.com/x")]

    def fake_discover(feeds, per_feed):
        captured["feeds"] = feeds
        captured["per_feed"] = per_feed
        return expected_items

    monkeypatch.setattr(local_module, "discover", fake_discover)

    custom_feeds = {"Test Feed": "https://example.com/feed.xml"}
    discoverer = RssDiscoverer(feeds=custom_feeds, per_feed=3)
    result = discoverer.discover()

    assert result == expected_items
    assert captured == {"feeds": custom_feeds, "per_feed": 3}


# T10 — with no explicit feeds/per_feed, RssDiscoverer falls back to
# spike.config.FEEDS / spike.config.PER_FEED (contract's stated default).
def test_rss_discoverer_defaults_to_config_feeds_and_per_feed(monkeypatch):
    import curation.local as local_module
    from spike import config

    captured = {}

    def fake_discover(feeds, per_feed):
        captured["feeds"] = feeds
        captured["per_feed"] = per_feed
        return []

    monkeypatch.setattr(local_module, "discover", fake_discover)

    RssDiscoverer().discover()

    assert captured == {"feeds": config.FEEDS, "per_feed": config.PER_FEED}
