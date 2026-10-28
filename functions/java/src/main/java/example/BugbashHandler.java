package example;

import java.time.Duration;
import java.util.Map;
import software.amazon.lambda.durable.DurableConfig;
import software.amazon.lambda.durable.DurableContext;
import software.amazon.lambda.durable.DurableHandler;
import software.amazon.lambda.durable.TypeToken;
import software.amazon.lambda.durable.otel.ExecutionOtelPlugin;
import software.amazon.lambda.durable.otel.InvocationOtelPlugin;

public final class BugbashHandler extends DurableHandler<Map<String, Object>, String> {
    public BugbashHandler() {
        super(new TypeToken<Map<String, Object>>() {});
    }

    @Override
    protected DurableConfig createConfiguration() {
        return DurableConfig.builder().withPlugins(
            "execution".equals(System.getenv("BUG_BASH_VIEW"))
                ? ExecutionOtelPlugin.factory()
                : InvocationOtelPlugin.factory()
        ).build();
    }

    @Override
    public String handleRequest(Map<String, Object> event, DurableContext context) {
        if ("success".equals(event.get("scenario"))) {
            return context.step("otel-success", String.class, step -> "success");
        }
        if ("wait-resume".equals(event.get("scenario"))) {
            String before = context.step("otel-before-wait", String.class, step -> {
                step.getLogger().info("BEFORE_WAIT_BODY: runs only when the step executes");
                return "before";
            });
            context.wait("otel-wait", Duration.ofSeconds(5));
            return context.step("otel-after-resume", String.class, step -> before + "/resumed");
        }
        throw new IllegalArgumentException("scenario must be success or wait-resume");
    }
}
