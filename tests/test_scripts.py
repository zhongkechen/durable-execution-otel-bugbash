import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build, deploy, smoke = load("build"), load("deploy"), load("smoke")


class SmokeTests(unittest.TestCase):
    def test_acceptance_is_not_completion(self):
        responses = iter([{"Status": "RUNNING"}, {"Status": "SUCCEEDED", "Result": '"success"'}])
        delays = []
        result = smoke.wait_for_result(lambda: next(responses), "success", 10, sleep=delays.append)
        self.assertEqual(result["Status"], "SUCCEEDED")
        self.assertEqual(delays, [2])

    def test_terminal_failure_is_not_a_pass(self):
        with self.assertRaises(RuntimeError):
            smoke.wait_for_result(lambda: {"Status": "FAILED"}, "success", 10)

    def test_wrong_result_is_not_a_pass(self):
        with self.assertRaises(RuntimeError):
            smoke.wait_for_result(lambda: {"Status": "SUCCEEDED", "Result": '"wrong"'}, "success", 10)

    def test_polling_is_bounded(self):
        ticks = iter([0, 20])
        with self.assertRaises(TimeoutError):
            smoke.wait_for_result(lambda: {"Status": "RUNNING"}, "success", 10, clock=lambda: next(ticks))


class DeploymentTests(unittest.TestCase):
    def test_deploy_passes_resolved_region_and_layer_to_sam(self):
        cases = [([], "us-west-2", deploy.resolve_layer("python", "us-west-2")),
                 (["--region", "us-east-1"], "us-east-1", deploy.resolve_layer("python", "us-east-1")),
                 (["--layer", "arn:aws:lambda:us-west-2:123456789012:layer:custom:7"],
                  "us-west-2", "arn:aws:lambda:us-west-2:123456789012:layer:custom:7")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sdk-lock.json").write_text(json.dumps({"python": {"commit": "test-commit"}}))
            output = root / ".build/python"
            output.mkdir(parents=True)
            (output / "template.json").write_text(json.dumps({"Globals": {"Function": {
                "Environment": {"Variables": {"BUG_BASH_SDK_COMMIT": "test-commit"}}
            }}}))
            for flags, region, layer in cases:
                with self.subTest(flags=flags), patch.object(deploy, "ROOT", root), \
                        patch("sys.argv", ["deploy.py", "python", "--stack", "test", *flags]), \
                        patch.object(deploy.subprocess, "run") as run, patch("builtins.print"):
                    deploy.main()
                    command = run.call_args_list[-1].args[0]
                    self.assertEqual(command[command.index("--region") + 1], region)
                    self.assertEqual(command[command.index("--parameter-overrides") + 1], f"AdotLayerArn={layer}")

    def test_deploy_and_smoke_default_to_same_region(self):
        args = deploy.create_parser().parse_args(["js", "--stack", "test"])
        self.assertEqual(args.region, "us-west-2")
        self.assertIsNone(args.layer)
        self.assertEqual(smoke.create_parser().parse_args(["--stack", "test"]).region, args.region)

    def test_default_layers_match_published_west_region_versions(self):
        expected = {"js": "AWSOpenTelemetryDistroJs:16",
                    "python": "AWSOpenTelemetryDistroPython:36",
                    "java": "AWSOpenTelemetryDistroJava:19"}
        for language, layer in expected.items():
            self.assertEqual(deploy.resolve_layer(language, "us-west-2"),
                             f"arn:aws:lambda:us-west-2:615299751070:layer:{layer}")

    def test_region_override_uses_its_published_version_and_account(self):
        self.assertEqual(deploy.resolve_layer("python", "us-east-1"),
                         "arn:aws:lambda:us-east-1:615299751070:layer:AWSOpenTelemetryDistroPython:32")
        self.assertEqual(deploy.resolve_layer("java", "ap-east-2"),
                         "arn:aws:lambda:ap-east-2:412664885777:layer:AWSOpenTelemetryDistroJava:8")

    def test_custom_layer_takes_precedence_even_without_regional_default(self):
        arn = "arn:aws-us-gov:lambda:us-gov-west-1:123456789012:layer:custom:7"
        args = deploy.create_parser().parse_args(
            ["js", "--stack", "test", "--region", "us-gov-west-1", "--layer", arn])
        self.assertEqual(deploy.resolve_layer(args.language, args.region, args.layer), arn)
        with self.assertRaisesRegex(ValueError, "supply --layer"):
            deploy.resolve_layer("js", "us-gov-west-1")
        with self.assertRaisesRegex(ValueError, "in --region"):
            deploy.resolve_layer("js", "us-east-1", arn)

    def test_all_pinned_arns_have_their_recorded_region_and_a_version(self):
        for language in deploy.ADOT["languages"].values():
            for region, arn in language["layers"].items():
                deploy.validate_layer(arn, region)

    def test_layer_must_match_region_and_include_version(self):
        deploy.validate_layer("arn:aws:lambda:us-west-2:123456789012:layer:adot:1", "us-west-2")
        for arn in ["arn:aws:lambda:us-east-1:123456789012:layer:adot:1", "arn:aws:lambda:us-west-2:123456789012:layer:adot"]:
            with self.assertRaises(ValueError):
                deploy.validate_layer(arn, "us-west-2")

    def test_template_preserves_both_views_and_no_public_trigger(self):
        template = build.render_template("java", {"Runtime": "java21"}, {"OTEL_JAVAAGENT_EXTENSIONS": "/var/task/lib/plugin.jar"})
        globals_ = template["Globals"]["Function"]
        self.assertEqual(globals_["Environment"]["Variables"]["OTEL_JAVAAGENT_EXTENSIONS"], "/var/task/lib/plugin.jar")
        views = set()
        for resource in template["Resources"].values():
            props = resource["Properties"]
            self.assertNotIn("FunctionUrlConfig", props)
            self.assertNotIn("Events", props)
            # SAM injects this policy for DurableConfig; redeclaring it can
            # produce duplicate ManagedPolicyArns after transformation.
            self.assertNotIn("AWSLambdaBasicDurableExecutionRolePolicy", json.dumps(props.get("Policies", [])))
            views.add(props["Environment"]["Variables"]["BUG_BASH_VIEW"])
        self.assertEqual(views, {"execution", "invocation"})


if __name__ == "__main__":
    unittest.main()
