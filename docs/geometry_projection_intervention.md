# Controlled geometry projection intervention (CPU-only candidate seam)

Branch: `ugrp/geometry-projection-intervention-20261106T0228Z`
Base: `74a546b5263aaa95834899e8dc8872a26e4db692` · Date: 2026-11-06
Owner: UGRP-Pair · Scope: **the seam only** — no runner, no bundle, no
observer, no learned execution.

## 1. What this is

The pinned geometry head injects the predicted geometry into the ACT encoder
through exactly one linear projection:

```python
# implementation/geometry_policy.py, install_geometry_head
conditioned[1] = conditioned[1] + model.geometry_to_state(geometry)
```

`geometry_to_state` is a plain `nn.Linear(3, dim)`.  The geometry
**prediction** (the visual head output, kept in `model._geometry_prediction`)
is computed and retained separately, so the geometry **contribution** to the
encoder state token can be toggled without touching the actor weights, the
inputs, the seed, the protocol or the gates.

`harness/geometry_projection_intervention.py` is that toggle: one context
manager, one hook, two arms.

| arm | what happens to the projection output |
|---|---|
| `on` | passed through unchanged — the returned object/value is preserved. **Control arm.** |
| `off` | replaced by a **fresh** zero-like output with the same shape, dtype and device |

The default path is unchanged: importing the module does nothing, and only
entering the context manager installs the hook.

### The zero-ness of the replacement is checked, not assumed

The `off` arm's contract is a **zero** contribution, so the replacement is
verified rather than presumed:

| situation | what the seam does | recorded as |
|---|---|---|
| the replacement was observed to be all zeros | it is returned | `verified_zero` |
| the zero-ness could **not** be checked at all (no zero counter) | it is returned, but the result is **not** claimed as verified | `unverified_zero` |
| the replacement was observed to carry **non-zero** values | **refused** with `InterventionError`; counted as a hook failure; **never** counted as a successful zero replacement | `failed` |

"Verification unavailable" and "verified contradiction" are different
statements and are never conflated.  A non-zero contribution is never passed
on as if it were a zeroed one: the coordinator's counterexample (a
`new_zeros` that returns `[9, 9, 9]` while preserving shape, dtype and
device) is refused instead of being applied.

## 2. Why this is the next useful intervention

The historical full SIM issued 14,400 zero-wheel rows but never logged the
raw candidate commands, so they cannot be reconstructed.  The known
candidate-vs-protocol confound is recorded in
`context/20261106-initial-control-trace/VERIFY-INITIAL-CONTROL.md`:

* **zero-init action equality is not final-20k vs frozen equality.**
  `geometry_to_state` is zero-initialised, so "the first output exactly
  equals the loaded baseline output" is a **structural** property of the
  zero-init layer, not evidence that the trained model matches the frozen
  one;
* **switching actors changes more than geometry**: a frozen actor has no
  geometry head at all, so an actor comparison mixes the weights AND the
  presence of the geometry conditioning path;
* the barrier rule is "pwm1 decreased relative to the previously **issued**
  command", so the first rejection tick depends on the initial PWM state —
  the measured first rejection ticks differ (2.300–3.000 s) between arms.

Toggling **only** the projected contribution on the **same** actor removes
the actor/conditioning confound and keeps the barrier comparison basis
identical.  It is cheaper than a new SIM and it is the cheapest measurement
that actually separates the two variables.

## 3. The contract of the seam

* **stdlib only.**  The module imports no framework and never loads or runs
  a model.  It reaches the target through the module's **own hook API**
  (`register_forward_hook`); it does not monkeypatch global classes and does
  not install a second geometry pipeline.
* **One hook, owned.**  The context manager removes **only its own** hook,
  on normal exit **and** on exception.  A foreign hook on the same module is
  left untouched.
* **No stale mode.**  After the exit the model behaves exactly as before;
  the next arm starts clean.
* **No mutation.**  The weights, the bias, the inputs and the retained
  geometry prediction are never written.  The projection **object** is never
  replaced, and the projection is still **evaluated** in the `off` arm — only
  its contribution is replaced.
* **Refusals.**  An invalid mode, a target without `geometry_to_state`, a
  target without the normal hook API, a handle that cannot be removed, a
  reused context and a **nested activation on the same model** are all
  refused.  A missing or drifted targeted source file is refused.  A
  zero-like replacement that is **observed to be non-zero** is refused as
  well: it is a failed replacement, not a zeroed one.
* **Original errors survive.**  If the caller's block raises, that exact
  exception propagates; a cleanup problem is recorded in the evidence and is
  never raised over the user's error.
* **No concurrency claim.**  The caller must own the actor's inference
  exclusively while the intervention is active.  Process/thread concurrency
  is **not** supported and is **not** claimed.

### The shared-projection assumption (R4)
The hook is installed on **one projection object**, and a hook on that object
affects **every caller of it** — including another model that happens to hold
the *same* projection object.  The `off` arm of model A would then also zero
model B's contribution.

The active-intervention registry is keyed by `id(model)`, so it detects a
nested activation on the **same** model, but it does **not** detect
cross-model sharing of one projection object.  This module does not claim
otherwise.

The caller must therefore:

* own the projection inference exclusively **across all aliases** of that
  projection object, and
* use an **unshared projection** in the production arms, or isolate every
  alias of the shared object.

No lifecycle redesign was made in this round: the registry and the hook
mechanism are unchanged, and the requirement above is a **caller**
obligation.

## 4. The two arms and what they mean

### `on` (control)

The hook is installed and counted, but the output passes through unchanged.
Its purpose is to show that **installing the hook changes nothing**.  If the
control arm and the untouched baseline ever differ, the difference is caused
by the seam and not by the geometry contribution.

### `off` (intervention)

The projected contribution becomes zero.  The geometry prediction is still
computed and retained; the actor, the inputs and the protocol are unchanged.

**Necessity, not sufficiency.**  If the `off` arm still produces the same
first rejection and the same zero-wheel issue, the geometry projection is
**not necessary** for that outcome.  If the `off` arm changes it, the
geometry projection **is a candidate contributor**.  Neither outcome is a
causal claim: the intervention changes one internal input of the encoder, and
the barrier sits downstream of a chain that also contains the protocol.

**Keep unknown.**  Whether the command was applied to the environment, whether
it was acknowledged, and whether any physical effect occurred remain
**unknown** — the same boundary the proposal observer keeps.  This module
adds **no new transport threshold** and proposes none.

## 5. Evidence: what is recorded and what is not

The seam records, per arm:

* the arm and the mode;
* the **targeted source SHA** (read-only hash of
  `implementation/geometry_policy.py`) and whether it matched the expected
  pin;
* the **module identity label** (`geometry_to_state:<module>.<qualname>`) —
  a **label**, not an authentication;
* the number of **active hook calls**, the number of failures, the number of
  zero replacements and **how the zero-ness was verified**
  (`verified_zero` / `unverified_zero` / `failed`);
* whether the hook was installed and removed, and any cleanup error.

When the hook handle exposes **no** `remove()` API, the intervention refuses
and the residual hook stays registered but **inert** (it can never change an
output).  The evidence keeps the **true** install fact
(`hook_installed=True`), reports `hook_removed=False` and records the
`cleanup_error`, so a residual registered hook is visible instead of being
reported as "never installed".

The `unverified_zero` state is a replacement whose zero-ness could **not** be
checked.  It is used, and it is explicitly **not** an accepted *verified*
control: a future runner must treat it as unverified and must not read it as
a verified zero contribution.

It explicitly does **not** establish:

* model success;
* independent source authentication (the identity is a label);
* proof of a model forward;
* transport or physical causation;
* process or thread concurrency safety.

### How a future runner records both arms

`build_arm_document()` defines the shape of the record a future runner
should write, so that the arms are comparable without guessing what else
differed.  For **both** arms it records:

| field | meaning |
|---|---|
| `checkpoint_sha256` | the actor identity (must be identical in both arms) |
| `input_sha256` | the input identity (must be identical in both arms) |
| `seed` | the seed (must be identical in both arms) |
| `proposal_status_path` | the independent `proposal-status-<runid>.json` of the raw ProposalObserver for that arm |
| `raw_proposal_log_path` | the raw proposal log of that arm |
| `intervention` | the arm evidence above |

**No runner or bundle file is edited here.**  The future runner is
responsible for: loading the same checkpoint in both arms, feeding the same
inputs with the same seed, running the raw ProposalObserver **on** in both
arms, and writing the arm document.  The observer's own completeness file
(`proposal-status-<runid>.json`) is the per-arm completeness authority.

### Conditions a future runner must satisfy before its arms are accepted

These are **acceptance conditions for a future run**, not results of this
task.  Nothing here has been executed.

| condition | requirement |
|---|---|
| same checkpoint / input / seed | the checkpoint, the input and the seed must be **identical** across the two arms; the arm document records all three per arm so a mismatch is visible |
| `on` reproduces the unhooked baseline | on the raw proposals, the `on` arm must **exactly match** the unhooked baseline — otherwise the seam itself is the difference, not the geometry contribution |
| retained geometry predictions agree | the retained geometry predictions must be **equal** on both arms (the prediction is computed and retained in both); a difference means the arms did not observe the same geometry |
| reset and remove per arm | the model must be **reset** and the owned hook **removed** between the arms; a stale mode across arms invalidates the comparison |
| replay, or compare only up to the first divergence | either replay **identical preserved observations**, or compare only **until the first divergent issued command / history**; comparing past a divergence mixes the arms |
| both orders are a proposed control | run both `on → off` and `off → on` orders and record both: a single order cannot separate an order effect from the geometry effect.  This is **proposed**, not yet run |
| `blocked=false` is not a motion claim | a robot can still hold through READY / permit while `blocked=false`; compare the **raw** proposals and the **issued** commands, not `blocked` alone |
| completeness is cross-read | the independent status file must be **cross-read with the sink summary** and a **matching run id** (per the observer docs); neither is a sole authority |
| interpretation is bounded | the `off` arm may be **out of distribution** for the actor, so the interpretation is limited to **this actor and the tested inputs** |

The Podium review is **design opinion, not experiment evidence**: none of the
conditions above is a measured result.

## 6. Test boundary

The tests use **explicit fake hook modules and fake tensors**
(`FakeTensor`, `FakeProjection`, `FakeModel`).  They validate the **seam's
own contract** — the arm behaviour, the cleanup, the refusals, the evidence
shape, the source drift detection.

They do **not** validate:

* real PyTorch behaviour (no torch is imported, not even as a fake);
* real tensor dtypes/devices/shape semantics;
* any learned output, model forward, physics or simulator behaviour.

The upstream file is **read** (hashed) only; it is never imported, edited or
executed.  A test asserts that its pinned bytes are unchanged.

### 6.1 Portability of the test suite (R1)

The suite must run on a machine **without** the host's archived research
source.  The rules it follows:

* the **fake-only** tests pass `source_path=None` explicitly, because the
  source bytes are irrelevant to what they check.  `None` means *the source
  byte check is skipped* — it is **not** authenticated evidence, and the
  evidence says so (`target_source_path is None`,
  `source_sha256_matches is None`);
* the **hash / evidence** tests use a **temp file with known bytes** and its
  **own known digest**, so they never touch the host archive;
* the **drift** and **missing-file** refusals are still covered, with an
  explicit expected digest that the temp file really does not match;
* **exactly one** test is a genuine archive integration check (the upstream
  pin).  It is **skipped** when the archive is absent, so it never turns a
  clean machine into a red suite.

The module's own default source check is **not** disabled: a missing source
file is still refused, and the default constant is still an **absolute
host path** (see §6.2).

### 6.2 The default source path is a host absolute path (R3)

`DEFAULT_TARGET_SOURCE` is the **host's** archived research source:

```
/home/ubuntu/ugrp-retrain-geom-20261029/implementation/geometry_policy.py
```

It is **not portable by itself**.  The behaviour is deliberate:

| input | behaviour |
|---|---|
| the default (no explicit path) | the source bytes are hashed and checked against `DEFAULT_TARGET_SOURCE_SHA256`; if the file is **absent** the intervention **refuses** — the default check is not weakened |
| an explicit `source_path` + `source_sha256` | the same check against the given path and digest |
| `source_path=None` | the source byte check is **skipped**; the evidence then carries no source path, no source digest and no match result.  This is **not** source authentication |

**A future deployment must pass the source path and the expected digest
explicitly** (or place the archive at the default path).  No runner wiring
exists yet: this module does not claim that any runner does this today.

### 6.3 Test count

The file contains **44 tests** (verified by counting the `def test_`
definitions and by the pytest run).  Earlier revisions of this document
stated 31 and then 38; both were stale.

## 7. Files

| file | role |
|---|---|
| `harness/geometry_projection_intervention.py` | the seam: the context manager, the evidence and the arm document |
| `tests/test_geometry_projection_intervention.py` | 44 fake-hook / fake-tensor unit tests (one optional archive integration check) |
| `docs/geometry_projection_intervention.md` | this document |

### CI note

The dedicated `geometry-projection-intervention.yml` workflow runs this
test file with pytest only. Its clean GitHub runner may skip the one real
archive integration check; fake-only and temporary-source tests must pass.
Prior PR645 CI runs do not cover this candidate. A workflow definition alone
is not a passing CI result; inspect the run for the published commit.

## 8. Scope compliance

No GPU/VM, no API, no network, no install, no service or account change, no
simulator, no MuJoCo, no model load or forward, no learned execution, no real
robot, no deletion, no extra delegation, no commit/push/PR/Linear, no
management tool call.  Only this worktree was modified; the pinned trees, the
Solo worktree, PR645 and the coordinator's evidence were read only.
