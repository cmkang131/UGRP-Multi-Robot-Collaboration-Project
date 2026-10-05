# B″ v-next (DRAFT, NOT FROZEN) — a zero deadband is a valid solution

Status: **draft for coordinator review**. This document freezes nothing and changes nothing in `criterion_B_double_prime.json` (`5f7d8905…`). No collection has been started.

## Why

The frozen v92 assembly (#367) rejected the loaded shared fit. The optimizer converged at full rank 13/13, but every deadband start c0 sat on its lower search bound: forward 0, left 0 and turn 0.006. Frozen B″ treats any active bound as a failure. For forward and left, however, c0 = 0 is not an arbitrary search-window edge. It is the physical lower limit of a deadband (`v88_c0_basis.json`: "비음수 deadband의 물리적 정의 c0>=0"). A constrained least-squares solution that rests on a physical constraint is a legitimate solution (no deadband), not an identification failure (Lawson & Hanson 1974, ch. 23; NNLS solutions with zero components). The turn axis is different: its floor of 0.006 was a search-window choice, made because the v92 design has no turn command below 0.006. A turn c0 inside (0, 0.006) therefore cannot be identified from v92 data.

## Proposed exact changes (relative to frozen B″)

1. `loaded_motion_bounds.c0_lower`: `[0.0, 0.0, 0.006]` → **`[0.0, 0.0, 0.0]`**. `c0_upper` `[0.015, 0.015, 0.015]`, `u1_lower` `[0.025]*3`, `u1_upper` `[0.04]*3`, initial values and `interior_distance_min = 1e-6` stay the same.
2. New text for `loaded_motion_bounds.interpretation`:
   > c0 ≥ 0 is the physical definition of a deadband. If the free shared fit returns c0_j at exactly the lower bound 0 (`active_mask = -1` for that parameter only), axis j is declared **no deadband (c0_j = 0)**. The fit is repeated with c0_j fixed at 0 and all other parameters free, using the same optimizer settings. The refit is accepted only if it converges, has full rank on its free parameters, has no active bound and is at least `interior_distance_min` from every remaining bound. Any other active bound (gain, tau, u1, or c0 at its upper bound) is still a failure (PARTIAL). A c0_j strictly between 0 and `c0_upper` must still be interior.
3. New text for `loaded_spread.deadband`:
   > steps-only position residual least squares. If c0_j > 0: c0 below the first moving command and above an observed near-zero level, as before. If c0_j = 0 (rule 2): no stop level is required. Both cases require two signed ramp magnitudes (0 < |u| < u1) and one signed saturated magnitude (|u| ≥ u1) at every horizon, plus rank and interior bounds on the free parameters.
4. Acquisition (for the re-collection, not a scoring rule): add turn step magnitudes **0.001, 0.002, 0.004** (mirroring the existing `additional_translation_magnitudes`), so that a positive turn c0 below 0.006 can be observed, or c0 = 0 can be confirmed with support on both sides.
5. Unchanged: horizons, components, Euler mean law, noise floors and selection, 95% training coverage, the PRBS gates of 90% two-sigma coverage and p95 ≤ 2, the pair model, camera, loaded selection, and `promotion`. "Frozen unloaded B still runs unchanged and can veto" also still applies.

## Consequences

- The v92 loaded collection (`257953ec`, already inspected, and already fit under exactly these rules as the DEV_PILOT run) becomes **exploratory** under v-next. It cannot confirm v-next. Promotion to `MEASURED_SIM` needs (a) v-next frozen and published with hashes before any new data, (b) a **new loaded re-collection** under that freeze (with the added turn magnitudes), and (c) one assembly under the frozen v-next.
- v-next does **not** remove the second blocker. The unloaded combined profile (`params.motion.*`) still has no accepted candidate.
- Dev evidence, which does not confirm anything: under exactly rule 2 with all three c0 = 0, the v92 refit converged at rank 10/10 with all parameters interior, and passed B″ training 36/36 and PRBS validation 36/36, spread and the pair model (`fit_dev_pilot.py`, output `outputs/v92-dev-pilot-c0zero-20261003T104043Z`).

## References

- C. L. Lawson, R. J. Hanson, *Solving Least Squares Problems* (1974), ch. 23 (NNLS, active constraints).
- SciPy `least_squares` documentation (`active_mask`, `status`): https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html
- Frozen B″ `experiments/2026-10-03-v92-loaded-schedule/criterion_B_double_prime.json`, basis `revision_d1_d4/v88_c0_basis.json`, #219 freeze comment 5967154276, v92 PARTIAL record #367.
