# Local handler replay checks

These exercise the real SDK local runners, including suspension/resume. They do
not assert export through ADOT. Run after building the corresponding language.
Testing dependencies stay in `.build/` and are not deployed.

## JavaScript

```bash
npm run build --prefix .build/sdks/js -w @aws/durable-execution-sdk-js-testing
node tests/replay/js.mjs
```

## Python

Use Python 3.13 for this local test environment:

```bash
python3.13 -m venv .build/python-local
.build/python-local/bin/python -m pip install \
  .build/sdks/python/packages/aws-durable-execution-sdk-python \
  '.build/sdks/python/packages/aws-durable-execution-sdk-python-otel[standalone]' \
  .build/sdks/python/packages/aws-durable-execution-sdk-python-testing
.build/python-local/bin/python tests/replay/python.py
```

The standalone extra here supplies OTel imports for the **local test process**.
The deployed function still gets its OTel libraries from ADOT.

## Java

With JDK 21 selected:

```bash
JAVA_TEST_JAR=$(find .build/sdks/java/sdk-testing/target -maxdepth 1 \
  -name 'aws-durable-execution-sdk-java-testing-*.jar' \
  ! -name '*-sources.jar' ! -name '*-javadoc.jar')
javac -cp ".build/java/function/lib/*:$JAVA_TEST_JAR" \
  -d .build tests/replay/JavaReplay.java
BUG_BASH_VIEW=execution java -cp ".build:.build/java/function/lib/*:$JAVA_TEST_JAR" JavaReplay
BUG_BASH_VIEW=invocation java -cp ".build:.build/java/function/lib/*:$JAVA_TEST_JAR" JavaReplay
```

The no-provider diagnostics are expected in these local runs. Use the cloud smoke
and trace checks in the root README to validate the actual instrumentation path.
