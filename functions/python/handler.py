import os

from aws_durable_execution_sdk_python import DurableContext, durable_execution
from aws_durable_execution_sdk_python.config import Duration
from aws_durable_execution_sdk_python_otel import (
    ExecutionOtelPluginFactory,
    InvocationOtelPluginFactory,
)


plugin = (
    ExecutionOtelPluginFactory()
    if os.environ.get("BUG_BASH_VIEW") == "execution"
    else InvocationOtelPluginFactory()
)


@durable_execution(plugins=[plugin])
def handler(event: dict, context: DurableContext) -> str:
    if event.get("scenario") == "success":
        return context.step(lambda _: "success", name="otel-success")
    if event.get("scenario") == "wait-resume":
        def before_wait(step_context):
            step_context.logger.info("BEFORE_WAIT_BODY: runs only when the step executes")
            return "before"

        before = context.step(before_wait, name="otel-before-wait")
        context.wait(Duration.from_seconds(5), name="otel-wait")
        return context.step(lambda _: f"{before}/resumed", name="otel-after-resume")
    raise ValueError("scenario must be success or wait-resume")
