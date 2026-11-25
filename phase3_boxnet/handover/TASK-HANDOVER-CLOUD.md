# TASK-HANDOVER-CLOUD: make the two-robot hand-over test runnable on Cloud Run (2026-11-25)

Context: `TASK-HANDOVER-GATE.md` is done (`REPORT-HANDOVER-GATE.md`, folder `handover/`, three new files under
`exec/`). No physics has run: this server has no environment with MuJoCo + OpenCV + PyTorch + LeRobot together, and
the `exec/` copy here lacks the scene XML, wheel assets and the grasp checkpoint. All earlier MuJoCo runs of this
project ran on Cloud Run from an image that contains the full executor, runtime and checkpoint. The user has
authorised the cloud build and the 12 runs. YOU prepare everything offline; the MAIN SESSION runs every cloud command.

## Goal
The main session must be able to (1) build ONE image that can run `handover/run_trial.py --trial K`, (2) run the
12 trials as Cloud Run job tasks, (3) fetch the 12 output folders and (4) score them with `handover/score.py`, with a
short list of commands and without editing anything by hand.

## Hard limits
- No network, no cloud command (`gcloud`, `docker push`, anything that leaves the machine), no LLM call. Dry-runs and
  local syntax / unit checks only.
- `../20261118-cloudrun-p2/` and every other phase-2 folder are READ-ONLY. If one of their scripts has to change,
  put a copy or a thin wrapper under `20261123-phase3/cloudrun/handover/` and change that. Existing phase-3 files
  (`cloudrun/cr_dispatch_p3.py`, the image task entry point, job definitions) keep their behaviour byte for byte for
  every existing use; the hand-over path is reachable only through new, explicitly named options or files.
- The executor repository `exec-repo/` (branch `phase3/reveal-trigger`): you may create a NEW local branch from the
  revision the last verified image was built from and commit the three hand-over files there (local commit only, no
  push, no rewriting of existing commits). Say which revision that is and how you established it (image manifests
  under `cloudrun/`, `manifests/`, `../20261118-cloudrun-p2/builds/`). The working copy `exec/` and `exec-repo/` must
  agree on those three files.
- No deletion or overwriting of existing files. Never print or copy secrets (keys, tokens, service-account files).
- Google Cloud project is `<project-id>` only, through the wrapper the existing scripts use (`gcloud-p`).

## What to choose
Choose the SMALLEST path that reuses the verified image contents (full simulator assets, runtime, grasp checkpoint,
upload of results). Two candidates; pick one and say why:
(a) a thin layer on top of the last verified image: copy `handover/` and the three executor files in, add an entry
    script that maps the Cloud Run task index to a trial number, runs the trial with a fresh output folder and
    uploads the folder with the same mechanism the existing worker uses (success, trial failure and error alike);
(b) the integration sketched in `REPORT-HANDOVER-GATE.md` ("Cloud Run preparation and dispatch": a build mode, a
    `handover_gate` entry in the wrapper, a two-robot job, routing before planner start).
Either way: one task per trial, no automatic task retries, 2 vCPU and enough memory for two robot cameras, a wall
limit that covers the driver's 1,080 s budget plus start-up, and the checkpoint / scene paths that
`handover/run_trial.py` expects (`handover/runtime/act`, `HANDOVER_ACT_MODEL`, `HANDOVER_SCENE_ROOT`) pointing at what
the image really contains (find the real paths in the existing image definition and worker script).

## Deliver
- The files (build script or Dockerfile, entry script, job definition, dispatch and fetch helpers) under
  `cloudrun/handover/`, the local commit in `exec-repo/`, and tests / dry-runs that prove offline what can be proved:
  the command lines, the task-index mapping for all 12 trials, the staged file list with hashes, that existing
  dispatcher tests still pass (`(cd cloudrun && python3 -B -m unittest test_cr_dispatch_p3)`), that
  `handover/tests` still pass, and that the three executor files are identical in `exec/` and the commit.
- `REPORT-HANDOVER-CLOUD.md`: the chosen path and why; the EXACT ordered commands for the main session (build,
  create or update the job, run, watch, fetch, score), each with what it costs or changes, how to tell that it
  worked, and how to undo it (delete the job, the image tag); the expected cost of the 12 tasks from the job size and
  the 1,080 s budget; which quotas or permissions could stop it; and a list "확인 안 됨".
- A one-trial smoke path: commands to run ONLY trial 1 first, so the main session can see one result before
  spending on all twelve.
Last step: create `review/ASTRA-HANDOVER-CLOUD.done`.
