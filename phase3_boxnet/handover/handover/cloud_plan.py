"""Offline Cloud Run row generator. Pure CSV/JSON and argv construction."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from handover import layout

IMAGE_ROOT = "/opt/ugrp"
FIELDS = ("run_id group scene_file scene_id team rep robots leader model vm_args server_args sha "
          "vmrun seed arm slot pilot_round selected map_seed scene_sha256").split()


def plan(sha):
    for k, trial in layout.trials().items():
        scene = f"HG{k:02d}"
        run_id = f"HANDOVER-{scene}"
        payload = (json.dumps(trial, indent=2) + "\n").encode()
        flags = ["--trial", str(k), "--wall-seconds", "1080"]
        row = dict(run_id=run_id, group="handover_gate", scene_id=scene,
                   scene_file=f"{IMAGE_ROOT}/handover/trials/{scene}.json", team="T1", rep=1,
                   robots="r1,r2", leader=trial["donor"], model="fixed-handover", vm_args=shlex.join(flags),
                   server_args="", sha=sha, vmrun="handover/run_trial.py", seed=trial["seed"],
                   arm="handover", slot=k, pilot_round="", selected="yes", map_seed=trial["seed"],
                   scene_sha256=hashlib.sha256(payload).hexdigest())
        yield row, payload, ["python3", "-B", f"{IMAGE_ROOT}/handover/run_trial.py", *flags,
                             "--out", f"/work/out/{run_id}"]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true", help="print all task argv without writing files")
    modes.add_argument("--stage", type=Path, help="write the CSV and row definitions into a new directory")
    p.add_argument("--exec-sha", help="frozen executor SHA for staging")
    a = p.parse_args(argv)
    if (a.stage or a.exec_sha) and not re.fullmatch(r"[0-9a-f]{40}", a.exec_sha or ""):
        p.error("staging requires a 40-hex --exec-sha")
    rows = list(plan(a.exec_sha or "DRY-RUN"))
    if a.dry_run:
        for row, _, command in rows:
            print(f"{row['run_id']}  seed={row['seed']}  {shlex.join(command)}")
        print("12 rows | 2 robots per row | 1 task per row | 0 planner processes")
    else:
        a.stage.mkdir(parents=True, exist_ok=False)
        scenes = a.stage / "trials"
        scenes.mkdir()
        with (a.stage / "manifest.csv").open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for row, payload, _ in rows:
                writer.writerow(row)
                with (scenes/(row["scene_id"]+".json")).open("xb") as file:
                    file.write(payload)


if __name__ == "__main__":
    main()
