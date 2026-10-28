import importlib
import json
import logging
import os
from pathlib import Path
import sys

from aws_durable_execution_sdk_python_testing.runner import DurableFunctionTestRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "functions/python"))
import handler

records = []


class Capture(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())


logging.getLogger().addHandler(Capture())
logging.getLogger().setLevel(logging.INFO)
for view in ("execution", "invocation"):
    os.environ["BUG_BASH_VIEW"] = view
    module = importlib.reload(handler)
    for scenario, expected in [("success", "success"), ("wait-resume", "before/resumed")]:
        records.clear()
        calls = []

        def tracked(event, context):
            calls.append(True)
            return module.handler(event, context)

        with DurableFunctionTestRunner(handler=tracked) as runner:
            result = runner.run(input=json.dumps({"scenario": scenario}), execution_timeout=30)
        assert json.loads(result.result) == expected, result
        if scenario == "wait-resume":
            assert len(calls) >= 2
            assert sum("BEFORE_WAIT_BODY" in item for item in records) == 1
        print("PASS", view, scenario, "invocations", len(calls))
