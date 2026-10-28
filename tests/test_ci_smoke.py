"""CI post-deploy smoke runner (spec backend-cicd-pipeline, outcome O4; AC7, AC10).

Spec: specs/backend-cicd-pipeline/execution-plan.md § Validation rows AC7 (smoke runner)
and AC10 (no credential / chat URL in output).

Interface (names chosen by the test writer):
`scripts.ci.smoke.run_smoke(*, feed_url, chat_url, runtime_ids, get, post, runtime_status,
sleep=...) -> SmokeReport` runs the four probes and never raises for a failed probe:
- `get(url) -> (status, body_text)`: used for the feed probe only.
- `post(url, *, signed: bool) -> (status, body_text)`: used for the two chat probes.
- `runtime_status(runtime_id) -> str`: used for the READY probe, one call per id.
- `SmokeReport.passed: bool`, `.failures: list[str]` (one entry per failed probe, all probes
  run even after a failure) and `.lines: list[str]` (what the runner printed).
No network and no boto3 call is made: every seam is a fake.

RED phase: `scripts.ci.smoke` does not exist yet.
"""
from __future__ import annotations

import json

import pytest
from ci_synth_helpers import load  # type: ignore[import-not-found]

API_ID = "abc123xyz9"
CHAT_URL = f"https://{API_ID}.execute-api.us-east-1.amazonaws.com"
FEED_URL = "https://feedid7777.execute-api.us-east-1.amazonaws.com"
RUNTIMES = ["ai_radar_curation-FW1w976PCI", "ai_radar_chat-JFCO0R9lkT"]

OK_FEED = (200, json.dumps({"cards": [{"id": "1"}], "next_cursor": None}))
OK_ANSWER = (200, json.dumps({"answer": "hello", "sources": []}))
CURATION_ACK = (200, json.dumps({"status": "accepted", "run_id": "r-1"}))


class Fakes:
    """Scriptable seams: `post_results[signed]` is a list consumed one call at a time."""

    def __init__(self, *, feed=OK_FEED, unsigned=(403, '{"message":"Forbidden"}'), signed=OK_ANSWER,
                 statuses=None):
        self.feed = feed
        self.post_results = {False: [unsigned], True: [signed]}
        self.statuses = statuses or {r: "READY" for r in RUNTIMES}
        self.get_calls: list[str] = []
        self.post_calls: list[tuple[str, bool]] = []
        self.status_calls: list[str] = []
        self.sleeps: list[float] = []

    def get(self, url):
        self.get_calls.append(url)
        return self.feed

    def post(self, url, *, signed):
        self.post_calls.append((url, signed))
        queue = self.post_results[signed]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def runtime_status(self, runtime_id):
        self.status_calls.append(runtime_id)
        return self.statuses[runtime_id]

    def run(self, smoke):
        return smoke.run_smoke(
            feed_url=FEED_URL,
            chat_url=CHAT_URL,
            runtime_ids=RUNTIMES,
            get=self.get,
            post=self.post,
            runtime_status=self.runtime_status,
            sleep=self.sleeps.append,
        )


@pytest.fixture
def smoke():
    return load("scripts.ci.smoke")


def test_all_four_probes_green_passes_and_probes_the_expected_targets(smoke):
    fakes = Fakes()
    report = fakes.run(smoke)
    assert report.passed is True
    assert report.failures == []
    assert fakes.get_calls == [FEED_URL + "/v1/cards?limit=1"]
    assert sorted(fakes.post_calls) == [(CHAT_URL + "/v1/chat", False), (CHAT_URL + "/v1/chat", True)]
    assert sorted(fakes.status_calls) == sorted(RUNTIMES)


@pytest.mark.parametrize(
    "feed",
    [
        (500, "{}"),
        (200, json.dumps({"items": []})),  # no `cards`
        (200, json.dumps({"cards": "not-a-list"})),
        (200, "not json"),
    ],
)
def test_feed_probe_fails_on_a_non_200_or_a_body_without_a_cards_list(smoke, feed):
    report = Fakes(feed=feed).run(smoke)
    assert report.passed is False
    assert len(report.failures) == 1


@pytest.mark.parametrize("status", [200, 401, 500])
def test_unsigned_probe_fails_unless_the_gateway_answers_403(smoke, status):
    report = Fakes(unsigned=(status, "{}")).run(smoke)
    assert report.passed is False
    assert len(report.failures) == 1


@pytest.mark.parametrize(
    "signed",
    [
        (403, '{"message":"Forbidden"}'),
        (500, "{}"),
        (200, json.dumps({"answer": "x"})),  # no sources
        (200, json.dumps({"sources": []})),  # no answer
        CURATION_ACK,  # chat agent deployed without AGENT_ENTRYPOINT=chat_app.py
        (200, "not json"),
    ],
)
def test_signed_probe_fails_unless_200_with_answer_and_sources(smoke, signed):
    report = Fakes(signed=signed).run(smoke)
    assert report.passed is False
    assert len(report.failures) == 1


@pytest.mark.parametrize("bad", RUNTIMES)
def test_runtime_probe_fails_when_either_runtime_is_not_ready(smoke, bad):
    statuses = {r: "READY" for r in RUNTIMES}
    statuses[bad] = "UPDATING"
    report = Fakes(statuses=statuses).run(smoke)
    assert report.passed is False
    assert len(report.failures) == 1


def test_every_probe_runs_and_every_failure_is_reported_even_after_the_first(smoke):
    fakes = Fakes(feed=(500, "{}"), statuses={r: "FAILED" for r in RUNTIMES})
    report = fakes.run(smoke)
    assert report.passed is False
    assert len(report.failures) >= 2
    assert fakes.post_calls  # the chat probes still ran after the feed probe failed


@pytest.mark.parametrize("transient", [502, 504])
def test_signed_probe_retries_once_on_a_gateway_error_and_can_then_pass(smoke, transient):
    fakes = Fakes()
    fakes.post_results[True] = [(transient, "{}"), OK_ANSWER]
    report = fakes.run(smoke)
    assert report.passed is True
    assert [s for _, s in fakes.post_calls].count(True) == 2


def test_signed_probe_retries_only_once(smoke):
    fakes = Fakes()
    fakes.post_results[True] = [(502, "{}"), (502, "{}"), OK_ANSWER]
    report = fakes.run(smoke)
    assert report.passed is False
    assert [s for _, s in fakes.post_calls].count(True) == 2


def test_signed_probe_does_not_retry_on_a_client_or_application_error(smoke):
    fakes = Fakes()
    fakes.post_results[True] = [(500, "{}"), OK_ANSWER]
    fakes.run(smoke)
    assert [s for _, s in fakes.post_calls].count(True) == 1


def test_unsigned_probe_is_never_retried(smoke):
    fakes = Fakes(unsigned=(502, "{}"))
    report = fakes.run(smoke)
    assert report.passed is False
    assert [s for _, s in fakes.post_calls].count(False) == 1


def test_smoke_only_posts_to_the_chat_route_and_never_touches_the_curation_agent(smoke):
    fakes = Fakes()
    fakes.run(smoke)
    assert {url for url, _ in fakes.post_calls} == {CHAT_URL + "/v1/chat"}
    assert fakes.status_calls and set(fakes.status_calls) == set(RUNTIMES)  # status reads only


def test_output_never_shows_the_chat_url_api_id_or_authorization_header_mask(smoke, capsys):
    # Both a passing and a failing run; an error body that echoes the URL must not be printed.
    echoing = (500, f"upstream error at {CHAT_URL}/v1/chat")
    for fakes in (Fakes(), Fakes(signed=echoing, unsigned=echoing, feed=echoing)):
        report = fakes.run(smoke)
        printed = capsys.readouterr()
        visible = "\n".join(
            line
            for line in [*report.lines, *report.failures, *printed.out.splitlines(), *printed.err.splitlines()]
            if not line.startswith("::add-mask::")
        )
        assert CHAT_URL not in visible
        assert API_ID not in visible
        assert "Authorization" not in visible
        assert "x-amz-security-token" not in visible.lower()
