import example.BugbashHandler;
import java.util.Map;
import software.amazon.lambda.durable.TypeToken;
import software.amazon.lambda.durable.model.ExecutionStatus;
import software.amazon.lambda.durable.testing.LocalDurableTestRunner;

public class JavaReplay {
    public static void main(String[] args) {
        for (String scenario : new String[]{"success", "wait-resume"}) {
            var runner = LocalDurableTestRunner.create(new TypeToken<Map<String, Object>>() {}, new BugbashHandler());
            Map<String, Object> input = Map.of("scenario", scenario);
            var first = runner.run(input);
            if (scenario.equals("wait-resume") && first.getStatus() != ExecutionStatus.PENDING) {
                throw new AssertionError("Wait must suspend the first invocation");
            }
            var result = scenario.equals("success") ? first : runner.runUntilComplete(input);
            String expected = scenario.equals("success") ? "success" : "before/resumed";
            if (!expected.equals(result.getResult(String.class))) {
                throw new AssertionError("Unexpected workflow result");
            }
            System.out.println("PASS " + System.getenv("BUG_BASH_VIEW") + " " + scenario);
        }
    }
}
