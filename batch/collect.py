#!/usr/bin/env python3
"""Collect finished runs (state.json says done) from the VMs into results/ in a form compare.py / causes.py read directly.

  collect.py [--dir D] [--results results] [--groups mainA,order] [--full]

Layout written (all under --results):
  <run_id>/                team.json, out-rK/summary.json, log-<name>.txt, exit-<name>.json, brain/{brain-record.json,llm-calls.jsonl}, meta.json
  compare/<group>/<alias>/ symlinks to the files above; one runs folder per group (compare.py pools by scene x structure only)
  brain/<alias>/           symlinks to brain-record.json / llm-calls.jsonl  (the --brain root)
  index.csv                one row per run
<alias> = t<team digit>-<scene token>-<run_id>, because compare.py reads structure/scene from the folder name (t[012]-<scene>-...).
rsync goes over ssh to the VM; with FAKE_LAUNCH=1 it copies from FAKE_VM_ROOT instead.
"""
import argparse
import csv
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dispatch  # noqa: E402

HERE = Path(__file__).resolve().parent
INDEX = ["run_id", "group", "scene_id", "team", "rep", "status", "attempts", "name", "vm", "alias", "collected", "team_status", "vm_exit_code",
         "summaries", "llm_calls", "cost_usd", "warnings"]


def alias_for(row):
    return "t%s-%s-%s" % (row["team"][1], re.sub(r"[^A-Za-z0-9_]", "_", row["scene_id"]), row["run_id"])


def rsync(cfg, vm, subpath, dest, filters):
    host = cfg.host(vm)
    if host is None:
        return 255
    root = (str(cfg.fake_root / host) + cfg.outroot) if cfg.fake else "%s%s:%s" % (cfg.user + "@" if cfg.user else "", host, cfg.outroot)
    cmd = ["rsync", "-a", "--prune-empty-dirs"]
    if not cfg.fake:
        cmd += ["-e", "ssh %s-o BatchMode=yes -o ConnectTimeout=15" % ("-i %s " % cfg.key if cfg.key else "")]
    return subprocess.run(cmd + filters + ["%s/%s" % (root, subpath), str(dest) + "/"], capture_output=True, text=True).returncode


def link(target, where):
    where.parent.mkdir(parents=True, exist_ok=True)
    if where.is_symlink() or where.exists():
        where.unlink()
    where.symlink_to(os.path.relpath(target, where.parent))


def read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def collect_one(cfg, results, row, rec, full):
    run_id, name, vm = row["run_id"], rec["name"], rec["vm"]
    dest = results / run_id
    dest.mkdir(parents=True, exist_ok=True)
    warnings = []
    filters = [] if full else ["--include=team.json", "--include=out-*/", "--include=out-*/summary.json", "--exclude=*"]
    if rsync(cfg, vm, name + "/", dest, filters):
        warnings.append("rsync of run folder failed")
    if rsync(cfg, vm, "", dest, ["--include=log-%s.txt" % name, "--include=exit-%s.json" % name, "--exclude=*"]):
        warnings.append("rsync of log/exit failed")
    (dest / "brain").mkdir(exist_ok=True)
    for fname in ("brain-record.json", "llm-calls.jsonl"):
        src = cfg.evidence / name / fname
        if src.exists():
            shutil.copy2(src, dest / "brain" / fname)
        elif not dispatch.no_brain(row["vm_args"]):  # reference-plan (--fixed) runs have no planner server, so no record
            warnings.append("server record missing: " + fname)
    team = read(dest / "team.json")
    if not isinstance(team, dict):
        warnings.append("team.json missing/invalid")
        team = {}
    elif team.get("status") != "complete":
        warnings.append("team status %s" % team.get("status"))
    robots = row["robots"].split(",")
    present = [r for r in robots if (dest / ("out-" + r) / "summary.json").exists()]
    if len(present) != len(robots):
        warnings.append("summary missing for %s" % sorted(set(robots) - set(present)))
    exit_json = read(dest / ("exit-%s.json" % name)) or {}
    if exit_json.get("exit_code") not in (None, 0):
        warnings.append("VM exit_code %s" % exit_json.get("exit_code"))
    brain = read(dest / "brain" / "brain-record.json") or {}
    (dest / "meta.json").write_text(json.dumps(dict(row, source_name=name, vm=vm, collected=dispatch.stamp()), ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    return dict(run_id=run_id, group=row["group"], scene_id=row["scene_id"], team=row["team"], rep=row["rep"], status="done",
                attempts=len(rec.get("history", [])), name=name, vm=vm,
                alias=alias_for(row), collected=dispatch.stamp(), team_status=team.get("status"), vm_exit_code=exit_json.get("exit_code"),
                summaries="%d/%d" % (len(present), len(robots)), llm_calls=brain.get("calls"), cost_usd=brain.get("cost_usd"),
                warnings="; ".join(warnings))


def build_views(results, row, alias):
    dest = results / row["run_id"]
    view = results / "compare" / row["group"] / alias
    if view.exists():
        shutil.rmtree(view)  # holds only symlinks created here
    for item in ("team.json",) + tuple("out-" + r for r in row["robots"].split(",")):
        if (dest / item).exists():
            link(dest / item, view / item)
    view.mkdir(parents=True, exist_ok=True)
    bview = results / "brain" / alias
    if bview.exists():
        shutil.rmtree(bview)
    for fname in ("brain-record.json", "llm-calls.jsonl"):
        if (dest / "brain" / fname).exists():
            link(dest / "brain" / fname, bview / fname)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default=str(HERE), help="dispatcher work dir (state.json)")
    p.add_argument("--results", type=Path, default=HERE / "results")
    p.add_argument("--groups", default="")
    p.add_argument("--full", action="store_true", help="copy whole run folders (rgb frames etc.), not only team/summary")
    a = p.parse_args(argv)
    st = dispatch.read_json(Path(a.dir) / "state.json")
    if not st:
        print("no state.json in %s" % a.dir, file=sys.stderr)
        return 1
    cfg = dispatch.Cfg(a.dir, st.get("outroot"))
    if st.get("evidence"):
        cfg.evidence = Path(st["evidence"])
    rows = {r["run_id"]: r for r in dispatch.load_manifest(st["manifest"])}
    wanted = set(g for g in a.groups.split(",") if g)
    results = a.results.resolve()
    results.mkdir(parents=True, exist_ok=True)
    old = {}
    if (results / "index.csv").exists():  # rows collected earlier stay when --groups narrows this run
        with open(results / "index.csv", encoding="utf-8", newline="") as stream:
            old = {r["run_id"]: r for r in csv.DictReader(stream)}
    out, index = [], []
    for run_id, row in rows.items():
        rec = st["runs"].get(run_id, {"status": "pending", "name": run_id, "history": []})
        if rec["status"] == "done" and (not wanted or row["group"] in wanted):
            entry = collect_one(cfg, results, row, rec, a.full)
            build_views(results, row, entry["alias"])
            out.append(entry)
        elif rec["status"] == "done" and run_id in old and old[run_id].get("status") == "done":
            entry = old[run_id]
        else:  # attempted or waiting runs stay visible, so the analysis sees N planned, not only N done
            entry = dict(run_id=run_id, group=row["group"], scene_id=row["scene_id"], team=row["team"], rep=row["rep"],
                         status=rec["status"], attempts=len(rec.get("history", [])), name=rec["name"], vm=rec.get("vm"),
                         warnings="not collected: " + str(rec.get("reason") or rec["status"]))
        index.append(entry)
    skipped = len(rows) - len(out)
    with open(results / "index.csv", "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=INDEX)
        writer.writeheader()
        writer.writerows(index)
    bad = [e for e in out if e["warnings"]]
    print("collected %d of %d manifest runs (%d not done or outside --groups), %d with warnings -> %s"
          % (len(out), len(rows), skipped, len(bad), results))
    for e in bad:
        print("  %s: %s" % (e["run_id"], e["warnings"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
