# Optional raw candidate observer

This add-on writes `raw_proposal_snapshot` to the existing `PairWorkerAudit.sink`.
It is disabled by default and does not change the pinned worker, bundle pins,
4-op replies, observation schema, barrier, issued commands or model weights.

Wrap the already audited controller with `ProposalObserver(audited_controller,
enabled=True, source_controller=raw_controller, sink=audit.sink,
expected_source_sha256=...)`. The raw object must be the same source controller
that the audited controller delegates to; that association is supplied by the
caller, not authenticated by a digest. Source hash means file identity, not
proof of executed code. The owned worker loop accepts `--observe-raw-proposals` only with audit enabled. Outer-runner/bundle pins are being updated separately; do not run an old bundle against changed sources.

The wrapper calls propose exactly once, then copies each raw
`(proposal, done, previous)` before issue empties `controller.proposals`.
Snapshot has sample/episode labels, observation/previous/proposal digests, stage,
blocked and source-file hash. It records the executor's candidate command,
not the entire network output chunk, issued origin, application, acknowledgment
or motion. No image bytes, GT or partner state enter the record or model input.
Existing sink envelope supplies run ID, sequence and row digest. This digest is
integrity checking, not authentication. It does not by itself supply a link to
a particular later issued record; sample/observation digest must be matched.

A capture/write failure increments out-of-band `capture_failures` and sets
`last_capture_error`, returns the unchanged controller result, and does not
prevent issue. In that case capture completeness is unknown. This policy only
covers this observer's optional write; existing audit checks retain their
original behavior. File writes are synchronous and can add latency; exceptions
are nonblocking for control, but a hung OS write has no hard timing guarantee.
Do not claim runtime timing equivalence from value equivalence.

Current source evidence: the external preserved 4-tree controller
`harness/pairact_r1_student.py` SHA256
`3e12d2f5408f82821187401e8a6d4298cb70fb27b48c229d689a54efdef77e81`.
A direct runtime test instantiates this controller, its actual executor and
barriers with a fixed synthetic predictor. Candidate wheels .35 are retained
while blocked issued wheels are zero, then proposals clear on issue; capture
ON/OFF values match. This confirms the current preserved controller interface.
The older SIM VM tarball lacks this controller file, so its historical runtime
identity is unresolved. Neither candidate reconstruction nor historical
controller identity is inferred from this new test.

Validation: 15 targeted tests, including existing sink JSONL envelope,
source-pin rejection, deep-copy separation, missing candidate, identity/time
mismatch, failing sink, default OFF and actual pinned-controller ON/OFF parity.
The integration test explicitly skips if the external pinned tree is absent;
pure observer tests remain runnable. No learned forward, SIM or GPU.

The previous report's zero-init action/stage equality concerns initialization,
not final20k versus frozen actor. A future geometry intervention should keep
the actor, weights, observations, seed and protocol fixed and explicitly version
the projection toggle, with this sidecar in both arms. This patch implements
neither that intervention nor a new inference/physics run. Data would test a
conditional necessity hypothesis, not establish a unique historical cause.


## Completeness artifact and grain

The owned loop reserves `proposal-status-<run_id>.json` exclusively and updates
it after each capture attempt. At normal/error shutdown it calls finish before
closing the existing audit sink. The independent status file carries run ID,
source-file hash, attempted/captured/failed ticks, expected/captured robot
candidates, last exception type, status-write failures and finished/complete.
Zero attempts is not a complete diagnostic. A failed per-tick snapshot drops
that entire tick, not one robot. The captured tick count increases only after
the sink write returns. A partially written/corrupt JSONL remains invalid.

The sink also receives `proposal_capture_summary` at finish, best effort.
When the shared sink fails, the independent file can still report missing
records. If both outputs fail, or the status file is absent/truncated/not
finished, capture completeness is unknown, never successful. A file write can
block at OS level; nonblocking refers to exception handling, not timing.

Each raw_proposal_snapshot JSONL row represents ONE propose tick and contains
all robots. Six ticks for two robots means six snapshot rows and twelve robot
candidates. propose_op has a separate tick denominator; issue_command counts
issued robot commands. These units must not be pooled. `previous` is the issued
command supplied by the environment/controller request, not an independently
measured application or actuator state.

Integration test: actual owned_worker_main + preserved pinned controller with
a fixed synthetic predictor, both arms audit ON and observer OFF/ON. Six ticks,
two robots, matching observation_digest across adjacent propose_op/snapshot,
12 captured robot candidates, complete final status and equal stdout responses.
Together with the existing worker suite:51 passed. Model/head/SIM/GPU0.
