"""CDK stack wrapping `CurationSchedule` (Spec 05: eventbridge-schedule)."""
from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from lib.curation_schedule import (  # infra/ on sys.path via app.py
    DEFAULT_AGENT_RUNTIME_ARN_PARAMETER,
    DEFAULT_ENABLED,
    DEFAULT_SCHEDULE_EXPRESSION,
    DEFAULT_TIMEZONE,
    CurationSchedule,
)


class CurationScheduleStack(Stack):
    """Cadence/timezone/enabled are overridable per-deploy via CDK context:

        cdk deploy -c schedule_expression="cron(5 14 * * ? *)" \
                   -c schedule_timezone="America/New_York" \
                   -c schedule_enabled=true

    Defaults (the "one place") live in lib/curation_schedule.py.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        expression = self.node.try_get_context("schedule_expression") or DEFAULT_SCHEDULE_EXPRESSION
        timezone = self.node.try_get_context("schedule_timezone") or DEFAULT_TIMEZONE
        parameter = (
            self.node.try_get_context("agent_runtime_arn_parameter")
            or DEFAULT_AGENT_RUNTIME_ARN_PARAMETER
        )
        # `-c schedule_enabled=true` arrives as the STRING "true"; anything
        # else (including absent) keeps the inert default.
        raw_enabled = self.node.try_get_context("schedule_enabled")
        enabled = DEFAULT_ENABLED if raw_enabled is None else str(raw_enabled).lower() == "true"

        curation_schedule = CurationSchedule(
            self, "CurationSchedule",
            schedule_expression=expression,
            timezone=timezone,
            enabled=enabled,
            agent_runtime_arn_parameter=parameter,
        )

        CfnOutput(self, "ScheduleName", value=curation_schedule.schedule.schedule_name)
        CfnOutput(self, "ScheduleArn", value=curation_schedule.schedule.schedule_arn)
        CfnOutput(self, "ScheduleExpression", value=expression)
        CfnOutput(self, "ScheduleTimezone", value=timezone)
        CfnOutput(self, "ScheduleEnabled", value=str(enabled))
        CfnOutput(self, "DeadLetterQueueUrl", value=curation_schedule.dead_letter_queue.queue_url)
        CfnOutput(self, "DeadLetterQueueArn", value=curation_schedule.dead_letter_queue.queue_arn)
        CfnOutput(self, "AgentRuntimeArnParameter", value=parameter)
