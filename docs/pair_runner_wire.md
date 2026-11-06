# Pair-runner audit wiring — contract (candidate)

Branch: `ugrp/pair-runner-wire-20261105T2017Z` · Base: `f041590b7…` · Date: 2026-11-05
Owner: UGRP-Pair · Reviewer: Ugrp (agent-24194e08-01b9-4e93-a6d7-0a8195436830)

This is a **candidate**. It connects the already accepted audit worker to the
**real outer runner**: the worker selection, the same-tree placement and the
required manifest, wired into a runnable candidate with **prepare execution
evidence** (not a plan).

## 1. Files (5)

| Path | Role |
| --- | --- |
| `harness/pair_worker_bundle.py` | bundle helper: exclusive creation, byte copy, pin tables, manifest, startup verifier |
| `harness/pair_worker_audit_entry.py` | launch entry: verifies the bundle, then calls `owned_worker_main` explicitly |
| `experiments/2026-11-05-pair-runner-wire/run_cpu_joint_e2e_audit_wire.py` | owned copy of the outer runner (worker selection parameterized) |
| `tests/test_pair_runner_wire.py` | pytest suite (50 tests) |
| `docs/pair_runner_wire.md` | this contract |

The original outer runner
`/home/ubuntu/UGRP/experiments/2026-11-04-joint-carry-cpu-e2e-real20k-v1/candidate/run_cpu_joint_e2e.py`
is **read-only and unmodified** (sha `6d62f2a2…`, checked by a test).

## 2. The real connection path

```
run_cpu_joint_e2e_audit_wire.py            (owned copy of the outer runner)
  └─ plan_worker(out, trace_dir, args)     (the only new control point)
       ├─ audit off → original_worker_argv(trace_dir)   == the original argv, byte for byte
       └─ audit on  → create_bundle(...)                 (exclusive, byte copy, same tree)
                      verify_manifest(...)               (strict, before any worker starts)
                      verify_import_same_tree(...)       (real import of the bundle)
                      audited_worker_argv(...)            (bundle entry + audit options)
  └─ boot_worker(argv=…, client_factory=…)               (the injectable worker client)
       └─ GeometryWorkerClient                            (the original transport)
```

The runner never *declares* an address: the argv it writes into the artefact is
the argv the same code hands to `subprocess.Popen` in S2.

### Why the entry file exists

`harness/pair_worker_audit.py` exposes the function `owned_worker_main` but has
**no `__main__` block**, so `python -m harness.pair_worker_audit` imports the
module and exits without running anything (checked by a test).
`harness/pair_worker_audit_entry.py` calls `owned_worker_main` explicitly and
is what the runner launches.

### Why a bundle tree

`harness.pair_worker_audit.check_same_tree` requires the audit module and the
audited `harness/pairact_r1_student.py` to live in ONE `harness` package
directory.  The bundle therefore copies the pinned worker tree (`harness` +
`scripts`) byte for byte into a fresh, exclusively created directory and places
the audit module, the launch entry **and the bundle helper** into the same
`harness` package.  The bundle root is then the `--student-root` of the worker
process, and the entry can verify the startup with the helper in its own tree.

## 3. Worker selection contract

| | audit OFF (default) | audit ON |
| --- | --- | --- |
| entry | the ORIGINAL `geometry_pair_worker.py` | `<bundle>/harness/pair_worker_audit_entry.py` |
| `--student-root` | the pinned tree | the bundle root |
| `--model` / `--config` / `--headworker` / `--head-source-root` / `--geometry-trace-dir` | unchanged | unchanged |
| added | none | `--geometry-worker`, `--audit-run-id`, `--audit-output-root`, `--audit-sources` |

OFF keeps the original argv **byte for byte** (asserted against the literal
list of the original runner).  ON changes only the entry, the student root and
the audit options.

## 4. Start-up verification (the audited entry)

The audited entry **verifies before it speaks**.  Before ANY output, before
the head worker is imported or started and before the audit file is created,
`harness/pair_worker_audit_entry.py` requires:

1. the whole audited option set — `--audit-run-id`, `--audit-output-root`
   **and** `--audit-sources`;
2. `--student-root` to be the bundle root of the entry itself;
3. `--geometry-worker` to be the pinned geometry worker, and `--headworker` /
   `--config` to be the pinned ones when they are given (both are required
   for a real head run);
4. the manifest to be a non-empty mapping that binds every required path, and
   every bound file to hash exactly as recorded;
5. every required path to hash as the **independent expected hash** — the pin
   tables of `harness/pair_worker_bundle.py` and the two candidate hashes
   baked into the entry.  A manifest that only agrees with itself is refused;
6. the **ORIGINAL pinned tree files** to still hash as the expected values, so
   a copy of a wrong source is refused;
7. the audit module and bundle helper to match independent candidate hashes;
   the entry path must be present with its recorded hash. The reviewed runner,
   rather than the entry itself, independently pins the entry bytes.

Any failure prints one line on stderr and exits non-zero: **no `ready` line,
no head worker, no audit file**.

### Trust chain

`entry (reviewed candidate)` → `bundle helper sha` → `helper pin tables` →
`pinned tree subset + read-only originals` → `manifest must agree`.
The runner keeps a **second, independent copy** of the pin tables and of the
three candidate hashes; it refuses to build a bundle when the two copies
disagree (`pin table drift …`) or when a candidate file does not hash as
pinned (`candidate source hash drift: …`).

## 5. Bundle and manifest contract

* The bundle root is created **exclusively**; an existing destination is
  refused, nothing is deleted and nothing is overwritten.
* The pinned `harness` and `scripts` are copied **byte for byte** and
  **every copied file is re-hashed against its source** at creation time
  (`files_byte_compared` in `bundle-info.json`, 1683 files for the current
  pinned tree).
* The manifest (16 entries) binds the **protected scope**:
  the copied controller / contract / pairact / beamact / policy / `__init__` /
  `robot_actions` (7), the candidate module, entry, helper **and the raw
  ProposalObserver** (4), and the read-only originals (geometry worker, head
  worker, head policy, config, ASTRA outer loop) (5).  Each tree entry also
  records its `source_path`, so the original pinned file is checked as well.

  **Why 16 and not 15 (2026-11-06, UGRP-Pair):** the raw ProposalObserver is
  imported by the audited worker as `harness.pair_proposal_observer`, so it
  must live in the **same** harness tree as the pinned controller.  A bundle
  without it would bind only 15 entries and could never be an audited start,
  so `create_bundle` now **refuses an incomplete candidate set** and pins the
  observer bytes independently (`EXPECTED_OBSERVER_SHA`).
* The manifest is verified **before the worker starts** and **again by the
  entry at start-up**.  An **empty or incomplete manifest is an error**,
  never a "verified pin"; a forged hash, a missing file and a self-consistent
  manifest over a wrong source are refused.
* The same-tree claim is checked with a **real import** of the bundle's
  `harness.pair_worker_audit`, `harness.pairact_r1_student`,
  `harness.grasp_act_contract` and `harness.pair_proposal_observer` in an
  isolated subprocess (neutral working directory, bundle-only `PYTHONPATH`),
  comparing the `__file__` paths **and** requiring them to be inside the
  **requested** bundle root.  A candidate from another tree is refused.

### Protected vs unprotected scope (stated precisely)

* **Protected (pinned by the manifest and re-verified at start-up):** the 7
  required tree files, the 4 candidate files (audit module, launch entry,
  bundle helper, raw ProposalObserver) and the 5 read-only originals.
* **Unprotected:** the rest of the copied tree (about 1676 further files).
  They are byte-compared against their source **at bundle creation**, but
  they are not in the manifest, so a later change to one of them is **not**
  detected.  `bundle-info.json:unprotected_scope` states this.

### Required subset (must be bound by the manifest)

`harness/__init__.py`, `harness/grasp_act_contract.py`, `harness/pairact_r1.py`,
`harness/pairact_r1_student.py`, `harness/beamact_pair_student.py`,
`harness/grasp_act_policy.py`, `scripts/robot_actions.py`
(+ the candidate `harness/pair_worker_audit.py`,
`harness/pair_worker_audit_entry.py`, `harness/pair_worker_bundle.py`,
+ the read-only originals).

## 6. `--prepare-only`

The real CLI

```
python experiments/2026-11-05-pair-runner-wire/run_cpu_joint_e2e_audit_wire.py \
    --run-dir <new dir> --audit-worker on --audit-run-id <id> --prepare-only
```

runs the original S0 pin block, creates the bundle, verifies the manifest,
checks the same tree with a real import, builds the launch argv and writes:

| artefact | content |
| --- | --- |
| `prepare.json` | bundle root, manifest path, verification flags, the final argv + its sha256, the **real** source hashes of every bound file, and the not-executed state |
| `final-argv.json` | the launch argv and its digest |
| `bundle-manifest.json` | the verified manifest |
| `e2e.json` | the runner's own record, including the original pins |

`prepare.json` states `executed: false`, `model_forwards: 0`,
`worker_started: false`, `mujoco_imported: false` and the list of stages that
were **not** executed (MuJoCo import, world build, head-worker Popen, model
forward, worker start, physics, actuator apply).  The test asserts that no
`scene.xml`, no `worker-stderr.log` and no head trace exist in the run dir.

## 7. What is still NOT connected

* **The consumer side.** The audit file records the producer side only.  The
  simulator / actuator path that applies an issued command is still not
  connected to the audit, so environment application and acknowledgement are
  **not** proven by anything here.
* **The real head and the real model.** The `--headworker` path of the owned
  entry is not exercised: the tests inject a synthetic predictor.  No model
  forward, no simulator, no GPU and no head-worker process ran.
* **The pair path is not complete.** The legacy solo path is not connected.
* The audit module must be deployed into the same harness tree as the audited
  controller; the bundle is the mechanism for that, not a source change.

## 8. Verification (normal pytest, coordinator venv only)

```
PYTHONPATH=<worktree> PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  <coordinator-venv>/bin/python -m pytest tests/test_pair_runner_wire.py -q -rs -p no:cacheprovider
```

* `50 passed`, exit `0`.

What it covers: the owned copy keeps S1/S3/S4/S5 **byte-identical** and
**AST-identical** to the original and differs only in the worker selection;
the OFF argv is the original argv; the ON argv selects the bundle entry and
keeps the original options; the bundle is exclusive, byte identical and
refuses to overwrite; the whole copied closure is byte compared; the manifest
binds the protected scope and is connected to the original expected hashes;
empty / incomplete / forged / missing entries are refused; the real import
proves the same tree and a foreign tree is refused; the runner's and the
helper's pin tables agree and the candidates hash as pinned; the **real CLI**
`--prepare-only` runs, writes the artefacts and starts nothing; the **boot
entry** really speaks the four operations with the synthetic predictor, OFF
and ON give identical responses, all 48 origins stay `unknown`, and the pinned
release/finish sequence is reachable with a synthetic completion flag; and the
**audited entry refuses to start** with a non-zero exit, no `ready`, no head
worker and no audit file on an empty manifest, a manifest without a required
controller / contract / geometry-worker key, a self-consistent manifest over a
forged source, a deleted required file, a file that drifted after the
preparation, a foreign geometry worker and a foreign student root.

## 9. Synthetic limits

* The predictor is a **fixed synthetic predictor**: constant chunk
  (`wheels 0.35`, `duration 0.15`, `pwm 1500`), constant stage plan.  The
  learned checkpoint is not exercised.
* `--synthetic-done` makes the completion flag appear after the first
  prediction, so the pinned `approach → READY → GO/ACK → execute` path
  completes first and the pinned release (3 s of continuous own done flags)
  and finish (1.5 s) sequences are reached.  The test asserts the `release`
  skill, the `release` segment and the `finished` flag.
* The audit does not certify the correctness of the pinned behaviour it
  records; it only records it.

### Startup argument interpretation

The entry validates the namespace from the same argparse parser as the worker.
Repeated options use the last value in both validation and execution; accepted
`--name=value` syntax and abbreviations are validated identically. A preceding
pinned value cannot mask a later unpinned configuration or source path.

The worker selection is retained separately from the S1 episode plan. The
actual S2 block is exercised with an injected client after an episode plan
has been loaded; prepare-only does not by itself prove S1-to-S2 execution.

### Reviewed validation and entry trust boundary

Independent review accepted the candidate with no code blockers. The runner
suite passed 50 tests; the four audit suites passed 188 tests and 13 subtests.
The impact suite passed 25 tests and skipped four because torch is absent.
These local checks used pytest 9.2.0, not the repository pin 9.1.1.

The entry cannot independently pin its own bytes. Its trust anchor is the
reviewed runner EXPECTED_CANDIDATE_SHAS plus the emitted manifest; invoke an
audited bundle through that runner. Directly launching an arbitrary entry
is not independent evidence of its authenticity.
