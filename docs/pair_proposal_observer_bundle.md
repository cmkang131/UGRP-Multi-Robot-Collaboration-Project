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

## 5. Current pins (independent of any manifest)

| File | sha256 |
|---|---|
| `harness/pair_worker_audit.py` (core, frozen) | `cfe4cbfa2565003063aa69980abd759b5364877e0aa45cc709ebb6a32bef099d` |
| `harness/pair_proposal_observer.py` (core, frozen) | `19d2af7f1d972b25b0e3069424046539d995ade4eef0e62fd2b66013a39ea35d` |
| `harness/pair_worker_bundle.py` | `a7828ba1bcc95082feeb3076a88488dcfb6f2de0f84b43db0293c5daf9b8459b` |
| `harness/pair_worker_audit_entry.py` | `a902afa0a8a50494507998b19e500af736f5a241439f7f2bbf9a0ec283c48ba9` |
| PR642 runner | `60179d3eca706c6071f0b790940543d66d8cf9d4cec27186ab9c9df070e1ea40` |
| consumer runner | `108efd11960bac295b2df2676400e239bdd567b926e7030e8c95c3d15b804c78` |

The core hashes are the coordinator's `core-wired-manifest.json` /
`wiring-manifest.json` values.  The order was **helper → entry → runner**:
the helper pins the observer, the entry pins the helper and the core, and
the runners pin all four candidates.

## 6. What was NOT done

* No GPU, no API, no network, no install, no service, no deletion.
* No model forward, no simulator import, no head worker: the real CLI was
  only exercised in `--prepare-only` mode (model/SIM/head = 0).
* No original file was modified; the pinned trees and the original runner
  stay read-only.
* No commit, no push, no delegation, no admin tool call.
