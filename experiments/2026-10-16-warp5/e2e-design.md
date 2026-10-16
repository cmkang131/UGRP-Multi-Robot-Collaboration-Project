# E2E adapter acceptance boundary — NOT_READY

The current PR contains relocation/carry generator scheduling, a 0.05 SIM-second E2E scheduling transformation, a world/robot asynchronous decision broker and a rule client adapter. The actual LLM + map + near ACT/teacher E2E path has NOT been validated on MJWarp. The public batch CLI currently admits carry/selfmap only; E2E remains a prototype and is not a READY workflow.

## Data and source owners

- Legacy E2E source is pinned independently (candidate claude/e2e18-gemma-planner / 89d54471f; exact full SHA must be supplied and verified). Relocation source is based on reloc20 and shared warp-act. Existing policy/LLM formats must remain fixed and separate from the scheduling adapter SHA.
- One lane owns all existing three-robot private maps, command history, event/message queues, decision clients and executor/near-skill state. Module globals are isolated when a generator runs. A model response in one lane must never stall another lane's physics; reset invalidates old world/robot futures. Unit tests exercise delayed peer response and reset.
- Live requests continue through the Mac loopback SSH relay. No model key, agent account or credentials are copied to either VM. AsyncDecisions rejects live requests unless a clear endpoint receipt and the user's price decision exist. Current Gemma+50% alert keeps live requests blocked. Endpoint/provider/model changes are not part of this PR.
- The explicit rule adapter calls the existing strong task rule locally, reports provider_calls0 and zero usage, and labels the source as local_strong_rule. It is never a Gemma result. The actual rule E2E physical gate has not run.

## Physics and observation boundary

Batch physics uses the shared MJWarp command tape/graph, with three camera JPEGs at640x480 and the original optics/PIL82 path. E2E's existing0.05 SIM period is captured as an exact integer number of physics substeps. Map/carry uses0.1. Segmentation, geometry and alpha compositing remain renderer-internal; actor() returns only own JPEG and own issued PWM/wheels. TOP is review/evaluation only. GPU get_data_into is confined to the physics/evaluation owner, without CPU rollout/contact reconstruction.

Native setup remains distinct from GPU rollout, as in the shared backend. Partial-alpha/spot180/texture-modulation candidates require the separate88-pose gate, then new closed-loop gates. CPU results never carry over.

## Remaining implementation and admission work

1. Connect the pinned current E2E source factory, fixed v5 scene and common per-world model parameters/canonical groups to the public batch CLI; validate the actual rule path. The current make_e2e prototype is not sufficient evidence of this connection.
2. Connect the near ACT/visible-only teacher slot to its original skill/kind/slot contract, preserving per-robot histories and input audit. Teacher/ACT execution and success cannot be inferred from the scheduler unit tests.
3. Support/test legacy sub-tick command revocation in the command tape. Current adapter rejects unsupported sub-tick revocation rather than silently changing a command.
4. Measure terminal-world freeze and mixed-model state isolation on actual GPU steps, then N16 initial30SIM diagnostics and the run-first place/complete cohort with failure playback/ring buffers. Current unit/source checks do not establish these outcomes.

No E2E source, provider, ACT checkpoint, physical success or model accuracy is admitted by this design/prototype. New physical submissions are currently blocked by the observed Mac16GiB being below the project20GiB submission floor. Existing other tasks/VMs remain untouched.
