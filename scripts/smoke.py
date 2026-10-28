#!/usr/bin/env python3
"""Run success and wait/resume in both views; save execution evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

EXPECTED = {"success": "success", "wait-resume": "before/resumed"}
TERMINAL = {"SUCCEEDED", "FAILED", "TIMED_OUT", "STOPPED"}
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGION = json.loads((ROOT / "adot-layers.json").read_text())["default_region"]


def aws(region, *arguments):
    completed = subprocess.run(
        ["aws", "--region", region, "--output", "json", "--no-cli-pager", *arguments],
        check=True, capture_output=True, text=True,
    )
    return json.loads(completed.stdout)


def wait_for_result(fetch, expected, timeout, *, sleep=time.sleep, clock=time.monotonic):
    deadline = clock() + timeout
    while True:
        execution = fetch()
        if execution.get("Status") in TERMINAL:
            if execution["Status"] != "SUCCEEDED":
                raise RuntimeError(f"Execution ended with {execution['Status']}: {execution}")
            result = json.loads(execution.get("Result", "null"))
            if result != expected:
                raise RuntimeError(f"Expected {expected!r}, received {result!r}")
            return execution
        if clock() >= deadline:
            raise TimeoutError(f"Execution did not finish within {timeout} seconds")
        sleep(2)


def create_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", required=True)
    parser.add_argument("--region", default=DEFAULT_REGION,
                        help=f"AWS deployment region (default: {DEFAULT_REGION})")
    parser.add_argument("--timeout", type=int, default=360)
    return parser


def main():
    args = create_parser().parse_args()
    stack = aws(args.region, "cloudformation", "describe-stacks", "--stack-name", args.stack)["Stacks"][0]
    outputs = {row["OutputKey"]: row["OutputValue"] for row in stack["Outputs"]}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    destination = Path("results") / args.stack / run_id
    destination.mkdir(parents=True)
    (destination / "stack.json").write_text(json.dumps(stack, indent=2))
    for view in ["Execution", "Invocation"]:
        function = outputs[f"{view}FunctionArn"] + ":$LATEST"
        config = aws(args.region, "lambda", "get-function-configuration", "--function-name", function)
        # Store only relevant non-secret configuration, never the whole environment.
        evidence = {key: config.get(key) for key in ["FunctionArn", "Runtime", "Architectures", "Layers", "CodeSha256"]}
        variables = config.get("Environment", {}).get("Variables", {})
        evidence["tracing"] = {key: variables.get(key) for key in ["BUG_BASH_VIEW", "BUG_BASH_SDK_COMMIT", "OTEL_SERVICE_NAME"]}
        (destination / f"{view.lower()}-config.json").write_text(json.dumps(evidence, indent=2))
        for scenario, expected in EXPECTED.items():
            prefix = destination / f"{view.lower()}-{scenario}"
            with tempfile.NamedTemporaryFile() as response:
                accepted = aws(args.region, "lambda", "invoke", "--function-name", function,
                    "--invocation-type", "Event", "--durable-execution-name", f"{run_id}-{view.lower()}-{scenario}",
                    "--cli-binary-format", "raw-in-base64-out", "--payload", json.dumps({"scenario": scenario}), response.name)
            arn = accepted["DurableExecutionArn"]
            prefix.with_suffix(".invoke.json").write_text(json.dumps(accepted, indent=2))
            print(f"{view} / {scenario}: {arn}", flush=True)

            def fetch():
                execution = aws(args.region, "lambda", "get-durable-execution", "--durable-execution-arn", arn)
                prefix.with_suffix(".execution.json").write_text(json.dumps(execution, indent=2))
                return execution

            try:
                wait_for_result(fetch, expected, args.timeout)
            finally:
                history = aws(args.region, "lambda", "get-durable-execution-history", "--durable-execution-arn", arn)
                prefix.with_suffix(".history.json").write_text(json.dumps(history, indent=2))
            print(f"PASS: {expected}", flush=True)
    print(f"Functional smoke passed. Evidence: {destination}")
    print("Next verify sampled OTel spans and replay behavior in CloudWatch Traces and logs; this command does not assert telemetry.")


if __name__ == "__main__":
    main()
