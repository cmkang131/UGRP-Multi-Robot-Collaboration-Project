#!/usr/bin/env python3
"""Two-robot ACT joint-carry, local CPU MuJoCo E2E: real 20k model + real physics.

One bounded run joins the two halves that were previously proven separately:

  * MODEL SIDE  -- the byte-identical original worker
    `received/final/extracted/scripts/geometry_pair_worker.py` (sha c7509a64...)
    driving the REAL `implementation/geometry_worker.py` head on the REAL
    step-020000 actor (model.safetensors sha 1b998586...) on CPU.  The worker
    owns the pinned controller (`harness/pairact_r1_student.PairStudentController`
    from the checkpoint-authoritative 4-tree worker) and therefore the 8-stage
    `PairActBarrier` and the chunk/clock semantics.

  * PHYSICS SIDE -- the pinned dependency closure `26f84d0f` MuJoCo pair world
    (158 bodies / 1386 geoms), each robot's OWN `robot_cam` JPEG, and the
    pinned `DutyActPort` actuator path (wheel pulse + arm/look servo pulses).

  * JOIN -- the ASTRA reference outer loop `harness/pairact_student_eval.py`
    (sha 03f6a231...) `StudentEpisode` + `RearmingSync`, driven by the pinned
    `GraspStartSync`/`PairCarrySync` READY->GO->ACK barrier.  Only the transport
    is new (a thin client that spawns the geometry worker instead of the
    legacy `scripts.pairact_r1_student_worker`); every protocol and gate
    decision is the pinned code's.

Scope discipline (nothing here relaxes a gate):
  * control input per robot = that robot's OWN camera JPEG + OWN issued
    history only; the worker's request allowlist rejects anything else;
  * the 8-stage barrier, the READY->GO->ACK permit barrier and the weld-off
    rule are the pinned ones and are enforced, not bypassed;
  * GPU 0, network 0, installs 0, real robot 0, published commands 0;
  * run dir is created exclusively; no existing artefact is read-modified,
    overwritten or deleted;
  * one owner process, one hard wall deadline, only its own children.

This is NOT a carry-success claim, NOT a promotion of the 20k checkpoint and
NOT an LLM-in-the-loop episode: the learner is the ACT/geometry policy only.

Owned audit wiring (UGRP-Pair, 2026-11-05, branch ugrp/pair-runner-wire-20261105T2017Z)
--------------------------------------------------------------------------------------
This file is an OWNED COPY of the original candidate above (the original stays
read-only and unmodified).  ONLY the worker selection is parameterized:

  * ``--audit-worker off`` (default) -> the ORIGINAL selection: the original
    ``geometry_pair_worker.py`` is launched with the original argv, byte for
    byte.
  * ``--audit-worker on`` -> an audited selection: a bundle tree is created
    exclusively, the pinned worker ``harness``/``scripts`` are copied into it
    byte for byte, the audit module, its launch entry, the bundle helper and
    the raw ProposalObserver are placed in the SAME harness package as the
    pinned controller. A strict manifest binds the 16-entry protected scope;
    the rest of the copied closure is byte-compared at creation only. The
    manifest and real-import same-tree check are verified BEFORE the worker
    is started.

  * ``--observe-raw-proposals`` -> OPT-IN (default OFF): the raw
    ProposalObserver records the controller proposal snapshots and an
    independent ``proposal-status-<runid>.json`` completeness file. It
    requires ``--audit-worker on``; the combination with ``--audit-worker
    off`` is refused at start-up. The observer NEVER changes control.

``--prepare-only`` stops after that preparation and writes the bundle, the
final launch argv, the real source hashes and the not-executed state as an
artefact.  The world build, the MuJoCo import, the head-worker Popen and the
model forward are never reached in that mode.

The world build (S1), the joined control loop (S3), the evidence collection
(S4) and the verdict (S5) are byte-identical to the original; the tests
compare them with a diff and an AST check.

Owned consumer-audit wiring (UGRP-Pair, 2026-11-05, branch ugrp/pair-consumer-audit-20261105T2046Z)
--------------------------------------------------------------------------------------------------
This file is an OWNED COPY of the PR642 owned runner above (that file stays
read-only and unmodified).  On top of the audited worker selection it adds a
CONSUMER-side ledger of the apply call.  Nothing else changes: the original
argv, S1, S3, S4, S5, the stdout shape, the gates and the model input stay
as they are.

  * ``--consumer-audit off`` (default) -> NO consumer ledger is created and
    the run behaves exactly like the PR642 runner.
  * ``--consumer-audit on`` -> requires ``--audit-worker on`` together with
    ``--audit-run-id`` (a consumer ledger without a producer audit file would
    have nothing to bind to, and that combination is refused).

What the ledger records (and what it does NOT):

  * BEFORE the single ``teacher_apply(ports[rid], cmd, now, previous[rid])``
    call of each robot it stores a DEEP COPY of the command and of the prior
    command, and it binds the call to the producer's ``issue_command`` row.
  * AFTER the call it records the RETURN VALUE or the EXCEPTION as two
    separate facts.  ``apply_returned`` is only what the function returned:
    it is NOT environment application, NOT a transport acknowledgement and
    NOT motion evidence.  The port state is not captured at all.
  * The robot's NEXT own observation (the ``observation`` of
    ``StudentEpisode.tick``) is linked to the apply that preceded it, using
    the producer's ``observation`` row and its ``linked_issue_seq``.

The legacy quirk of the original runner (it overwrites ``previous[rid]`` with
the command right after the apply, so the logged "previous" is the current
command) is NOT changed here.  The ledger copies the prior BEFORE the call,
so the ledger keeps the real prior, while the original metrics stay as they
are.

This is NOT a carry-success claim: it is consumer-side call accounting with a
synthetic wiring, on CPU, without physics.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import importlib.util
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------- pins
PINNED = "/home/ubuntu/ugrp-dep-26f84d0f-20261104"          # physics closure
TREE = ("/home/ubuntu/UGRP/experiments/2026-11-04-joint-act-4tree-assembly-diag-v1"
        "/out/trees/worker")                                  # checkpoint-authoritative harness
ASTRA = ("/home/ubuntu/UGRP/experiments/2026-11-04-astra-strict-eval-v1"
         "/snapshot/harness/pairact_student_eval.py")          # reference outer loop
WORKER = ("/home/ubuntu/ugrp-retrain-geom-20261029/received/final/extracted"
          "/scripts/geometry_pair_worker.py")                 # ORIGINAL worker, unmodified
HEADWORKER = "/home/ubuntu/ugrp-retrain-geom-20261029/implementation/geometry_worker.py"
CKPT = "/home/ubuntu/ugrp-retrain-geom-20261029/checkpoints/step-020000/actor"
CONFIG = ("/home/ubuntu/ugrp-wt/codex-pair-fix-cpu-20261027/experiments"
          "/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json")
OVERLAY = "/home/ubuntu/ugrp-support-manifest-diag-20261030/.cpu-python312"
DEPS = ("/home/ubuntu/projects/ugrp/evidence/f-train-only-diagnostic-20261103T1000Z"
        "/cpu-deps")
SHIM = ("/home/ubuntu/UGRP/experiments/2026-11-04-joint-carry-p5-real-20k-telemetry-capture-v1"
        "/shim")
MUJOCO_SP = "/home/ubuntu/ugrp-render-arm-s-20261027/.venv-mujoco/lib/python3.12/site-packages"
CV2_SP = "/home/ubuntu/ugrp-venv/lib/python3.12/site-packages"
PLAN = "/home/ubuntu/UGRP/experiments/2026-10-16-gatesv5-beampair/beampair-short-plan.json"
SCENARIO = "/home/ubuntu/UGRP/experiments/2026-10-15-beampair1/scenario-v7.json"

EXPECT_WORKER_SHA = "c7509a6423b252d4941b68ecfa3ce2ffc75783c4f3cd1f3aac2fe467b9d601bc"
EXPECT_CKPT_SHA = "1b998586bb02097ebf09782a227baeed853546548b0f388893e08ad95efd5155"
EXPECT_ASTRA_SHA = "03f6a2311c0d4f4a97495fdce5efe7d345a35fa2815c9c5ab3660223818efbec"
SERVOS = (1, 3, 4, 5, 6)
T0 = time.monotonic()

# ---- owned audit wiring ------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
BUNDLE_HELPER = REPO / "harness" / "pair_worker_bundle.py"
CANDIDATE_AUDIT = REPO / "harness" / "pair_worker_audit.py"
CANDIDATE_ENTRY = REPO / "harness" / "pair_worker_audit_entry.py"
CANDIDATE_OBSERVER = REPO / "harness" / "pair_proposal_observer.py"
HEAD_POLICY = ("/home/ubuntu/ugrp-retrain-geom-20261029/implementation"
               "/geometry_policy.py")

# The pinned worker-tree subset the audited pair path needs.  The bundle copy
# must hash exactly like this; a mismatch stops the run before any worker
# starts.
EXPECTED_TREE_SHAS = {
    "harness/__init__.py": "953d3229d4ed66dc30e1ddeab38440397fc01303fcd022fb147d45d4345abdcf",
    "harness/grasp_act_contract.py": "6bc58d6f9707abd5d854c6dbbb63357ed14dab6c37bcf055ddd8d1d66d171056",
    "harness/pairact_r1.py": "8a9869248740bf5ad2da7194cdd9a582347ac09e88783cd6ea127ef3f208a210",
    "harness/pairact_r1_student.py": "3e12d2f5408f82821187401e8a6d4298cb70fb27b48c229d689a54efdef77e81",
    "harness/beamact_pair_student.py": "9650e08573adf61e622a2e832a7ca12f476d4e5988f9bbc299bb125a766ee1c6",
    "harness/grasp_act_policy.py": "0cfa080f086ea991368e3c686960cf54cab9a8f9796e1077557f17a639f79c6c",
    "scripts/robot_actions.py": "fffb0c4d351294275c9dab497feb201fb045a05939e51ff892c2027af54ba96c",
}

# The read-only originals the audited run binds.  The worker sha is the one
# the ORIGINAL runner already pinned; the rest are additional pins.
EXPECTED_EXTERNAL_SHAS = {
    WORKER: "c7509a6423b252d4941b68ecfa3ce2ffc75783c4f3cd1f3aac2fe467b9d601bc",
    HEADWORKER: "e9a29e81fdc1b3b0faa760bd89533953ea49c23eb325f48c5c7f01aec042e90c",
    HEAD_POLICY: "3681da67642f681615b42673ae004690d2341d62b99c3c6caeae647c8851788f",
    CONFIG: "37835e1ff9bd7b9686b4d7258b7597e6cd8e40b84a121c4f4156704c04b49326",
    ASTRA: "03f6a2311c0d4f4a97495fdce5efe7d345a35fa2815c9c5ab3660223818efbec",
}

# The candidate files that travel into the bundle.  Their bytes are pinned
# HERE, independently of the manifest, so a replaced candidate is refused
# before the bundle is built.  Four candidates: the audit module, its launch
# entry, the bundle helper and the raw ProposalObserver.
EXPECTED_CANDIDATE_SHAS = {
    str(CANDIDATE_AUDIT): "cfe4cbfa2565003063aa69980abd759b5364877e0aa45cc709ebb6a32bef099d",
    str(CANDIDATE_ENTRY): "a902afa0a8a50494507998b19e500af736f5a241439f7f2bbf9a0ec283c48ba9",
    str(BUNDLE_HELPER): "a7828ba1bcc95082feeb3076a88488dcfb6f2de0f84b43db0293c5daf9b8459b",
    str(CANDIDATE_OBSERVER): "19d2af7f1d972b25b0e3069424046539d995ade4eef0e62fd2b66013a39ea35d",
}

# ---- owned consumer audit wiring --------------------------------------
# The consumer ledger helper is loaded BY PATH (never as a package member), so
# it can never shadow the pinned ``harness`` package of the physics closure.
CONSUMER_HELPER = REPO / "harness" / "pair_consumer_audit.py"
EXPECTED_CONSUMER_HELPER_SHA = "4cd01c557953bb1a319852ecbad09ae65a94f1b1c829f8658f830d9d9a57cce7"
# The apply callable that this runner wraps.  The module is checked before the
# ledger is created, so a swapped or aliased callable is refused.
EXPECT_APPLY_MODULE = "scripts.run_grasp_act_teacher"


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GeometryWorkerClient:
    """Transport only: JSON-lines to the ORIGINAL geometry_pair_worker.py.

    The request/response shapes are the frozen four-operation protocol
    (reset / propose / issue / summary) that `StudentEpisode` already speaks.
    """

    def __init__(self, argv, env, cwd, stderr_path, deadline_s):
        self.deadline_s = deadline_s
        self.stderr = open(stderr_path, "x", encoding="utf-8")
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.stderr, text=True, bufsize=1, env=env, cwd=cwd)
        self.requests = 0
        try:
            hello = self._read()
        except BaseException:
            # the child exists even when the handshake failed: clean it up
            self.close()
            raise
        if hello != {"ready": True, "mode": "pairact_r1_student_eval_v1"}:
            self.close()
            raise RuntimeError(f"geometry worker startup mismatch: {hello!r}")
        self.handshake = hello

    def _read(self):
        fd = self.proc.stdout.fileno()
        remain = self.deadline_s - (time.monotonic() - T0)
        if remain <= 0:
            raise TimeoutError("wall deadline reached while waiting for the worker")
        ready, _, _ = select.select([fd], [], [], max(0.5, remain))
        if not ready:
            raise TimeoutError("geometry worker produced no line within the deadline")
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"geometry worker closed stdout rc={self.proc.poll()}")
        return json.loads(line)

    def request(self, payload):
        self.proc.stdin.write(json.dumps(payload, allow_nan=False) + "\n")
        self.proc.stdin.flush()
        self.requests += 1
        return self._read()

    def close(self):
        try:
            if self.proc.poll() is None:
                try:
                    self.proc.stdin.close()
                except Exception:
                    pass
                try:
                    self.proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=15)
        finally:
            self.stderr.close()


def load_module(path, name, *, expected_sha=None):
    """Load a module by path so that no package namespace is touched."""
    if expected_sha is not None and sha256_file(path) != expected_sha:
        raise RuntimeError("module hash drift before import: " + str(path))
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bundle = load_module(BUNDLE_HELPER, "ugrp_pair_worker_bundle")
consumer = load_module(CONSUMER_HELPER, "ugrp_pair_consumer_audit",
                       expected_sha=EXPECTED_CONSUMER_HELPER_SHA)


def original_worker_argv(trace_dir):
    """The ORIGINAL worker selection, byte-identical to the original runner."""
    return ["/usr/bin/python3", "-B", WORKER,
            "--model", CKPT, "--config", CONFIG, "--device", "cpu", "--threads", "1",
            "--student-root", TREE, "--headworker", HEADWORKER,
            "--head-source-root", TREE, "--geometry-trace-dir", str(trace_dir)]


def audited_worker_argv(trace_dir, *, bundle_root, manifest_path, run_id, audit_root,
                        observe_raw_proposals=False):
    """The audited selection: the bundle entry, in ONE tree with the controller.

    The model, config, head worker, head source root and trace directory are
    the original ones; only the entry, the student root and the audit
    options are added.  ``--observe-raw-proposals`` is OPT-IN and is only
    added when it was explicitly requested; the raw input, the four-operation
    protocol and the gates are unchanged.
    """
    argv = ["/usr/bin/python3", "-B",
            str(bundle_root / "harness" / "pair_worker_audit_entry.py"),
            "--model", CKPT, "--config", CONFIG, "--device", "cpu", "--threads", "1",
            "--student-root", str(bundle_root), "--headworker", HEADWORKER,
            "--head-source-root", TREE, "--geometry-trace-dir", str(trace_dir),
            "--geometry-worker", WORKER,
            "--audit-run-id", run_id, "--audit-output-root", str(audit_root),
            "--audit-sources", str(manifest_path)]
    if observe_raw_proposals:
        argv.append("--observe-raw-proposals")
    return argv


def plan_worker(*, out, trace_dir, args):
    """Choose the worker entry and build the launch argv.

    OFF -> the original selection.  ON -> the bundle entry; the bundle is
    created exclusively, the manifest is verified and the same-tree claim is
    checked with a real import BEFORE any worker is started.

    The raw proposal observer is OPT-IN: it can only be selected together
    with the audited worker (``--audit-worker on``), because the observer
    lives in the bundle and writes into the audit output root.  The
    combination ``--audit-worker off`` + ``--observe-raw-proposals`` is
    refused at start-up: no bundle, no worker, no file.
    """
    observe = bool(getattr(args, "observe_raw_proposals", False))
    if args.audit_worker == "off":
        if observe:
            raise SystemExit("--observe-raw-proposals requires --audit-worker on")
        return {"mode": "off", "argv": original_worker_argv(trace_dir),
                "student_root": TREE, "bundle_root": None, "manifest_path": None,
                "manifest_verified": False, "same_tree_verified": False,
                "manifest_entries": 0, "bundle": None, "audit_run_id": None,
                "audit_output_root": None, "observe_raw_proposals": False}
    if not args.audit_run_id:
        raise SystemExit("--audit-run-id is required with --audit-worker on")
    bundle_root = (Path(args.bundle_root).resolve() if args.bundle_root
                   else (out / "bundle").resolve())
    audit_root = (Path(args.audit_output_root).resolve() if args.audit_output_root
                  else (out / "audit").resolve())
    # The runner keeps its own copy of the pin tables; the bundle helper
    # carries a second one.  They must agree exactly, and the candidate files
    # must hash as pinned here -- both are independent of the manifest.
    if EXPECTED_TREE_SHAS != bundle.EXPECTED_TREE_SHAS:
        raise SystemExit("pin table drift between the owned runner and the bundle helper")
    if EXPECTED_EXTERNAL_SHAS != bundle.EXPECTED_EXTERNAL_SHAS:
        raise SystemExit("pin table drift between the owned runner and the bundle helper")
    for candidate, want in EXPECTED_CANDIDATE_SHAS.items():
        if bundle.sha256_file(candidate) != want:
            raise SystemExit("candidate source hash drift: " + candidate)
    created = bundle.create_bundle(dest=bundle_root, pinned_tree=TREE,
                                   candidates=[CANDIDATE_AUDIT, CANDIDATE_ENTRY,
                                               BUNDLE_HELPER, CANDIDATE_OBSERVER],
                                   externals=[WORKER, HEADWORKER, HEAD_POLICY, CONFIG, ASTRA])
    expected = {}
    for relative, want in bundle.EXPECTED_TREE_SHAS.items():
        expected[str(bundle_root / relative)] = want
    for path, want in bundle.EXPECTED_EXTERNAL_SHAS.items():
        expected[path] = want
    required = set(expected) | {str(bundle_root / "harness" / "pair_worker_audit.py"),
                                str(bundle_root / "harness" / "pair_worker_audit_entry.py"),
                                str(bundle_root / "harness" / "pair_worker_bundle.py"),
                                str(bundle_root / "harness" / "pair_proposal_observer.py")}
    verified = bundle.verify_manifest(created["manifest_path"], expected=expected,
                                      required=required)
    modules = bundle.verify_import_same_tree(bundle_root)
    argv = audited_worker_argv(trace_dir, bundle_root=bundle_root,
                               manifest_path=created["manifest_path"],
                               run_id=args.audit_run_id, audit_root=audit_root,
                               observe_raw_proposals=observe)
    return {"mode": "on", "argv": argv, "student_root": str(bundle_root),
            "bundle_root": str(bundle_root), "manifest_path": created["manifest_path"],
            "manifest_verified": True, "same_tree_verified": True,
            "manifest_entries": len(verified),
            "bundle": {"info": created["info"], "imports": modules,
                       "expected_pins": expected},
            "audit_run_id": args.audit_run_id, "audit_output_root": str(audit_root),
            "observe_raw_proposals": observe}


def plan_consumer_ledger(*, args, out, worker_selection):
    """Plan the consumer-side ledger.  OFF by default.

    ON requires the audited worker selection (``--audit-worker on``) together
    with its run id: the ledger binds the consumer apply call to the
    producer's audit rows, so without a producer audit file it would have
    nothing to bind to.
    """
    if args.consumer_audit == "off":
        return {"mode": "off", "ledger": None,
                "plan": {"mode": "off",
                         "ledger_created": False,
                         "note": "no consumer ledger is created; the run is unchanged"}}
    if worker_selection["mode"] != "on":
        raise SystemExit("--consumer-audit on requires --audit-worker on")
    run_id = worker_selection.get("audit_run_id")
    if not run_id:
        raise SystemExit("--consumer-audit on requires --audit-run-id")
    if sha256_file(CONSUMER_HELPER) != EXPECTED_CONSUMER_HELPER_SHA:
        raise SystemExit("consumer helper hash drift: " + str(CONSUMER_HELPER))
    audit_root = Path(worker_selection["audit_output_root"])
    producer_path = audit_root / ("pair-audit-%s.jsonl" % run_id)
    output_root = (Path(args.consumer_output_root).resolve() if args.consumer_output_root
                   else (out / "consumer-audit").resolve())
    return {"mode": "on", "ledger": None,
            "plan": {"mode": "on", "run_id": run_id,
                     "producer_audit_path": str(producer_path),
                     "consumer_output_root": str(output_root),
                     "episode_id": args.consumer_episode_id,
                     "ledger_created": False,
                     "note": "the ledger file is created after the world build and "
                             "before the worker starts; in prepare-only mode it is "
                             "not created at all"}}


def apply_issued_commands(*, apply_callable, roles, issued, ports, now, previous,
                          ledger=None, tick=None):
    """Apply the issued commands to the actuators -- the S3 hook.

    The original runner calls ``teacher_apply(ports[rid], cmd, now,
    previous[rid])`` exactly once per robot and then overwrites
    ``previous[rid]`` with the command.  That is preserved here.  When a
    consumer ledger is attached, it is wrapped AROUND that single call: the
    ledger copies the command and the prior before the call and records the
    return value or the exception after it.  No second call is made and the
    original metric (``previous_issued_command``) is not touched.
    """
    applied = {}
    for rid in roles:
        cmd = issued[rid]["command"]
        prior = previous[rid]
        if ledger is not None:
            ledger.begin_apply(rid, cmd=cmd, prior=prior, now=now, tick=tick)
        try:
            returned = apply_callable(ports[rid], cmd, now, prior)
        except Exception as exc:
            if ledger is not None:
                try:
                    ledger.end_apply(rid, outcome="exception",
                                     error={"type": type(exc).__name__, "message": str(exc)})
                except Exception as audit_exc:
                    exc.add_note("consumer exception recording failed: %r" % (audit_exc,))
            raise
        if ledger is not None:
            ledger.end_apply(rid, outcome="returned", result=returned)
        applied[rid] = {"command": cmd, "actuator_state": ports[rid]._actuator_state()}
        previous[rid] = cmd
    return applied


def shutdown_owned(*, client, ledger, res):
    """Close the started child and the consumer ledger; keep the evidence.

    A failure of the ledger close is recorded in ``res["errors"]`` instead of
    replacing the exception that caused the shutdown.
    """
    errors = res.setdefault('errors', [])
    if client is not None:
        try:
            client.close()
        except Exception as exc:
            errors.append("worker client close failed: %r" % (exc,))
    if ledger is not None:
        try:
            ledger.close()
        except Exception as exc:
            errors.append("consumer ledger close failed: %r" % (exc,))


@contextlib.contextmanager
def owned_worker_scope(*, res, ledger):
    """Own the worker child and the ledger for the whole S2/S3 region.

    If anything fails inside -- the worker startup included -- the child and
    the ledger are closed and the ORIGINAL exception is re-raised unchanged.
    """
    owned = {'client': None}
    try:
        yield owned
    finally:
        shutdown_owned(client=owned.get('client'), ledger=ledger, res=res)


def make_worker_client(argv, env, cwd, stderr_path, deadline_s):
    """The worker client factory.  This is the only injection point."""
    return GeometryWorkerClient(argv, env, cwd, stderr_path, deadline_s)


def boot_worker(*, argv, env, out, deadline_s, client_factory=None):
    """Start the worker with the planned argv (the real external process)."""
    factory = client_factory or make_worker_client
    return factory(argv, env, str(out), out / "worker-stderr.log", deadline_s)


def write_exclusive(path, text):
    with open(path, "x", encoding="utf-8") as stream:
        stream.write(text)


def write_prepare_artifacts(*, out, res, plan, pins):
    """Leave the preparation evidence: bundle, final argv, real hashes, state."""
    argv = plan["argv"]
    manifest = {}
    if plan["manifest_path"]:
        manifest = json.loads(Path(plan["manifest_path"]).read_text(encoding="utf-8"))
    payload = {
        "schema": "ugrp.joint_carry.pair_runner_prepare.v1",
        "run_dir": str(out),
        "prepared_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "audit_worker": plan["mode"],
        "bundle_root": plan["bundle_root"],
        "manifest_path": plan["manifest_path"],
        "manifest_verified": bool(plan["manifest_verified"]),
        "manifest_entries": plan["manifest_entries"],
        "same_tree_import_verified": bool(plan["same_tree_verified"]),
        "final_argv": argv,
        "final_argv_sha256": sha256_bytes(json.dumps(argv, sort_keys=True).encode()),
        "source_hashes": {path: entry["sha256"] for path, entry in sorted(manifest.items())},
        "executed": False,
        "not_executed": ["mujoco_import", "world_build", "head_worker_popen",
                         "model_forward", "worker_start", "physics", "actuator_apply"],
        "mujoco_imported": "mujoco" in sys.modules,
        "model_forwards": 0,
        "worker_started": False,
        "audit_run_id": plan["audit_run_id"],
        "audit_output_root": plan["audit_output_root"],
        "observe_raw_proposals": bool(plan.get("observe_raw_proposals", False)),
        "pins": pins,
        "scope": ("preparation only: the bundle, the manifest and the launch argv are "
                  "real and verified; nothing was simulated, no head worker was started "
                  "and no model forward happened"),
        "safety": {"gpu": 0, "network": 0, "installs": 0, "paid_api": 0,
                   "real_robot": 0, "published_commands": 0,
                   "existing_artefacts_modified": 0, "deletions": 0,
                   "model_forwards": 0, "head_workers_started": 0},
    }
    write_exclusive(out / "prepare.json",
                    json.dumps(payload, indent=1, sort_keys=True, default=str) + "\n")
    write_exclusive(out / "final-argv.json",
                    json.dumps({"argv": argv,
                                "argv_sha256": payload["final_argv_sha256"],
                                "audit_worker": plan["mode"]},
                               indent=1, sort_keys=True) + "\n")
    if plan["manifest_path"]:
        write_exclusive(out / "bundle-manifest.json",
                        Path(plan["manifest_path"]).read_text(encoding="utf-8"))
    return payload


def load_astra(path):
    """Load the ASTRA reference outer loop by path (no `harness` namespace clash)."""
    spec = importlib.util.spec_from_file_location("astra_pairact_student_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--ticks", type=int, default=12)
    ap.add_argument("--deadline-s", type=float, default=120.0)
    ap.add_argument("--audit-worker", choices=("off", "on"), default="off")
    ap.add_argument("--audit-run-id", default=None)
    ap.add_argument("--audit-output-root", default=None)
    ap.add_argument("--bundle-root", default=None)
    ap.add_argument("--consumer-audit", choices=("off", "on"), default="off")
    ap.add_argument("--consumer-output-root", default=None)
    ap.add_argument("--consumer-episode-id", default=None)
    ap.add_argument("--observe-raw-proposals", action="store_true")
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()

    out = Path(args.run_dir).resolve()
    if out.exists():
        raise SystemExit("run dir must not exist (unique exclusive path): " + str(out))
    out.mkdir(parents=True, exist_ok=False)          # exclusive create
    (out / "rgb").mkdir()
    for rid in ("r1", "r2"):
        (out / "rgb" / rid).mkdir()
    trace_dir = out / "trace"
    trace_dir.mkdir()

    res = {
        "schema": "ugrp.joint_carry.cpu_e2e_real20k.v1",
        "run_dir": str(out),
        "owner_pid": os.getpid(),
        "argv": sys.argv,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ticks_requested": args.ticks,
        "wall_deadline_s": args.deadline_s,
        "scope": ("bounded local-CPU MuJoCo E2E: real step-020000 geometry ACT (own RGB + own issued "
                  "only) inside the pinned 8-stage + READY/GO/ACK gates, actuating the real pinned "
                  "pair MuJoCo world; NOT a carry-success claim, NOT a promotion, NOT an LLM episode"),
        "safety": {"gpu": 0, "network": 0, "installs": 0, "paid_api": 0, "real_robot": 0,
                   "published_commands": 0, "existing_artefacts_modified": 0,
                   "deletions": 0, "model_forwards": 0},
        "ticks": [], "notes": [], "errors": [],
    }

    def note(text):
        res["notes"].append(text)

    # ---- S0 pins -----------------------------------------------------
    pins = {
        "worker": {"path": WORKER, "sha256": sha256_file(WORKER)},
        "headworker": {"path": HEADWORKER, "sha256": sha256_file(HEADWORKER)},
        "astra_outer_loop": {"path": ASTRA, "sha256": sha256_file(ASTRA)},
        "checkpoint": {"path": CKPT, "model_sha256": sha256_file(CKPT + "/model.safetensors"),
                       "adapter_sha256": sha256_file(CKPT + "/adapter.json")},
        "config": {"path": CONFIG, "sha256": sha256_file(CONFIG)},
        "tree_pairact_r1_sha256": sha256_file(TREE + "/harness/pairact_r1.py"),
        "tree_contract_sha256": sha256_file(TREE + "/harness/grasp_act_contract.py"),
        "tree_beamact3_sha256": sha256_file(TREE + "/harness/beamact3.py"),
        "geometry_policy_sha256": sha256_file(
            "/home/ubuntu/ugrp-retrain-geom-20261029/implementation/geometry_policy.py"),
        "pinned_physics_closure": PINNED,
    }
    adapter = json.loads(Path(CKPT + "/adapter.json").read_text())
    pins["adapter"] = {k: adapter.get(k) for k in (
        "schema", "contract_sha256", "pairact_source_sha256", "adapter_source_sha256",
        "geometry_source_sha256", "upstream_sha", "image_hw", "model_image_hw",
        "done_recovery", "place_sync", "issued_clock_deadband", "pairact_r1_config_sha256",
        "learned_stages")}
    pins["adapter_pins_match_tree"] = {
        "contract_sha256": pins["adapter"]["contract_sha256"] == pins["tree_contract_sha256"],
        "pairact_source_sha256": pins["adapter"]["pairact_source_sha256"] == pins["tree_pairact_r1_sha256"],
        "adapter_source_sha256": pins["adapter"]["adapter_source_sha256"] == pins["tree_beamact3_sha256"],
        "geometry_source_sha256": pins["adapter"]["geometry_source_sha256"] == pins["geometry_policy_sha256"],
        "pairact_r1_config_sha256": pins["adapter"]["pairact_r1_config_sha256"] == pins["config"]["sha256"],
    }
    res["pins"] = pins
    if pins["worker"]["sha256"] != EXPECT_WORKER_SHA:
        raise SystemExit("worker sha drift: " + pins["worker"]["sha256"])
    if pins["checkpoint"]["model_sha256"] != EXPECT_CKPT_SHA:
        raise SystemExit("checkpoint sha drift: " + pins["checkpoint"]["model_sha256"])
    if pins["astra_outer_loop"]["sha256"] != EXPECT_ASTRA_SHA:
        raise SystemExit("ASTRA outer-loop sha drift: " + pins["astra_outer_loop"]["sha256"])

    # ---- worker selection (owned audit wiring) ------------------------
    worker_selection = plan_worker(out=out, trace_dir=trace_dir, args=args)
    res["worker_selection"] = {
        "mode": worker_selection["mode"], "argv": worker_selection["argv"],
        "student_root": worker_selection["student_root"], "bundle_root": worker_selection["bundle_root"],
        "manifest_path": worker_selection["manifest_path"],
        "manifest_verified": worker_selection["manifest_verified"],
        "same_tree_import_verified": worker_selection["same_tree_verified"],
        "audit_run_id": worker_selection["audit_run_id"],
        "audit_output_root": worker_selection["audit_output_root"],
    }
    if worker_selection["bundle"]:
        res["bundle"] = worker_selection["bundle"]

    # ---- consumer ledger plan (owned consumer-audit wiring) -----------
    consumer_plan = plan_consumer_ledger(args=args, out=out,
                                         worker_selection=worker_selection)
    res["consumer_audit"] = consumer_plan["plan"]
    if args.prepare_only:
        res["prepare"] = write_prepare_artifacts(out=out, res=res, plan=worker_selection, pins=pins)
        (out / "e2e.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
        write_exclusive(out / "consumer-audit-plan.json",
                        json.dumps(res["consumer_audit"], indent=1, sort_keys=True,
                                   default=str) + "\n")
        print(json.dumps({
            "run_dir": str(out), "prepared": True, "audit_worker": worker_selection["mode"],
            "bundle_root": worker_selection["bundle_root"], "manifest_verified": worker_selection["manifest_verified"],
            "final_argv": worker_selection["argv"], "executed": False, "model_forwards": 0,
            "consumer_audit": res["consumer_audit"]["mode"],
            "consumer_ledger_created": res["consumer_audit"]["ledger_created"],
        }, indent=1))
        return 0

    # ---- S1 world build (pinned closure) ------------------------------
    for p in (MUJOCO_SP, CV2_SP):
        if p not in sys.path:
            sys.path.insert(0, p)
    sys.path.insert(0, PINNED)
    os.environ.setdefault("MUJOCO_GL", "egl")
    import mujoco
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    from sim.render_profile import install as profile_install
    from sim.final_pair_highpose_nearclip import wrap
    from sim import masterpi_camera_review_v3 as camera
    from sim.s2_servo_stiffness import transform_xml as stiffness
    from sim.s2_realism_camera_binding import bind_camera
    from sim.grasp_act_scene import colors
    from sim.masterpi_drive_friction_v7 import build_world, PROFILE
    from sim.zone_cargo import place, CargoInstance
    from sim.grasp_act_port import DutyActPort
    from harness.grasp_act_start_sync import GraspStartSync
    from scripts.run_grasp_act_teacher import apply as teacher_apply

    plan_all = json.loads(Path(PLAN).read_text())
    plan = plan_all["episodes"][0]
    roles = dict(plan["roles"])
    scenario = json.loads(Path(SCENARIO).read_text())
    res["plan"] = {k: plan[k] for k in ("episode_id", "seed", "roles", "scenario_id",
                                        "scenario_source_sha256", "scene_profile")}
    res["plan"]["scenario_sha256_actual"] = sha256_file(SCENARIO)
    res["plan"]["scenario_sha_matches_plan"] = (
        res["plan"]["scenario_sha256_actual"] == plan["scenario_source_sha256"])

    t0 = time.monotonic()
    base_scene = ScenarioFinalV3Scene.from_scenario(scenario, plan["seed"], base_dir=PINNED)
    scene = wrap(profile_install(base_scene, "floor_light_v1"))
    scene.config["setup_only"]["spawns"] = plan["spawns"]
    original = scene.robot_transform

    def transform(xml, **kw):
        value = camera.transform_xml(original(xml, **kw), profile_id=camera.PROFILE_ID)
        for rid in ("r1", "r2", "r3"):
            value = stiffness(value, servo_stiffness="real_v1", robot_id=rid)
        return colors(value, plan["end_color_scene"])

    scene.robot_transform = transform
    world = build_world(scene, drive_profile=PROFILE, seed=plan["seed"], width=640, height=480,
                        render=True, warehouse_layout=scene.engine_layout,
                        warehouse_cargo_ids=None, roller_collision="mesh",
                        idle_robot_contacts="off")
    scene.setup(world)
    place(world, [CargoInstance("beam_1", "long_beam", tuple(plan["beam_pose"]))])
    for controller in world.controllers.values():
        bind_camera(controller)
    (out / "scene.xml").write_text(world.scene_xml)
    json.dump(scene.manifest, open(out / "scene.json", "w"), indent=1)
    ports = {rid: DutyActPort(world, rid, allow_reverse=True, allow_mecanum=True) for rid in roles}
    for rid, port in ports.items():
        port.apply(dict(kind="look", pan_pulse=int(plan["initial_pan"][rid])), float(world.data.time))
    dt = float(world.model.opt.timestep)
    res["world"] = {
        "mujoco_version": mujoco.__version__, "mujoco_path": mujoco.__file__,
        "numpy": __import__("numpy").__version__, "cv2": __import__("cv2").__version__,
        "nbody": int(world.model.nbody), "ngeom": int(world.model.ngeom),
        "dt": dt, "sim_time_after_build": float(world.data.time),
        "build_wall_s": round(time.monotonic() - t0, 3),
        "scene_xml_sha256": sha256_bytes(world.scene_xml.encode()),
        "robots": sorted(world.controllers), "roles": roles,
        "cargo": [c.item_id for c in scene.cargo],
        "weld_active_after_build": bool(world.data.eq_active.any()),
    }
    note("pinned closure lacks sim.scene_contrast_v5/gatesv5_scene: base floor_light_v1 only "
         "(same documented deviation as the feasibility-v1 run)")

    # ---- consumer ledger (owned consumer-audit wiring) -----------------
    # Created AFTER the world build and BEFORE the worker starts: the ledger
    # file is created exclusively and the producer audit file may still be
    # empty at this point (the producer writes it while it runs).
    ledger = None
    if consumer_plan["mode"] == "on":
        apply_module = getattr(teacher_apply, "__module__", None)
        if apply_module != EXPECT_APPLY_MODULE:
            raise SystemExit("unexpected apply callable module: %r" % (apply_module,))
        episode_id = consumer_plan["plan"]["episode_id"] or plan["episode_id"]
        ledger = consumer.ConsumerLedger(
            run_id=consumer_plan["plan"]["run_id"], episode_id=episode_id,
            output_root=consumer_plan["plan"]["consumer_output_root"],
            producer_audit_path=consumer_plan["plan"]["producer_audit_path"],
            robots=sorted(roles))
        identity = ledger.attach_apply(teacher_apply)
        consumer_plan["plan"]["episode_id"] = episode_id
        consumer_plan["plan"]["ledger_created"] = True
        consumer_plan["plan"]["ledger_path"] = str(ledger.sink.path)
        consumer_plan["plan"]["apply_callable"] = identity
        note("consumer audit ledger created: %s" % ledger.sink.path)

    # ---- S2 worker start (real 20k head, CPU) -------------------------
    env = dict(os.environ)
    env.update(PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="",
               OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               PYTHONPATH=os.pathsep.join([SHIM, OVERLAY, DEPS]))
    argv = worker_selection["argv"]
    client = None
    with owned_worker_scope(res=res, ledger=ledger) as owned:
        client = boot_worker(argv=argv, env=env, out=out, deadline_s=args.deadline_s)
        owned["client"] = client
        res["worker"] = {"argv": argv, "handshake": client.handshake, "device": "cpu", "threads": 1,
                         "student_root": worker_selection["student_root"], "head_source_root": TREE,
                         "checkpoint_model_sha256": pins["checkpoint"]["model_sha256"]}

        # ---- S3 the joined loop -------------------------------------------
        astra = load_astra(ASTRA)
        origin = float(world.data.time)
        initial = {}
        pwm_clamped = []
        for rid, port in ports.items():
            pwm = {}
            for s in SERVOS:
                raw = int(port._servo_pulses.get(s, 1500))
                if not 500 <= raw <= 2500:
                    pwm_clamped.append({"robot": rid, "servo": s, "raw": raw})
                    raw = max(500, min(2500, raw))
                pwm[str(s)] = raw
            initial[rid] = {"t": origin, "wheels": [0.0] * 4, "duration_s": [0.0] * 4, "pwm": pwm}
        if pwm_clamped:
            res["notes"].append("initial issued PWM clamped into the legal 500..2500 range: "
                                + json.dumps(pwm_clamped))
        episode, delays = astra.start({}, roles, plan["episode_id"], initial, seed=int(plan["seed"]),
                                       factory=GraspStartSync, client=client)
        res["sync"] = {"barrier": "harness.grasp_act_start_sync.GraspStartSync + harness.pair_carry_sync.PairCarrySync",
                       "rearming_rule": "astra RearmingSync (beamact4 READY-withdrawn re-arm)",
                       "delays_s": delays}

        previous = {rid: dict(initial[rid]) for rid in roles}
        qpos_prev = {rid: None for rid in roles}
        steps_per_tick = int(round(0.1 / dt))
        state_transitions = 0
        try:
            for tick in range(args.ticks):
                if time.monotonic() - T0 > args.deadline_s - 12:
                    note(f"wall deadline reached at tick {tick}")
                    res["errors"].append("wall deadline before the requested tick count")
                    break
                now = float(world.data.time)
                # own camera JPEG per robot (control input only)
                jpegs = {}
                for rid, port in ports.items():
                    jpeg = base64.b64decode(port.capture()["image"])
                    (out / "rgb" / rid / f"{tick:06d}.jpg").write_bytes(jpeg)
                    jpegs[rid] = jpeg
                # propose -> permits -> issue (pinned controller + pinned barrier)
                proposed, issued = episode.tick(now, jpegs, previous)
                if ledger is not None:
                    # The robot's NEXT own observation answers the PREVIOUS apply.
                    # The observation is the one the worker produced for this tick
                    # and the RGB digest is the own JPEG that was given to it.
                    for rid in roles:
                        ledger.record_observation(
                            rid, observation=proposed[rid]["observation"],
                            rgb_sha256=sha256_bytes(jpegs[rid]), tick=tick)
                # apply the issued command to the real actuators (S3 hook)
                applied = apply_issued_commands(
                    apply_callable=teacher_apply, roles=roles, issued=issued, ports=ports,
                    now=now, previous=previous, ledger=ledger, tick=tick)
                # advance the real physics by one control period (0.1 s sim)
                target = now + 0.1
                while float(world.data.time) < target - 1e-8:
                    t_now = float(world.data.time)
                    for port in ports.values():
                        port.tick(t_now)
                    world._physics_step_for(world.robot("r1"))
                weld = bool(world.data.eq_active.any())
                # own RGB + state AFTER the applied command (eval-only measurement)
                after = {}
                for rid, port in ports.items():
                    jpeg = base64.b64decode(port.capture()["image"])
                    qpos = world.data.qpos.tobytes()
                    after[rid] = {"own_rgb_sha256_after": sha256_bytes(jpeg),
                                  "own_rgb_bytes_after": len(jpeg),
                                  "qpos_sha256_after": sha256_bytes(qpos)}
                moved = 0
                for rid in roles:
                    if qpos_prev[rid] is not None and qpos_prev[rid] != after[rid]["qpos_sha256_after"]:
                        moved += 1
                    qpos_prev[rid] = after[rid]["qpos_sha256_after"]
                cmd_changed = sum(1 for rid in roles
                                  if issued[rid]["command"]["pwm"] != previous[rid]["pwm"])
                state_transitions += 1 if moved >= 1 else 0
                res["ticks"].append({
                    "tick": tick, "t_sim": now, "t_sim_after": float(world.data.time),
                    "physics_steps": steps_per_tick, "sim_advanced_s": round(float(world.data.time) - now, 6),
                    "weld_active": weld,
                    "own_rgb_sha256_in": {rid: sha256_bytes(jpegs[rid]) for rid in roles},
                    "previous_issued_command": {rid: dict(previous[rid]) for rid in roles},
                    "proposed_stage": {rid: proposed[rid]["stage"] for rid in roles},
                    "proposed_ready": {rid: bool(proposed[rid]["ready"]) for rid in roles},
                    "issued": {rid: {k: v for k, v in issued[rid].items()} for rid in roles},
                    "applied": applied, "after": after,
                    "robots_with_changed_qpos": moved,
                    "robots_with_changed_issued_pwm": cmd_changed,
                })
        finally:
            try:
                summary = episode.summary()
            except Exception as exc:
                summary = {"error": repr(exc)}
            res["worker_summary"] = summary

    # The scope owns cleanup exactly once on both success and failure. Gather
    # final child status only after it has closed; cleanup failures are logged.
    res["worker"]["exit_code"] = client.proc.returncode
    res["worker"]["requests"] = client.requests

    # ---- S4 evidence from the head's own trace ------------------------
    traces = sorted(trace_dir.glob("geometry-predictions-worker-*.jsonl"))
    preds = []
    for t in traces:
        for line in t.read_text().splitlines():
            if line.strip():
                preds.append(json.loads(line))
    real_forwards = [p for p in preds if p.get("record_type") == "geometry_prediction"]
    res["model_forward"] = {
        "trace_files": [str(t) for t in traces],
        "head_prediction_records": len(real_forwards),
        "model_forwards": len(real_forwards),
        "records": real_forwards,
        "note": "each record is one real GeometryActor.forward on the step-020000 actor (CPU)",
    }
    res["safety"]["model_forwards"] = len(real_forwards)

    # ---- S5 verdict --------------------------------------------------
    ticks = res["ticks"]
    consecutive = 0
    best = 0
    for t in ticks:
        if t["robots_with_changed_qpos"] >= 1:
            consecutive += 1
            best = max(best, consecutive)
        else:
            consecutive = 0
    res["state_transitions"] = {
        "ticks_run": len(ticks),
        "ticks_with_changed_qpos": sum(1 for t in ticks if t["robots_with_changed_qpos"] >= 1),
        "longest_consecutive_ticks_with_changed_qpos": best,
        "total_issued_pwm_changes": sum(t["robots_with_changed_issued_pwm"] for t in ticks),
        "definition": "a robot's MuJoCo qpos digest changed between consecutive control ticks "
                      "after the model's issued command was applied to the real actuators",
    }
    checks = {
        "worker_sha_pinned": pins["worker"]["sha256"] == EXPECT_WORKER_SHA,
        "checkpoint_sha_pinned": pins["checkpoint"]["model_sha256"] == EXPECT_CKPT_SHA,
        "astra_outer_loop_sha_pinned": pins["astra_outer_loop"]["sha256"] == EXPECT_ASTRA_SHA,
        "adapter_pins_match_tree": all(pins["adapter_pins_match_tree"].values()),
        "config_sha_matches_adapter_pin": pins["adapter_pins_match_tree"]["pairact_r1_config_sha256"],
        "worker_started_cpu": res["worker"]["handshake"] == {"ready": True,
                                                             "mode": "pairact_r1_student_eval_v1"},
        "real_model_forwards_2_or_more": len(real_forwards) >= 2,
        "ticks_run": len(ticks) >= 2,
        "every_tick_issued_a_command": all(
            set(t["issued"][rid]) >= {"command", "stage", "permit", "blocked"} for t in ticks for rid in roles),
        "every_tick_applied_to_actuators": all(
            t["applied"][rid]["actuator_state"] is not None for t in ticks for rid in roles),
        "physics_advanced_every_tick": all(t["sim_advanced_s"] > 0.099 for t in ticks),
        "weld_never_active": not any(t["weld_active"] for t in ticks),
        "own_rgb_after_every_tick": all(
            t["after"][rid]["own_rgb_sha256_after"] for t in ticks for rid in roles),
        "own_rgb_differs_between_robots": all(
            t["after"]["r1"]["own_rgb_sha256_after"] != t["after"]["r2"]["own_rgb_sha256_after"]
            for t in ticks),
        "two_consecutive_state_transitions": best >= 2,
        "worker_exit_zero": res["worker"]["exit_code"] == 0,
        "no_errors": not res["errors"],
        "gpu_zero": res["safety"]["gpu"] == 0 and res["safety"]["network"] == 0,
    }
    if ledger is not None:
        res["consumer_audit"].update({
            "ledger_rows": ledger.rows_written,
            "apply_calls": ledger.apply_calls,
            "apply_returned": ledger.apply_returned,
            "apply_exceptions": ledger.apply_exceptions,
            "observations": ledger.observations,
            "observations_linked_to_an_apply": ledger.observations_linked,
            "environment_applied": "unknown",
            "transmission_acknowledged": "unknown",
            "motion_observed": "unknown",
            "port_state": "not captured by the consumer ledger",
            "scope": "consumer-side call accounting; NOT a carry-success claim",
        })
    res["checks"] = checks
    res["verdict"] = "PASS" if all(checks.values()) else "FAIL"
    res["failed_checks"] = [k for k, v in checks.items() if not v]
    res["wall_s"] = round(time.monotonic() - T0, 3)
    res["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out / "e2e.json").write_text(json.dumps(res, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({
        "run_dir": str(out), "verdict": res["verdict"], "failed": res["failed_checks"],
        "ticks": len(ticks), "model_forwards": len(real_forwards),
        "state_transitions": res["state_transitions"], "wall_s": res["wall_s"],
        "worker_exit": res["worker"]["exit_code"],
    }, indent=1))
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
