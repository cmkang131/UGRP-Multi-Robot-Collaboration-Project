#!/usr/bin/env python3
"""Phase-2 front end for cr_dispatch.py (20261115-batch/cloudrun). cr_dispatch.py, dispatch.py and the phase-1 job `ugrp-run` are NOT modified; this file patches them in memory only.

What it changes for phase-2 manifests (phase2-main.csv / phase2-pilot.csv, and the map-gate manifest gate.csv of group p2gate):
  * groups `p2core` / `p2pilot` / `p2gate` are added to dispatch.ALL_GROUPS (dispatch.load_manifest rejects them otherwise)
  * the Cloud Run job is not hard-wired to `ugrp-run`: --size 9 or 6 -> job `ugrp-run9` (4 vCPU / 12 GiB), --size 3 -> job `ugrp-run3` (2 vCPU / 6 GiB) (override with --job);
    rows are filtered by robot count, optionally by --pilot-round N. The 2026-11-18 setup is 3 robots against 6 robots (9 robots cancelled); 6 robots use the same job as 9 did.
  * LLM guard: a row without `--fixed` in its vm_args starts the planner and the container has the OpenRouter secrets mounted. `run --go` therefore refuses such rows unless
    --allow-llm is given (the map gate is fixed-oracle only: it must never start a planner). Rows of group p2gate must have `--fixed oracle` and empty server_args.
  * --others SIZE=SLOTS: slots per region that another dispatcher of the same project is running at the same time (they share the regional quota; the check sums both)
  * --wall-cap-s defaults to 61200 (17 h: the OUTER timeout in the container, above the executor's own --wall-cap-s 57600 that is inside vm_args; the task timeout of the job is 72000 s)
  * real runs (--go) refuse rows that still hold TODO/PLACEHOLDER (dispatch.load_manifest real=True), check the job's cpu / memory / task timeout / IMAGE_TAG against what was asked,
    and check slots x memory and slots x cpu against the regional quota (40 GiB / 20 vCPU)

  cr_dispatch_p2.py plan   --manifest M.csv --size 9 --regions us-central1=2,us-east1=2,us-west1=2 [--pilot-round N] [--image-tag T]   # NO network: prints the commands `run --go` would issue
  cr_dispatch_p2.py run    --manifest M.csv --dir runs/p2-pilot-9 --size 9 --regions ... --image-tag T --go                          # real (money!)
  cr_dispatch_p2.py status|cancel|stop|fetch --dir D ...                                                                            # forwarded unchanged

`plan` runs the REAL cr_dispatch.Scheduler (same code as `run --go`) against a fake gcloud and a fake clock: every `gcloud-p ... run jobs execute ...` it would issue is printed
with the simulated time T+hh:mm (each fake execution lasts --sim-hours, default 9 h for --size 9 and 2.5 h for --size 3: the estimate in README-PHASE2-CLOUDRUN.md, not a measurement).
`plan` loads the manifest with real=False, so TODO rows are accepted there; `run --go` would refuse them.
"""
import argparse
import csv
import json
import os
import shlex
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH = HERE.parent / "20261115-batch"
sys.path.insert(0, str(BATCH / "cloudrun"))
sys.path.insert(0, str(BATCH))
sys.dont_write_bytecode = True
import cr_dispatch  # noqa: E402
import dispatch  # noqa: E402

P2_GROUPS = ("p2core", "p2pilot", "p2gate")
dispatch.ALL_GROUPS = tuple(dispatch.ALL_GROUPS) + tuple(g for g in P2_GROUPS if g not in dispatch.ALL_GROUPS)
JOBS = {3: "ugrp-run3", 6: "ugrp-run9", 9: "ugrp-run9"}
SHAPE = {3: {"cpu": 2, "mem_gib": 6}, 6: {"cpu": 4, "mem_gib": 12}, 9: {"cpu": 4, "mem_gib": 12}}   # per task; must equal create_jobs_p2.sh defaults
QUOTA = {"cpu": 20, "mem_gib": 40}                                   # per region (CpuAllocPerProjectRegion 20000 mCPU, MemAllocPerProjectRegion 40 GiB)
WALL_CAP_S = 61200
TASK_TIMEOUT_MIN_S = 72000


def robots_of(row):
    return len(row["robots"].split(","))


def filter_manifest(a, work):
    """Rows of --manifest with the wanted robot count (and pilot round); the filtered copy keeps ALL columns and goes into the work dir."""
    with open(a.manifest, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if robots_of(r) == a.size and (a.pilot_round is None or r.get("pilot_round", "") == str(a.pilot_round))]
        names = reader.fieldnames
    work.mkdir(parents=True, exist_ok=True)
    out = work / ("manifest-n%d%s.csv" % (a.size, "" if a.pilot_round is None else "-round%d" % a.pilot_round))
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=names)
        w.writeheader()
        w.writerows(rows)
    return out, rows


def parse_others(text):
    """--others 3=2,6=1 -> {3: 2, 6: 1} (slots per region of other dispatchers running at the same time)."""
    out = {}
    for part in filter(None, (text or "").split(",")):
        size, slots = part.split("=")
        if int(size) not in SHAPE or int(slots) < 0:
            raise SystemExit("bad --others %r" % text)
        out[int(size)] = int(slots)
    return out


def quota_check(a):
    shape, regions, others = SHAPE[a.size], cr_dispatch.parse_regions(a.regions), parse_others(getattr(a, "others", ""))
    lines, bad = [], False
    for region, n in regions.items():
        cpu, mem = n * shape["cpu"], n * shape["mem_gib"]
        note = ""
        for size, slots in others.items():
            cpu, mem, note = cpu + slots * SHAPE[size]["cpu"], mem + slots * SHAPE[size]["mem_gib"], note + " + %d slots of size %d (other dispatcher)" % (slots, size)
        flag = "OK" if cpu <= QUOTA["cpu"] and mem <= QUOTA["mem_gib"] else "OVER QUOTA"
        bad |= flag != "OK"
        lines.append("  %s: %d slots x (%d vCPU, %d GiB)%s = %d vCPU of %d, %d GiB of %d  %s" % (region, n, shape["cpu"], shape["mem_gib"], note, cpu, QUOTA["cpu"], mem, QUOTA["mem_gib"], flag))
    print("quota check for job %s (jobs of other sizes/dispatchers share the same regional quota):\n%s" % (a.job, "\n".join(lines)))
    return not bad


def llm_guard(rows, allow_llm):
    """Rows that would start the planner (no --fixed) need --allow-llm; the map gate (group p2gate) must be fixed-oracle with empty server_args."""
    problems = []
    for r in rows:
        vm = shlex.split(r["vm_args"])
        fixed = "--fixed" in vm
        if r["group"] == "p2gate" and not (fixed and vm[vm.index("--fixed") + 1] == "oracle" and not r["server_args"].strip()):
            problems.append("%s: a p2gate row must have `--fixed oracle` and empty server_args" % r["run_id"])
        elif not fixed and not allow_llm:
            problems.append("%s: no --fixed in vm_args = the planner would start and call the LLM; pass --allow-llm only for a real LLM run" % r["run_id"])
    return problems


def common_args(a, work, manifest, go):
    argv = ["run", "--manifest", str(manifest), "--dir", str(work), "--image-tag", a.image_tag, "--regions", a.regions, "--wall-cap-s", str(a.wall_cap_s),
            "--max-retries", str(a.max_retries), "--abort-after", str(a.abort_after), "--tick", str(a.tick), "--alerts-log", a.alerts_log]
    if a.batch:
        argv += ["--batch", a.batch]
    if a.limit:
        argv += ["--limit", str(a.limit)]
    return argv + (["--go"] if go else [])


def check_jobs(a):
    """Real-run guard: the job in every region has the shape/timeout/tag that was asked for (read-only gcloud describe)."""
    ok, shape = True, SHAPE[a.size]
    for region in cr_dispatch.parse_regions(a.regions):
        rc, out, err = cr_dispatch.gcloud("run", "jobs", "describe", a.job, "--region", region, "--format", "json")
        if rc != 0:
            print("refuse: job %s not found in %s: %s" % (a.job, region, err.strip()[-150:]), file=sys.stderr)
            ok = False
            continue
        spec = json.loads(out)["spec"]["template"]["spec"]["template"]["spec"]
        res = spec["containers"][0]["resources"]["limits"]
        env = {e["name"]: e.get("value") for e in spec["containers"][0].get("env", [])}
        timeout = int(spec.get("timeoutSeconds", 0))
        mem = res.get("memory", "")
        mem_gib = float(mem[:-2]) if mem.endswith("Gi") else float("nan")
        problems = []
        if int(float(res.get("cpu", 0))) != shape["cpu"] or mem_gib != shape["mem_gib"]:
            problems.append("cpu/memory %s/%s != %d/%dGi" % (res.get("cpu"), mem, shape["cpu"], shape["mem_gib"]))
        if timeout < max(TASK_TIMEOUT_MIN_S, a.wall_cap_s + 3600):
            problems.append("task timeout %d s < max(%d, wall cap %d + 3600)" % (timeout, TASK_TIMEOUT_MIN_S, a.wall_cap_s))
        if env.get("IMAGE_TAG") != a.image_tag:
            problems.append("job IMAGE_TAG=%s != --image-tag %s" % (env.get("IMAGE_TAG"), a.image_tag))
        if spec.get("maxRetries", 0) != 0:
            problems.append("maxRetries %s != 0 (cr_dispatch does its own retries)" % spec.get("maxRetries"))
        print("job %s %s: %s %s, timeout %d s, IMAGE_TAG %s -> %s" % (a.job, region, res.get("cpu"), mem, timeout, env.get("IMAGE_TAG"), "; ".join(problems) or "OK"))
        ok &= not problems
    return ok


def cmd_plan(a):
    """Real Scheduler, fake gcloud + fake clock. Nothing leaves this process."""
    tmp = Path(tempfile.mkdtemp(prefix="cr_p2_plan_"))
    os.environ["EVIDENCE_DIR"] = str(tmp / "evidence")
    manifest, rows = filter_manifest(a, tmp)
    if not rows:
        print("no rows for --size %d%s in %s" % (a.size, "" if a.pilot_round is None else " --pilot-round %d" % a.pilot_round, a.manifest))
        return 1
    a.alerts_log = str(tmp / "ALERTS.log")   # never the real ALERTS.log
    a.batch = a.batch or (a.manifest.stem.lower().replace("_", "-") + "-n%d" % a.size + ("" if a.pilot_round is None else "-round%d" % a.pilot_round))
    clock = [0.0]
    started = {}
    sim_s = a.sim_hours * 3600
    printed = []
    project = cr_dispatch.PROJECT
    job_json = {"spec": {"template": {"spec": {"template": {"spec": {"timeoutSeconds": str(a.sim_task_timeout_s), "containers": [{"image": "<image of %s>" % a.job,
                "env": [{"name": "IMAGE_TAG", "value": a.image_tag}]}]}}}}}}

    def stamp():
        return "T+%02d:%02d" % (clock[0] // 3600, clock[0] % 3600 // 60)

    def fake_gcloud(*args, timeout=120):
        args = [str(x) for x in args]
        if args[:3] == ["run", "jobs", "execute"]:
            printed.append(args)
            ex = "%s-fake%03d" % (args[3], len(printed))
            started[ex] = clock[0]
            print("%s  gcloud-p %s %s" % (stamp(), project, " ".join(shlex.quote(x) for x in args)), flush=True)
            return 0, ex + "\n", ""
        if args[:3] == ["run", "jobs", "describe"]:
            return 0, json.dumps(job_json), ""
        if args[:3] == ["run", "jobs", "executions"] and args[3] == "list":
            region = args[args.index("--region") + 1]
            items = []
            for ex, t0 in started.items():
                done = clock[0] >= t0 + sim_s
                items.append({"metadata": {"name": ex}, "status": {"succeededCount": 1, "completionTime": "x"} if done else {"runningCount": 1}})
            return 0, json.dumps(items), ""
        if args[0] == "storage" and args[1] == "ls":
            return 1, "", ""
        if args[0] == "storage" and args[1] == "cat":
            return 0, json.dumps({"exit_code": 0, "uploaded": True, "wall_s": sim_s, "team_status": "complete", "cloud_run": {"IMAGE_TAG": a.image_tag}, "wall_cap_s": a.wall_cap_s}), ""
        raise SystemExit("plan mode: unexpected gcloud call %r" % (args,))

    def fake_sleep(s):
        clock[0] += s

    cr_dispatch.gcloud = fake_gcloud
    cr_dispatch.time = types.SimpleNamespace(time=lambda: clock[0], sleep=fake_sleep)
    real_stamp = dispatch.stamp
    dispatch.stamp = lambda: stamp()   # the scheduler's own log lines ("시작 ...") carry the simulated time
    cr_dispatch.JOB = a.job
    orig_load = dispatch.load_manifest
    dispatch.load_manifest = lambda path, real=False: orig_load(path, real=False)
    print("PLAN (no network, fake gcloud, fake clock): job %s, size %d, %d rows, regions %s, wall cap %d s, image tag %s, each fake execution lasts %.1f h" %
          (a.job, a.size, len(rows), a.regions, a.wall_cap_s, a.image_tag, a.sim_hours))
    quota_check(a)
    try:
        code = cr_dispatch.main(common_args(a, tmp / "state", manifest, True))
    finally:
        dispatch.stamp = real_stamp
        dispatch.load_manifest = orig_load
    print("PLAN end: %d execute commands, simulated makespan %s, scheduler exit code %s (state in %s is a throw-away)" % (len(printed), stamp(), code, tmp))
    return 0 if len(printed) == len(rows) else 1


def cmd_run(a):
    work = Path(a.dir).resolve()
    manifest, rows = filter_manifest(a, work)
    if not rows:
        print("no rows for --size %d%s" % (a.size, "" if a.pilot_round is None else " --pilot-round %d" % a.pilot_round), file=sys.stderr)
        return 2
    problems = llm_guard(rows, a.allow_llm)
    if problems and a.go:
        print("refuse (--go): " + "; ".join(problems[:3]) + (" ..." if len(problems) > 3 else ""), file=sys.stderr)
        return 2
    os.environ.setdefault("EVIDENCE_DIR", str(HERE / "evidence" / "physical"))
    cr_dispatch.JOB = a.job
    if not a.go:
        print("DRY (no --go): %d rows would go to job %s. Use `plan` for the commands. Real runs also need: no TODO rows, job checks, quota check." % (len(rows), a.job))
        return 0 if quota_check(a) else 2
    try:
        dispatch.load_manifest(str(manifest), real=True)
    except ValueError as error:
        print("refuse (--go): %s" % error, file=sys.stderr)
        return 2
    if not quota_check(a) or not check_jobs(a):
        print("refuse (--go): see lines above", file=sys.stderr)
        return 2
    return cr_dispatch.main(common_args(a, work, manifest, True))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        q = sub.add_parser(name)
        q.add_argument("--manifest", required=True, type=Path)
        q.add_argument("--size", type=int, choices=(3, 6, 9), required=True, help="robots per run: selects the rows and the job (3 -> ugrp-run3, 6 or 9 -> ugrp-run9)")
        q.add_argument("--others", default="", help="slots per region of ANOTHER dispatcher running at the same time, e.g. 3=2 (summed into the quota check)")
        q.add_argument("--job", default=None)
        q.add_argument("--pilot-round", type=int, default=None, help="only rows whose pilot_round column equals this (pilot manifest: 1..4)")
        q.add_argument("--regions", required=True, help="region=slots,...; slots x memory must fit 40 GiB (and x cpu 20 vCPU) per region together with other running tasks")
        q.add_argument("--image-tag", default="?")
        q.add_argument("--wall-cap-s", type=int, default=WALL_CAP_S)
        q.add_argument("--max-retries", type=int, default=1)
        q.add_argument("--abort-after", type=int, default=8)
        q.add_argument("--limit", type=int, default=0)
        q.add_argument("--tick", type=int, default=30)
        q.add_argument("--batch", default=None)
        q.add_argument("--alerts-log", default=str(cr_dispatch.REAL_ALERTS))
        if name == "run":
            q.add_argument("--dir", required=True)
            q.add_argument("--go", action="store_true")
            q.add_argument("--allow-llm", action="store_true", help="allow rows without --fixed (planner + OpenRouter key); not for the map gate")
        else:
            q.add_argument("--sim-hours", type=float, default=None, help="fake duration of every execution (default 9 for size 9, 6 for size 6, 2.5 for size 3)")
            q.add_argument("--sim-task-timeout-s", type=int, default=72000)
    for name in ("status", "cancel", "stop", "fetch"):
        q = sub.add_parser(name)
        q.add_argument("--dir", required=True)
        if name == "fetch":
            q.add_argument("--results", type=Path)
            q.add_argument("--groups", default="")
            q.add_argument("--full", action="store_true")
    a = p.parse_args(argv)
    if a.cmd in ("status", "cancel", "stop", "fetch"):
        return cr_dispatch.main([a.cmd, "--dir", a.dir] + (["--results", str(a.results)] if getattr(a, "results", None) else []) +
                                (["--groups", a.groups] if getattr(a, "groups", "") else []) + (["--full"] if getattr(a, "full", False) else []))
    a.job = a.job or JOBS[a.size]
    if a.cmd == "plan":
        a.sim_hours = a.sim_hours or {3: 2.5, 6: 6.0, 9: 9.0}[a.size]
        return cmd_plan(a)
    return cmd_run(a)


if __name__ == "__main__":
    sys.exit(main())
