# r4: noisy own observations, frozen parser, bounded DEV

PR #473. Offline text decisions only; no VM submission or execution. Existing
bundle registrations are unchanged; this round reserves no new execution ID.
`planner_evidence_gate=on_v1` remains opt-in (default off).

## Observation evidence and limits

The 16 r80 runs at `/Users/changmin/projects/ugrp-wt/e2e18/outputs/azure3-runs/e2e18-*-r80/raw`
contain 735 Gemma decision requests. The actual request envelope contains
`own_rgb.{frame_id,t_sim}`, `own_map_summary.pose.{mean,covariance,sources}`,
and `own_command_history` (issued commands, not realized motion). None contains
a task `observed_facts` list. A causal join with the same robot's `ownmap.jsonl`
finds the last positive `own_beam` perception; invisible does not mean absent.
109/735 have no earlier beam observation, 352/735 are at most 30 seconds old,
and 274/735 are older. Age uses the perception's RGB timestamp, not map refresh.

Offline only, the estimated beam center is transformed from the robot's start
frame using `eval_only/setup.json`, and compared with the most recent preceding
`eval_only/referee_truth.jsonl`. 450/602 scored estimates exceed 30 cm; 24 early
observations cannot be scored. The threshold is half the fixed 60 cm beam length,
not a grasp tolerance. `e2e_live_mapping._receive` explicitly computes the center
from an observed end and known length. The calibration script records source
hashes and exact request IDs. No truth position is copied into planner inputs.

**Unverified assumption:** these are geometric errors on one beam task, not
categorical error rates for eight task types. We use the measured joint
availability/age/error distribution as a *synthetic corruption stress test*.
Large geometric error becomes a randomly incorrect categorical hypothesis;
small error becomes a matching hypothesis. This transfer (especially visual
inference of a partner's intention) is not empirically validated. Unscored
observations retain only the RGB/pose envelope, with no categorical fact.
Noisy pose/observer pose, observation time, RGB reference and two issued commands
preserve the raw schema; these are synthetic contexts, not r80 image replays.
Largest-remainder allocation preserves the measured joint proportions to within
one case per stratum. Assignment is independent of peer quality and identical
across communication arms. Private generation labels stay in separate files.

## Frozen development protocol

All 54 stale + 56 wrong nonambiguous tuning cases plus 90 cases stratified across
the other domain/quality cells: 200 worlds × no_comm/peer_en = 400 decisions.
No extra solo calls in DEV. Existing full-information action labels stay fixed;
verification can be sensible under uncertainty without being the oracle's
minimum-cost action. Count offered verification separately when own facts are
absent; a question in no_comm does not count as a usable verification action.

Parser changes use only the original tuning vocabulary: contractions,
compositional phrase patterns, explicit target clauses, and negation. Both arms
get the same timestamped own evidence. A fresh own hypothesis is weighted at
0.8, not certainty; >30-second-old own evidence cannot certify a peer report.
The evidence comparison now covers all eight public task fact families. It
does not use peer quality labels. Gemma still selects the offered act/args.

Freeze code and parser before calls. Check `/api/v1/key` without exposing the
credential; reserve the batch hard cap and stop if projected balance < $1.50.
DEV estimate $0.18, cap $0.30. Only if peer_en wrong improves above r3's 0/56,
run the full tuning set and one new confirmation seed once. This comparison
changes observation inputs and is descriptive, not a causal ablation.
Seeds 2026101302 and 2026101303 are not reused. Do not retune on confirmation.
Every failure/fallback stays in N; report model-only and effective scores,
same-input rule scores, paired wins/losses, and parser failures by arm.

## 참고 자료

- [SayCan](https://say-can.github.io/): task usefulness is weighted by skill
  affordance. Our finite public-cost/evidence weighting is a heuristic adaptation,
  not its learned value function or an independently validated affordance model.
- [Age of Information survey](https://arxiv.org/abs/2007.08564): timestamp-based
  update freshness motivates age tracking. The 30 s cutoff and truth reliability
  weights here are engineering choices, not values established by that paper.
- [Inner Monologue](https://arxiv.org/abs/2207.05608): environmental feedback in
  closed-loop language planning motivates explicit perception/result records.
  Our sensor-error transfer to categorical tasks remains unverified.

## Completed results

See [RESULTS.md](RESULTS.md) and [summary_short.json](summary_short.json).
Detailed recount and call IDs are losslessly compressed with verified hashes.
All source records remain local; no physical run was submitted.
