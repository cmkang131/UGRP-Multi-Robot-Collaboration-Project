# Pair-worker provenance audit — contract (candidate)

Branch: `ugrp/pair-worker-audit-20261105T1952Z` · Date: 2026-11-05 · Owner: UGRP-Pair

This document is the contract of a **candidate** add-on. It is not a claim that
the pair path is complete. Nothing here changes the pinned worker, the pin,
the checkpoint, the model/geometry allowlist, the barrier/GO-ACK semantics or
the physical control path.

## 1. What the candidate is

| File | Role |
| --- | --- |
| `harness/pair_worker_audit.py` | the opt-in audit module **and** the owned four-operation entry wrapper |
| `tests/pair_worker_audit_scenario.py` | synthetic scenario driver (subprocess) |
| `tests/test_pair_worker_audit.py` | pytest suite (unit + integration) |
| `docs/pair_worker_audit.md` | this contract |

The candidate is **default OFF**. It is enabled only by passing both
`--audit-run-id` and `--audit-output-root` to the owned entry.

## 2. Real connection points

The pinned pair path is `scripts/geometry_pair_worker.py` (four JSON-lines
operations `reset` / `propose` / `issue` / `summary`) on top of the pinned
`harness/pairact_r1_student.py` (`OwnInputs`, `PairStudentController`).

* `owned_worker_main` in `harness/pair_worker_audit.py` is the **owned copy**
  of that four-operation loop. The pinned script is imported **read-only**
  (`load_pinned_geometry_worker`) and its operation allowlist (`OPS`) and
  `MODE` are compared against the candidate's own copy; a mismatch stops the
  run. The pinned file is never edited.
* At `reset` the pinned controller is wrapped by `PairWorkerAudit.attach`.
  The wrapper is transparent: it returns the pinned values unchanged.
* `AuditedInputs` replaces `controller.inputs[robot_id]` **in place** with a
  proxy that delegates every attribute to the pinned `OwnInputs`. The pinned
  `OwnInputs` object is not modified, and the pinned `OwnHistory` of the main
  branch is **not** used in its place.
* `AuditedController` proxies `propose` / `issue` / `summary` and records the
  protocol view of each call.

The candidate's own sha256 is recorded in the audit inventory and is
**different** from the pinned worker sha256. The inventory states
`candidate_is_the_pinned_worker: false`.

## 3. Conservation contract

* The stdout four-operation responses are byte-identical with the audit ON
  and OFF (verified by test). No audit field is added to a response, to a
  model observation, or to a command.
* The pinned observation dict, the returned values and the issued command
  values are passed through unchanged.
* The barrier, the READY/GO-ACK hold and the `done`/segment sequence are the
  pinned ones. The audit only records them.
* The audit material goes to **one new JSONL file per run**, opened with the
  exclusive `'x'` mode. An existing file is never overwritten and a run id is
  never reused; a second attempt raises `AuditError`.
* **Fail closed.** A harness tree mismatch, a pinned source hash mismatch, an
  unwritable audit file or a malformed audited value raises `AuditError` and
  stops the run. A harness tree that mixes the candidate with another tree is
  refused.

## 4. What is recorded, in which order

| kind | meaning |
| --- | --- |
| `inventory` | candidate path + sha256, audited controller path + sha256, contract path + sha256, tree root, verified pinned sources, origin policy |
| `reset_padding` | the replicated initial window of one robot: count, whether all rows are identical, row digest, contract history length |
| `observation` | one produced observation: robot, sample id, `t`, observation digest, issued-window digest, window length, `linked_issue_seq` (the issue that preceded it) |
| `issue_command` | one issued command: robot, `t`, command digest, the command values, origin, `supersedes_observation_seq` (the observation it supersedes), issue number |
| `propose_op` | the protocol view of one propose: per robot the sample id, observation digest, window digest, ready flag, stage, rgb path |
| `issue_op` | the protocol view of one issue: per robot the command digest, permit, blocked, done, stage, segment and the linked propose sequence |
| `summary_op` | the digest of one summary response |
| `pending_observation` | an issue command that no observation followed (`unpaired: true`) |

Order rules:

* The propose observation is **validated and written before** the issue that
  supersedes it; the issue names it in `supersedes_observation_seq`.
* The issue command is written **immediately**, before the next observation.
* When no observation follows an issue, the record is marked `unpaired`.
  **No sample is ever invented.**
* The records carry a contiguous `seq` and a `record_digest` over the
  canonical JSON of the record, so the file can be re-read and verified.

Every record carries the constant claim:

> issued at the producer only; not environment application, acknowledgement,
> or motion success

## 5. Origin policy

The origin of an issued command is `unknown` unless the caller **explicitly
declares** `policy` or `protocol_hold` at the moment of the call. A zero-wheel
command, `permit=False` or an identical command value are **not** used to
infer an origin, because the pinned path cannot tell those cases apart. In
the synthetic run all 48 issued commands are recorded with `origin: unknown`,
including the 4 protocol holds.

## 6. What this candidate does NOT prove

* It does not prove that a command was applied to the environment, that the
  robot moved, or that any GO/ACK was received.
* It does not prove environment application or acknowledgement of anything.
* It does not replace the pinned `OwnInputs` with the main-branch
  `OwnHistory`; the pinned pair path still uses `OwnInputs`.
* It does not connect the legacy solo `run_grasp_act_student` path, and the
  pair path is **not** complete.
* It does not use a learned model. The predictor in the scenario is a **fixed
  synthetic predictor** (constant chunk, constant stage plan); no model
  forward, no simulator, no GPU, no real robot and no head worker process is
  started.

## 7. Unconnected boundaries (explicit)

* The `GeometryHeadClient` of the pinned script still spawns the real head
  process when the owned entry is used with `--headworker`; that path is
  **not** exercised by the tests (the tests inject a synthetic predictor).
* The audit records the **producer** side only. The consumer side (the
  simulator / runner applying the command) is not connected to the audit file.
* The `run_cpu_joint_e2e.py` CPU e2e candidate and
  `pairact_student_eval.py` are verified by hash only; they are not wired to
  the audit.
* The recorded `origin` cannot reach `protocol_hold` on the pinned path
  without an explicit declaration at the call site; the pinned controller
  calls `OwnInputs.issue(value)` without one.

## 8. How to run the checks

```
PYTHONPATH=<worktree> PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  <coordinator-venv>/bin/python -m pytest tests/test_pair_worker_audit.py -q -rs -p no:cacheprovider
```

The pinned worker tree and the pinned geometry worker are read-only inputs.
The scenario copies the pinned harness into a scratch tree and drops the
candidate module next to it; the originals are never modified.

## Coordinator corrections

The sink refuses caller overrides of schema/run_id/seq/claim/record_digest and keeps custom filenames within output_root. Invalid origin/command input is checked before the pinned input proxy mutates; recorded issue values are read back from its actual issued tail. JSONL state counters advance only after the corresponding write succeeds. Source manifests and partial audit options are validated before importing or launching a head. File I/O failure remains fail-closed, and is not a cross-process transaction guarantee.

The scenario preparation helper refuses an existing destination and preserves its content. It never deletes or replaces caller-provided directories.


## Independent review and exact evidence boundaries

UGRP-Verify independently reproduced 138 passing tests and 13 subtests for the reviewed candidate; no code contract violation remained. The following scope clarifications resolve review D1–D7 without changing code:

- `pinned_sources` contains only the operator-supplied manifest entries. An empty manifest verifies no pins. Controller and contract runtime hashes are recorded independently, but a manifest that omits those actual runtime files does not protect them. In particular, the geometry worker script path/hash is absent unless the manifest explicitly includes it. A deployment bundle must include it and the actual controller/contract paths before treating the file as a pinned-source audit.
- The tested sequence has no `done=true` event. Release, finish, completion transitions and the actual GeometryHeadClient process are untested. The tests prove only the synthetic grasp-segment path.
- The ready protocol line precedes reset/attach. An attach failure can therefore occur after ready and leave an empty exclusively-created JSONL file. Empty output is incomplete/failed attachment evidence, never a successful zero-event run; preserve it and its failure log.
- `record_digest` checks each JSON row's self-consistency. It is not an authenticated origin, a cryptographic event chain, an environment acknowledgement or independent evidence that an operation occurred.
- Controller inputs are wrapped with delegation proxies. The original objects remain the behaviour providers; no main-branch OwnHistory substitution occurs.
- The audit module must be installed in the same harness package as the audited controller. Launching directly from a different tree can fail with ModuleNotFoundError before attach. That is an unsupported deployment, not a tested fallback. The deployment bundle must prove actual import paths rather than just sys.path intent.

The same-tree deployment bundle, outer-runner worker selection and consumer-side receipt linkage remain the next implementation stage. JSONL from the current synthetic run must not be cited as a learned-model, environment-application or transport-success result.
