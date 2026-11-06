# Raw ProposalObserver: bundle / entry / outer wiring

Branch: `ugrp/raw-proposal-observer-20261106T0043Z` · Date: 2026-11-06
Owner: UGRP-Pair · Scope: **wiring only** — the coordinator's frozen core
(`harness/pair_worker_audit.py`, `harness/pair_proposal_observer.py`) is
read-only here.

## 1. What this round changed

The coordinator already implemented and froze the raw ProposalObserver core
and wired it into the owned worker loop.  This round does the **bundle / entry
/ outer wiring** so the observer can actually be used in a run:

| File | Change |
|---|---|
| `harness/pair_worker_bundle.py` | the observer is the **fourth candidate** and is copied into the **same** harness tree; an incomplete candidate set is refused; the observer bytes are pinned independently (`EXPECTED_OBSERVER_SHA`); the import probe now imports the observer too |
| `harness/pair_worker_audit_entry.py` | `--observe-raw-proposals` is connected (opt-in, default OFF); the startup scope covers the observer (16 manifest entries); the independent hashes of the audit module, the helper and the observer were refreshed to the current core |
| `experiments/2026-11-05-pair-runner-wire/run_cpu_joint_e2e_audit_wire.py` | `--observe-raw-proposals` opt-in flag; passed into the audited argv only when requested; refused with `--audit-worker off`; candidate pins refreshed |
| `experiments/2026-11-05-pair-consumer-audit/run_cpu_joint_e2e_consumer_audit.py` | the same wiring, on top of the consumer ledger |
| `tests/test_pair_proposal_observer_bundle.py` | **new**: 32 wiring tests |
| `tests/test_pair_runner_wire.py` | the bundle fixture now carries the fourth candidate (15 → 16 entries) |
| `docs/pair_runner_wire.md` | the manifest scope is stated as 16 entries, with the reason |

## 2. The 16-entry manifest

| Group | Count | Members |
|---|---|---|
| pinned tree subset | 7 | `__init__`, `grasp_act_contract`, `pairact_r1`, `pairact_r1_student`, `beamact_pair_student`, `grasp_act_policy`, `robot_actions` |
| candidate files | **4** | `pair_worker_audit.py`, `pair_worker_audit_entry.py`, `pair_worker_bundle.py`, **`pair_proposal_observer.py`** |
| read-only originals | 5 | geometry worker, head worker, head policy, config, ASTRA outer loop |

**Why 16 and not 15:** the audited worker imports the observer as
`harness.pair_proposal_observer`, so it must sit in the **same** harness
package as the pinned controller.  A bundle without it would bind only 15
entries, so `create_bundle` now refuses an incomplete candidate set
(`REQUIRED_CANDIDATE_NAMES`) and pins the observer bytes independently of the
manifest (`EXPECTED_OBSERVER_SHA`).  A manifest that only agrees with itself
still cannot make a swapped observer good.

The entry requires **all 16** paths: 15 independent expected hashes plus the
entry file itself.  An empty, incomplete, forged or drifted manifest is
refused **before** the `ready` line, before the head worker and before any
audit file.

## 3. The opt-in switch

`--observe-raw-proposals` is **OFF by default**.

| Layer | Behaviour |
|---|---|
| outer runner (both copies) | the option is passed into the audited argv **only** when it was explicitly requested; `--audit-worker off` + the option is **refused at start-up** (no bundle, no worker, no file) |
| entry | the option may only be given together with the whole audited option set (`--audit-run-id`, `--audit-output-root`, `--audit-sources`); a partial set is refused with exit 2 |
| worker | the observer snapshots the controller proposal **after** `propose` and **before** `issue` clears it; it can only fail into a counted capture failure |

The observer **never** changes control: the raw input (own JPEG + own issued
history only), the four-operation protocol, the 8-stage barrier and the
READY→GO→ACK gates are unchanged.  The wiring test drives the real entry
process with the fixed synthetic predictor and asserts that the observer ON
and OFF runs produce **identical** responses and keep the origins `unknown`.

## 4. The independent status file

With the observer ON the audited worker writes the independent
`proposal-status-<runid>.json` completeness file into the audit output root:
attempted / captured / failed ticks, expected / captured robot candidates, the
controller source hash, the last capture error and the finished / complete
flags.  A best-effort summary also goes to the shared audit sink.

The summary is written **once**, at loop exit.  `run_id` is a reserved sink
field: the observer drops it from the body before the write, because the
existing sink envelope already supplies it.  The wiring test asserts both:
exactly one `proposal_capture_summary` row, and the row's `run_id` coming
from the envelope rather than from a duplicated body field.

## 5. Current pins (independent of any manifest)

| File | sha256 |
|---|---|
| `harness/pair_worker_audit.py` (core, frozen) | `8aeb8692ed0defe9e35fdd388d6009bd005ebf398e94ee2409eb4b67bccd7349` |
| `harness/pair_proposal_observer.py` (core, frozen) | `b8d5d885ce5d6a93520fd7e7e3da71ad193d5abda0a0ff5e6bc88eae321fe201` |
| `harness/pair_worker_bundle.py` | `b3497b3cefaefae1e38feaa6aaf88644194c5e7580c52bdf2237cf3240626a2e` |
| `harness/pair_worker_audit_entry.py` | `5c85b0dda46ba1da6d43f9b8029f6280ffff6753b35a8b8c78b542fde3e4d792` |
| PR642 runner | `91d527490c736206d708056eb303825db3e8ffbbed503e5272c883223bd3e404` |
| consumer runner | `61a019664123c3d6fac3da1abfe48acde16d994ac462a214967b1e67ea9cbde2` |

The current core includes atomic status publication and independent cleanup:
`b8d5d885…321fe201` for the observer and `8aeb8692…ccd7349` for the
audit module, as recorded in the table above. The earlier wiring hashes
describe superseded bytes and must not be used to validate this revision.
Pin updates follow **core → helper → entry → runner**: the helper pins the
observer, the entry pins the helper and the core, and the runners pin all
four candidates. The summary body omits the reserved `run_id`; the sink
envelope supplies it.

## 6. What was NOT done

* No GPU, no API, no network, no install, no service, no deletion.
* No model forward, no simulator import, no head worker: the real CLI was
  only exercised in `--prepare-only` mode (model/SIM/head = 0).
* No original file was modified; the pinned trees and the original runner
  stay read-only.
* No commit, no push, no delegation, no admin tool call.

The completeness writer now uses flush/fsync/close-before-atomic-replace. Read proposal_capture_summary by kind, not as the final file row. Worker cleanup preserves the original exception and attempts every owned close. These changes required refreshing independent core/entry/helper/runner pins; none was weakened.
