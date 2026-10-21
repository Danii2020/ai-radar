"""Send one SigV4-signed `POST /v1/chat` to the chat API (spec `chat-api-auth`).

Usage:
    CHAT_API_URL=https://<api-id>.execute-api.us-east-1.amazonaws.com \\
        uv run run_chat_api_smoke.py ["question"] [--unsigned | --tamper]

Credentials come from the default botocore chain; set AWS_PROFILE_NAME to pick a
named profile. `--unsigned` sends no signature, `--tamper` changes the body after
signing (both should be rejected with 403). Prints the caller identity, then the
status and body. Never prints the secret key, session token or Authorization header.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

REGION = "us-east-1"
SERVICE = "execute-api"
ROUTE = "/v1/chat"
DEFAULT_QUESTION = "What is new in open-weight models?"


def build_signed_headers(url: str, body: bytes, credentials: Credentials) -> dict[str, str]:
    """SigV4-sign a JSON POST for execute-api / us-east-1 and return the headers."""
    host = urlsplit(url).netloc
    request = AWSRequest(
        method="POST",
        url=url,
        data=body,
        headers={"Content-Type": "application/json", "Host": host},
    )
    SigV4Auth(credentials, SERVICE, REGION).add_auth(request)
    return {str(k): str(v) for k, v in request.headers.items()}


def _identity(session: boto3.Session) -> str:
    try:
        ident = session.client("sts", region_name=REGION).get_caller_identity()
        return f"account={ident['Account']} arn={ident['Arn']}"
    except Exception:  # noqa: BLE001 - informational only
        return "identity=unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--unsigned", action="store_true", help="send without a signature")
    group.add_argument("--tamper", action="store_true", help="alter the body after signing")
    args = parser.parse_args(argv)

    base = os.environ.get("CHAT_API_URL", "").rstrip("/")
    if not base:
        print("CHAT_API_URL is not set", file=sys.stderr)
        return 2
    url = base + ROUTE

    session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE_NAME") or None)
    print(_identity(session))

    body = json.dumps({"question": args.question}).encode()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if not args.unsigned:
        creds = session.get_credentials()
        if creds is None:
            print("no AWS credentials found", file=sys.stderr)
            return 2
        frozen = creds.get_frozen_credentials()
        headers = build_signed_headers(
            url, body, Credentials(frozen.access_key, frozen.secret_key, frozen.token)
        )
    if args.tamper:
        body = body + b" "

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=40) as resp:
            status, text = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status, text = exc.code, exc.read().decode("utf-8", "replace")
    print(f"status={status}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
