#!/usr/bin/env python3
"""Fake run for tests (called by launch_team_run_v3.sh when FAKE_LAUNCH=1). No ssh, no LLM, no simulation.

Writes a fake VM result folder under $FAKE_VM_ROOT/$VMHOST$OUTROOT/<name>/ and fake planner records under $EVIDENCE_DIR/<name>/.
Env switches (comma separated run_ids; they affect the first attempt only, i.e. names without -retryN, unless ALWAYS):
  FAKE_SLEEP=<sec>          run time (default 3)
  FAKE_FAIL_ONCE=<ids>      exit 1, no summary files on the first attempt
  FAKE_INCOMPLETE=<ids>     exit 0 but out-r2/summary.json missing on the first attempt
  FAKE_FAIL_ALWAYS=<ids>    every attempt exits 1
Start/end events go to $FAKE_VM_ROOT/events.log (tab separated: time, start|end, name, host, rc).
"""
import json
import os
import re
import sys
import time
from pathlib import Path


def ids(var):
    return {x for x in os.environ.get(var, "").split(",") if x}


def event(root, kind, name, host, rc=""):
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "events.log", "a", encoding="utf-8") as stream:
        stream.write("%.3f\t%s\t%s\t%s\t%s\n" % (time.time(), kind, name, host, rc))


def main():
    sha, team, seed, name, port = sys.argv[1:6]
    rest = sys.argv[6:]
    scene = rest[rest.index("--scene-id") + 1] if "--scene-id" in rest else "C01"
    root, host = Path(os.environ["FAKE_VM_ROOT"]), os.environ["VMHOST"]
    robots = os.environ.get("ROBOTS", "r1,r2").split(",")
    base = re.sub(r"-retry\d+$", "", name)
    first = base == name
    log = Path(os.environ["EVIDENCE_DIR"]) / name
    log.mkdir(parents=True, exist_ok=False)  # like brain_server.py: a reused name fails
    event(root, "start", name, host)
    time.sleep(float(os.environ.get("FAKE_SLEEP", "3")))
    rc = 0
    skip_summary = set()
    if base in ids("FAKE_FAIL_ALWAYS") or (first and base in ids("FAKE_FAIL_ONCE")):
        rc = 1
        skip_summary = set(robots)
    if first and base in ids("FAKE_INCOMPLETE"):
        skip_summary = {robots[-1]}
    out = root / host / os.environ["OUTROOT"].lstrip("/") / name
    out.mkdir(parents=True, exist_ok=True)
    correct = 2 if rc == 0 else 0
    team_json = {"schema": "fake", "seed": int(seed), "robots": robots, "scene": scene, "orders": [], "knows": {},
                 "status": "complete" if rc == 0 else "running", "end_s": 100.0 + len(name), "brain": {"calls": 4, "cost_usd": 0.0},
                 "decisions": [], "correct_boxes": correct, "required_boxes": 2, "wrong_place_boxes": 0,
                 "choices": {r: {"picked": None} for r in robots}, "fake": {"sha": sha, "team": team, "port": port, "args": rest}}
    (out / "team.json").write_text(json.dumps(team_json), encoding="utf-8")
    for rid in robots:
        if rid not in skip_summary:
            (out / ("out-" + rid)).mkdir(exist_ok=True)
            (out / ("out-" + rid) / "summary.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    (out.parent / ("log-" + name + ".txt")).write_text("fake log %s\n" % name, encoding="utf-8")
    (out.parent / ("exit-" + name + ".json")).write_text(json.dumps({"name": name, "exit_code": rc}), encoding="utf-8")
    (log / "brain-record.json").write_text(json.dumps({"team": team, "leader": os.environ.get("LEADER", "r1"), "decisions": {},
                                                      "messages": [], "calls": 4, "cost_usd": 0.0, "kind": "fake",
                                                      "server_args": os.environ.get("SERVER_ARGS", "")}), encoding="utf-8")
    (log / "llm-calls.jsonl").write_text("".join(json.dumps({"call_index": i, "fake": True}) + "\n" for i in range(1, 5)), encoding="utf-8")
    event(root, "end", name, host, rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
