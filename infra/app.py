#!/usr/bin/env python3
"""CDK app entrypoint (Specs 03-04). `cdk synth`-able; `cdk deploy` out of scope
(except AiRadarRuntimeRole, whose real deploy is Spec 04's own deliverable).

Adds this directory (`infra/`) to `sys.path` so `stacks.card_store_stack` /
`stacks.agent_runtime_stack` (and their own `from lib.* import ...`) resolve as
flat modules, matching `tests/test_infra.py`'s `sys.path.insert(0, ".../infra")`
convention.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import aws_cdk as cdk  # noqa: E402

from stacks.agent_runtime_stack import AgentRuntimeStack  # noqa: E402
from stacks.card_store_stack import CardStoreStack  # noqa: E402

app = cdk.App()
CardStoreStack(app, "AiRadarCardStore")  # env resolved from CDK context / profile
AgentRuntimeStack(app, "AiRadarRuntimeRole")
app.synth()
