#!/usr/bin/env python3
"""Plan (never execute) raw option B of 2026-09-27: T3 + T4 + non-test T6 of the primary outputs/.

    plan     choose deletion units, apply the exclusions below, write plan-b.json
    receipt  list every file of the deletion units with size and sha256 (jsonl.gz) and a per-unit summary
    execute  FOR THE USER TO RUN: re-list and re-hash each unit, delete it only if its listing hash still
             equals the receipt and nothing in it changed in the last --idle-minutes; append to a log

Exclusions (the unit stays and is listed with its reason):
  test       a test-cohort name (T1) anywhere in the unit path
  model      a checkpoint (safetensors/pt/pth/ckpt/onnx/joblib/pkl) whose sha256 is not a file of an
             `available` artifact in configs/model_artifacts.json (AGENTS.md model preservation)
  code_ref   code or config (py/sh/yaml/toml/configs json/experiments py) on origin/main or an open PR
             names the unit as an input path
  open_pr    a file an open PR adds or changes (vs origin/main) names the unit
  active     a file modified in the last --idle-minutes, or a file open in any process
  archive    an archive-tier folder (may be a unique copy)
plan and receipt delete nothing. execute is irreversible and needs --i-confirm-permanent-deletion.
"""

from __future__ import annotations

import argparse
import collections
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.disk_report import tier_of  # noqa: E402
from scripts.tree_manifest import file_sha256  # noqa: E402

PRIMARY = Path("/Users/changmin/projects/ugrp")
OUTPUTS = PRIMARY / "outputs"
T4 = re.compile(r"^(simulation-realtime|simulation-performance|sim-speed)")
T7 = re.compile(r"^(zone|owncam|m1-|m2-|plan-|dynamic-|map-goto|beam-|vision-|study)")
T0 = re.compile(r"^(tensorboard|agent-locks|storage-cleanup|disk-|worktree-cleanup|models$|dispatch-models|model-release)")
MODEL_SUFFIXES = (".safetensors", ".pt", ".pth", ".ckpt", ".onnx", ".joblib", ".pkl")
CODE_GLOBS = ["*.py", "*.sh", "*.command", "*.yaml", "*.yml", "*.toml", "configs/*.json", "configs/**/*.json"]
REF_RE = r"outputs/[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)?"
SELF_PR = "#239"  # this record's own PR mentions every folder it plans; not a dependency
# Names inside retired worktrees that also exist as shared primary folders; a reference to them means the
# primary folder, not the retired copy.
GENERIC = {"simulation-runs", "models", "dispatch-models", "real_traces", "sim_traces", "tensorboard", "rl",
           "retired-worktrees", "archive"}


def line_tier(top: str) -> str:
    if top == "retired-worktrees":
        return "T3"
    if top == "experiment-archives-20260907":
        return "T5"
    if T0.match(top) or tier_of(top) == "infrastructure":
        return "T0"
    if T4.match(top):
        return "T4"
    date = re.search(r"(2026\d{4})", top)
    if T7.match(top) and (not date or date.group(1) >= "20260924"):
        return "T7"
    return "T6"


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(PRIMARY), *args], capture_output=True, text=True).stdout


def refs_in(ref: str, paths: list[str]) -> set[str]:
    out = git("grep", "-h", "-o", "-I", "-E", REF_RE, ref, "--", *paths)
    found = set()
    for hit in out.splitlines():
        parts = hit.split("outputs/", 1)[-1].split("/")
        found.add(parts[0])
        if len(parts) > 1:
            found.add("/".join(parts[:2]))
    return found


def open_pr_refs() -> tuple[set[str], dict[str, list[str]]]:
    prs = json.loads(subprocess.run(["gh", "pr", "list", "--state", "open", "--limit", "100", "--json",
                                     "number,headRefName"], cwd=PRIMARY, capture_output=True, text=True).stdout)
    code, changed = set(), collections.defaultdict(list)
    for pr in prs:
        ref = f"origin/{pr['headRefName']}"
        code |= refs_in(ref, CODE_GLOBS)
        files = git("diff", "--name-only", f"origin/main...{ref}").split()
        if files:
            for name in refs_in(ref, files):
                changed[name].append(f"#{pr['number']}")
    return code, changed


def units() -> list[tuple[str, str]]:
    out = []
    for top in sorted(os.listdir(OUTPUTS)):
        path = OUTPUTS / top
        if path.is_symlink() or not path.is_dir():
            continue
        tier = line_tier(top)
        if tier == "T3":
            out += [(f"{top}/{c}", "T3") for c in sorted(os.listdir(path)) if (path / c).is_dir()]
        elif tier in ("T4", "T6"):
            children = sorted(os.listdir(path))
            if tier_of(top) == "test-cohort" or any(tier_of(c) == "test-cohort" for c in children):
                out += [(f"{top}/{c}", tier) for c in children]
            else:
                out.append((top, tier))
    return out


def released_sha() -> set[str]:
    data = json.loads(git("show", "origin/main:configs/model_artifacts.json"))
    return {f["sha256"] for a in data["artifacts"] if a.get("status") == "available" for f in a.get("files", [])}


def open_files() -> set[str]:
    out = subprocess.run(["lsof", "-n", "-P", "-w", "-F", "n"], capture_output=True, text=True).stdout
    return {line[1:] for line in out.splitlines() if line.startswith("n" + str(OUTPUTS) + "/")}


def cmd_plan(args: argparse.Namespace) -> int:
    main_code = refs_in("origin/main", CODE_GLOBS + ["experiments/**/*.py"])
    pr_code, pr_changed = open_pr_refs()
    code = main_code | pr_code
    released = released_sha()
    opened = open_files()
    cutoff = time.time() - args.idle_minutes * 60
    rows = []
    for rel, tier in units():
        top = rel.split("/")[0]
        path = OUTPUTS / rel
        reasons, models, files, size, newest = [], [], 0, 0, 0.0
        if any(tier_of(p) == "test-cohort" for p in rel.split("/")):
            reasons.append("test")
        if tier_of(top) == "archive":
            reasons.append("archive")
        keys = {rel, top} if tier != "T3" else {rel}
        hit = sorted(k for k in keys if k in code)
        if hit:
            reasons.append("code_ref:" + ",".join(hit))
        if tier == "T3":  # retired worktree folders hold <label>/outputs/<name>; open PRs may cite those names
            for dirpath, dirs, _ in os.walk(path):
                if Path(dirpath).name == "outputs":
                    keys |= set(dirs) - GENERIC
                    dirs[:] = []
        prs = sorted({p for k in keys for p in pr_changed.get(k, []) if p != SELF_PR})
        if prs:
            reasons.append("open_pr:" + ",".join(prs))
        is_file = path.is_file()
        walk = [(str(path.parent), [], [path.name])] if is_file else os.walk(path)
        for dirpath, _dirs, names in walk:
            for name in names:
                full = os.path.join(dirpath, name)
                st = os.lstat(full)
                files += 1
                size += st.st_blocks * 512
                newest = max(newest, st.st_mtime)
                if full in opened:
                    reasons.append("active:open_file")
                if name.lower().endswith(MODEL_SUFFIXES) and not os.path.islink(full):
                    digest = file_sha256(Path(full))
                    if digest not in released:
                        models.append({"path": os.path.relpath(full, OUTPUTS), "bytes": st.st_size, "sha256": digest})
        if newest > cutoff:
            reasons.append("active:recent")
        if models:
            reasons.append(f"model:{len(models)}")
        rows.append({"unit": rel, "tier": tier, "files": files, "bytes": size, "exclude": sorted(set(reasons)),
                     "unreleased_models": models})
    keep = [r for r in rows if r["exclude"]]
    delete = [r for r in rows if not r["exclude"]]
    summary = {"planned_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "idle_minutes": args.idle_minutes,
               "units": len(rows), "delete_units": len(delete), "delete_files": sum(r["files"] for r in delete),
               "delete_gib": round(sum(r["bytes"] for r in delete) / 2**30, 2),
               "excluded_units": len(keep), "excluded_gib": round(sum(r["bytes"] for r in keep) / 2**30, 2),
               "by_tier_delete_gib": {t: round(sum(r["bytes"] for r in delete if r["tier"] == t) / 2**30, 2)
                                      for t in ("T3", "T4", "T6")}}
    args.out.write_text(json.dumps({"summary": summary, "delete": delete, "excluded": keep}, indent=1,
                                   ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


def hash_row(full: str) -> dict:
    st = os.lstat(full)
    row = {"path": os.path.relpath(full, OUTPUTS), "bytes": st.st_size, "mtime_ns": st.st_mtime_ns}
    if os.path.islink(full):
        row["symlink"] = os.readlink(full)
    else:
        row["sha256"] = file_sha256(Path(full))
    return row


def cmd_receipt(args: argparse.Namespace) -> int:
    plan = json.loads(args.plan.read_text())
    if args.receipt.exists():
        raise SystemExit(f"refusing to overwrite {args.receipt}")
    per_unit = []
    with gzip.open(args.receipt, "wt", encoding="utf-8") as out, ThreadPoolExecutor(args.workers) as pool:
        for unit in plan["delete"]:
            path = OUTPUTS / unit["unit"]
            fulls = [str(path)] if path.is_file() else sorted(
                os.path.join(d, n) for d, _, names in os.walk(path) for n in names)
            unit_hash = hashlib.sha256()
            count = size = 0
            for row in pool.map(hash_row, fulls, chunksize=64):
                line = json.dumps(row, ensure_ascii=False, sort_keys=True)
                out.write(line + "\n")
                unit_hash.update((line + "\n").encode())
                count += 1
                size += row["bytes"]
            per_unit.append({"unit": unit["unit"], "tier": unit["tier"], "files": count,
                             "gib": round(size / 2**30, 3), "listing_sha256": unit_hash.hexdigest()})
    summary = {"receipt": str(args.receipt), "receipt_sha256": file_sha256(args.receipt),
               "files": sum(u["files"] for u in per_unit), "gib": round(sum(u["gib"] for u in per_unit), 2),
               "units": per_unit}
    args.summary.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: summary[k] for k in ("receipt_sha256", "files", "gib")}))
    return 0


def cmd_execute(args: argparse.Namespace) -> int:
    import shutil
    if not args.i_confirm_permanent_deletion:
        raise SystemExit("refusing: pass --i-confirm-permanent-deletion (irreversible)")
    summary = json.loads(args.summary.read_text())
    if file_sha256(Path(summary["receipt"])) != summary["receipt_sha256"]:
        raise SystemExit("receipt hash changed; re-run plan and receipt")
    cutoff = time.time() - args.idle_minutes * 60
    with open(args.log, "a", encoding="utf-8") as log, ThreadPoolExecutor(args.workers) as pool:
        for unit in summary["units"]:
            path = OUTPUTS / unit["unit"]
            if not (path.exists() or path.is_symlink()):
                log.write(json.dumps({"unit": unit["unit"], "status": "missing"}) + "\n")
                continue
            fulls = [str(path)] if path.is_file() else sorted(
                os.path.join(d, n) for d, _, names in os.walk(path) for n in names)
            unit_hash = hashlib.sha256()
            recent = False
            for row in pool.map(hash_row, fulls, chunksize=64):
                unit_hash.update((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode())
                recent |= row["mtime_ns"] / 1e9 > cutoff
            if recent or unit_hash.hexdigest() != unit["listing_sha256"]:
                log.write(json.dumps({"unit": unit["unit"], "status": "skipped_changed", "recent": recent}) + "\n")
                continue
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
            log.write(json.dumps({"unit": unit["unit"], "status": "deleted", "files": unit["files"],
                                  "gib": unit["gib"], "listing_sha256": unit["listing_sha256"],
                                  "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n")
            log.flush()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--out", type=Path, required=True)
    plan.add_argument("--idle-minutes", type=float, default=120)
    receipt = sub.add_parser("receipt")
    receipt.add_argument("--plan", type=Path, required=True)
    receipt.add_argument("--receipt", type=Path, required=True)
    receipt.add_argument("--summary", type=Path, required=True)
    receipt.add_argument("--workers", type=int, default=3)
    execute = sub.add_parser("execute")
    execute.add_argument("--summary", type=Path, required=True)
    execute.add_argument("--log", type=Path, required=True)
    execute.add_argument("--idle-minutes", type=float, default=60)
    execute.add_argument("--workers", type=int, default=4)
    execute.add_argument("--i-confirm-permanent-deletion", action="store_true")
    args = parser.parse_args()
    return {"plan": cmd_plan, "receipt": cmd_receipt, "execute": cmd_execute}[args.action](args)


if __name__ == "__main__":
    raise SystemExit(main())
