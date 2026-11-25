# Two-robot hand-over on Cloud Run

**Ready for the main session to build one image and run trial 1.** If the smoke produces usable evidence, the same image and job can run trials 2–12. The smoke then counts toward the twelve authorized trials. Preparation and verification were offline. The hand-over image build, native trials and gate verdict are pending.

## Image and executor

I chose path (a). The last verified image already carried the simulator, scene assets, CPU runtime, ACT checkpoint and GCS uploader. The hand-over needs three additional executor modules, the fixed driver and its table. A dedicated image entry point and job let the driver use those dependencies directly. The existing dispatcher and planner are outside its execution path. [Layer Dockerfile](cloudrun/handover/Dockerfile) · [Build context generator](cloudrun/handover/stage.py) · [Worker](cloudrun/handover/worker.py)

| Item | Verified from local records |
|---|---|
| Parent image | `us-docker.pkg.dev/<project-id>/ugrp/ugrp-run:p3v8-d369231-2`. Cloud Build `<record-id>` recorded `SUCCESS` and digest `sha256:6599cdc46e1dc6b89881466279b9360ba4b2baf8853b2f2f89cce0256ee5ad26`. The layer uses that digest in `FROM`. [Build log](cloudrun/logs/build-p3v8-d369231-2.log) · [Phase-2 build receipt](../20261118-cloudrun-p2/builds/p3v8-d369231-2.json) |
| Parent executor | `d369231d5e0198c67e63b0bb557e7ed328ee603a`, tree `921852d04aa30370532f85c7045be2789ef3449b`. Both build records identify this revision. All 12 v8 check rows and 88 v8 main rows use it. The archived job names the same image tag, and the corresponding rerun log records four successful earlier executions. [Check manifest](manifests/phase3v8-check.csv) · [Main manifest](manifests/phase3v8-main.csv) · [Job export](cloudrun/jobs/ugrp-run3.us-central1.yaml) · [Rerun log](cloudrun/runs/p3v8-rerun.log) |
| New executor | Local branch `phase3/handover-cloud`, commit `b04f88c6110b6301d78a8ed4dd76c9e0f06f3eb2`, with the verified parent as its sole parent. Staging reads its three added blobs and checks both working copies byte for byte. Four pre-existing tracked bytecode deletions in the checkout are outside this commit. [Commit, tree and three file hashes](cloudrun/handover/verification/provenance.txt) |

The driver lives at `/opt/ugrp/handover/run_trial.py`. Its sibling `/opt/ugrp/exec` links to the full baked executor at `<home>/hybrid/student-p2`, with the three new modules added there. `HANDOVER_ACT_MODEL` and the driver's default `/opt/ugrp/handover/runtime/act` both resolve to `<home>/hybrid/gseg-actor`. `HANDOVER_SCENE_ROOT=<home>/hybrid/graw/scene/frozen_slim` supplies the driver's `sim/` directory. The process uses `<home>/ugrp-cpu/bin/python`, the parent's `graw/pyvendor` and OSMesa. These paths come from the existing image definition, worker launch and build check. [Parent Dockerfile](../20261118-cloudrun-p2/image/Dockerfile.p2) · [Parent worker](../20261118-cloudrun-p2/image/cr/cr_task_p2.py) · [Parent image verification](../20261118-cloudrun-p2/image/p2/verify_build.sh)

## Main-session commands

Run these blocks in one Bash shell. The printed cohort directory holds the build ID, resolved image digest, execution IDs and fetched trials. Keep that path when resuming. The main-session host needs its existing `gcloud-p` setup, Python 3, Pillow for scoring, Git and `zstd`.

### 1. Build once and create or update the job

```bash
cd <work>/20261123-phase3
export PATH="$HOME/bin:$PATH"
kit="$PWD/cloudrun/handover"
work=$(mktemp -d "$PWD/cloudrun/runs/handover-XXXXXXXXXXXX")
printf 'Cohort directory %s\n' "$work"
hg() {
  local operation="$1"
  shift
  python3 -B "$kit/ops.py" "$operation" "$work" "$@"
}
hg build && hg deploy
```

`build` stages the 15 allowlisted files, checks the proposed tag, submits one Cloud Build and records its returned image digest in `$work/build/image.txt`. Build time, source staging, logs and registry storage can incur charges. Success requires a `SUCCESS` build receipt for the exact tag. During that build the image check verifies payload hashes, loads the checkpoint on CPU, checks ArUco and compiles the two-robot XML under the driver’s import paths. Its success line is `hand-over image check OK`. [Cloud Build definition](cloudrun/handover/cloudbuild.yaml) · [In-image check](cloudrun/handover/check_image.py)

`deploy` renders `$work/job.yaml` with the returned digest and creates or replaces only `ugrp-handover-gate` in `us-central1`. Deployment starts zero tasks. The definition sets 2 vCPU, 6 GiB, one parallel task, zero retries and 1,800 seconds per task. The default count is twelve. Six GiB matches the recorded three-robot job allocation and gives the two cameras, ACT and the in-memory output filesystem room to share. Actual peak use needs the smoke. Every launch reads the deployed image back and checks it against the build receipt. [Job definition](cloudrun/handover/job.yaml.in) · [Operator commands](cloudrun/handover/ops.py)

### 2. Run only trial 1, fetch it and score it

```bash
hg run smoke && hg watch smoke
hg fetch smoke && python3 -B handover/score.py "$work/trials/trial-01"
```

`run smoke` submits one task and saves its execution name in `$work/smoke/execution.txt`. `watch` polls that exact execution and reports succeeded and failed task counts. Polls are read-only. Even if the watch ends with a task error, run the fetch line to collect diagnostics. Fetch reads GCS objects and writes the local trial folder. Storage operations and applicable egress can incur charges. Scoring is local.

Inspect the trial line, `run.json` and `cloud-meta.json`. A usable smoke reports **one evaluated trial** and cohort gate `PENDING`. An evaluated grasp miss is a trial result. A setup error, zero evaluated trials or an incomplete fetch calls for inspecting `driver.log`, the recorded stage and available evidence before spending on the continuation. [Driver](handover/run_trial.py) · [Scorer](handover/score.py)

### 3. Complete the cohort with trials 2–12

```bash
hg run remaining && hg watch remaining
hg fetch remaining && python3 -B handover/score.py "$work"/trials/trial-{01..12}
```

This submission starts eleven tasks. Indices 0–10 map to trials 2–12. The driver's 1,080-second budget has a 1,140-second outer watchdog, leaving time inside the 1,800-second task limit for startup, packaging and upload. Successful collection yields `trial-01` through `trial-12` under the same directory. Look for **12 evaluated** and the scorer's `PASS` or `FAIL`. The gate requires at least ten successes. A nonzero scorer exit can be a measured gate failure. [Fetch helper](cloudrun/handover/fetch.py) · [Scoring criteria](handover/score.py)

**Single-execution alternative.** After step 1, a cohort with zero submissions can use this block in place of steps 2 and 3. It starts twelve tasks with indices 0–11 mapped to trials 1–12. The helper rejects overlap between `all` and the split path in the same cohort.

```bash
hg run all && hg watch all
hg fetch all && python3 -B handover/score.py "$work"/trials/trial-{01..12}
```

## Result and recovery contract

Each task creates an exclusive output directory. The driver runs in a separate process with its existing socket restriction. After it exits, the parent worker's `make_tar` and `gcs_upload` helpers publish the complete trial directory and driver log using the job's runtime identity. The worker sends `full.tar.zst` first and `meta.json` last under `gs://<bucket>/handover/<execution>/trial-NN/`. The marker contains the raw driver exit, task outcome, build provenance, table hash, archive length and SHA-256. A valid recorded trial failure (driver 1) and a finished trial (driver 0) both complete the task after publication. Driver 2, a crash, a watchdog timeout or an inconsistent summary produces a diagnostic task failure. Upload failure has task exit 98. [Worker](cloudrun/handover/worker.py)

Fetch checks execution ID, image digest, layer hash, trial index and the archive's length and SHA-256 before publishing a local folder. Missing or damaged rows produce a nonzero fetch status and the helper still collects the other available rows. Repeat the same `hg fetch` command to fill gaps. Repeat `hg watch` to resume monitoring. Repeating `hg build` or `hg run` in the same cohort uses the recorded ID, or looks up a uniquely matching interrupted submission. All control-plane commands go through `gcloud-p <project-id>`. [Fetch implementation](cloudrun/handover/fetch.py) · [Submission receipts and recovery](cloudrun/handover/ops.py)

### Cancellation and cleanup

For an active build, the first command below requests cancellation. The second is the equivalent for an active eleven-task continuation. The one-task and twelve-task execution IDs live in `$work/smoke/execution.txt` and `$work/all/execution.txt`. Cancellation can interrupt an upload. Compute already consumed and objects already written are billable under the project's terms.

```bash
# Use the applicable command only while that operation is active.
gcloud-p <project-id> builds cancel "$(cat "$work/build/id.txt")" --quiet
gcloud-p <project-id> run jobs executions cancel "$(cat "$work/remaining/execution.txt")" --region us-central1 --quiet
```

After fetching and scoring, these commands delete the dedicated job and remove the one image tag recorded for this build. A successful delete exits zero. The image digest can continue to occupy registry storage until a retention policy removes it. The archived GCS evidence and Cloud Build logs have their own retention. Watch and score require no cloud cleanup. The fresh cohort directory contains the local footprint of staging and fetching.

```bash
gcloud-p <project-id> run jobs delete ugrp-handover-gate --region us-central1 --quiet
gcloud-p <project-id> artifacts docker tags delete "$(cat "$work/build/tag.txt")" --quiet
```

## Cost and access

At the project's archived **2026-11-18** Jobs rates, the task costs `2 × $0.000018 + 6 × $0.000002 = $0.000048` per active second. Twelve full driver budgets use 25,920 vCPU-seconds and 77,760 GiB-seconds. **Estimated task compute is $0.62208 for all twelve**, including the smoke. With one slot, the twelve driver budgets total 3 h 36 min before startup and transfer. [Archived pricing inputs](../20261118-cloudrun-p2/scripts/estimate_p2.py)

| Billed time scenario | Smoke | Remaining 11 | All 12 |
|---|---:|---:|---:|
| 1,080 s per task | $0.05184 | $0.57024 | $0.62208 |
| 1,800 s per task | $0.08640 | $0.95040 | $1.03680 |

One extra billed minute per task adds about $0.03456 across the cohort. The estimates exclude the E2_HIGHCPU_8 build (2,400-second configured timeout), registry and bucket storage, logs, operations, egress, discounts and free-tier credits.

| Operation | What could stop it |
|---|---|
| Build | Cloud Build and Artifact Registry APIs, build submission and status access, regional build capacity for E2_HIGHCPU_8, read/write access to the source-staging bucket, read access to the parent digest and registry tag list, write access to the image package and logs. |
| Deploy and run | Cloud Run API, permission to create/update/read the job, act as its configured runtime service account, pull the image, and execute with task-count/environment overrides (`run.jobs.runWithOverrides`). Status and submission recovery need execution get/list access. Shared regional headroom must fit at least 2 vCPU and 6 GiB for one running task. The historical log lists 20 vCPU and 40 GiB in the region. [Historical quota check](cloudrun/runs/p3v8-rerun.log) |
| Upload, fetch, cleanup | The runtime identity needs object creation on the result bucket and access to the metadata and storage endpoints. The operator needs object reads for fetch, cancellation rights for active work, and job/tag delete rights for cleanup. Bucket policies, retention rules and organization restrictions can affect these operations. |

## Offline verification

| Check | Observed result |
|---|---|
| Existing suites | 17 dispatcher tests and 24 hand-over tests passed. The dispatcher suite includes its historical phase-2 file checksum checks. [Dispatcher log](cloudrun/handover/verification/dispatcher.log) · [Gate log](cloudrun/handover/verification/gate.log) |
| Dedicated Cloud Run path | 11 tests passed. A synthetic smoke and eleven continuation rows went through the parent's real tar helper, an in-memory object store, byte-checked extraction and the existing scorer. Tests also cover driver failure/error/timeout, upload rejection, damaged or mixed artifacts, resume and duplicate-submission prevention. [Test log](cloudrun/handover/verification/cloud-tests.log) · [Tests](cloudrun/handover/test_handover_cloud.py) |
| Staging | An actual fresh context contained **15 files, 70,566 bytes**. An independent file walk and `sha256sum -c` matched every entry. Inventory SHA-256 is `ebf1e1fdafde4ca2b72c98a33a4aebb0ff20479cbbc2e839d8d0672dd932450b`. [Staged SHA-256 list](cloudrun/handover/verification/staged.sha256) · [Verification output](cloudrun/handover/verification/context-check.txt) |
| Commands and mapping | Saved expanded build, replace, execute, status, per-index driver and per-object fetch commands for all three selections. The preview labels its example output digest and execution IDs. [Command transcript](cloudrun/handover/verification/commands.txt) · [Commit comparison](cloudrun/handover/verification/provenance.txt) |

Reproduce these checks from the phase-3 root. The verification shell uses the workspace's offline Python hook and local scratch directory.

```bash
(
  export TMPDIR="$PWD/.tmp" PYTHONPATH="$PWD/.tmp/v10-offline" PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1
  (cd cloudrun && python3 -B -m unittest test_cr_dispatch_p3) &&
  python3 -B -m unittest discover -s handover/tests -v &&
  python3 -B -m unittest discover -s cloudrun/handover -p 'test_handover_cloud.py' -v &&
  python3 -B cloudrun/handover/stage.py | diff - cloudrun/handover/verification/staged.sha256
)
python3 -B cloudrun/handover/ops.py plan "$PWD/cloudrun/runs/handover-offline-preview"
```

## 확인 안 됨

- Current registry availability, cloud APIs, IAM, quotas, live rates and billing.
- A successful build of this overlay and its in-image checkpoint, ArUco and native XML checks.
- Job creation, real task-index overrides, camera memory peaks, shutdown behavior, upload latency and retrieval from the live bucket. A platform kill before publication can leave a missing marker.
- Any measured grasp, transfer, physical simulation outcome, wall time or twelve-trial gate verdict. The round-trip test used constructed observations.

## FIX1

Build `<record-id>` succeeded for `handover-20261125a`. The subsequent `jobs replace` failed when it looked up the YAML’s numeric namespace through Cloud Resource Manager. From the phase-3 root, resume this build with `python3 -B cloudrun/handover/ops.py deploy cloudrun/runs/handover-20261125a`. The helper checks the saved `job.yaml` and generates this create-or-update command from the image receipt. [Cohort log](cloudrun/runs/handover-20261125a/chain.log) · [Image receipt](cloudrun/runs/handover-20261125a/build/image.txt)

```bash
gcloud-p <project-id> run jobs deploy ugrp-handover-gate \
  --region us-central1 \
  --image us-docker.pkg.dev/<project-id>/ugrp/ugrp-run@sha256:ee4bb3f0841e70d74558c929feedcdadb77f40bb3ac0017c78804ff9d9b9ec53 \
  --cpu 2 --memory 6Gi --task-timeout 1800s --max-retries 0 --tasks 12 --parallelism 1 \
  --service-account <service-account> \
  --set-env-vars HANDOVER_IMAGE=us-docker.pkg.dev/<project-id>/ugrp/ugrp-run@sha256:ee4bb3f0841e70d74558c929feedcdadb77f40bb3ac0017c78804ff9d9b9ec53,HANDOVER_FIRST_TRIAL=1,RESULT_BUCKET=<bucket>
```

Cloud Run jobs use gen2 automatically. Before each new submission, `jobs describe` reads the named job’s image and requires an exact digest match. Launch, execution recovery and watch use named Cloud Run resources. Upload and fetch use bucket object paths. None of these commands requests the numeric namespace lookup that failed. The archived regional job export confirms both gen2 and the image field used for read-back. [Job specification](cloudrun/handover/job.yaml.in) · [Regional job export](cloudrun/jobs/ugrp-run3.us-central1.yaml) · [Operator code](cloudrun/handover/ops.py)

All 55 offline tests passed (14 cloud, 17 dispatcher, 24 hand-over). The dispatcher emitted two existing `cr.lock` resource warnings. With subprocess execution intercepted, the deploy entry point produced the command above from the existing cohort. All 21 cohort files retained their SHA-256 hashes and modification times. [FIX1 verification](cloudrun/handover/verification/fix1-tests.log) · [Offline command transcript](cloudrun/handover/verification/commands.txt)

### 확인 안 됨

Live deployment with Cloud Resource Manager disabled, any implicit lookups by the installed SDK, the deployed image read-back, and trial execution, upload, fetch and scoring against real results await a cloud run.
