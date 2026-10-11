# S4 Gemma standard DEV preparation
Single model `study_gemma4_31b_v1`: `gemma-4-31b-it`, models.list version `001`; mutable service revision is recorded, not claimed immutable.
New adapter v184/7.77.0 defaults to English; event_driven_llm and compact_prompt_v1 default off; ko is reproduction-only.
Actual countTokens on peer_ko s601 call-0261-r1: 8203 → compact ko 2367 / en 2257; original own RGB retained, static map removed.
Seed601 snapshot eligibility: no_comm 306→82; peer 265→118; leader 313→126; structured 317→121. Targets unmet; counterfactual execution is not measured.
Global shared budget: 14400 TPM / 27 RPM / 12960 RPD; synchronous quota waits preserve SIM and request identity.
plan.json: 16 paired DEV stage runs, seed603, Gemma/Gemini × event on/off × 4 conditions; Azure notification + own-map + moving-camera qualification pending.
Evidence and limits: summary.json; raw /Users/changmin/projects/ugrp/outputs/s4-gemma-standard; prior full raw oracle:/home/ubuntu/ugrp-archive/runs/s4live11-*.
References: [Gemma API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api), [countTokens](https://ai.google.dev/gemini-api/docs/tokens), [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [CoMuRoS event replanning](https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2026.1843313/full).
