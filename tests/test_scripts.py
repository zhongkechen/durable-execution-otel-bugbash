import importlib.util
from pathlib import Path
import unittest

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
            views.add(props["Environment"]["Variables"]["BUG_BASH_VIEW"])
        self.assertEqual(views, {"execution", "invocation"})


if __name__ == "__main__":
    unittest.main()
