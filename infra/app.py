#!/usr/bin/env python3
"""CDK app entrypoint (Specs 03-05). `cdk synth`-able for all three stacks; each
stack also has a real `cdk deploy` as an explicit deliverable of its own spec:
AiRadarCardStore (Spec 03), AiRadarRuntimeRole (Spec 04), and AiRadarSchedule
(Spec 05).

Adds this directory (`infra/`) to `sys.path` so `stacks.card_store_stack` /
`stacks.agent_runtime_stack` / `stacks.curation_schedule_stack` (and their own
`from lib.* import ...`) resolve as flat modules, matching
`tests/test_infra.py`'s `sys.path.insert(0, ".../infra")` convention.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import aws_cdk as cdk
from stacks.agent_runtime_stack import AgentRuntimeStack
from stacks.card_store_stack import CardStoreStack
from stacks.cost_budget_stack import CostBudgetStack
from stacks.curation_schedule_stack import CurationScheduleStack
from stacks.feed_api_stack import FeedApiStack

app = cdk.App()
CardStoreStack(app, "AiRadarCardStore")  # env resolved from CDK context / profile
AgentRuntimeStack(app, "AiRadarRuntimeRole")
CurationScheduleStack(app, "AiRadarSchedule")
CostBudgetStack(app, "AiRadarBudget")  # NEW (Spec 06)
FeedApiStack(app, "AiRadarFeedApi")  # NEW (Phase 2, spec 01)
app.synth()
