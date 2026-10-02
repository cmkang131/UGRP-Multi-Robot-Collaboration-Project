#!/usr/bin/env python3
"""Run a command and stop it when its output directory grows past a write cap (docs/disk_management.md section 5).

    python3 scripts/ugrp_session.py run <name> -- \
        python3 scripts/write_cap_guard.py --watch <run_out_dir> --max-mib 256 -- <command...>

Independent of any runner: the guard measures how much the watched directories GREW since the command started
(allocated bytes, so sparse and cloned files are counted as the disk sees them). When growth exceeds the cap it
sends SIGTERM to the command's process group (SIGKILL after the grace), writes ``write-cap.json`` into the first
watched directory and exits with code 3. A command that stops by itself keeps its own exit code. This is a safety
net for dev/smoke/diagnostic runs; the cap and any exception to it belong in the run's bundle/config and must be
recorded with the run (the guard prints one JSON line with cap, growth and outcome).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

EXIT_CAP = 3
DEFAULT_MAX_MIB = 512.0
POLL_S = 1.0


def allocated_bytes(root: Path) -> int:
    """Sum of allocated bytes (st_blocks * 512) of regular files under root; 0 if it does not exist yet."""
    total = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_blocks * 512
                    except FileNotFoundError:
                        continue
        except (FileNotFoundError, NotADirectoryError):
            continue
    return total


def run(command: list[str], watch: list[Path], max_bytes: int, *, poll_s: float = POLL_S, grace_s: float = 5.0) -> dict:
    baseline = {w: allocated_bytes(w) for w in watch}
    child = subprocess.Popen(command, start_new_session=True)
    growth, exceeded = 0, False
    try:
        while child.poll() is None:
            growth = sum(max(0, allocated_bytes(w) - baseline[w]) for w in watch)
            if growth > max_bytes:
                exceeded = True
                break
            time.sleep(poll_s)
    except BaseException:
        _stop(child, grace_s)
        raise
    if exceeded:
        _stop(child, grace_s)
    growth = sum(max(0, allocated_bytes(w) - baseline[w]) for w in watch)
    return {"schema": "ugrp.write-cap.v1", "command": command, "watch": [str(w) for w in watch],
            "cap_bytes": max_bytes, "growth_bytes": growth, "cap_exceeded": exceeded,
            "child_returncode": child.returncode}


def _stop(child: subprocess.Popen, grace_s: float) -> None:
    for sig, wait in ((signal.SIGTERM, grace_s), (signal.SIGKILL, grace_s)):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            break
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if child.poll() is not None:
                return
            time.sleep(0.05)
    child.wait()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--watch", type=Path, action="append", required=True, help="directory to measure (repeatable)")
    parser.add_argument("--max-mib", type=float, default=DEFAULT_MAX_MIB,
                        help=f"growth cap in MiB (default {DEFAULT_MAX_MIB:g}); there is no unlimited mode")
    parser.add_argument("--poll-s", type=float, default=POLL_S, help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    if args.max_mib <= 0:
        parser.error("--max-mib must be positive")
    result = run(command, args.watch, int(args.max_mib * 2**20), poll_s=args.poll_s)
    print(json.dumps(result), file=sys.stderr)
    if result["cap_exceeded"]:
        receipt = args.watch[0] / "write-cap.json"
        try:
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json.dumps(result, indent=1) + "\n")
        except OSError as exc:
            print(f"could not write {receipt}: {exc}", file=sys.stderr)
        return EXIT_CAP
    rc = result["child_returncode"]
    return 128 - rc if rc < 0 else rc


if __name__ == "__main__":
    sys.exit(main())
