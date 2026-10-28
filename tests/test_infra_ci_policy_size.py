"""The scoped execution policy must fit IAM's managed-policy size limit (6,144 characters,
whitespace excluded). Synth cannot catch this; CloudFormation would reject the deploy.
Added by the executor for backend-cicd-pipeline AC13; revision 3 (O15) generalizes it from one
policy to each of one or two policies (spec § Validation AC13 shape and size).
"""
from __future__ import annotations

import json
import re

from ci_synth_helpers import (  # type: ignore[import-not-found]
    ci_access_template,
    resources_of,
)

LIMIT = 6144


def _resolve(value):
    """Collapse Fn::Join and Ref to the strings CloudFormation produces."""
    if isinstance(value, dict):
        if "Fn::Join" in value:
            sep, parts = value["Fn::Join"]
            return sep.join(str(_resolve(p)) for p in parts)
        if "Ref" in value:
            return {"AWS::Partition": "aws", "AWS::AccountId": "123456789012",
                    "AWS::Region": "us-east-1"}.get(value["Ref"], "x")
        return {k: _resolve(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    return value


def test_each_execution_policy_fits_the_iam_managed_policy_size_limit():
    # Revision 3: one or two policies; the limit applies to each one separately.
    policies = resources_of(ci_access_template(), "AWS::IAM::ManagedPolicy")
    assert 1 <= len(policies) <= 2
    for logical_id, policy in policies.items():
        doc = json.dumps(_resolve(policy["Properties"]["PolicyDocument"]), separators=(",", ":"))
        size = len(re.sub(r"\s", "", doc))
        assert size < LIMIT, f"{logical_id} is about {size} characters, limit {LIMIT}"
