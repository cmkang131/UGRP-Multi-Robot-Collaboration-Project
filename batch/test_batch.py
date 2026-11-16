"""Tests for the batch tools. Run: python3 -B -m unittest -v   (in this folder). Fake runner only: no ssh, VM, LLM or real ALERTS.log."""
import csv
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from argparse import Namespace
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("VM_SCENE_DIR", "/vmscenes")   # the scene folder on the VMs; make_manifest reads it when it is imported
COMPARE = HERE.parent / "analysis"
SCENES = HERE.parent / "scenes"
import collect  # noqa: E402
import dispatch  # noqa: E402
import make_manifest  # noqa: E402

PY = [sys.executable, "-B"]


class Sandbox:
    """A throw-away world: fake VM root, evidence, alerts, work dir, and an `ssh` stub that records any call."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="batch-test-"))
        self.vm, self.ev, self.work = self.root / "vm", self.root / "ev", self.root / "work"
        self.alerts, self.sshlog = self.root / "ALERTS.log", self.root / "ssh-called"
        bindir = self.root / "bin"
        bindir.mkdir()
        (bindir / "ssh").write_text('#!/bin/sh\necho "$@" >> %s\nexit 99\n' % self.sshlog)
        (bindir / "ssh").chmod(0o755)
        self.env = dict(os.environ, PATH="%s:%s" % (bindir, os.environ["PATH"]), FAKE_LAUNCH="1", FAKE_VM_ROOT=str(self.vm),
                        ALERTS_LOG=str(self.alerts), EVIDENCE_DIR=str(self.ev), FAKE_SLEEP="1.0", PYTHONDONTWRITEBYTECODE="1")
        for key in ("FAKE_FAIL_ONCE", "FAKE_FAIL_ALWAYS", "FAKE_INCOMPLETE", "OUTROOT", "VMHOST"):
            self.env.pop(key, None)
        self.manifest = self.root / "manifest.csv"

    def write_manifest(self, rows):
        make_manifest.write_manifest(rows, self.manifest)

    def start(self, *extra, **env):
        extra = list(extra) if "--outroot" in extra else list(extra) + ["--outroot", "/vmroot/team-main"]   # the dispatcher has no default
        cmd = PY + [str(HERE / "dispatch.py"), "run", "--manifest", str(self.manifest), "--dir", str(self.work), "--tick", "0.2",
                    "--probe-interval", "0.5"] + extra
        return subprocess.Popen(cmd, env=dict(self.env, **env), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def run(self, *extra, **env):
        p = self.start(*extra, **env)
        out = p.communicate(timeout=120)[0]
        return p.returncode, out

    def state(self):
        try:
            return json.loads((self.work / "state.json").read_text())
        except (OSError, ValueError):
            return None

    def status(self):
        return subprocess.run(PY + [str(HERE / "dispatch.py"), "status", "--dir", str(self.work)], env=self.env, capture_output=True, text=True).stdout

    def events(self):
        rows = []
        try:
            for line in (self.vm / "events.log").read_text().splitlines():
                t, kind, name, host, rc = line.split("\t")
                rows.append((float(t), kind, name, host, rc))
        except OSError:
            pass
        return rows

    def peak(self):
        """Peak concurrent fake runs per host, from start/end events."""
        cur, peak = {}, {}
        for t, kind, name, host, rc in sorted(self.events()):
            cur[host] = cur.get(host, 0) + (1 if kind == "start" else -1)
            peak[host] = max(peak.get(host, 0), cur[host])
        return peak

    def starts(self):
        return [name for t, kind, name, host, rc in self.events() if kind == "start"]

    def alert_lines(self):
        return self.alerts.read_text().splitlines() if self.alerts.exists() else []

    def cleanup(self):
        pids = self.work / "pids"
        for f in pids.glob("*.pid") if pids.exists() else []:  # by pid file only, never by pattern
            pid = f.read_text().strip()
            if dispatch.pid_alive(pid, f.name[:-4], "launch_team_run_v3"):
                os.killpg(int(pid), signal.SIGKILL)
        shutil.rmtree(self.root, ignore_errors=True)


def rows20():
    rows = make_manifest.shuffled(make_manifest.build_rows(), 20261115)[:20]
    assert len(rows) == 20
    return rows


class Base(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)

    def tearDown(self):
        self.assertFalse(self.sb.sshlog.exists(), "real ssh was called")


class ManifestTests(Base):
    def test_generator_is_deterministic_and_valid(self):
        a = make_manifest.shuffled(make_manifest.build_rows(), 5)
        b = make_manifest.shuffled(make_manifest.build_rows(), 5)
        c = make_manifest.shuffled(make_manifest.build_rows(), 6)
        self.assertEqual([r["run_id"] for r in a], [r["run_id"] for r in b])
        self.assertNotEqual([r["run_id"] for r in a], [r["run_id"] for r in c])
        self.assertEqual(sorted(r["run_id"] for r in a), sorted(r["run_id"] for r in make_manifest.build_rows()))
        self.assertEqual(len({r["run_id"] for r in a}), len(a))
        self.assertEqual({r["group"] for r in a}, set(dispatch.GROUPS))
        self.sb.write_manifest(a)
        self.assertEqual(len(dispatch.load_manifest(self.sb.manifest)), len(a))

    def test_real_mode_rejects_placeholders_and_bad_rows(self):
        self.sb.write_manifest(rows20())
        dispatch.load_manifest(self.sb.manifest, real=False)
        with self.assertRaisesRegex(ValueError, "placeholder"):
            dispatch.load_manifest(self.sb.manifest, real=True)
        bad = rows20()
        bad[1]["run_id"] = bad[0]["run_id"]
        self.sb.write_manifest(bad)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            dispatch.load_manifest(self.sb.manifest)
        bad = rows20()
        bad[0]["leader"] = "r9"
        self.sb.write_manifest(bad)
        with self.assertRaisesRegex(ValueError, "leader"):
            dispatch.load_manifest(self.sb.manifest)

    def test_real_run_needs_go(self):
        self.sb.write_manifest(rows20()[:3])
        env = {k: v for k, v in self.sb.env.items() if not k.startswith("FAKE_")}
        env["EVIDENCE_DIR"] = str(self.sb.ev)
        r = subprocess.run(PY + [str(HERE / "dispatch.py"), "run", "--manifest", str(self.sb.manifest), "--dir", str(self.sb.work),
                                 "--outroot", "/vmroot/team-main"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)  # real mode: placeholders (TODO_SHA etc.) are refused
        self.assertIn("placeholder", r.stderr)
        self.sb.write_manifest([dict(r, sha="abc1234", model="z-ai/glm-5.3-flash", vm_args="--robot-tags", server_args="") for r in rows20()[:3]])
        r = subprocess.run(PY + [str(HERE / "dispatch.py"), "run", "--manifest", str(self.sb.manifest), "--dir", str(self.sb.work),
                                 "--outroot", "/vmroot/team-main"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DRY RUN", r.stdout)
        self.assertFalse((self.sb.work / "state.json").exists())
        self.assertEqual(list(self.sb.ev.glob("*")), [])


class PortTests(Base):
    def test_blocks_skip_busy_ports_and_running_blocks(self):
        self.sb.write_manifest(rows20()[:3])
        args = Namespace(manifest=self.sb.manifest, port_base=12000, port_max=12040, port_span=10, max_retries=1, abort_after=8)
        with mock.patch.dict(os.environ, self.sb.env):
            cfg = dispatch.Cfg(self.sb.work, "/x")
            d = dispatch.Dispatcher(cfg, dispatch.load_manifest(self.sb.manifest), {1: 1}, args)
        with socket.socket() as s:
            s.bind(("0.0.0.0", 12003))  # inside block 0
            first = d.alloc_block()
            self.assertEqual(first, 12010)
            rid = d.rows[0]["run_id"]
            d.rec(rid).update(status="running", port_block=first)
            second = d.alloc_block()
            self.assertEqual(second, 12020)
            self.assertNotEqual(second, first)


class LauncherTests(Base):
    def launch(self, name, **env):
        e = dict(self.sb.env, VMHOST="fakevm1", VMRUN="run_team_v31.sh", OUTROOT="/vmroot/out", ROBOTS="r1,r2", FAKE_SLEEP="0.1", **env)
        return subprocess.run(["bash", str(HERE / "launch_team_run_v3.sh"), "abc1234", "T1", "90721", name, "12000",
                               "--scenes", "/x/scenes.json", "--scene-id", "C01", "--robot-tags"], env=e, capture_output=True, text=True)

    def test_exit_file_server_args_and_name_reuse(self):
        r = self.launch("L-1", SERVER_ARGS="--pre-exchange --option-order reverse")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.sb.ev / "L-1.exit").read_text().strip(), "0")
        rec = json.loads((self.sb.ev / "L-1" / "brain-record.json").read_text())
        self.assertEqual(rec["server_args"], "--pre-exchange --option-order reverse")
        team = json.loads((self.sb.vm / "fakevm1/vmroot/out/L-1/team.json").read_text())
        self.assertIn("--robot-tags", team["fake"]["args"])
        self.assertIn("[팀 실행 끝] L-1", self.sb.alerts.read_text())
        again = self.launch("L-1")
        self.assertEqual(again.returncode, 98)
        self.assertEqual((self.sb.ev / "L-1.exit").read_text().strip(), "0")  # not overwritten

    def test_failure_code_vm_down_and_real_alerts_refused(self):
        r = self.launch("L-2", FAKE_FAIL_ALWAYS="L-2")
        self.assertEqual((r.returncode, (self.sb.ev / "L-2.exit").read_text().strip()), (1, "1"))
        (self.sb.vm / "fakevm1.down").touch()
        r = self.launch("L-3")
        self.assertEqual((r.returncode, (self.sb.ev / "L-3.exit").read_text().strip()), (99, "99"))
        self.assertFalse((self.sb.ev / "L-3").exists())
        env = {k: v for k, v in self.sb.env.items() if k != "ALERTS_LOG"}
        r = subprocess.run(["bash", str(HERE / "launch_team_run_v3.sh"), "a", "T0", "1", "L-4", "12000"],
                           env=dict(env, VMHOST="fakevm1", VMRUN="run_team_v31.sh", OUTROOT="/o"), capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


class RealBranchWithStubs(Base):
    """The non-fake path of the launcher, with stub `ssh` and a stub brain_server.py (still no network, no LLM)."""

    def setUp(self):
        super().setUp()
        self.calls = self.sb.root / "stub-calls"
        bindir = self.sb.root / "bin2"
        bindir.mkdir()
        (bindir / "ssh").write_text('#!/bin/sh\necho "ssh $*" >> %s\ncase " $* " in *" -R "*) exit ${STUB_SSH_RC:-0};; esac\nexit ${STUB_PREFLIGHT_RC:-0}\n' % self.calls)
        (bindir / "ssh").chmod(0o755)
        self.brain = self.sb.root / "brain"
        self.brain.mkdir()
        (self.brain / "brain_server.py").write_text(
            "import sys, time, pathlib\n"
            "open(%r, 'a').write('server ' + ' '.join(sys.argv[1:]) + '\\n')\n"
            "if '--bad-arg' in sys.argv: sys.exit(2)\n"
            "pathlib.Path(sys.argv[sys.argv.index('--log-dir') + 1]).mkdir(parents=True)\n"
            "time.sleep(30)\n" % str(self.calls))
        self.env = dict(self.sb.env, PATH="%s:%s" % (bindir, self.sb.env["PATH"]), BRAIN_DIR=str(self.brain), VMHOST="vmhost-1",
                        VM_USER="worker", VM_WORKDIR="vmwork", VMRUN="run_team_v31.sh", OUTROOT="/vmroot/team-main", ROBOTS="r1,r2,r3", LEADER="r2", MODEL="m/x")
        self.env.pop("FAKE_LAUNCH")

    def launch(self, name, **extra):
        return subprocess.run(["bash", str(HERE / "launch_team_run_v3.sh"), "abc1234", "T2", "90721", name, "12000", "--scenes", "/s.json",
                               "--scene-id", "C01", "--tag", "two words"], env=dict(self.env, **extra), capture_output=True, text=True)

    def test_command_lines_and_exit_file(self):
        r = self.launch("R-1", SERVER_ARGS="--pre-exchange --option-order reverse")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls.read_text()
        self.assertIn("server --team T2 --robots r1,r2,r3 --leader r2 --model m/x --port 12000 --log-dir %s/R-1 --pre-exchange --option-order reverse"
                      % self.sb.ev, calls)
        self.assertIn("-R 12000:localhost:12000 worker@vmhost-1 cd vmwork && mkdir -p .launch-pgid && setsid --wait sh -c 'echo $$ > .launch-pgid/$0; exec \"$@\"' R-1 timeout --kill-after=60 4.5h ./run_team_v31.sh abc1234 90721 "
                      "/vmroot/team-main R-1 --brain-url http://localhost:12000 --scenes /s.json --scene-id C01 --tag two\\ words", calls)
        self.assertEqual((self.sb.ev / "R-1.exit").read_text().strip(), "0")

    def test_ssh_failure_code_is_kept_and_server_dies_early_is_97(self):
        r = self.launch("R-2", STUB_PREFLIGHT_RC="255")
        self.assertEqual(r.returncode, 99)  # pre-flight `ssh true` failed: nothing started
        self.assertFalse((self.sb.ev / "R-2").exists())
        r = self.launch("R-4", STUB_SSH_RC="7")
        self.assertEqual((r.returncode, (self.sb.ev / "R-4.exit").read_text().strip()), (7, "7"))  # the VM run's code, not 0
        r = self.launch("R-3", SERVER_ARGS="--bad-arg")
        self.assertEqual(r.returncode, 97)
        self.assertEqual((self.sb.ev / "R-3.exit").read_text().strip(), "97")
        self.assertNotIn("-R 12000", self.calls.read_text().split("--bad-arg")[-1])

    def test_fixed_reference_plan_run_starts_no_planner_and_passes_no_brain_url(self):
        e = dict(self.env, NO_BRAIN="1")
        r = subprocess.run(["bash", str(HERE / "launch_team_run_v3.sh"), "abc1234", "T0", "90721", "REF-1", "12000", "--scenes", "/s.json",
                            "--scene-id", "C01", "--fixed", "oracle"], env=e, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls.read_text()
        self.assertNotIn("server ", calls)       # no brain_server.py
        self.assertNotIn("--brain-url", calls)   # run_team_carry.py would otherwise ignore --fixed oracle
        self.assertNotIn(" -R ", calls)
        self.assertIn("./run_team_v31.sh abc1234 90721 /vmroot/team-main REF-1 --scenes /s.json --scene-id C01 --fixed oracle", calls)
        self.assertEqual((self.sb.ev / "REF-1.exit").read_text().strip(), "0")
        self.assertTrue((self.sb.ev / "REF-1").is_dir())  # the name stays used
        again = subprocess.run(["bash", str(HERE / "launch_team_run_v3.sh"), "abc1234", "T0", "90721", "REF-1", "12000"], env=e,
                               capture_output=True, text=True)
        self.assertEqual(again.returncode, 98)


class RealManifestTests(Base):
    def test_presets_have_the_frozen_shape_and_pass_the_checker(self):
        import check_manifests
        out = self.sb.root / "manifests"
        make_manifest.main_real(Namespace(preset="all", outdir=out, shuffle_seed=20261115, baseline_first=True))
        self.assertEqual(check_manifests.main(["--dir", str(out)]), 0)
        core = dispatch.load_manifest(out / "core.csv", real=True)
        self.assertEqual([r["group"] for r in core[:40]], ["baseline"] * 40)
        self.assertTrue(all(dispatch.no_brain(r["vm_args"]) == (r["group"] in ("baseline", "random_baseline")) for r in core))
        self.assertEqual(len({r["vm_args"] for r in core if r["group"] == "mainA"}), 1)  # analyze_main: one arm for the main group
        again = [r["run_id"] for r in make_manifest.core_rows(20261115, True)]
        self.assertEqual(again, [r["run_id"] for r in core])  # deterministic
        # the checker really fails on a bad row (unknown scene)
        text = (out / "confirm2.csv").read_text().replace(",C01,", ",C99,", 1)
        (out / "confirm2.csv").write_text(text)
        self.assertEqual(check_manifests.main(["--dir", str(out)]), 1)


class ScenarioTests(Base):
    def wait_for(self, cond, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.05)
        return False

    def running(self, st=None):
        st = st or self.sb.state() or {"runs": {}}
        out = {}
        for r in st["runs"].values():
            if r["status"] == "running":
                out[r.get("vm")] = out.get(r.get("vm"), 0) + 1
        return out

    def test_kill_restart_retry_and_slots(self):
        ids = [r["run_id"] for r in rows20()]
        once, always, incomplete = ids[0], ids[1], ids[2]
        self.sb.write_manifest(rows20())
        env = dict(FAKE_FAIL_ONCE=once, FAKE_FAIL_ALWAYS=always, FAKE_INCOMPLETE=incomplete, FAKE_SLEEP="2.2")
        peak_state = {}

        def sample():
            for vm, n in self.running().items():
                peak_state[vm] = max(peak_state.get(vm, 0), n)
            return sum(self.running().values()) >= 7

        # 1st dispatcher: kill -9 while 5+2 runs are in flight
        p1 = self.sb.start(**env)
        self.assertTrue(self.wait_for(sample), "7 runs never in flight")
        p1.kill()
        p1.communicate()
        inflight = self.sb.status()
        print("\n--- status at kill time ---\n" + inflight)
        self.assertIn("실행", inflight)
        self.assertIn("디스패처 멈춤", inflight)
        # 2nd dispatcher adopts the live launchers (they count against the slots), then is killed too
        p2 = self.sb.start(**env)
        self.wait_for(lambda: (sample(), sum(r["status"] == "done" for r in (self.sb.state() or {"runs": {}})["runs"].values()) >= 8)[1])
        p2.kill()
        out2 = p2.communicate()[0]
        print("--- 2nd dispatcher log (head) ---\n" + "\n".join(out2.splitlines()[:12]))
        self.assertIn("이어받음", out2)  # live launchers were adopted, not relaunched
        time.sleep(2.5)  # whatever is in flight finishes unattended; its .exit files appear
        # 3rd dispatcher finishes everything
        p3 = self.sb.start(**env)
        end = time.time() + 60
        while p3.poll() is None and time.time() < end:
            sample()
            time.sleep(0.05)
        out3 = p3.communicate(timeout=10)[0]
        self.assertEqual(p3.returncode, 1, out3)  # 1 = finished with a failed run
        st = self.sb.state()
        statuses = {i: r["status"] for i, r in st["runs"].items()}
        print("--- final counts ---", {k: list(statuses.values()).count(k) for k in set(statuses.values())})
        self.assertEqual(len(statuses), 20)
        self.assertEqual({k for k, v in statuses.items() if v == "failed"}, {always})
        self.assertEqual(sum(v == "done" for v in statuses.values()), 19)
        starts = self.sb.starts()
        self.assertEqual(len(starts), len(set(starts)), "a name was launched twice")
        expected = set(ids) | {once + "-retry1", always + "-retry1", incomplete + "-retry1"}
        self.assertEqual(set(starts), expected)
        self.assertEqual(st["runs"][once]["name"], once + "-retry1")
        self.assertEqual(st["runs"][incomplete]["name"], incomplete + "-retry1")
        self.assertEqual(len(st["runs"][always]["history"]), 2)
        self.assertEqual([h["result"] for h in st["runs"][once]["history"]], ["rc=1", "done"])
        self.assertEqual([h["result"] for h in st["runs"][incomplete]["history"]], ["incomplete_results", "done"])
        peak = self.sb.peak()
        print("--- peak concurrency (events) %s, (state samples) %s ---" % (peak, peak_state))
        self.assertLessEqual(peak.get("fakevm1", 0), 5)
        self.assertLessEqual(peak.get("fakevm2", 0), 2)
        self.assertLessEqual(peak_state.get(1, 0), 5)
        self.assertLessEqual(peak_state.get(2, 0), 2)
        self.assertGreaterEqual(peak_state.get(1, 0), 4)
        alerts = self.sb.alert_lines()
        self.assertEqual(sum("[묶음 끝] 전체 20건 중 완료 19, 실패 1" in a for a in alerts), 1, alerts)
        for g in dispatch.GROUPS:
            self.assertEqual(sum("[묶음 끝] 그룹 %s:" % g in a for a in alerts), 1, alerts)
        self.assertFalse(any("[경보]" in a for a in alerts), alerts)
        # a 4th start does nothing: nothing launched, same result
        n = len(self.sb.starts())
        code, out = self.sb.run(**env)
        self.assertEqual((code, len(self.sb.starts())), (1, n), out)
        print("--- status at the end ---\n" + self.sb.status())

    def test_vm_down_at_start_keeps_other_vm_and_does_not_requeue(self):
        self.sb.write_manifest(rows20())
        (self.sb.vm / "fakevm2.down").parent.mkdir(parents=True, exist_ok=True)
        (self.sb.vm / "fakevm2.down").touch()
        code, out = self.sb.run(FAKE_SLEEP="0.3")
        self.assertEqual(code, 0, out)
        self.assertEqual({h for t, k, n, h, rc in self.sb.events()}, {"fakevm1"})
        self.assertLessEqual(self.sb.peak()["fakevm1"], 5)
        alerts = self.sb.alert_lines()
        self.assertEqual(sum("[경보] VM2 접속 실패" in a for a in alerts), 1, alerts)
        n = len(self.sb.starts())
        code, out = self.sb.run()  # restart with VM2 still down: no duplicate alert, nothing relaunched
        self.assertEqual((code, len(self.sb.starts())), (0, n), out)
        self.assertEqual(sum("[경보] VM2 접속 실패" in a for a in self.sb.alert_lines()), 1)

    def test_unreadable_vm_never_requeues_finished_runs(self):
        self.sb.write_manifest(rows20())
        code, out = self.sb.run(FAKE_SLEEP="0.3")
        self.assertEqual(code, 0, out)
        on2 = [i for i, r in self.sb.state()["runs"].items() if r["vm"] == 2]
        self.assertTrue(on2, "VM2 ran nothing")
        n = len(self.sb.starts())
        (self.sb.work / "state.json").unlink()  # state lost + VM2 unreachable
        (self.sb.vm / "fakevm2.down").touch()
        code, out = self.sb.run()
        self.assertEqual(code, 3, out)
        st = self.sb.state()
        self.assertEqual(sorted(i for i, r in st["runs"].items() if r["status"] == "verifying"), sorted(on2))
        self.assertEqual(sum(r["status"] == "done" for r in st["runs"].values()), 20 - len(on2))
        self.assertEqual(len(self.sb.starts()), n, "something was relaunched")
        (self.sb.vm / "fakevm2.down").unlink()  # VM2 back
        code, out = self.sb.run()
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.sb.starts()), n)
        self.assertTrue(all(r["status"] == "done" for r in self.sb.state()["runs"].values()))
        self.assertTrue(any("[알림] VM2 접속 복구" in a for a in self.sb.alert_lines()))

    def test_vm_goes_down_midway(self):
        self.sb.write_manifest(rows20())
        p = self.sb.start()
        self.assertTrue(self.wait_for(lambda: len(self.sb.starts()) >= 7))
        (self.sb.vm / "fakevm2.down").touch()
        out = p.communicate(timeout=90)[0]
        self.assertEqual(p.returncode, 3, out)
        st = self.sb.state()
        alerts = self.sb.alert_lines()
        self.assertEqual(sum("[경보] VM2 접속 실패" in a for a in alerts), 1, alerts)
        done_or_verifying = {r["status"] for r in st["runs"].values()}
        self.assertEqual(done_or_verifying, {"done", "verifying"})
        self.assertTrue(all(r["vm"] == 2 for r in st["runs"].values() if r["status"] == "verifying"))
        starts = self.sb.starts()
        self.assertEqual(len(starts), len(set(starts)))
        self.assertEqual(len(starts), 20)  # a launch refused for an unreachable VM is not a retry and not a start


class InterruptedTests(Base):
    def test_running_record_with_dead_launcher_becomes_retry(self):
        self.sb.write_manifest(rows20()[:2])
        args = Namespace(manifest=self.sb.manifest, port_base=12000, port_max=12100, port_span=10, max_retries=1, abort_after=8,
                         probe_interval=1, tick=0.1, run_alerts=False)
        rows = dispatch.load_manifest(self.sb.manifest)
        with mock.patch.dict(os.environ, self.sb.env):
            cfg = dispatch.Cfg(self.sb.work, "/vmroot/out")
            d = dispatch.Dispatcher(cfg, rows, {1: 1}, args)
            rid = rows[0]["run_id"]
            d.rec(rid).update(status="running", vm=1, pid=999999, port=12000, port_block=12000)
            (self.sb.ev / rid).mkdir(parents=True)  # the interrupted attempt left its record dir, but no .exit
            d.reconcile()
        rec = d.rec(rid)
        self.assertEqual((rec["status"], rec["name"], rec["attempt"]), ("pending", rid + "-retry1", 1))
        self.assertEqual(rec["history"][0]["result"], "interrupted")


class ResumeSafetyTests(Base):
    def make_dispatcher(self, rows, slots=None):
        args = Namespace(manifest=self.sb.manifest, port_base=12000, port_max=12600, port_span=10, max_retries=1, abort_after=8,
                         probe_interval=1, tick=0.1, run_alerts=False)
        with mock.patch.dict(os.environ, self.sb.env):
            return dispatch.Dispatcher(dispatch.Cfg(self.sb.work, "/vmroot/team-main"), rows, slots or {1: 5, 2: 2}, args)

    def test_dead_running_records_and_old_halt_do_not_stop_a_restart(self):
        self.sb.write_manifest(rows20())
        rows = dispatch.load_manifest(self.sb.manifest)
        d = self.make_dispatcher(rows)
        for r in rows[:7]:  # like a server reboot with 7 runs in flight
            d.rec(r["run_id"]).update(status="running", vm=1, pid=999999, port=12000, port_block=12000)
        d.st["consecutive_failures"] = 9  # left over from an earlier halt
        d.save()
        code, out = self.sb.run(FAKE_SLEEP="0.2")
        self.assertEqual(code, 0, out)
        self.assertFalse(any("[경보]" in a for a in self.sb.alert_lines()), self.sb.alert_lines())
        self.assertTrue(all(r["status"] == "done" for r in self.sb.state()["runs"].values()))

    def test_rc99_does_not_use_a_retry_and_reuses_the_name(self):
        self.sb.write_manifest(rows20()[:3])
        rows = dispatch.load_manifest(self.sb.manifest)
        rid = rows[0]["run_id"]
        (self.sb.vm / "fakevm2.down").parent.mkdir(parents=True, exist_ok=True)
        (self.sb.vm / "fakevm2.down").touch()
        env = dict(self.sb.env, VMHOST="fakevm2", VMRUN="run_team_v31.sh", OUTROOT="/vmroot/team-main", ROBOTS="r1,r2")
        r = subprocess.run(["bash", str(HERE / "launch_team_run_v3.sh"), "abc", "T0", "1", rid, "12000"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 99)  # a real launcher result, not a simulated one
        d = self.make_dispatcher(rows)
        d.rec(rid).update(status="running", vm=2, port=12000, port_block=12000)
        d.finish(rid, 99)
        rec = d.rec(rid)
        self.assertEqual((rec["status"], rec["name"], rec["attempt"]), ("pending", rid, 0))
        self.assertEqual(d.st["vms"]["2"]["state"], "down")
        d.save()
        (self.sb.vm / "fakevm2.down").unlink()
        code, out = self.sb.run(FAKE_SLEEP="0.2")
        self.assertEqual(code, 0, out)
        st = self.sb.state()
        self.assertEqual((st["runs"][rid]["status"], st["runs"][rid]["name"]), ("done", rid))
        self.assertEqual(self.sb.starts().count(rid), 1)
        self.assertEqual((self.sb.ev / (rid + ".exit")).read_text().strip(), "0")  # the stale 99 was replaced

    def test_outroot_and_evidence_mismatch_are_refused_and_state_is_reused(self):
        self.sb.write_manifest(rows20()[:3])
        cmd = PY + [str(HERE / "dispatch.py"), "run", "--manifest", "manifest.csv", "--dir", str(self.sb.work), "--tick", "0.2"]
        env = dict(self.sb.env, FAKE_SLEEP="0.2")
        kw = dict(cwd=self.sb.root, capture_output=True, text=True)
        r = subprocess.run(cmd + ["--outroot", "/vmroot/custom"], env=env, **kw)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(Path(self.sb.state()["manifest"]).is_absolute())
        self.assertTrue(list((self.sb.vm / "fakevm1/vmroot/custom").glob("*/team.json")) + list((self.sb.vm / "fakevm2/vmroot/custom").glob("*/team.json")))
        n = len(self.sb.starts())
        r = subprocess.run(cmd + ["--outroot", "/vmroot/other"], env=env, **kw)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("--outroot", r.stderr)
        r = subprocess.run(cmd, env=dict(env, EVIDENCE_DIR=str(self.sb.root / "other-ev")), **kw)
        self.assertEqual(r.returncode, 2)
        self.assertIn("EVIDENCE_DIR", r.stderr)
        r = subprocess.run(cmd, env=env, **kw)  # no --outroot: the stored one is used, nothing re-runs
        self.assertEqual((r.returncode, len(self.sb.starts())), (0, n), r.stdout + r.stderr)


class CollectTests(Base):
    def test_collect_layout_is_readable_by_compare_and_causes(self):
        sys.path.insert(0, str(COMPARE))
        import causes
        import compare
        self.sb.write_manifest(rows20())
        code, out = self.sb.run(FAKE_SLEEP="0.2")
        self.assertEqual(code, 0, out)
        results = self.sb.root / "results"
        with mock.patch.dict(os.environ, self.sb.env):
            self.assertEqual(collect.main(["--dir", str(self.sb.work), "--results", str(results)]), 0)
            self.assertEqual(collect.main(["--dir", str(self.sb.work), "--results", str(results), "--groups", "mainA"]), 0)  # idempotent
        with open(results / "index.csv", encoding="utf-8", newline="") as stream:
            index = list(csv.DictReader(stream))
        self.assertEqual(len(index), 20)
        self.assertEqual({r["status"] for r in index}, {"done"})
        self.assertTrue(all(r["warnings"] == "" for r in index), [r["warnings"] for r in index if r["warnings"]])
        scenes = {s["id"]: s for s in compare.read_json(SCENES / "scenes18b.json")["scenes"]}
        checked = 0
        for group in sorted((results / "compare").iterdir()):
            for path in sorted(group.iterdir()):
                row = compare.analyze_run(path, scenes, results / "brain")
                team = {r["alias"]: r["team"] for r in index}[path.name]
                self.assertEqual(row["structure"], team)
                self.assertEqual(row["excluded"], "", row)
                self.assertEqual(row["brain_source"], "brain-record.json")
                self.assertEqual(row["llm_calls"], 4)
                self.assertNotIn("summary missing", row["warnings"])
                if team in ("T0", "T1", "T2"):
                    res = causes.analyze_causes(path, scenes, results / "brain")
                    self.assertIsNotNone(res)
                checked += 1
        self.assertEqual(checked, 20)
        self.assertTrue((results / "A-C01-T0-r1" / "team.json").exists() or any((results / r["run_id"] / "team.json").exists() for r in index))
        self.assertFalse(list(COMPARE.rglob("__pycache__")), "analysis/ got a __pycache__")


    def test_index_lists_failed_runs_too(self):
        rows = rows20()
        self.sb.write_manifest(rows)
        bad = rows[3]["run_id"]
        code, out = self.sb.run(FAKE_SLEEP="0.2", FAKE_FAIL_ALWAYS=bad)
        self.assertEqual(code, 1, out)
        results = self.sb.root / "results"
        with mock.patch.dict(os.environ, self.sb.env):
            self.assertEqual(collect.main(["--dir", str(self.sb.work), "--results", str(results)]), 0)
        with open(results / "index.csv", encoding="utf-8", newline="") as stream:
            index = {r["run_id"]: r for r in csv.DictReader(stream)}
        self.assertEqual(len(index), 20)
        self.assertEqual(index[bad]["status"], "failed")
        self.assertIn("not collected", index[bad]["warnings"])
        self.assertEqual(sum(r["status"] == "done" for r in index.values()), 19)
        self.assertFalse((results / bad).exists())


if __name__ == "__main__":
    unittest.main()
