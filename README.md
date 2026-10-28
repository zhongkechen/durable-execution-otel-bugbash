# Durable Execution OpenTelemetry starter

Deploy a small AWS Lambda Durable Execution workflow in JavaScript, Python, or
Java and inspect its OpenTelemetry traces. Each deployment creates two functions:
one using the **Execution view**, and one using the **Invocation view**. Both use
an ADOT Lambda layer to export to CloudWatch Traces / X-Ray.

This is an independent test starter, not an official AWS SDK release. The core
SDK and OTel plugin are built together from the public commits in
[`sdk-lock.json`](sdk-lock.json), captured from `main` on October 28, 2026.
Package version strings alone may not identify an unreleased main-branch build.

| Language | Pinned source | Runtime / architecture |
| --- | --- | --- |
| JS | [`6d024cbe7ee6`](https://github.com/aws/aws-durable-execution-sdk-js/commit/6d024cbe7ee6a95e8d814eb8a58d5c5bb41d67ab) | Node.js 22 / x86_64 |
| Python | [`4625d01bbfa9`](https://github.com/aws/aws-durable-execution-sdk-python/commit/4625d01bbfa97da67050014851af7eb41c61a842) | Python 3.13 / x86_64 |
| Java | [`64339d4f0e07`](https://github.com/aws/aws-durable-execution-sdk-java/commit/64339d4f0e071cd841bdaf43c95a35324a3132bb) | Java 21 / x86_64 |

## Before starting

1. Install Git, Python 3.11+, a recent AWS CLI v2 with durable-execution commands,
   and a recent AWS SAM CLI supporting `DurableConfig`. Also install your chosen
   language's build tools: Node.js 22+ and npm for JS; JDK 21 and Maven for Java.
2. Select AWS credentials. Deployment and smoke tests default to **us-west-2**;
   use `--region` to choose another region where Lambda Durable Execution is
   available. Run `aws sts get-caller-identity` to confirm the account. Deployment
   uses CloudFormation, SAM-managed artifact storage, Lambda, and IAM; your
   identity needs deployment and role-creation/pass-role permissions.
3. The deploy script automatically selects a **versioned ADOT layer ARN** for
   your language and region from [`adot-layers.json`](adot-layers.json). These are
   the latest stable release ARNs checked on October 28, 2026, with support for
   the runtimes above and **x86_64**. Use `--layer` to override the default with a
   compatible versioned ARN in your selected region.
4. Choose a unique stack name, such as `youralias-otel-js`. Deployment creates
   billable resources in your account. The functions use IAM-authorized Lambda
   invocation and have no HTTP endpoint.
5. Clone this repository:

   ```bash
   git clone https://github.com/zhongkechen/durable-execution-otel-bugbash.git
   cd durable-execution-otel-bugbash
   ```

Only build the language you are testing. The first build fetches SDK source and
dependencies into ignored `.build/` directories. Build tools do not need AWS
credentials. SDK source commits are pinned; transitive dependencies follow the
SDK's lockfiles and package constraints and are not all independently frozen.

## Region and ADOT defaults

Both `deploy.py` and `smoke.py` default to **us-west-2**, independent of the AWS
CLI's configured region. The default layer comes from the selected language and
region; changing `--region` also selects that region's published layer version.

| Language | Latest stable ADOT release checked on October 28 | Default ARN in us-west-2 |
| --- | --- | --- |
| JS | [v0.13.0](https://github.com/aws-observability/aws-otel-js-instrumentation/releases/tag/v0.13.0) | `arn:aws:lambda:us-west-2:615299751070:layer:AWSOpenTelemetryDistroJs:16` |
| Python | [v0.21.0](https://github.com/aws-observability/aws-otel-python-instrumentation/releases/tag/v0.21.0) | `arn:aws:lambda:us-west-2:615299751070:layer:AWSOpenTelemetryDistroPython:36` |
| Java | [v2.32.0](https://github.com/aws-observability/aws-otel-java-instrumentation/releases/tag/v2.32.0) | `arn:aws:lambda:us-west-2:615299751070:layer:AWSOpenTelemetryDistroJava:19` |

The checked-in tables preserve the exact accounts and versions for all 35 regions
listed by each release. They stay pinned until deliberately updated; deployment
does not fetch a moving latest release. A listed ADOT layer does not establish
Durable Execution availability in that region. An unlisted region requires an
explicit `--layer`.

Override just the region to use its default layer:

```bash
python3 scripts/deploy.py python --stack youralias-otel-python --region us-east-1
python3 scripts/smoke.py --stack youralias-otel-python --region us-east-1
```

Or override both values (replace the ARN placeholder):

```bash
python3 scripts/deploy.py python --stack youralias-otel-python \
  --region us-east-1 --layer '<custom-versioned-layer-arn-in-us-east-1>'
```

`--layer` can also be used alone to override the layer in the default `us-west-2`
region. The deploy script prints the chosen region and ARN before deployment and
rejects an ARN from a different region.

## JavaScript

1. Confirm `node --version` reports 22 or later. Inspect
   [`functions/js/index.mjs`](functions/js/index.mjs) for the handler.
2. Build the pinned core and OTel packages, install their tarballs into the Lambda
   artifact, and check that the handler imports:

   ```bash
   python3 scripts/build.py js
   ```

   The artifact contains `index.mjs` and `node_modules`; the Lambda handler is
   `index.handler`. The template uses `nodejs22.x`.
3. Deploy with the default region and pinned ADOT JS layer:

   ```bash
   python3 scripts/deploy.py js --stack youralias-otel-js
   ```

4. Run both scenarios in both tracing views:

   ```bash
   python3 scripts/smoke.py --stack youralias-otel-js
   ```

5. Continue to [Verify the traces](#verify-the-traces). To edit the handler, change
   `functions/js/index.mjs`, then rerun build and deploy.

## Python

1. Inspect [`functions/python/handler.py`](functions/python/handler.py).
2. Build the pinned core and base OTel plugin wheels and package their runtime
   dependencies for Lambda Python 3.13 / Linux x86_64:

   ```bash
   python3 scripts/build.py python
   ```

   The artifact contains `handler.py` and installed dependencies at its root;
   the Lambda handler is `handler.handler`. The builder deliberately omits the
   plugin's `[standalone]` extra: the ADOT layer supplies the OTel API, SDK,
   exporter, and propagator. This avoids shadowing the layer's aligned packages.
   The core's required boto3/botocore versions are packaged with the function.
3. Deploy with the default region and pinned ADOT Python layer:

   ```bash
   python3 scripts/deploy.py python --stack youralias-otel-python
   ```

4. Run both scenarios in both views:

   ```bash
   python3 scripts/smoke.py --stack youralias-otel-python
   ```

5. Continue to [Verify the traces](#verify-the-traces). Change the source handler
   and rebuild/redeploy for additional tests.

## Java

1. Confirm both `java -version` and `mvn -version` select **JDK 21**. Set
   `JAVA_HOME` to your JDK 21 installation if needed. Inspect
   [`BugbashHandler.java`](functions/java/src/main/java/example/BugbashHandler.java).
2. Build the pinned SDK and OTel plugin into an isolated Maven repository, then
   compile the handler and copy runtime dependencies into the Lambda artifact:

   ```bash
   python3 scripts/build.py java
   ```

   The Lambda handler is `example.BugbashHandler`; the runtime is `java21`.
   The artifact's `lib/` directory contains the handler JAR, core SDK, plugin,
   and runtime dependencies. Log4j2 writes JSON logs with the plugin's MDC fields.
   The builder resolves the SDK version from the
   pinned POM instead of assuming a Maven Central release exists.
3. The generated template sets `OTEL_JAVAAGENT_EXTENSIONS` to the **actual plugin
   JAR under `/var/task/lib/`** and sets the same agent extension system property
   in `JAVA_TOOL_OPTIONS`. This lets the ADOT agent install the plugin's ID and
   sampling customizers. The application registers the selected view explicitly.
   Installing the agent alone is insufficient.
4. Deploy with the default region and pinned ADOT Java layer. For a custom layer,
   check its OTel API/agent compatibility against the pinned
   [plugin README](https://github.com/aws/aws-durable-execution-sdk-java/blob/64339d4f0e071cd841bdaf43c95a35324a3132bb/otel-plugin/README.md).

   ```bash
   python3 scripts/deploy.py java --stack youralias-otel-java
   ```

5. Run both scenarios in both views:

   ```bash
   python3 scripts/smoke.py --stack youralias-otel-java
   ```

6. Continue to the trace checks below. If Lambda/platform traces appear without
   durable spans, first check the extension JAR path and agent compatibility.

## What deployment configures

The shared [`template.json`](template.json) is rendered into
`.build/<language>/template.json` by the builder. Deploy **that generated file**;
`deploy.py` chooses it automatically. A separate stack per language lets testers
rebuild and remove their own resources independently.

- Two functions with `BUG_BASH_VIEW=execution` or `invocation` and distinct
  `OTEL_SERVICE_NAME` values: `<stack>-execution` and `<stack>-invocation`.
- One explicit OTel factory registration in each handler. **Do not also set
  `DURABLE_EXECUTION_PLUGINS`** on these examples: that would register a second
  view. `BUG_BASH_VIEW` is this sample's selector, not an SDK setting.
- The default or overridden ADOT layer, `AWS_LAMBDA_EXEC_WRAPPER=/opt/otel-instrument`,
  `OTEL_TRACES_EXPORTER=otlp`, `OTEL_PROPAGATORS=xray`, and Active tracing. The
  selected layer supplies the provider and export pipeline.
- JSON logging, a 60-second invocation timeout, a 300-second durable execution
  timeout, and one day of durable execution retention.
- SAM-generated roles with `AWSLambdaBasicDurableExecutionRolePolicy` and
  `AWSXRayDaemonWriteAccess`. The deployer needs `CAPABILITY_IAM` acknowledgement;
  the deploy command supplies it.
- `BUG_BASH_SDK_COMMIT` and a packaged copy of `sdk-lock.json` for provenance.

Use the template to make configuration changes so a later deployment does not
overwrite console edits. Preserve existing environment values and attached
layers when manually experimenting.

## Verify the traces

The smoke script performs four **functional** checks. It invokes `:$LATEST`
asynchronously, waits for a terminal status, verifies the serialized result, and
saves configuration, execution ARN, execution details, and history under
`results/<stack>/<run>/`. An accepted invocation is not treated as completion.
It does not query or assert the trace backend.

| Input | Expected result | What to inspect |
| --- | --- | --- |
| `{"scenario":"success"}` | `"success"` | Workflow, Invocation, `otel-success`, and its attempt |
| `{"scenario":"wait-resume"}` | `"before/resumed"` | `otel-before-wait`, `otel-wait`, and `otel-after-resume`; resumed invocation stays on the execution trace |

1. Open **CloudWatch → Traces** in the deployment region. Find the service name
   and execution ARN from the saved evidence. Use **Group by nodes** when the
   ungrouped X-Ray timeline obscures the hierarchy.
2. Confirm the run was sampled. An explicit upstream `Sampled=0` takes precedence
   over local sampler settings. Rerun with a fresh execution if needed and allow
   time for backend indexing; absent spans in an unsampled run are not a failure.
3. In Execution view, durable operations belong to Workflow (or their durable
   parent context); in Invocation view, their segments belong to the invocation
   that ran them. Both views include Workflow and Invocation spans.
4. For wait/resume, compare invocation request IDs, execution history, and logs.
   The `BEFORE_WAIT_BODY` log should appear once in an ordinary uninterrupted
   test run: the completed step's body is skipped on replay, while its saved
   `"before"` value is reused to produce `"before/resumed"`. An interrupted
   uncheckpointed attempt can run again; this is not an exactly-once guarantee.
5. Record runtime, SDK commit, layer ARN, service name, execution ARN, trace ID,
   invocation request IDs, expected/actual behavior, and links with each finding.
   Review evidence before sharing; it contains your account/resource identifiers.

For retries, callbacks, child contexts, parallel work, propagation, and failures,
start from the SDK-owned conformance handlers linked from each pinned SDK tree.
Keep operation names static, put side effects in steps, use durable waits, and
return values from steps instead of mutating captured orchestration state.

## Local validation

```bash
python3 -m unittest discover -s tests -v
sam validate --lint --template-file .build/js/template.json
sam validate --lint --template-file .build/python/template.json
sam validate --lint --template-file .build/java/template.json
```

Validate only the templates you have built. Local build/template checks do not
establish that a particular ADOT layer exports successfully in your account;
complete the cloud smoke and trace checks before recording a pass.
For success and suspension/resume checks using the real SDK local runners, see
[`tests/replay/README.md`](tests/replay/README.md).

## Cleanup

Wait for executions to finish, save your evidence, and delete each test stack.
Use the same region you deployed to (the default is `us-west-2`):

```bash
sam delete --stack-name youralias-otel-js --region us-west-2
sam delete --stack-name youralias-otel-python --region us-west-2
sam delete --stack-name youralias-otel-java --region us-west-2
```

Inspect any retained CloudWatch log groups and SAM-managed artifact storage in
your account separately. Local build caches and evidence are ignored by Git.

## License

Apache-2.0. The SDKs and dependencies retain their own licenses; their source and
build artifacts are downloaded locally and are not vendored into this repository.
