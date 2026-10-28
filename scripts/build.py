#!/usr/bin/env python3
"""Build one language from the SDK commits recorded in sdk-lock.json."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".build"
LOCK = json.loads((ROOT / "sdk-lock.json").read_text())


def run(*command, cwd=ROOT, capture=False, env=None):
    print("+", " ".join(str(item) for item in command), flush=True)
    result = subprocess.run(
        [str(item) for item in command], cwd=cwd, check=True,
        text=True, stdout=subprocess.PIPE if capture else None, env=env,
    )
    return result.stdout.strip() if capture else None


def source(language):
    spec = LOCK[language]
    checkout = BUILD / "sdks" / language
    if not (checkout / ".git").exists():
        checkout.mkdir(parents=True, exist_ok=True)
        run("git", "init", checkout)
        run("git", "remote", "add", "origin", spec["repository"], cwd=checkout)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout, text=True,
        capture_output=True,
    )
    if head.stdout.strip() != spec["commit"]:
        run("git", "fetch", "--depth", "1", "origin", spec["commit"], cwd=checkout)
        run("git", "checkout", "--detach", spec["commit"], cwd=checkout)
    return checkout


def build_js(checkout, output):
    if int(run("node", "-p", "process.versions.node.split('.')[0]", capture=True)) < 22:
        raise SystemExit("Node.js 22 or later is required; select it before running the build.")
    run("npm", "ci", cwd=checkout, env={**os.environ, "HUSKY": "0"})
    packages = ["aws-durable-execution-sdk-js", "aws-durable-execution-sdk-js-otel"]
    tarballs = []
    for package in packages:
        run("npm", "run", "build", "-w", "@aws/" + package.removeprefix("aws-"), cwd=checkout)
        packed = json.loads(run("npm", "pack", "--json", "--ignore-scripts", cwd=checkout / "packages" / package, capture=True))
        tarballs.append(checkout / "packages" / package / packed[0]["filename"])
    (output / "package.json").write_text(json.dumps({"name": "durable-otel-bugbash", "private": True}))
    run("npm", "install", "--omit=dev", "--save-exact", *tarballs, cwd=output)
    shutil.copy2(ROOT / "functions/js/index.mjs", output)
    run("node", "--check", output / "index.mjs")
    run("node", "-e", "import('./index.mjs').then(() => console.log('Handler import OK'))", cwd=output)
    return {"Runtime": "nodejs22.x", "Handler": "index.handler", "MemorySize": 512}, {}


def build_python(checkout, output):
    venv = BUILD / "build-venv"
    if not (venv / "bin/python").exists():
        run(sys.executable, "-m", "venv", venv)
    python = venv / "bin/python"
    wheels = BUILD / "wheels"
    wheels.mkdir(exist_ok=True)
    for old in wheels.glob("*.whl"):
        old.unlink()
    run(python, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", wheels,
        checkout / "packages/aws-durable-execution-sdk-python",
        checkout / "packages/aws-durable-execution-sdk-python-otel")
    run(python, "-m", "pip", "install", "--target", output,
        "--platform", "manylinux2014_x86_64", "--implementation", "cp",
        "--python-version", "3.13", "--only-binary=:all:", *sorted(wheels.glob("*.whl")))
    shutil.copy2(ROOT / "functions/python/handler.py", output)
    # The ADOT layer owns the OTel API, SDK, exporter and propagator packages.
    if (output / "opentelemetry").exists():
        raise SystemExit("Unexpected bundled OpenTelemetry packages; check the pinned plugin's dependencies.")
    return {"Runtime": "python3.13", "Handler": "handler.handler", "MemorySize": 512}, {}


def build_java(checkout, output):
    repository = BUILD / "m2"
    maven = ["mvn", "-B", f"-Dmaven.repo.local={repository}"]
    version = run(*maven, "-q", "-Dstyle.color=never", "-Dexpression=project.version",
                  "-DforceStdout", "help:evaluate", cwd=checkout, capture=True)
    # Maven can emit ANSI reset codes even with color disabled.
    import re
    version = re.sub(r"\x1b\[[0-9;]*m", "", version).strip()
    if not re.fullmatch(r"[0-9][A-Za-z0-9_.-]*", version):
        raise SystemExit(f"Could not resolve Java SDK version: {version!r}")
    run(*maven, "--projects", "sdk,otel-plugin", "--also-make", "-DskipTests", "install", cwd=checkout)
    project = BUILD / "java-project"
    shutil.copytree(ROOT / "functions/java", project, dirs_exist_ok=True)
    libraries = output / "lib"
    libraries.mkdir()
    run(*maven, f"-Ddurable.sdk.version={version}", "-DskipTests", "package",
        "dependency:copy-dependencies", "-DincludeScope=runtime",
        f"-DoutputDirectory={libraries}", cwd=project)
    shutil.copy2(project / "target/durable-otel-bugbash-1.0.0.jar", libraries)
    extension = f"aws-durable-execution-sdk-java-plugin-otel-{version}.jar"
    if not (libraries / extension).is_file():
        raise SystemExit("Missing Java agent extension JAR in deployment artifact")
    return {"Runtime": "java21", "Handler": "example.BugbashHandler", "MemorySize": 1024}, {
        "OTEL_JAVAAGENT_EXTENSIONS": f"/var/task/lib/{extension}",
        "JAVA_TOOL_OPTIONS": f"-Dotel.javaagent.extensions=/var/task/lib/{extension}",
    }


def render_template(language, settings, environment):
    template = json.loads((ROOT / "template.json").read_text())
    function = template["Globals"]["Function"]
    function.update(settings)
    function["Environment"]["Variables"].update(environment)
    function["Environment"]["Variables"]["BUG_BASH_SDK_COMMIT"] = LOCK[language]["commit"]
    return template


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("language", choices=["js", "python", "java"])
    language = parser.parse_args().language
    checkout = source(language)
    output = BUILD / language / "function"
    template = output.parent / "template.json"
    # A failed rebuild must not leave a deployable template pointing at partial artifacts.
    template.unlink(missing_ok=True)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    settings, environment = globals()[f"build_{language}"](checkout, output)
    shutil.copy2(ROOT / "sdk-lock.json", output)
    template.write_text(json.dumps(render_template(language, settings, environment), indent=2) + "\n")
    print(f"Built {language} at {LOCK[language]['commit']}\nTemplate: {template}")


if __name__ == "__main__":
    main()
