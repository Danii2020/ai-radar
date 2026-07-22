#!/usr/bin/env python3
"""CDK app entrypoint (Spec 03). `cdk synth`-able; `cdk deploy` out of scope.

Adds this directory (`infra/`) to `sys.path` so `stacks.card_store_stack` (and
its own `from lib.card_store import CardStoreTable`) resolve as flat modules,
matching `tests/test_infra.py`'s `sys.path.insert(0, ".../infra")` convention.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import aws_cdk as cdk  # noqa: E402

from stacks.card_store_stack import CardStoreStack  # noqa: E402

app = cdk.App()
CardStoreStack(app, "AiRadarCardStore")  # env resolved from CDK context / profile
app.synth()
