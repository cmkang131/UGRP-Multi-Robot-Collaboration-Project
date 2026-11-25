"""Explicit hand-over image entry point. The network-disabled driver runs in a child."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

# The installed entry point sits beside handover/. The checkout keeps this worker two levels below it.
_directory = Path(__file__).resolve().parent
if not (_directory / "handover/layout.py").is_file():
    sys.path.insert(0, str(_directory.parents[1]))
from handover import layout

PROJECT = os.environ.get("HANDOVER_PROJECT", "<project-id>")
BUCKET = os.environ.get("HANDOVER_BUCKET", "<bucket>")
JOB = "ugrp-handover-gate"
REGION = "us-central1"
PACKAGE = f"us-docker.pkg.dev/{PROJECT}/ugrp/ugrp-run"
REGISTRY_DIGEST = re.compile(re.escape(PACKAGE) + r"@sha256:[0-9a-f]{64}")
TRIAL_GROUPS = {"smoke": (1,), "remaining": tuple(range(2, 13)), "all": tuple(range(1, 13)),
                "blue-smoke": (2,), "after-blue": (1, *range(3, 13))}
SELECTIONS = {name: (rows[0], len(rows)) for name, rows in TRIAL_GROUPS.items()}
ROOT = Path("/opt/ugrp")
SCRATCH = Path("/tmp/ugrp-handover")
PYTHON = os.environ.get("HANDOVER_PYTHON", sys.executable)


def execution_name(name):
    if not re.fullmatch(re.escape(JOB) + r"-[a-z0-9][a-z0-9-]*", name):
        raise ValueError("expected an execution ID for " + JOB)
    return name


def trial_number(first, count, index):
    for name, selection in SELECTIONS.items():
        if selection == (first, count) and 0 <= index < count:
            return TRIAL_GROUPS[name][index]
    raise ValueError(f"invalid trial slice: first={first} count={count} index={index}")


def row_name(trial):
    return f"trial-{trial:02d}"


def object_prefix(execution, trial):
    return f"handover/{execution_name(execution)}/{row_name(trial)}"


def driver_argv(trial, out, root=ROOT, table_name=layout.TABLE.name):
    if table_name not in layout.TRIAL_TABLES:
        raise ValueError(f"unknown trial table: {table_name!r}")
    argv = [PYTHON, "-B", str(root / "handover/run_trial.py"), "--trial", str(trial),
            "--out", str(out), "--wall-seconds", "1080"]
    if table_name != layout.TABLE.name:
        argv.extend(["--trial-table", table_name])
    return argv


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parent_worker():
    # The pinned Dockerfile installed this module. Importing it does not run its main().
    sys.path.insert(0, "/opt")
    import cr_task
    # The inherited HTTP helper may include curl argv in a timeout exception.
    cr_task.log = lambda _message: print("GCS transfer retry", file=sys.stderr, flush=True)
    return cr_task


def run_task(env, parent, *, root=ROOT, scratch=SCRATCH, run=subprocess.run):
    if env["CLOUD_RUN_JOB"] != JOB or env["RESULT_BUCKET"] != BUCKET:
        raise ValueError("unexpected job or result bucket")
    execution = execution_name(env["CLOUD_RUN_EXECUTION"])
    index, count, first = (int(env[key]) for key in
                           ("CLOUD_RUN_TASK_INDEX", "CLOUD_RUN_TASK_COUNT", "HANDOVER_FIRST_TRIAL"))
    trial = trial_number(first, count, index)
    if int(env["CLOUD_RUN_TASK_ATTEMPT"]) != 0:
        raise ValueError("refusing a repeated task attempt")
    work = scratch / execution / f"task-{index}"
    work.mkdir(parents=True, exist_ok=False)
    name = row_name(trial)
    out = work / name  # run_trial.py must create this directory itself
    prefix = object_prefix(execution, trial)
    table_name = env.get("HANDOVER_TRIAL_TABLE", layout.TABLE.name)
    argv = driver_argv(trial, out, root, table_name)
    meta = {"schema": "handover.cloud.v1", "execution": execution, "image": env.get("HANDOVER_IMAGE"),
            "first_trial": first, "task_index": index, "task_count": count, "trial": trial, "attempt": 0,
            "driver_argv": argv, "driver_exit": None, "task_exit": 2, "uploaded": False}
    if table_name != layout.TABLE.name:
        meta["trial_table"] = table_name
    print(f"{execution} task {index}/{count} -> {name}", flush=True)
    log = work / "driver.log"
    with log.open("x") as stream:
        try:
            layer_bytes = (root / "layer.json").read_bytes()
            meta["layer_sha256"] = hashlib.sha256(layer_bytes).hexdigest()
            layer = json.loads(layer_bytes)
            meta.update(exec_commit=layer["exec_commit"], base_image=layer["base_image"],
                        trials_sha256=layer["sha256"][f"handover/scenes/{table_name}"])
            if not REGISTRY_DIGEST.fullmatch(meta["image"] or ""):
                raise ValueError("job image must be pinned by digest")
            if env.get("HANDOVER_EXPECT_IMAGE", meta["image"]) != meta["image"]:
                raise ValueError("deployed job image differs from submitted cohort")
            rc = run(argv, stdout=stream, stderr=subprocess.STDOUT, timeout=1140).returncode
            meta["driver_exit"] = rc
            summary = json.loads((out / "run.json").read_bytes())
            status = summary["status"]
            meta["driver_status"] = status
            if (summary["schema"], summary["trial"]) != ("handover.run.v1", trial):
                raise ValueError("run.json identifies a different trial")
            if {0: "finished", 1: "failed", 2: "error"}.get(rc) != status:
                raise ValueError("driver exit and run.json disagree")
            meta["task_exit"] = 0 if rc in (0, 1) else 2
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            meta["worker_error"] = f"{type(exc).__name__}: {exc}"
            print(meta["worker_error"], file=stream)
    out.mkdir(exist_ok=True)  # retain diagnostics even if the child never started
    log.rename(out / "driver.log")
    archive = work / "full.tar.zst"
    try:
        parent.make_tar(archive, work, [name])
        meta["archive_bytes"] = archive.stat().st_size
        meta["archive_sha256"] = file_hash(archive)
        meta["uploaded"] = parent.gcs_upload(BUCKET, prefix + "/full.tar.zst", archive)
    except Exception as exc:
        meta["archive_error"] = type(exc).__name__
    if not meta["uploaded"]:
        meta["task_exit"] = 98
    marker = work / "meta.json"
    marker.write_text(json.dumps(meta, indent=2) + "\n")
    try:
        published = parent.gcs_upload(BUCKET, prefix + "/meta.json", marker, "application/json")
    except Exception as exc:
        print(f"{prefix} marker upload failed ({type(exc).__name__})", file=sys.stderr)
        return 98
    if not published:
        return 98
    print(f"{prefix} driver={meta['driver_exit']} uploaded={meta['uploaded']} task={meta['task_exit']}",
          flush=True)
    return meta["task_exit"]


if __name__ == "__main__":
    sys.exit(run_task(os.environ, parent_worker()))
