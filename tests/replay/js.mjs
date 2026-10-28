import assert from "node:assert/strict";
import { LocalDurableTestRunner } from "../../.build/sdks/js/packages/aws-durable-execution-sdk-js-testing/dist/index.mjs";

// Resolve modules before enabling the local runner's fake clock.
const handlers = [];
for (const view of ["execution", "invocation"]) {
  process.env.BUG_BASH_VIEW = view;
  handlers.push([view, (await import(`../../.build/js/function/index.mjs?view=${view}`)).handler]);
}
await LocalDurableTestRunner.setupTestEnvironment({ skipTime: true });
try {
  for (const [view, handler] of handlers) {
    for (const [scenario, expected] of [["success", "success"], ["wait-resume", "before/resumed"]]) {
      const runner = new LocalDurableTestRunner({ handlerFunction: handler });
      const execution = await runner.run({ payload: { scenario } });
      assert.equal(execution.getStatus(), "SUCCEEDED");
      assert.equal(execution.getResult(), expected);
      if (scenario === "wait-resume") assert.ok(execution.getInvocations().length >= 2);
      console.log("PASS", view, scenario, "invocations", execution.getInvocations().length);
    }
  }
} finally {
  await LocalDurableTestRunner.teardownTestEnvironment();
}
