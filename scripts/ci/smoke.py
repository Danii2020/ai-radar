"""CI post-deploy smoke: four probes, non-zero exit when any fails (AC7, AC8, AC10).

1. `GET /v1/cards?limit=1` on the feed API returns 200 with a `cards` list.
2. An unsigned `POST /v1/chat` returns 403.
3. One signed `POST /v1/chat` returns 200 with `answer` and `sources` (one retry on 502/504).
4. Both agent runtimes report `READY`.

The curation agent is never invoked. Output never shows the chat URL, an error body, a
credential or an Authorization header; the URL is masked before anything can print it.
Run as `python -m scripts.ci.smoke` with the smoke role's credentials.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REGION = "us-east-1"
CHAT_ROUTE = "/v1/chat"
FEED_PATH = "/v1/cards?limit=1"
QUESTION = "What is new in open-weight models?"
RETRY_STATUSES = (502, 504)
RETRY_DELAY_S = 5.0

Response = tuple[int, str]


@dataclass
class SmokeReport:
    failures: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def run_smoke(
    *,
    feed_url: str,
    chat_url: str,
    runtime_ids: list[str],
    get: Callable[[str], Response],
    post: Callable[..., Response],
    runtime_status: Callable[[str], str],
    sleep: Callable[[float], Any] = time.sleep,
) -> SmokeReport:
    """Run all four probes (none is skipped after a failure). Only statuses are reported."""
    report = SmokeReport()

    def record(name: str, ok: bool, detail: str) -> None:
        report.lines.append(f"{'ok  ' if ok else 'FAIL'} {name}: {detail}")
        if not ok:
            report.failures.append(f"{name}: {detail}")

    status, body = get(feed_url.rstrip("/") + FEED_PATH)
    parsed = _json_object(body)
    cards_ok = parsed is not None and isinstance(parsed.get("cards"), list)
    record("feed", status == 200 and cards_ok, f"status={status} cards_list={cards_ok}")

    route = chat_url.rstrip("/") + CHAT_ROUTE
    status, _ = post(route, signed=False)
    record("chat-unsigned", status == 403, f"status={status} (expected 403)")

    status, body = post(route, signed=True)
    if status in RETRY_STATUSES:
        sleep(RETRY_DELAY_S)
        status, body = post(route, signed=True)
    parsed = _json_object(body)
    shape_ok = parsed is not None and "answer" in parsed and "sources" in parsed
    record("chat-signed", status == 200 and shape_ok, f"status={status} answer_and_sources={shape_ok}")

    for runtime_id in runtime_ids:
        state = runtime_status(runtime_id)
        record(f"runtime {runtime_id}", state == "READY", f"status={state}")

    return report


# --- real seams (network and AWS), used only by `main` ---------------------------------------


def _http(request: urllib.request.Request) -> Response:
    try:
        with urllib.request.urlopen(request, timeout=40) as resp:
            return int(resp.status), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        return 0, ""


def _stack_outputs(session: Any, stack: str) -> dict[str, str]:
    client = session.client("cloudformation", region_name=REGION)
    outputs = client.describe_stacks(StackName=stack)["Stacks"][0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outputs}


def _agent_ids() -> list[str]:
    import yaml  # type: ignore[import-untyped]

    from scripts.ci.agentcore_config import AGENTS, TEMPLATE

    agents = yaml.safe_load(TEMPLATE.read_text())["agents"]
    return [str(agents[name]["bedrock_agentcore"]["agent_id"]) for name in AGENTS]


def main() -> int:
    import boto3
    from botocore.credentials import Credentials

    from run_chat_api_smoke import build_signed_headers

    session = boto3.Session()
    feed_url = _stack_outputs(session, "AiRadarFeedApi")["FeedApiUrl"]
    chat_url = _stack_outputs(session, "AiRadarChatApi")["ChatApiUrl"]
    print(f"::add-mask::{chat_url}")
    print(f"::add-mask::{chat_url.split('//', 1)[-1].split('.', 1)[0]}")

    frozen = session.get_credentials()
    if frozen is None:
        print("smoke: no AWS credentials", file=sys.stderr)
        return 2
    creds = frozen.get_frozen_credentials()
    body = json.dumps({"question": QUESTION}).encode()
    control = session.client("bedrock-agentcore-control", region_name=REGION)

    def get(url: str) -> Response:
        return _http(urllib.request.Request(url, method="GET"))

    def post(url: str, *, signed: bool) -> Response:
        headers = {"Content-Type": "application/json"}
        if signed:
            headers = build_signed_headers(
                url, body, Credentials(creds.access_key, creds.secret_key, creds.token)
            )
        return _http(urllib.request.Request(url, data=body, headers=headers, method="POST"))

    def runtime_status(runtime_id: str) -> str:
        try:
            return str(control.get_agent_runtime(agentRuntimeId=runtime_id)["status"])
        except Exception as exc:  # noqa: BLE001 - report the error class only, never the message
            return f"error:{type(exc).__name__}"

    report = run_smoke(
        feed_url=feed_url,
        chat_url=chat_url,
        runtime_ids=_agent_ids(),
        get=get,
        post=post,
        runtime_status=runtime_status,
    )
    for line in report.lines:
        print(line)
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
