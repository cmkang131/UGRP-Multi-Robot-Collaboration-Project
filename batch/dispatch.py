#!/usr/bin/env python3
"""Batch dispatcher for the main experiment (standard library only).

  dispatch.py run --manifest M.csv [--slots 1=5,2=2] [--outroot <result folder on the work VMs>] [--go]
  dispatch.py status [--dir D]          progress summary from state.json
  dispatch.py stop [--runs] [--dir D]   stop the dispatcher (running launchers keep going, unless --runs)

Resumable: state.json + per-run files on this server (<EVIDENCE_DIR>/<name>.exit) + one batched listing per VM.
Real runs need --go (otherwise a dry plan is printed). FAKE_LAUNCH=1 + FAKE_VM_ROOT=<dir> simulates the VMs locally.
"""
import argparse
import csv
import datetime
import fcntl
import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ALERTS = Path("outputs/batch-alerts.log")   # the alert log of a real batch unless $ALERTS_LOG says otherwise (relative to the working directory)
COLUMNS = ["run_id", "group", "scene_file", "scene_id", "team", "rep", "robots", "leader", "model",
           "vm_args", "server_args", "sha", "vmrun", "seed"]
GROUPS = ("baseline", "mainA", "random", "leader", "three", "model2", "ablation", "order", "fullinfo")
EXTRA_GROUPS = ("confirm2", "listen0", "random_baseline", "main3", "baseline3")  # + 3-robot main (11/16 user: three robots are the core)  # confirm re-run, listen-0 ablation, oracle plan on the random scenes
ALL_GROUPS = GROUPS + EXTRA_GROUPS
KST = datetime.timezone(datetime.timedelta(hours=9))
LABEL = {"pending": "대기", "running": "실행", "verifying": "검증대기", "done": "완료", "failed": "실패"}
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
NOT_STARTED = 99  # launcher: VM unreachable before anything started


def now():
    return datetime.datetime.now(KST)


def stamp():
    return now().strftime("%Y-%m-%d %H:%M:%S KST")


def write_json(path, obj):
    tmp = path.with_name(path.name + ".tmp%d" % os.getpid())
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ------------------------------------------------------------------ manifest
def load_manifest(path, real=False):
    with open(path, encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = [c for c in COLUMNS[:-1] if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("manifest missing columns: %s" % missing)
        rows = [{k: (v or "").strip() for k, v in r.items() if k in COLUMNS} for r in reader]
    seen = set()
    for i, r in enumerate(rows, 2):
        where = "manifest line %d (%s)" % (i, r.get("run_id"))
        if not RUN_ID.match(r["run_id"]) or re.search(r"-retry\d+$", r["run_id"]):
            raise ValueError(where + ": bad run_id")
        if r["run_id"] in seen:
            raise ValueError(where + ": duplicate run_id")
        seen.add(r["run_id"])
        if r["group"] not in ALL_GROUPS:
            raise ValueError(where + ": group must be one of %s" % (ALL_GROUPS,))
        if r["team"] not in ("T0", "T1", "T2"):
            raise ValueError(where + ": team must be T0/T1/T2")
        robots = r["robots"].split(",")
        if not r["robots"] or not all(re.fullmatch(r"r\d+", x) for x in robots):
            raise ValueError(where + ": bad robots")
        r["leader"] = r["leader"] or "r1"
        if r["leader"] not in robots:
            raise ValueError(where + ": leader not in robots")
        if not re.fullmatch(r"run_team_v\d+\.sh", r["vmrun"]):
            raise ValueError(where + ": vmrun must look like run_team_vNN.sh")
        for key in ("scene_file", "scene_id", "model", "sha"):
            if not r[key]:
                raise ValueError(where + ": empty " + key)
        r["seed"] = r.get("seed") or "90721"
        if not r["seed"].isdigit() or not r["rep"].isdigit():
            raise ValueError(where + ": seed/rep must be integers")
        for key in ("vm_args", "server_args"):
            shlex.split(r[key])
        if real and any(w in " ".join(r.values()) for w in ("TODO", "PLACEHOLDER")):
            raise ValueError(where + ": placeholder (TODO/PLACEHOLDER) left in a row; fill it before a real run")
    return rows


# ------------------------------------------------------------------ environment / VM access
class Cfg:
    def __init__(self, work, outroot=None):
        self.work = Path(work).resolve()
        self.evidence = Path(os.environ.get("EVIDENCE_DIR") or HERE / "evidence" / "physical")
        self.alerts = Path(os.environ.get("ALERTS_LOG") or DEFAULT_ALERTS)
        self.fake = os.environ.get("FAKE_LAUNCH") == "1"
        self.fake_root = Path(os.environ["FAKE_VM_ROOT"]) if os.environ.get("FAKE_VM_ROOT") else None
        self.key = os.environ.get("SSH_KEY") or None          # private key file; unset = the ssh default identity
        self.user = os.environ.get("VM_USER") or None         # login name on the work VMs; unset = the ssh default
        # one file per VM holding its current address (re-read on every use); unset = that VM counts as unreachable
        self.ipfile = {1: os.environ.get("VM1_IP_FILE"), 2: os.environ.get("VM2_IP_FILE")}
        self.brain_dir = os.environ.get("BRAIN_DIR", str(HERE.parent / "team"))   # folder with brain_server.py
        self.outroot = outroot or os.environ.get("OUTROOT")
        if not self.outroot:
            raise SystemExit("--outroot (or $OUTROOT) is required: the absolute result folder on the work VMs")
        if self.fake:
            if not self.fake_root:
                raise SystemExit("FAKE_LAUNCH=1 needs FAKE_VM_ROOT")
            if self.alerts.resolve() == DEFAULT_ALERTS.resolve():
                raise SystemExit("FAKE_LAUNCH=1 refuses the real alert log; set ALERTS_LOG")

    def host(self, vm):
        """VM address, re-read on every use (the IP can change when the idle watcher stops and restarts a VM)."""
        if self.fake:
            return "fakevm%d" % vm
        try:
            return Path(self.ipfile[vm]).read_text().strip() or None
        except (OSError, TypeError):    # TypeError: no file given for this VM
            return None

    def vm_run(self, vm, script, timeout=60):
        """Run a bash script on a VM. Returns (rc, stdout); rc 255 = cannot connect."""
        host = self.host(vm)
        if host is None:
            return 255, ""
        try:
            if self.fake:
                if (self.fake_root / (host + ".down")).exists():
                    return 255, ""
                script = "PREFIX=%s\n%s" % (shlex.quote(str(self.fake_root / host)), script)
                cmd = ["bash", "-s"]
            else:
                script = "PREFIX=\n" + script
                cmd = ["ssh"] + (["-i", self.key] if self.key else []) + ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                       "-o", "ServerAliveInterval=30", (self.user + "@" if self.user else "") + host, "bash -s"]
            r = subprocess.run(cmd, input=script, capture_output=True, text=True, timeout=timeout)
            return r.returncode, r.stdout
        except (subprocess.TimeoutExpired, OSError):
            return 255, ""

    def alert(self, text):
        self.alerts.parent.mkdir(parents=True, exist_ok=True)
        with open(self.alerts, "a", encoding="utf-8") as stream:
            stream.write(now().strftime("%Y-%m-%d %H:%M KST") + " " + text + "\n")


SCAN = r'''cd "$PREFIX"%s 2>/dev/null || exit 0
for d in */; do
  d=${d%%/}; [ -f "$d/team.json" ] || continue
  r=""; for s in "$d"/out-*/summary.json; do [ -f "$s" ] || continue; x=${s#*/out-}; r="$r${x%%%%/*},"; done
  e=""; [ -f "exit-$d.json" ] && e=$(sed -n 's/.*"exit_code"[^0-9-]*\(-\{0,1\}[0-9]*\).*/\1/p' "exit-$d.json" | head -1)
  printf '%%s\t%%s\t%%s\n' "$d" "$r" "$e"
done
'''


def no_brain(vm_args):
    """A run with `--fixed ...` in its VM args uses the reference plan: run_team_carry.py reads --fixed only when --brain-url is
    absent, so such a run must start neither the planner server nor pass --brain-url (launch_team_run_v3.sh, NO_BRAIN=1)."""
    return "--fixed" in shlex.split(vm_args)


def pid_alive(pid, token, script):
    """True if /proc/<pid>/cmdline has `token` as an argument and mentions `script` (pids are reused after a reboot)."""
    try:
        args = Path("/proc/%d/cmdline" % int(pid)).read_bytes().decode(errors="replace").split("\0")
    except (OSError, TypeError, ValueError):
        return False
    return token in args and any(script in a for a in args)


# ------------------------------------------------------------------ dispatcher
class Dispatcher:
    def __init__(self, cfg, rows, slots, args):
        self.cfg, self.rows, self.slots, self.a = cfg, rows, slots, args
        self.by_id = {r["run_id"]: r for r in rows}
        self.procs, self.stopping, self.halt = {}, False, False
        self.last_probe = {}
        (cfg.work / "pids").mkdir(parents=True, exist_ok=True)
        cfg.evidence.mkdir(parents=True, exist_ok=True)
        self.path = cfg.work / "state.json"
        st = read_json(self.path, {})
        st.setdefault("runs", {})
        st.setdefault("vms", {})
        st.setdefault("alerted_groups", [])
        st.setdefault("consecutive_failures", 0)
        st.setdefault("next_block", 0)
        st["consecutive_failures"] = 0  # a fresh start never inherits an earlier halt
        st.update(manifest=str(Path(args.manifest).resolve()), outroot=cfg.outroot, evidence=str(cfg.evidence),
                  slots={str(k): v for k, v in slots.items()})
        for r in rows:
            st["runs"].setdefault(r["run_id"], {"status": "pending", "attempt": 0, "name": r["run_id"],
                                               "group": r["group"], "history": []})
        for vm in slots:
            st["vms"].setdefault(str(vm), {"state": "up", "since": stamp()})
        self.st = st

    # -- small helpers
    def save(self):
        self.st["updated"] = stamp()
        write_json(self.path, self.st)

    def rec(self, run_id):
        return self.st["runs"][run_id]

    def runs_with(self, status):
        return [i for i, r in self.st["runs"].items() if r["status"] == status and i in self.by_id]

    def name_for(self, run_id, attempt):
        return run_id if attempt == 0 else "%s-retry%d" % (run_id, attempt)

    def exit_code(self, name):
        try:
            return int((self.cfg.evidence / (name + ".exit")).read_text().strip())
        except (OSError, ValueError):
            return None

    def name_used(self, name):
        code = self.exit_code(name)
        return (self.cfg.evidence / name).exists() or (code is not None and code != NOT_STARTED)

    def pidfile(self, name):
        return self.cfg.work / "pids" / (name + ".pid")

    def vm_up(self, vm):
        return self.st["vms"][str(vm)]["state"] == "up"

    def running_on(self, vm):
        return sum(1 for i in self.runs_with("running") if self.rec(i).get("vm") == vm)

    # -- VM state (alerts on transitions only)
    def mark_down(self, vm, why):
        v = self.st["vms"][str(vm)]
        if v["state"] == "up":
            v.update(state="down", since=stamp())
            self.cfg.alert("[경보] VM%d 접속 실패 (%s): VM%d 슬롯 %d개 멈춤, 다른 VM 은 계속" % (vm, why, vm, self.slots[vm]))
        self.last_probe[vm] = time.time()

    def mark_up(self, vm):
        v = self.st["vms"][str(vm)]
        if v["state"] != "up":
            v.update(state="up", since=stamp())
            self.cfg.alert("[알림] VM%d 접속 복구, 슬롯 다시 사용" % vm)

    def probe(self, vm):
        ok = self.cfg.vm_run(vm, "true", timeout=30)[0] == 0
        self.last_probe[vm] = time.time()
        self.mark_up(vm) if ok else self.mark_down(vm, "probe")
        return ok

    def scan(self, vm):
        """{name: (robots, exit_code|None)} for result folders on the VM, or None if the VM cannot be read."""
        rc, out = self.cfg.vm_run(vm, SCAN % shlex.quote(self.cfg.outroot), timeout=120)
        if rc != 0:
            self.mark_down(vm, "scan")
            return None
        self.mark_up(vm)
        listing = {}
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                listing[parts[0]] = (set(x for x in parts[1].split(",") if x), int(parts[2]) if re.fullmatch(r"-?\d+", parts[2]) else None)
        return listing

    def complete(self, run_id, name, listing):
        robots = set(self.by_id[run_id]["robots"].split(","))
        info = listing.get(name)
        return bool(info) and robots <= info[0] and info[1] in (None, 0) and self.exit_code(name) == 0

    # -- finishing an attempt
    def finish(self, run_id, rc, listing=None):
        rec = self.rec(run_id)
        name, vm = rec["name"], rec.get("vm")
        rec.update(ended=stamp(), rc=rc)
        rec.pop("pid", None)
        self.pidfile(name).unlink(missing_ok=True)
        entry = {"name": name, "vm": vm, "port": rec.get("port"), "started": rec.get("started"), "ended": rec["ended"], "rc": rc}
        if rc == NOT_STARTED:  # never started: does not use a retry
            rec.update(status="pending", vm=None, port_block=None)
            rec["history"].append(dict(entry, result="vm_unreachable"))
            self.mark_down(vm, "launcher rc=99")
            return
        rec["port_block"] = None
        if rc == 0:
            if listing is None:
                listing = self.scan(vm) if vm else None
            if listing is None:
                rec["status"] = "verifying"  # cannot check != incomplete: keep, never requeue
                return
            if self.complete(run_id, name, listing):
                rec["status"] = "done"
                self.st["consecutive_failures"] = 0
                rec["history"].append(dict(entry, result="done"))
                return
            result = "incomplete_results"
        else:
            result = "interrupted" if rc is None else "rc=%s" % rc
            if rc == 255 and vm:
                self.probe(vm)
        rec["history"].append(dict(entry, result=result))
        if rc is not None:  # an interrupted attempt (reboot, killed launcher) says nothing about the code or the VM
            self.st["consecutive_failures"] += 1
        if self.st["consecutive_failures"] >= self.a.abort_after:
            self.halt = True
            self.cfg.alert("[경보] 연속 실패 %d건, 새 실행 중지 (%s)" % (self.st["consecutive_failures"], run_id))
        if rec["attempt"] < self.a.max_retries:
            rec["attempt"] += 1
            rec.update(status="pending", name=self.name_for(run_id, rec["attempt"]), retry_front=True)
        else:
            rec["status"] = "failed"
            rec["reason"] = result

    # -- resume
    def reconcile(self):
        for vm in self.slots:
            self.probe(vm)
        listing = {vm: self.scan(vm) for vm in self.slots if self.vm_up(vm)}
        for run_id in list(self.st["runs"]):
            if run_id not in self.by_id:
                continue
            rec = self.rec(run_id)
            if rec["status"] == "running":
                pid = rec.get("pid")
                if pid is None and self.pidfile(rec["name"]).exists():
                    pid = int(self.pidfile(rec["name"]).read_text() or 0)
                if pid_alive(pid, rec["name"], "launch_team_run_v3"):
                    rec["pid"] = pid
                    print("%s 이어받음 %s (VM%s, pid %s)" % (stamp(), rec["name"], rec.get("vm"), pid), flush=True)
                else:
                    code = self.exit_code(rec["name"])
                    print("%s 멈춘 사이 끝남 %s rc=%s" % (stamp(), rec["name"], code), flush=True)
                    self.finish(run_id, code, listing.get(rec.get("vm")))
            elif rec["status"] == "verifying":
                self.reverify(run_id)
            elif rec["status"] == "failed" and rec["attempt"] < self.a.max_retries:
                rec.update(status="pending", attempt=rec["attempt"] + 1)
                rec["name"] = self.name_for(run_id, rec["attempt"])
        for run_id in self.runs_with("pending"):  # state lost or run finished while we were down
            self.resolve_pending(run_id, listing)
        self.save()

    def resolve_pending(self, run_id, listing):
        rec = self.rec(run_id)
        for attempt in range(self.a.max_retries + 1):
            name = self.name_for(run_id, attempt)
            if self.exit_code(name) == 0 and (self.cfg.evidence / name).exists():
                found = [vm for vm, lst in listing.items() if lst is not None and self.complete(run_id, name, lst)]
                if found:
                    rec.update(status="done", attempt=attempt, name=name, vm=found[0])
                    return
                if any(lst is None for lst in listing.values()) or len(listing) < len(self.slots):
                    rec.update(status="verifying", attempt=attempt, name=name)  # a VM is unreachable: do not requeue
                    return
            if not self.name_used(name):
                rec.update(attempt=attempt, name=name)
                return
        rec.update(status="failed", reason="all attempt names used", attempt=self.a.max_retries)

    # -- ports: each run owns a block of `span` ports (launcher bumps +1 inside it only)
    def alloc_block(self):
        a = self.a
        count = (a.port_max - a.port_base) // a.port_span
        used = {r.get("port_block") for r in self.st["runs"].values() if r["status"] == "running"}
        for k in range(count):
            idx = (self.st["next_block"] + k) % count
            base = a.port_base + idx * a.port_span
            if base in used or any(port_busy(base + j) for j in range(a.port_span)):
                continue
            self.st["next_block"] = idx + 1
            return base
        return None

    # -- launching
    def pick_vm(self):
        free = [vm for vm in sorted(self.slots) if self.vm_up(vm) and self.running_on(vm) < self.slots[vm]]
        return min(free, key=lambda vm: self.running_on(vm) / self.slots[vm]) if free else None

    def launch(self, run_id, vm):
        rec, row = self.rec(run_id), self.by_id[run_id]
        while self.name_used(rec["name"]):
            if rec["attempt"] >= self.a.max_retries:
                rec.update(status="failed", reason="all attempt names used")
                return
            rec["attempt"] += 1
            rec["name"] = self.name_for(run_id, rec["attempt"])
        host, block = self.cfg.host(vm), self.alloc_block()
        if host is None:
            self.mark_down(vm, "no IP file")
            return
        if block is None:
            return
        name = rec["name"]
        env = dict(os.environ, VMHOST=host, VMRUN=row["vmrun"], OUTROOT=self.cfg.outroot, LEADER=row["leader"],
                   ROBOTS=row["robots"], MODEL=row["model"], SERVER_ARGS=row["server_args"], BRAIN_DIR=self.cfg.brain_dir,
                   EVIDENCE_DIR=str(self.cfg.evidence), ALERTS_LOG=str(self.cfg.alerts), PORT_SPAN=str(self.a.port_span),
                   RUN_ALERT="1" if self.a.run_alerts else "0", PIDFILE=str(self.pidfile(name)),
                   NO_BRAIN="1" if no_brain(row["vm_args"]) else "0")
        cmd = ["bash", str(HERE / "launch_team_run_v3.sh"), row["sha"], row["team"], row["seed"], name, str(block),
               "--scenes", row["scene_file"], "--scene-id", row["scene_id"]] + shlex.split(row["vm_args"])
        rec.update(status="running", vm=vm, port=block, port_block=block, started=stamp(), ended=None, rc=None, pid=None)
        rec.pop("retry_front", None)
        self.save()  # recorded before the process exists: a crash here is read as "interrupted", never as a lost run
        try:
            with open(self.cfg.evidence / (name + ".launch.log"), "wb") as logf:
                proc = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=logf, stderr=subprocess.STDOUT,
                                        start_new_session=True)
        except OSError as error:
            rec["status"] = "pending"
            print("launch failed: %s" % error, file=sys.stderr)
            return
        self.pidfile(name).write_text(str(proc.pid))
        rec["pid"] = proc.pid
        self.procs[run_id] = proc
        self.save()
        print("%s 시작 %s (VM%d, 포트 %d, pid %d)" % (stamp(), name, vm, block, proc.pid), flush=True)

    def launch_new(self):
        if self.halt or self.stopping:
            return
        order = sorted(self.runs_with("pending"), key=lambda i: (not self.rec(i).get("retry_front"), self.rows.index(self.by_id[i])))
        for run_id in order:
            vm = self.pick_vm()
            if vm is None:
                break
            self.launch(run_id, vm)

    def reap(self):
        for run_id in self.runs_with("running"):
            rec = self.rec(run_id)
            proc = self.procs.get(run_id)
            if proc is not None:
                rc = proc.poll()
                if rc is None:
                    continue
                rc = rc if rc >= 0 else None
            elif pid_alive(rec.get("pid"), rec["name"], "launch_team_run_v3"):
                continue
            else:
                rc = self.exit_code(rec["name"])
            self.procs.pop(run_id, None)
            print("%s 끝 %s rc=%s" % (stamp(), rec["name"], rc), flush=True)
            self.finish(run_id, rc)

    def reverify(self, run_id):
        """A finished run whose VM could not be read: decide only when every VM that may hold it was readable."""
        rec = self.rec(run_id)
        vms = [rec["vm"]] if rec.get("vm") else sorted(self.slots)
        lists = {vm: self.scan(vm) if self.vm_up(vm) else None for vm in vms}
        found = [vm for vm, lst in lists.items() if lst is not None and self.complete(run_id, rec["name"], lst)]
        if found:
            rec.update(status="done", vm=found[0], ended=rec.get("ended") or stamp())
            self.st["consecutive_failures"] = 0
            rec["history"].append({"name": rec["name"], "vm": found[0], "result": "done(verified later)"})
        elif all(lst is not None for lst in lists.values()):
            rec["vm"] = vms[0]
            self.finish(run_id, 0, lists[vms[0]])

    def recheck(self):
        for vm in self.slots:
            if not self.vm_up(vm) and time.time() - self.last_probe.get(vm, 0) >= self.a.probe_interval:
                self.probe(vm)
        for run_id in self.runs_with("verifying"):
            self.reverify(run_id)

    def group_alerts(self):
        for g in sorted({r["group"] for r in self.rows}):
            ids = [r["run_id"] for r in self.rows if r["group"] == g]
            states = [self.rec(i)["status"] for i in ids]
            if g not in self.st["alerted_groups"] and all(s in ("done", "failed") for s in states):
                self.st["alerted_groups"].append(g)
                self.cfg.alert("[묶음 끝] 그룹 %s: %d건 중 완료 %d, 실패 %d" % (g, len(ids), states.count("done"), states.count("failed")))
        states = [self.rec(r["run_id"])["status"] for r in self.rows]
        if "ALL" not in self.st["alerted_groups"] and all(s in ("done", "failed") for s in states):
            self.st["alerted_groups"].append("ALL")
            self.cfg.alert("[묶음 끝] 전체 %d건 중 완료 %d, 실패 %d (%s)" % (len(states), states.count("done"), states.count("failed"),
                                                                  Path(self.a.manifest).name))

    def loop(self):
        while True:
            self.reap()
            self.recheck()
            self.launch_new()
            self.group_alerts()
            self.save()
            if self.stopping:
                return 130
            running = self.runs_with("running")
            pending = [i for i in self.runs_with("pending")]
            verifying = self.runs_with("verifying")
            if not running:
                if self.halt:
                    return 4
                if not pending and not verifying:
                    return 1 if self.runs_with("failed") else 0
                if not any(self.vm_up(vm) for vm in self.slots) or (not pending and verifying and not all(self.vm_up(vm) for vm in self.slots)):
                    self.cfg.alert("[경보] VM 접속 불가로 진행 못함, 디스패처 중지 (대기 %d, 검증대기 %d). VM 을 켠 뒤 다시 실행" % (len(pending), len(verifying)))
                    return 3
            time.sleep(self.a.tick)


def port_busy(port):
    with socket.socket() as s:
        try:
            s.bind(("0.0.0.0", port))
            return False
        except OSError:
            return True


# ------------------------------------------------------------------ commands
def parse_slots(text):
    slots = {}
    for part in text.split(","):
        vm, n = part.split("=")
        slots[int(vm)] = int(n)
        if slots[int(vm)] < 1 or int(vm) not in (1, 2):
            raise ValueError("bad --slots " + text)
    return slots


def cmd_run(a):
    work = Path(a.dir).resolve()
    prior = read_json(work / "state.json", {})
    requested = a.outroot or os.environ.get("OUTROOT")
    if requested and prior.get("outroot") and requested != prior["outroot"]:
        print("state.json was made with --outroot %s, not %s; a different folder would re-run finished work. "
              "Use a new --dir for a new batch." % (prior["outroot"], requested), file=sys.stderr)
        return 2
    cfg = Cfg(work, requested or prior.get("outroot"))
    if prior.get("evidence") and str(cfg.evidence) != prior["evidence"]:
        print("state.json was made with EVIDENCE_DIR %s, not %s; use the same one (or a new --dir)." % (prior["evidence"], cfg.evidence),
              file=sys.stderr)
        return 2
    cfg.work.mkdir(parents=True, exist_ok=True)
    try:
        rows = load_manifest(a.manifest, real=not cfg.fake)
    except ValueError as error:
        print("manifest rejected: %s" % error, file=sys.stderr)
        return 2
    slots = parse_slots(a.slots)
    if (a.port_max - a.port_base) // a.port_span < 1:   # 2026-11-16: base >= max left zero blocks and the run waited silently
        print("dispatcher: no port block: --port-base %d --port-max %d --port-span %d" % (a.port_base, a.port_max, a.port_span), file=sys.stderr)
        return 2
    if not cfg.fake and not a.go:
        by_group = {}
        for r in rows:
            by_group[r["group"]] = by_group.get(r["group"], 0) + 1
        print("DRY RUN (no --go): %d runs, groups %s, slots %s, outroot %s" % (len(rows), by_group, slots, cfg.outroot))
        print("would start e.g.: %s %s %s %s ... --scenes %s --scene-id %s" % (rows[0]["vmrun"], rows[0]["sha"], rows[0]["team"],
                                                                          rows[0]["run_id"], rows[0]["scene_file"], rows[0]["scene_id"]))
        shown = set()
        for r in rows:  # first row of each group, with everything that differs between groups
            if r["group"] in shown:
                continue
            shown.add(r["group"])
            print("  [%s] %s: team %s, robots %s, leader %s, model %s, planner server %s%s\n      VM: %s %s %s %s --scenes %s --scene-id %s %s%s"
                  % (r["group"], r["run_id"], r["team"], r["robots"], r["leader"], r["model"], "NONE (--fixed)" if no_brain(r["vm_args"]) else "yes",
                     (", server_args: " + r["server_args"]) if r["server_args"] else "", r["vmrun"], r["sha"], r["seed"], r["run_id"],
                     r["scene_file"], r["scene_id"], r["vm_args"], "" if no_brain(r["vm_args"]) else " (+ --brain-url)"))
        return 0
    lock = open(cfg.work / "dispatch.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another dispatcher already holds %s" % (cfg.work / "dispatch.lock"), file=sys.stderr)
        return 2
    (cfg.work / "dispatch.pid").write_text(str(os.getpid()))
    d = Dispatcher(cfg, rows, slots, a)
    signal.signal(signal.SIGTERM, lambda *_: setattr(d, "stopping", True))
    signal.signal(signal.SIGINT, lambda *_: setattr(d, "stopping", True))
    print("%s dispatcher 시작: %d건, 슬롯 %s" % (stamp(), len(rows), slots), flush=True)
    d.reconcile()
    code = d.loop()
    d.save()
    (cfg.work / "dispatch.pid").unlink(missing_ok=True)
    print("%s dispatcher 끝 (코드 %d)" % (stamp(), code), flush=True)
    return code


def cmd_status(a):
    work = Path(a.dir).resolve()
    st = read_json(work / "state.json")
    if not st:
        print("state.json 없음: %s" % work)
        return 1
    pid = (work / "dispatch.pid").read_text().strip() if (work / "dispatch.pid").exists() else None
    alive = pid_alive(pid, "run", "dispatch.py")
    runs = st["runs"]
    counts = {k: sum(r["status"] == k for r in runs.values()) for k in LABEL}
    print("갱신 %s | 디스패처 %s | manifest %s" % (st.get("updated"), "실행 중(pid %s)" % pid if alive else "멈춤", st.get("manifest")))
    print("전체 %d건: " % len(runs) + ", ".join("%s %d" % (LABEL[k], counts[k]) for k in LABEL))
    for g in sorted({r["group"] for r in runs.values()}):
        gr = [r for r in runs.values() if r["group"] == g]
        print("  그룹 %-9s %3d건: " % (g, len(gr)) + ", ".join("%s %d" % (LABEL[k], sum(r["status"] == k for r in gr)) for k in LABEL))
    for vm, v in sorted(st["vms"].items()):
        n = sum(r["status"] == "running" and str(r.get("vm")) == vm for r in runs.values())
        print("  VM%s %s(%s 부터) 슬롯 %s, 실행 %d" % (vm, v["state"], v["since"], st["slots"].get(vm), n))
    for i, r in runs.items():
        if r["status"] == "running":
            print("  실행 %s (VM%s, 포트 %s, 시작 %s)" % (r["name"], r.get("vm"), r.get("port"), r.get("started")))
    for i, r in runs.items():
        if r["status"] == "failed":
            print("  실패 %s: %s (시도 %d회)" % (i, r.get("reason"), len(r["history"])))
    for i, r in runs.items():
        if r["status"] == "verifying":
            print("  검증대기 %s (VM%s 접속 불가로 결과 확인 못함)" % (r["name"], r.get("vm")))
    return 0


def cmd_stop(a):
    work = Path(a.dir).resolve()
    pid = (work / "dispatch.pid").read_text().strip() if (work / "dispatch.pid").exists() else None
    if pid and pid_alive(pid, "run", "dispatch.py"):
        os.kill(int(pid), signal.SIGTERM)
        print("dispatcher %s 에 TERM" % pid)
    else:
        print("dispatcher 실행 중 아님")
    if a.runs:
        for f in sorted((work / "pids").glob("*.pid")):
            name, p = f.name[:-4], f.read_text().strip()
            if pid_alive(p, name, "launch_team_run_v3"):
                os.kill(int(p), signal.SIGTERM)
                print("launcher %s (pid %s) 에 TERM" % (name, p))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--manifest", required=True, type=Path)
    r.add_argument("--dir", default=str(HERE), help="state.json, pids/, lock live here")
    r.add_argument("--slots", default="1=5,2=2", help="VM=concurrent runs, e.g. 1=5,2=2")
    r.add_argument("--outroot", help="absolute VM result folder (default $OUTROOT; one of the two is required)")
    r.add_argument("--max-retries", type=int, default=1)
    r.add_argument("--abort-after", type=int, default=8, help="stop launching after N consecutive failed attempts")
    r.add_argument("--tick", type=float, default=2.0)
    r.add_argument("--probe-interval", type=float, default=60.0)
    r.add_argument("--port-base", type=int, default=12000)
    r.add_argument("--port-max", type=int, default=12600)
    r.add_argument("--port-span", type=int, default=10)
    r.add_argument("--run-alerts", action="store_true", help="also let each launcher write its own ALERTS line")
    r.add_argument("--go", action="store_true", help="really run (paid LLM calls); without it only a dry plan is printed")
    s = sub.add_parser("status")
    s.add_argument("--dir", default=str(HERE))
    t = sub.add_parser("stop")
    t.add_argument("--dir", default=str(HERE))
    t.add_argument("--runs", action="store_true", help="also TERM the running launchers")
    a = p.parse_args(argv)
    return {"run": cmd_run, "status": cmd_status, "stop": cmd_stop}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
