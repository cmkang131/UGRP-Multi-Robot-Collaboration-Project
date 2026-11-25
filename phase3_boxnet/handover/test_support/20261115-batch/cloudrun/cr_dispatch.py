#!/usr/bin/env python3
"""Send manifest rows to Cloud Run jobs (standard library only). Does NOT touch dispatch.py or its state (runs/main3-rest/state.json).

  cr_dispatch.py run    --manifest M.csv --dir runs/main3-cr --image-tag v37-1 [--regions us-central1=8,us-east1=8] [--exclude-state OLD/state.json] [--go]
  cr_dispatch.py status [--dir D]
  cr_dispatch.py fetch  [--dir D] [--results results-main3-cr] [--full] [--groups main3]   # GCS -> local layout, then collect.py logic
  cr_dispatch.py cancel [--dir D]                                                         # cancel running executions of this batch
  cr_dispatch.py stop   [--dir D]                                                         # stop this scheduler only; executions keep running and are re-adopted

One execution of the job `ugrp-run` per manifest row (1 task, CPU 2, 5Gi). The scheduler keeps at most <slots> executions per region (quota: 20 vCPU
= 10 tasks of CPU 2, 40 GiB memory = 8 tasks of 5Gi per region; the smaller one binds) and records state in <dir>/state.json in the same shape as dispatch.py's, so
collect.py logic (cr_collect via `fetch`) can read it. Results land in GCS: gs://<bucket>/<batch>/<name>/{meta.json,light,evidence,full}.tar.zst.
Resumable: run it again with the same --dir; running executions are adopted by name.
Real submissions need --go (otherwise a dry plan is printed).

Provenance (since 2026-11-17): every run record in state.json carries image_tag (the --image-tag you typed), wall_cap_s and task_timeout_s (read from the job),
and, once the execution is listed, image (digest Cloud Run actually ran). Each history entry repeats them per attempt (so a failed first attempt keeps its own),
plus what the container reported in meta.json (container_image_tag, container_wall_cap_s). cr_collect copies them into results/<run_id>/meta.json and index.csv.
"""
import argparse
import datetime
import fcntl
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.dont_write_bytecode = True
import dispatch  # noqa: E402  (load_manifest, no_brain, read_json, write_json, stamp)

PROJECT = os.environ.get("HANDOVER_PROJECT", "<project-id>")
BUCKET = os.environ.get("HANDOVER_BUCKET", "<bucket>")
JOB = "ugrp-run"
REAL_ALERTS = Path(os.environ.get("BOXNET_ALERTS_FILE", HERE / "ALERTS.log"))
LABEL = dispatch.LABEL


def gcloud(*args, timeout=120):
    """gcloud-p wrapper (the only way to reach this project). Returns (rc, stdout, stderr)."""
    try:
        r = subprocess.run(["gcloud-p", PROJECT] + [str(a) for a in args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:  # a hung gcloud call must not kill the scheduler: callers already handle rc != 0
        return 124, "", "gcloud timed out after %ss" % timeout
    return r.returncode, r.stdout, r.stderr


def task_facts(task_spec):
    """Facts of one task template (an execution's spec.template.spec, or a job's spec.template.spec.template.spec): timeout, image, IMAGE_TAG env."""
    try:
        container = task_spec["containers"][0]
        env = {x.get("name"): x.get("value") for x in container.get("env", [])}
        return {"task_timeout_s": task_spec.get("timeoutSeconds"), "image": container.get("image"), "image_tag_env": env.get("IMAGE_TAG")}
    except (KeyError, IndexError, TypeError, AttributeError):
        return {}


def exec_facts_of(execution):
    try:
        return task_facts(execution["spec"]["template"]["spec"])
    except (KeyError, TypeError):
        return {}


def job_facts_of(job):
    try:
        return task_facts(job["spec"]["template"]["spec"]["template"]["spec"])
    except (KeyError, TypeError):
        return {}


def parse_regions(text):
    out = {}
    for part in text.split(","):
        region, n = part.split("=")
        out[region] = int(n)
        if out[region] < 1:
            raise ValueError("bad --regions " + text)
    return out


def spec_for(row, name, batch, wall_cap_s, extra=None):
    keys = ("run_id", "group", "scene_file", "scene_id", "team", "rep", "robots", "leader", "model", "vm_args", "server_args", "sha", "vmrun", "seed")
    spec = {k: row[k] for k in keys}
    spec.update(name=name, batch=batch, wall_cap_s=wall_cap_s)
    spec.update({k: v for k, v in (extra or {}).items() if v is not None})  # echoed into meta.json["spec"] by cr_task.py (also by images built before 2026-11-17)
    return spec


class Scheduler:
    def __init__(self, a, rows):
        self.a, self.rows = a, rows
        self.by_id = {r["run_id"]: r for r in rows}
        self.work = Path(a.dir).resolve()
        self.work.mkdir(parents=True, exist_ok=True)
        self.evidence = Path(os.environ.get("EVIDENCE_DIR") or HERE.parent / "evidence" / "physical")
        self.outroot = self.work / "outroot"
        self.path = self.work / "state.json"
        self.regions = parse_regions(a.regions)
        st = dispatch.read_json(self.path, {})
        st.setdefault("runs", {})
        st.setdefault("vms", {})
        st.setdefault("alerted_groups", [])
        st["consecutive_failures"] = 0
        st.update(manifest=str(Path(a.manifest).resolve()), outroot=str(self.outroot), evidence=str(self.evidence), batch=a.batch,
                  slots=dict(self.regions), image_tag=a.image_tag, wall_cap_s=a.wall_cap_s, kind="cloudrun")
        for r in rows:
            st["runs"].setdefault(r["run_id"], {"status": "pending", "attempt": 0, "name": r["run_id"], "group": r["group"], "history": []})
        for region in self.regions:
            st["vms"].setdefault(region, {"state": "up", "since": dispatch.stamp()})
        self.st = st
        self.halt = self.stopping = False
        self.last_launch = 0.0
        self.exec_facts = {}  # execution name -> {task_timeout_s, image, image_tag_env}, filled by list_executions()
        self.job_facts = {}   # region -> same, from `run jobs describe` (read once per region)

    # -- helpers
    def save(self):
        self.st["updated"] = dispatch.stamp()
        dispatch.write_json(self.path, self.st)

    def rec(self, run_id):
        return self.st["runs"][run_id]

    def runs_with(self, status):
        return [i for i, r in self.st["runs"].items() if r["status"] == status and i in self.by_id]

    def name_for(self, run_id, attempt):
        return run_id if attempt == 0 else "%s-retry%d" % (run_id, attempt)

    def alert(self, text):
        path = Path(self.a.alerts_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(dispatch.now().strftime("%Y-%m-%d %H:%M KST") + " " + text + "\n")

    def prefix(self, name):
        return "gs://%s/%s/%s" % (BUCKET, self.a.batch, name)

    def gcs_exists(self, name):
        rc, out, _ = gcloud("storage", "ls", self.prefix(name) + "/")
        return rc == 0 and bool(out.strip())

    def meta(self, name):
        rc, out, _ = gcloud("storage", "cat", self.prefix(name) + "/meta.json")
        if rc != 0:
            return None
        try:
            return json.loads(out)
        except ValueError:
            return None

    def running_in(self, region):
        return sum(1 for i in self.runs_with("running") if self.rec(i).get("region") == region)

    # -- Cloud Run
    def job_info(self, region):
        """Task timeout / image / IMAGE_TAG of the job in this region, read once (read-only). Warns when the job's IMAGE_TAG differs from --image-tag."""
        if region not in self.job_facts:
            rc, out, err = gcloud("run", "jobs", "describe", JOB, "--region", region, "--format", "json")
            facts = {}
            if rc == 0:
                try:
                    facts = job_facts_of(json.loads(out))
                except ValueError:
                    pass
            if not facts:
                print("%s job %s 설정을 못 읽음(%s): task timeout 은 기록 안 됨" % (dispatch.stamp(), region, err.strip()[-120:]), flush=True)
            elif facts.get("image_tag_env") and self.a.image_tag not in ("?", facts["image_tag_env"]):  # a job without IMAGE_TAG (other job names) is not a mismatch
                print("%s 경고: job %s 의 IMAGE_TAG=%s 인데 --image-tag=%s" % (dispatch.stamp(), region, facts.get("image_tag_env"), self.a.image_tag), flush=True)
            self.job_facts[region] = facts
        return self.job_facts[region]

    def list_executions(self, region):
        rc, out, err = gcloud("run", "jobs", "executions", "list", "--job", JOB, "--region", region, "--limit", "400", "--format", "json", timeout=180)
        if rc != 0:
            print("%s executions list %s failed: %s" % (dispatch.stamp(), region, err.strip()[-200:]), flush=True)
            return None
        try:
            listed = json.loads(out)
            for e in listed:
                self.exec_facts[e["metadata"]["name"]] = exec_facts_of(e)
            return {e["metadata"]["name"]: e.get("status", {}) for e in listed}
        except (ValueError, KeyError):
            return None

    def launch(self, run_id, region):
        rec, row = self.rec(run_id), self.by_id[run_id]
        name = rec["name"]
        if (self.evidence / name).exists() or self.gcs_exists(name):
            if rec["attempt"] >= self.a.max_retries:
                rec.update(status="failed", reason="all attempt names used")
                return
            rec["attempt"] += 1
            rec["name"] = self.name_for(run_id, rec["attempt"])
            return self.launch(run_id, region)
        timeout_s = self.job_info(region).get("task_timeout_s")
        spec = spec_for(row, name, self.a.batch, self.a.wall_cap_s, {"task_timeout_s": timeout_s, "dispatch_image_tag": self.a.image_tag})
        env = "^@@^RUN_SPEC=%s@@WALL_CAP_S=%d" % (json.dumps(spec, ensure_ascii=False, separators=(",", ":")), self.a.wall_cap_s)
        gap = 60.0 / 25 - (time.time() - self.last_launch)  # JobRunPerMinutePerProjectRegion = 30
        if gap > 0:
            time.sleep(gap)
        rec.update(status="running", vm="cr:" + region, region=region, started=dispatch.stamp(), ended=None, rc=None, execution=None,
                   image_tag=self.a.image_tag, wall_cap_s=self.a.wall_cap_s, task_timeout_s=timeout_s)
        self.save()  # recorded before the call: a crash here is read as "interrupted", never as a lost run
        rc, out, err = gcloud("run", "jobs", "execute", JOB, "--region", region, "--async", "--update-env-vars", env,
                              "--format", "value(metadata.name)")
        self.last_launch = time.time()
        if rc != 0 or not out.strip():
            print("%s execute failed %s: %s" % (dispatch.stamp(), name, err.strip()[-300:]), flush=True)
            rec.update(status="pending", region=None, vm=None)
            self.st["vms"][region].update(state="down", since=dispatch.stamp())
            return
        rec["execution"] = out.strip().splitlines()[-1].strip()
        self.save()
        print("%s 시작 %s (%s, %s)" % (dispatch.stamp(), name, region, rec["execution"]), flush=True)

    # -- finishing
    def finish(self, run_id, state):
        rec = self.rec(run_id)
        name = rec["name"]
        meta = self.meta(name)
        rec.update(ended=dispatch.stamp())
        entry = {"name": name, "vm": rec.get("vm"), "started": rec.get("started"), "ended": rec["ended"], "execution": rec.get("execution")}
        facts = self.exec_facts.get(rec.get("execution")) or {}  # what Cloud Run recorded for this execution
        for key, value in (("image_tag", rec.get("image_tag")), ("wall_cap_s", rec.get("wall_cap_s")),
                           ("task_timeout_s", facts["task_timeout_s"] if facts.get("task_timeout_s") is not None else rec.get("task_timeout_s")),
                           ("image", facts.get("image"))):
            if value is not None:
                entry[key] = value
                if key in ("task_timeout_s", "image"):
                    rec[key] = value
        if meta is None:  # container died before the upload finished (infrastructure): the name is still unused
            rec["infra_failures"] = rec.get("infra_failures", 0) + 1
            rec["history"].append(dict(entry, result="no_meta(%s)" % state))
            if rec["infra_failures"] <= 2:
                rec.update(status="pending", region=None, vm=None, execution=None)
                return
            rec.update(status="failed", reason="no result after %d executions" % rec["infra_failures"])
            self.st["consecutive_failures"] += 1
            return
        rc = meta.get("exit_code")
        entry.update(rc=rc, wall_s=meta.get("wall_s"), team_status=meta.get("team_status"))
        for key, value in (("container_image_tag", (meta.get("cloud_run") or {}).get("IMAGE_TAG")), ("container_wall_cap_s", meta.get("wall_cap_s"))):
            if value is not None:
                entry[key] = value
        rec["rc"] = rc
        if rc == 0 and meta.get("uploaded"):
            rec["status"] = "done"
            self.st["consecutive_failures"] = 0
            rec["history"].append(dict(entry, result="done"))
            return
        result = "rc=%s%s" % (rc, "" if meta.get("uploaded") else " upload-failed")
        rec["history"].append(dict(entry, result=result))
        self.st["consecutive_failures"] += 1
        if self.st["consecutive_failures"] >= self.a.abort_after:
            self.halt = True
            self.alert("[경보] Cloud Run 연속 실패 %d건, 새 실행 중지 (%s)" % (self.st["consecutive_failures"], run_id))
        if rec["attempt"] < self.a.max_retries:
            rec["attempt"] += 1
            rec.update(status="pending", name=self.name_for(run_id, rec["attempt"]), retry_front=True, region=None, vm=None, execution=None)
        else:
            rec.update(status="failed", reason=result)

    def reap(self):
        by_region = {}
        for run_id in self.runs_with("running"):
            by_region.setdefault(self.rec(run_id).get("region"), []).append(run_id)
        for region, ids in by_region.items():
            execs = self.list_executions(region)
            if execs is None:
                continue
            for run_id in ids:
                rec = self.rec(run_id)
                st = execs.get(rec.get("execution"))
                if st is None:
                    if rec.get("execution") is None:
                        rec.update(status="pending", region=None, vm=None)  # crash between recording and execute
                    continue
                if st.get("runningCount") or not (st.get("succeededCount") or st.get("failedCount") or st.get("cancelledCount")
                                                  or st.get("completionTime")):
                    continue
                state = "succeeded" if st.get("succeededCount") else ("cancelled" if st.get("cancelledCount") else "failed")
                print("%s 끝 %s (%s) %s" % (dispatch.stamp(), rec["name"], region, state), flush=True)
                self.finish(run_id, state)

    def launch_new(self):
        if self.halt or self.stopping:
            return
        limit = self.a.limit
        order = sorted(self.runs_with("pending"), key=lambda i: (not self.rec(i).get("retry_front"), self.rows.index(self.by_id[i])))
        for run_id in order:
            if limit and len(self.runs_with("running")) >= limit:
                break
            free = [r for r in self.regions if self.st["vms"][r]["state"] == "up" and self.running_in(r) < self.regions[r]]
            if not free:
                break
            self.launch(run_id, min(free, key=lambda r: self.running_in(r) / self.regions[r]))

    def recheck_regions(self):
        for region, v in self.st["vms"].items():
            if v["state"] != "up" and time.time() - self.last_launch > 300:
                v.update(state="up", since=dispatch.stamp())

    def group_alerts(self):
        states = [self.rec(r["run_id"])["status"] for r in self.rows]
        if "ALL" not in self.st["alerted_groups"] and all(s in ("done", "failed") for s in states):
            self.st["alerted_groups"].append("ALL")
            self.alert("[묶음 끝] Cloud Run %s 전체 %d건 중 완료 %d, 실패 %d (%s)" % (self.a.batch, len(states), states.count("done"), states.count("failed"),
                                                                           Path(self.a.manifest).name))

    def reconcile(self):
        """After a restart: running records keep their execution name and are checked by reap(); nothing else to do."""
        for run_id in self.runs_with("running"):
            print("%s 이어받음 %s (%s)" % (dispatch.stamp(), self.rec(run_id)["name"], self.rec(run_id).get("execution")), flush=True)
        self.save()

    def loop(self):
        while True:
            self.reap()
            self.recheck_regions()
            self.launch_new()
            self.group_alerts()
            self.save()
            if self.stopping:
                return 130
            running, pending = self.runs_with("running"), self.runs_with("pending")
            if not running:
                if self.halt:
                    return 4
                if not pending:
                    return 1 if self.runs_with("failed") else 0
            time.sleep(self.a.tick)


def exclude_started(rows, old_state_path):
    """Rows the VM dispatcher already started (or finished) must not be sent to Cloud Run."""
    old = dispatch.read_json(old_state_path, {}).get("runs", {})
    keep, skipped = [], []
    for r in rows:
        o = old.get(r["run_id"])
        if o and (o["status"] != "pending" or o.get("history") or o.get("attempt")):
            skipped.append((r["run_id"], o["status"]))
        else:
            keep.append(r)
    return keep, skipped


def vm_dispatcher_alive(old_state_path):
    """True if the VM dispatcher that owns this state.json is running (its dispatch.pid names a live `dispatch.py run` process)."""
    pid_file = Path(old_state_path).resolve().parent / "dispatch.pid"
    try:
        return dispatch.pid_alive(pid_file.read_text().strip(), "run", "dispatch.py")
    except OSError:
        return False


def live_manifest_clash(rows, old_state_path):
    """The VM dispatcher's state.json names the manifest it is (still) running. Any run_id of ours in it is a row it may start itself."""
    st = dispatch.read_json(old_state_path)
    if not st or not st.get("manifest"):
        raise ValueError("cannot read the VM dispatcher state: %s" % old_state_path)
    live = {r["run_id"] for r in dispatch.load_manifest(st["manifest"])}
    return st["manifest"], sorted({r["run_id"] for r in rows} & live)


def cmd_run(a):
    rows = dispatch.load_manifest(a.manifest, real=True)
    for vm_state in a.vm_state or []:
        rows, skipped = exclude_started(rows, vm_state)
        for run_id, status in skipped:
            print("건너뜀 %s: VM 디스패처 상태 %s" % (run_id, status), file=sys.stderr)
        try:
            live_path, clash = live_manifest_clash(rows, vm_state)
        except (ValueError, OSError) as error:
            print("거부: %s" % error, file=sys.stderr)
            return 2
        if clash and a.allow_stopped_vm_dispatcher and not vm_dispatcher_alive(vm_state):
            print("주의: VM 디스패처(%s)가 멈춰 있어 매니페스트 겹침 %d건을 허용함. 이 디스패처를 같은 매니페스트로 다시 띄우면 같은 행을 시작할 수 있다" % (vm_state, len(clash)), file=sys.stderr)
            clash = []
        if clash:  # the VM dispatcher still has these rows in the manifest it runs: it could start them too
            print("거부: %d건이 VM 디스패처가 지금 쓰는 매니페스트(%s)에 아직 있음: %s ... VM 디스패처를 멈추고 split_manifest 의 --out-keep 으로 다시 띄운 뒤에 보낼 것"
                  % (len(clash), live_path, clash[:5]), file=sys.stderr)
            return 2
    if not rows:
        print("보낼 행이 없음")
        return 0
    if not a.go:
        by_group = {}
        for r in rows:
            by_group[r["group"]] = by_group.get(r["group"], 0) + 1
        print("DRY RUN (no --go): %d runs, groups %s, regions %s, image tag %s, batch %s" % (len(rows), by_group, a.regions, a.image_tag, a.batch))
        r = rows[0]
        print("첫 행 %s: team %s robots %s model %s planner %s\n  vm_args: %s" % (r["run_id"], r["team"], r["robots"], r["model"],
                                                                          "NONE (--fixed)" if dispatch.no_brain(r["vm_args"]) else "yes", r["vm_args"]))
        return 0
    work = Path(a.dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    lock = open(work / "cr.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another scheduler holds %s" % (work / "cr.lock"), file=sys.stderr)
        return 2
    (work / "cr.pid").write_text(str(os.getpid()))
    s = Scheduler(a, rows)
    signal.signal(signal.SIGTERM, lambda *_: setattr(s, "stopping", True))
    signal.signal(signal.SIGINT, lambda *_: setattr(s, "stopping", True))
    print("%s cr_dispatch 시작: %d건, 지역 %s, 이미지 태그 %s" % (dispatch.stamp(), len(rows), s.regions, a.image_tag), flush=True)
    s.reconcile()
    code = s.loop()
    s.save()
    (work / "cr.pid").unlink(missing_ok=True)
    print("%s cr_dispatch 끝 (코드 %d)" % (dispatch.stamp(), code), flush=True)
    return code


def cmd_status(a):
    st = dispatch.read_json(Path(a.dir) / "state.json")
    if not st:
        print("state.json 없음")
        return 1
    runs = st["runs"]
    print("갱신 %s | 배치 %s | 이미지 %s | wall cap %s | manifest %s" % (st.get("updated"), st.get("batch"), st.get("image_tag"), st.get("wall_cap_s", "?"), st.get("manifest")))
    print("전체 %d건: " % len(runs) + ", ".join("%s %d" % (LABEL[k], sum(r["status"] == k for r in runs.values())) for k in LABEL))
    for region, n in st.get("slots", {}).items():
        print("  %s 슬롯 %s, 실행 %d" % (region, n, sum(r["status"] == "running" and r.get("region") == region for r in runs.values())))
    for i, r in runs.items():
        if r["status"] in ("running", "failed"):
            print("  %s %s (%s) %s" % (LABEL[r["status"]], r["name"], r.get("region"), r.get("reason") or r.get("execution") or ""))
    return 0


def cmd_cancel(a):
    st = dispatch.read_json(Path(a.dir) / "state.json", {})
    for i, r in st.get("runs", {}).items():
        if r["status"] == "running" and r.get("execution"):
            rc, _, err = gcloud("run", "jobs", "executions", "cancel", r["execution"], "--region", r["region"], "--quiet")
            print("cancel %s: %s" % (r["execution"], "ok" if rc == 0 else err.strip()[-120:]))
    return 0


def cmd_stop(a):
    pid = (Path(a.dir) / "cr.pid")
    if pid.exists():
        os.kill(int(pid.read_text()), signal.SIGTERM)
        print("scheduler 에 TERM")
    else:
        print("scheduler 실행 중 아님")
    return 0


def cmd_fetch(a):
    """GCS -> local layout identical to the VM path, then collect.py's own logic builds results-*/:
       <dir>/outroot/<name>/{team.json,out-rK/summary.json[,full]}, <dir>/outroot/{log-<name>.txt,exit-<name>.json}  (= the VM outroot)
       <EVIDENCE_DIR>/<name>/{brain-record.json,llm-calls.jsonl,...}, <name>.exit, <name>.server.log                  (= evidence/physical)
    """
    work = Path(a.dir).resolve()
    st = dispatch.read_json(work / "state.json")
    if not st:
        print("no state.json in %s" % work, file=sys.stderr)
        return 1
    outroot, evidence, batch = Path(st["outroot"]), Path(st["evidence"]), st["batch"]
    outroot.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    got = 0
    for run_id, rec in st["runs"].items():
        if rec["status"] != "done" or (a.groups and rec["group"] not in a.groups.split(",")):
            continue
        name = rec["name"]
        marker = outroot / (".fetched-" + name + (".full" if a.full else ""))
        if marker.exists():
            continue
        tmp = work / "dl" / name
        tmp.mkdir(parents=True, exist_ok=True)
        want = ["light", "evidence"] + (["full"] if a.full else [])
        ok = True
        for part in want:
            rc, _, err = gcloud("storage", "cp", "gs://%s/%s/%s/%s.tar.zst" % (BUCKET, batch, name, part), str(tmp / (part + ".tar.zst")), timeout=1800)
            if rc != 0:
                print("download failed %s %s: %s" % (name, part, err.strip()[-150:]), file=sys.stderr)
                ok = False
        gcloud("storage", "cp", "gs://%s/%s/%s/meta.json" % (BUCKET, batch, name), str(tmp / "meta.json"))
        if not ok:
            continue
        for part, base in (("light", outroot), ("evidence", evidence), ("full", outroot)):
            if part in want:
                r = subprocess.run(["tar", "--zstd", "-xf", str(tmp / (part + ".tar.zst")), "-C", str(base)], capture_output=True, text=True)
                if r.returncode:
                    print("extract failed %s %s: %s" % (name, part, r.stderr[-150:]), file=sys.stderr)
                    ok = False
        if ok:
            if (tmp / "meta.json").exists():
                (evidence / name).mkdir(exist_ok=True)
                (evidence / name / "cloudrun-meta.json").write_bytes((tmp / "meta.json").read_bytes())
            marker.write_text(dispatch.stamp() + "\n")
            for f in tmp.iterdir():
                f.unlink()
            tmp.rmdir()
            got += 1
    print("downloaded %d runs -> %s, %s" % (got, outroot, evidence))
    if a.results:
        sys.path.insert(0, str(HERE))
        import cr_collect  # noqa: E402
        return cr_collect.main(["--dir", str(work), "--results", str(a.results)] + (["--groups", a.groups] if a.groups else []) + (["--full"] if a.full else []))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--manifest", required=True, type=Path)
    r.add_argument("--dir", required=True, help="new work dir for this Cloud Run batch (own state.json), not the VM dispatcher's")
    r.add_argument("--batch", default=None, help="GCS folder name (default: basename of --dir); lower-case letters, digits, - _ .")
    r.add_argument("--image-tag", default="?", help="only recorded in state.json (the image is whatever the job ugrp-run currently points to)")
    r.add_argument("--regions", default="us-central1=8", help="region=max concurrent executions, comma separated (min(20 vCPU / 2, 40 GiB / 5Gi) = 8 per region)")
    r.add_argument("--wall-cap-s", type=int, default=9900, help="in-container wall cap per run; must be <= the job task timeout minus ~900 s for the upload "
                   "(create_jobs.sh default task timeout 10800 s; for 4.5 h use TASK_TIMEOUT_S=18000 there and --wall-cap-s 16200 here)")
    r.add_argument("--max-retries", type=int, default=1)
    r.add_argument("--abort-after", type=int, default=8, help="stop launching after this many consecutive failures")
    r.add_argument("--limit", type=int, default=0, help="at most this many executions at once overall (0 = per-region slots only)")
    r.add_argument("--tick", type=int, default=30)
    r.add_argument("--vm-state", action="append", help="a VM dispatcher's state.json (repeatable). Rows it already started are skipped; refuses "
                   "if the manifest named in that state.json (the one it is running now) still contains any of these rows")
    r.add_argument("--allow-stopped-vm-dispatcher", action="store_true",
                   help="only if the VM dispatcher is NOT running and will not be restarted with that manifest: skip the manifest-overlap refusal")
    r.add_argument("--alerts-log", default=str(REAL_ALERTS))
    r.add_argument("--go", action="store_true")
    for name in ("status", "cancel", "stop"):
        q = sub.add_parser(name)
        q.add_argument("--dir", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--dir", required=True)
    f.add_argument("--results", type=Path, help="also build collect.py's results folder here")
    f.add_argument("--groups", default="")
    f.add_argument("--full", action="store_true", help="also download full.tar.zst (rgb frames etc.)")
    a = p.parse_args(argv)
    if a.cmd == "run":
        a.batch = a.batch or Path(a.dir).name
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", a.batch):
            print("bad --batch", file=sys.stderr)
            return 2
    return {"run": cmd_run, "status": cmd_status, "cancel": cmd_cancel, "stop": cmd_stop, "fetch": cmd_fetch}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
