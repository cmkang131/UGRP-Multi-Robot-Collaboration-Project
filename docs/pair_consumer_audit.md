# Consumer-side apply-call ledger (UGRP-Pair, 2026-11-05)

Branch: `ugrp/pair-consumer-audit-20261105T2046Z`
Base commit: `90c6e6580c7f9bde39c6b228e16786d8392bd14d` (the PR642 draft, no merge)

This round measures the **consumer side** of the pinned pair path: that the
apply callable was called, with what, and what came back -- and it binds that
call to the producer's issue record and to the robot's next own observation.

It is **not** a carry-success claim and **not** a security audit.

## What is new (4 candidate files, nothing else touched)

| File | Role |
| --- | --- |
| `harness/pair_consumer_audit.py` | the ledger + the verified producer reader (standard library only, loaded **by path**) |
| `experiments/2026-11-05-pair-consumer-audit/run_cpu_joint_e2e_consumer_audit.py` | an owned copy of the PR642 runner with the consumer wiring |
| `tests/test_pair_consumer_audit.py` | the new suite (53 tests) |
| `docs/pair_consumer_audit.md` | this document |

Nothing existing was modified: the PR642 runner, the producer audit module,
the bundle helper, the audit entry, the pinned trees, the original runner and
the schema files are untouched.  The new helper is loaded by path so it can
never shadow the pinned `harness` package of the physics closure.

## The contract

* **OFF by default.** `--consumer-audit off` (the default) creates no ledger
  and the run preserves the successful control behavior of the PR642 runner.
* **ON is a combination contract.** `--consumer-audit on` requires
  `--audit-worker on` together with `--audit-run-id`.  A consumer ledger
  without a producer audit file would have nothing to bind to, so that
  combination is refused (`SystemExit`) before anything is started.
* **The apply call is wrapped exactly once.** The S3 block of the owned copy
  calls `apply_issued_commands(...)`, which calls
  `apply_callable(ports[rid], cmd, now, prior)` -- the pinned
  `teacher_apply(ports[rid], cmd, now, previous[rid])` -- exactly once per
  robot.  No second call, no changed argument.
* **The prior is copied before the call.**  The original runner overwrites
  `previous[rid]` with the command right after the apply, so its logged
  `previous_issued_command` is the *current* command (a known legacy quirk).
  The ledger copies the command and the prior **before** the call, so the
  ledger keeps the real prior.  The original metric is left exactly as it is.

## Phases: nothing changes before everything is checked

The ledger is a state machine.  Every phase validates **everything** before it
changes **anything**, so a refused call leaves the ledger exactly as it was --
pending applies, consumed rows, issue counters and counters included:

1. `attach_apply` -- bind one identified apply callable (an alias is refused).
2. `begin_apply` -- the call is about to happen: the command and the prior are
   copied and the call is bound to the producer's **next** issue of that robot.
3. `end_apply` -- the call returned or raised: exactly one result row, and the
   apply becomes *pending* (it awaits an observation).
4. `record_observation` -- the robot's next own observation: it is checked
   against the body, the producer row and the pending apply; only then is the
   pending apply released and a counter moved.
5. `close` -- the applies that no observation answered are written
   explicitly, followed by the summary.

A closed ledger refuses every call.  An open apply may not be overwritten, a
result may not be written twice, and an apply that no observation answered
blocks the next apply of that robot (so the evidence is never overwritten
either).

## What the ledger records

One JSONL file per `(run_id, episode_id)`:
`<consumer-output-root>/pair-consumer-audit-<run-id>-<episode-id>.jsonl`

The file is created with the exclusive `'x'` mode: an existing file is
refused, never overwritten.  The file name must be a plain basename inside the
output root; an absolute path or a path that leaves the root is refused.  Every
row carries the schema `ugrp.pair_consumer_audit.v1`, the run id, a contiguous
`seq` and a `row_digest` over the canonical JSON of the row (the same rule the
producer uses: `sort_keys`, `separators=(',',':')`, `allow_nan=False`).  The
reserved envelope fields (`schema`, `run_id`, `seq`, `claim`, `row_digest`)
may not be overridden by a row.  Rows are interleaved in one ledger file; `robot_id` identifies each robot-specific row.

| Row | Content |
| --- | --- |
| `inventory` | the episode, the robots, the producer file, the identified apply callable, and the explicit "unknown" statements |
| `apply_call` | **before** the call: a deep copy of the command, a deep copy of the prior, both digests, the bound producer issue |
| `apply_result` | **after** the call: `outcome` = `returned` (with the return value) **or** `exception` (with type and message) |
| `observation_link` | the robot's next own observation, the RGB digest of the own JPEG that was given, and the apply it answers |
| `unanswered_apply` | an apply that no later own observation answered (or whose outcome was never recorded) |
| `run_summary` | the counters and the explicit limits |

### The exact limits (also written into the rows)

* `apply_returned` is **only the return value of the called function**.  It is
  NOT environment application, NOT a transport acknowledgement and NOT motion
  evidence.  Every result row states
  `environment_applied = unknown`, `transmission_acknowledged = unknown`,
  `motion_observed = unknown`.
* The **port state is not captured at all** (`port_state = "not captured by
  this ledger"`).
* An exception is recorded as an exception.  A missing port state stays
  missing.  No acknowledgement, no "applied" flag and no motion result is ever
  synthesised.
* The **origin** of an issued command is never inferred.  Values, zero wheels,
  a `permit` flag or a repeated command are never used to attribute anything;
  the origin is only copied from what the producer declared.
* The last own observation of a robot may precede its last apply; such an
  apply is listed as an `unanswered_apply` row.

### What the identity and the episode id are (and are not)

* The apply callable is identified by **module, qualname and the sha256 of
  its source file**, and the identity must match the expected one and must
  not change within a ledger.  That is a **label that detects a swapped or
  aliased callable** -- it is **not** an authentication of the caller, it
  proves nothing about who called it, and it is not a security control.
* The episode id is **only a file name and a label** in the rows.  Nothing
  verifies that the episode really happened.

## Binding to the producer

The producer file is `<audit-output-root>/pair-audit-<run-id>.jsonl`.  It is
read **read-only**: the schema and the run id must match, the `seq` values
must be contiguous integers (a string or a boolean sequence is refused), the
issue numbers must be dense per robot, and every row's `record_digest` must
recompute.

The file is re-read completely on every refresh, but only the part that was
not accepted before is parsed, and the **already accepted prefix is
re-verified by its hash**: a file that was edited, truncated or replaced after
it was read is refused, and the reader becomes **terminally invalid** -- it is
not trusted again.  A refresh that fails is atomic (no partial state).  Only
the rows the producer actually flushed are read: a trailing partial line is
ignored.

A command is bound to the producer issue with the **next `issue_number`** of
that robot, so the order is preserved, a skipped issue is refused, a
duplicated issue is refused, one issue can never be bound twice, and a
repeated identical command at the same time stays distinguishable.

The next own observation is the `observation` of `StudentEpisode.tick`
(`proposed[rid]['observation']`).  It is bound to the producer's `observation`
row through the **robot id and the sample id**, and the checks are: the body's
robot id, the producer row's robot id, the sample id, the time, the
observation digest and the producer's `linked_issue_seq` against the pending
apply.  Only when all of them agree is the pending apply released; a mismatch
is refused and the pending apply (and its unanswered evidence) survives.  The
RGB digest is the digest of **the own JPEG that was given to that robot** for
that tick, and of nothing else.

Times are checked: they must be finite numbers and must not go backwards for
a robot.

## The producer is never modified

The producer's raw records, its responses, its schema and its model input are
untouched; no metadata is added to them and no ground truth is fed to the
model.  The consumer only *reads* the producer file.

## The CLI

```
--consumer-audit {off,on}     default off
--consumer-output-root PATH    default <run-dir>/consumer-audit
--consumer-episode-id ID       default the plan's episode id
```

`--prepare-only` plans the ledger and writes `consumer-audit-plan.json`, but
it does **not** create the ledger file (the worker never starts, so there is
nothing to account for).

## Lifecycle

The ledger is created **after the world build and before the worker starts**
(its file is created exclusively; the producer audit file may still be empty
at that point, because the producer writes it while it runs).  The worker
startup and the joined loop run inside an ownership scope: if anything fails
there -- the worker startup included -- the child is closed, the ledger is
closed (an unanswered apply is written), a ledger close failure is recorded
in `res["errors"]` and the **original exception is re-raised unchanged**.  The
worker client also closes its own child when the handshake fails.

## Tests

`tests/test_pair_consumer_audit.py` -- 53 tests, CPU only, no model, no
simulator, no head worker, no physics, no network.

* the S3 hook of the **owned runner file is executed** with a fake apply
  callable and fake ports (an AST check additionally proves that `main()`
  really calls the hook and no longer calls `teacher_apply` directly);
* the call happens exactly once, with the pinned arguments;
* the prior is the real prior; the return value and an exception are two
  separate facts; nothing is dressed up as an acknowledgement;
* the next own observation links to the apply; an observation that points at a
  different issue is refused;
* an unanswered apply is recorded at close;
* **the seven counterexamples of the coordinator's direct review are refused
  one by one** (wrong-robot observation, changed observation, out-of-order
  issue, edited producer prefix, duplicate result, a failed observation that
  must not delete the pending apply, an absolute file name) and each refusal
  keeps the evidence;
* further refusals: a shrunk producer file, a foreign run id, a foreign
  robot, a missing issue, a duplicated row, an edited row, a reused issue, an
  existing consumer output, an aliased apply callable, a missing producer file
  at binding time, a reserved envelope field, a path that leaves the output
  root, a closed ledger, an open apply, an unanswered apply, a non-finite or
  backwards time, a string or boolean producer sequence;
* consumer OFF creates nothing and preserves the successful control behavior of the original;
* the real CLI in `--prepare-only` mode plans the ledger and creates no ledger
  file (exit 0, `model_forwards = 0`, `worker_started = false`,
  `mujoco_imported = false`).

## What is NOT connected (honest limits)

* There is **no consumer of the apply result**: nothing observes the
  environment, the transmission or the motion.  The ledger stops at the
  function boundary.
* The **port state is not captured**; `ports[rid]._actuator_state()` is
  still recorded by the runner itself, exactly as before, and it is not part
  of the ledger.
* The producer-side and consumer-side rows are linked by the producer's own
  `linked_issue_seq` and by the command digest; there is **no independent
  proof** that the command the consumer applied is the one the producer
  issued -- the link is the producer's own bookkeeping.
* The callable identity is a **label, not an authentication**; the episode id
  is a **file name, not a verified fact**.
* The link is only exercised with a **synthetic wiring** (fake apply, fake
  ports, a synthetic producer file).  No real run of the pair path was
  performed in this round: no model forward, no MuJoCo, no head worker, no
  real robot, no GPU, no network.
* The pytest environment is **pytest 9.2.0**; the repository CI pins
  **pytest 9.1.1**.  The numbers below were produced with 9.2.0.
* This is a **runtime forensic logger**, not a security audit, and not an
  origin attestation.

## Coordinator corrections after producer-prefix review

Refresh validates each new row against a private prospective index, including
rows in the same read. Duplicate issue/sample numbers, a non-dense issue order
and an issue command that disagrees with its digest are refused before the
accepted index changes; reader failure remains terminal.

The worker scope owns cleanup exactly once on both normal and exceptional
exit. Cleanup failures are logged and cannot replace the body exception.
An apply exception also remains the original exception if writing its audit
result fails. Final local validation: 53 consumer tests, 266 total passing tests,
four torch skips and 13 subtests; pytest 9.2.0 is separate from pinned CI.

### Review follow-up

Audit OFF preserves successful control behavior. Failure paths include the
child cleanup improvements described above. The bundle helper loads once;
the consumer helper hash is checked before its module code executes and is
rechecked when consumer auditing is enabled. These checks pin source bytes,
not the identity of a caller.
