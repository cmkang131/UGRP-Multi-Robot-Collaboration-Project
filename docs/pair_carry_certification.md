# Opt-in recorded transport evidence precheck v1

`harness.pair_carry_certification.certify` returns a separate schema when
`opt_in=True`. Otherwise it returns an unchanged deep copy of the supplied
legacy result, without adding keys. No existing evaluator, gate, student
input or saved report is modified. The caller explicitly selects the existing
evaluator and geometry source modules; their constants are reused, not copied.

Axes A-G distinguish sampled forward aperture crossings, bilateral grip,
registered window/parent labels, distributed displacement, recomputed legacy
placement/report contradictions, ground reference, and release duration.
The saved runner window is `t > handover_t`; missing boundaries remain unknown.
Timestamps must be finite and strictly increasing. Raw rows, map and roles
are copied before evaluation. Parent ids and registrations are caller labels,
not authenticated source evidence. Input kinds remain separate (synthetic,
original mutation, real original); no student success counter is inferred.

Version 1 cannot output `certified_transport`. Ground reference, release
duration, physical continuity tolerances and wall-contact certification policy
are unregistered. Any contradicted axis yields `refused`; otherwise the verdict
is `unknown`. Supported sampled axes do not resolve these missing definitions.
No ground-height lower bound, speed bound or release time is invented.
A new reviewed contract version is required before actual certification.

The API is for recorded evaluation-only GT. It is not control input, evidence
of actuator application/acknowledgement, or a physical experiment. Teacher
records are controls, not student successes. Current tests use synthetic rows;
local pinned-source integration cases explicitly skip if those sources are
absent. Teacher-control replay remains a separate required validation.

## Reviewed boundary handling

Missing or unsupported geometry/evaluation inputs yield a refused report
instead of propagating geometry lookup errors. Known differing saved window
boundaries defer cross-report comparison to unknown; internal success/placement,
drop, collision or funnel contradictions still refuse.

V1 distance axis D describes the full post-handover evidence window, not only
the pre-lowering carry window. A and B use strictly t < lower_start_t; their
749/856-row teacher controls exclude one boundary row included by the historical
audit's 750/857-row window. Empty evidence remains unknown in this version.
These are explicit scope limits; none can yield certification. Tightening D
or empty-window semantics requires a separate reviewed contract version.
