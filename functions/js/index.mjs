import { withDurableExecution } from "@aws/durable-execution-sdk-js";
import {
  createExecutionOtelPluginFactory,
  createInvocationOtelPluginFactory,
} from "@aws/durable-execution-sdk-js-otel";

const plugin = process.env.BUG_BASH_VIEW === "execution"
  ? createExecutionOtelPluginFactory()
  : createInvocationOtelPluginFactory();

export const handler = withDurableExecution(async (event, context) => {
  if (event.scenario === "success") {
    return context.step("otel-success", async () => "success");
  }
  if (event.scenario === "wait-resume") {
    const before = await context.step("otel-before-wait", async () => {
      context.logger.info("BEFORE_WAIT_BODY: runs only when the step executes");
      return "before";
    });
    await context.wait("otel-wait", { seconds: 5 });
    return context.step("otel-after-resume", async () => `${before}/resumed`);
  }
  throw new Error("scenario must be success or wait-resume");
}, { plugins: [plugin] });
