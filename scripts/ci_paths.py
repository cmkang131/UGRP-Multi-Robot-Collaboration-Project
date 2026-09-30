#!/usr/bin/env python3
"""Select the docs-only CI path conservatively, without third-party actions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]
# Code/config under docs/ is deliberately excluded; unknown suffixes run CI.
DOC_ASSET_SUFFIXES = {".md", ".rst", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def is_documentation(path: str) -> bool:
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    suffix = PurePosixPath(path).suffix
    if len(parts) == 1:
        return suffix == ".md"
    if parts[0] == "docs":
        return suffix in DOC_ASSET_SUFFIXES
    return parts[0] == "experiments" and suffix == ".md"


def requires_full_suite(paths: list[str]) -> bool:
    # Empty/unknown changes must never create a docs-only success by accident.
    return not paths or not all(is_documentation(path) for path in paths)


def changed_paths(root: Path, base: str, head: str) -> list[str]:
    # Disable rename detection to inspect BOTH names of a code -> docs rename.
    # NUL separation preserves spaces/newlines; no API pagination/300-file cap.
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}", "--"],
        cwd=root, check=True, capture_output=True,
    )
    return [os.fsdecode(path) for path in result.stdout.split(b"\0") if path]


def select_full_suite(event: str, base: str, head: str, root: Path = ROOT) -> bool:
    if event != "pull_request" or not base or not head:
        print("CI path: full suite (main push or unavailable PR comparison)")
        return True
    try:
        paths = changed_paths(root, base, head)
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"CI path: full suite (cannot compare revisions: {error})")
        return True
    full = requires_full_suite(paths)
    print(f"CI path: {'full suite' if full else 'docs only'}; changed paths={json.dumps(paths)}")
    return full


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    args = parser.parse_args(argv)
    full = select_full_suite(args.event, args.base, args.head)
    output = f"full_suite={str(full).lower()}\n"
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write(output)
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
