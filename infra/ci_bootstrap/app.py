#!/usr/bin/env python3
"""CDK app for the CI access stack. Human-only: never run by CI, never part of `infra/app.py`.

    cdk deploy --app "python infra/ci_bootstrap/app.py" -c chat_api_id=<chat-api-id> CiAccess

Run it with your own administrator credentials. See the README "Backend CI/CD" runbook.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aws_cdk as cdk
from ci_bootstrap.ci_access_stack import CiAccessStack

app = cdk.App()
CiAccessStack(app, "CiAccess")
app.synth()
