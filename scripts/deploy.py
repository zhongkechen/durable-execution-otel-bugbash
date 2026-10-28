#!/usr/bin/env python3
"""Deploy the two views for one built language to your AWS account."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ADOT = json.loads((ROOT / "adot-layers.json").read_text())


def validate_layer(arn, region):
    parts = arn.split(":")
    if (len(parts) != 8 or parts[0] != "arn" or parts[2] != "lambda"
            or parts[3] != region or parts[5] != "layer" or not parts[7].isdigit()):
        raise ValueError("--layer must be a versioned Lambda layer ARN in --region")


def resolve_layer(language, region, override=None):
    arn = override or ADOT["languages"][language]["layers"].get(region)
    if not arn:
        raise ValueError(
            f"No pinned ADOT {language} layer for {region}; supply --layer with a compatible versioned ARN"
        )
    validate_layer(arn, region)
    return arn


def create_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("language", choices=["js", "python", "java"])
    parser.add_argument("--stack", required=True)
    parser.add_argument("--region", default=ADOT["default_region"],
                        help=f"AWS deployment region (default: {ADOT['default_region']})")
    parser.add_argument("--layer", help="Override the pinned ADOT layer ARN for the selected language and region")
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()
    try:
        layer = resolve_layer(args.language, args.region, args.layer)
    except ValueError as error:
        parser.error(str(error))
    template = ROOT / ".build" / args.language / "template.json"
    if not template.exists():
        parser.error(f"Build first: python3 scripts/build.py {args.language}")
    pinned = json.loads((ROOT / "sdk-lock.json").read_text())[args.language]["commit"]
    built = json.loads(template.read_text())["Globals"]["Function"]["Environment"]["Variables"]["BUG_BASH_SDK_COMMIT"]
    if pinned != built:
        parser.error("SDK pin changed since the last build; rebuild before deploying")
    print(f"Region: {args.region}\nADOT layer: {layer}", flush=True)
    subprocess.run(["aws", "sts", "get-caller-identity", "--region", args.region], check=True)
    subprocess.run([
        "sam", "deploy", "--template-file", str(template), "--stack-name", args.stack,
        "--region", args.region, "--resolve-s3", "--capabilities", "CAPABILITY_IAM",
        "--parameter-overrides", f"AdotLayerArn={layer}",
        "--no-fail-on-empty-changeset",
    ], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
