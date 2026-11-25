# TASK-HANDOVER-CLOUD-FIX1: deploy the job without `run jobs replace` (2026-11-25)

Context: `TASK-HANDOVER-CLOUD.md` is done. The main session ran `ops.py build` (SUCCESS, image digest in
`cloudrun/runs/handover-20261125a/build/image.txt`) and then `ops.py deploy`, which failed:
`gcloud run jobs replace <job.yaml>` needs the Cloud Resource Manager API, which is disabled in project
`<project-id>` (full error at the end of `cloudrun/runs/handover-20261125a/chain.log`). The main session will
NOT enable an API. The existing scripts never needed it because they use
`gcloud run jobs deploy JOB --region R --image ... --cpu ... --memory ... --task-timeout ...s --max-retries 0 --tasks N --parallelism 1`
(`../20261118-cloudrun-p2/scripts/create_jobs_p2.sh`, read-only).

Do, with the same hard limits as the original task (no network, no cloud command, phase-2 folders read-only, nothing
outside `20261123-phase3/`):
1. Change `cloudrun/handover/ops.py` so that `deploy` creates or updates `ugrp-handover-gate` with
   `run jobs deploy` and flags that reproduce `job.yaml.in` exactly: image by digest, 2 vCPU, 6 GiB, 12 tasks,
   parallelism 1, max retries 0, task timeout 1,800 s, gen2 execution environment, the same service account, and the
   env vars HANDOVER_IMAGE, HANDOVER_FIRST_TRIAL, RESULT_BUCKET. Keep everything else (receipts, the read-back check
   of the deployed image before every launch, resume behaviour). If the read-back or any later step also depends on
   something only `replace` provided, fix that too and say so. Keep `job.yaml.in` as the written specification and
   add a test that the flags and the YAML agree.
2. The existing cohort `cloudrun/runs/handover-20261125a` must be usable as is: `ops.py deploy <that dir>` must work
   after the successful build without rebuilding. Do not modify files in that directory.
3. Update the tests and the offline command transcript, rerun `test_handover_cloud.py`, the dispatcher tests and
   `handover/tests`, and append a short section "FIX1" to `REPORT-HANDOVER-CLOUD.md` (what changed, the exact deploy
   command now issued, anything else in the flow that could hit the disabled API, "확인 안 됨").
Last step: create `review/ASTRA-HANDOVER-CLOUD-FIX1.done`.
