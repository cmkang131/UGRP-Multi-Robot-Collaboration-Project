"""Produce the allowlisted, reproducible build context for the hand-over image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PARENT = "d369231d5e0198c67e63b0bb557e7ed328ee603a"
FIRST_OVERLAY = "b04f88c6110b6301d78a8ed4dd76c9e0f06f3eb2"
FIX2 = "2891894258b177ac4850a4992329b7795da056ae"
FIX3 = "7ab759bb7d7c29a1c5eb2612c4c690f513612e0c"
FIX4 = "d013eeabeeff4f228d9afb9ac107c4b0d1f7448a"  # executor used by the FIX3 and FIX4 cohorts
COMMIT = "ba0eb353ef00e376bfa64b3b17d7b26d77425973"  # executor used by the FIX6 image (FIX5 reused FIX4)
EXEC_FILES = ("harness/handover_policy.py", "scripts/handover_card_check.py",
              "scripts/handover_world.py", "sim/handover_scene.py")
GATE_FILES = ("run_trial.py", "layout.py", "records.py", "criteria.py", "score.py", "scenes/trials.csv",
              "scenes/trials-swapped.csv", "check_donor_view.py")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT / "exec-repo"), *args])


def context():
    # An original executor checkout also proves ancestry and the Git blob identity.
    # The public snapshot carries immutable digests for the four reviewed blobs.
    pins = json.loads((HERE / "verification/exec-source.json").read_text())
    if pins["commit"] != COMMIT or set(pins["sha256"]) != set(EXEC_FILES):
        raise ValueError("executor pin or file list differs")
    files = {}
    for name in EXEC_FILES:
        blob = (ROOT / "exec" / name).read_bytes()
        if digest(blob) != pins["sha256"][name]:
            raise ValueError(f"{name} differs from the pinned executor blob")
        files["exec/" + name] = blob
    if (ROOT / "exec-repo/.git").exists():
        lineage = git("rev-list", "--parents", f"{PARENT}..{COMMIT}").decode().splitlines()
        if lineage != [f"{COMMIT} {FIX4}", f"{FIX4} {FIX3}", f"{FIX3} {FIX2}", f"{FIX2} {FIRST_OVERLAY}",
                   f"{FIRST_OVERLAY} {PARENT}"]:
            raise ValueError("unexpected hand-over history above the baked executor")
        changes = git("diff", "--no-renames", "--name-status", PARENT, COMMIT)
        if set(changes.decode().splitlines()) != {"A\t" + name for name in EXEC_FILES}:
            raise ValueError("overlay must add exactly the allowlisted hand-over files")
        for name in EXEC_FILES:
            blob = git("show", f"{COMMIT}:{name}")
            for tree in ("exec", "exec-repo"):
                if (ROOT / tree / name).read_bytes() != blob:
                    raise ValueError(f"{tree}/{name} differs from {COMMIT}")
            files["exec/" + name] = blob
    for name in GATE_FILES:
        files["handover/" + name] = (ROOT / "handover" / name).read_bytes()
    for name in ("worker.py", "check_image.py"):
        files[name] = (HERE / name).read_bytes()
    template = (HERE / "Dockerfile").read_text()
    dockerfile = template.replace("<project-id>", os.environ.get("HANDOVER_PROJECT", "<project-id>")).encode()
    base = dockerfile.decode().splitlines()[0].removeprefix("FROM ")
    layer = {"schema": "handover.layer.v1", "base_image": base, "base_exec": PARENT,
             "exec_commit": COMMIT, "sha256": {name: digest(data) for name, data in files.items()}}
    files["layer.json"] = (json.dumps(layer, indent=2, sort_keys=True) + "\n").encode()
    files["Dockerfile"] = dockerfile
    files["cloudbuild.yaml"] = (HERE / "cloudbuild.yaml").read_bytes()
    files[".gcloudignore"] = b"# All files in this generated context are build inputs.\n"
    return files


def inventory(files):
    return "".join(f"{digest(files[name])}  {name}\n" for name in sorted(files))


def write_context(directory, files):
    directory.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as dest:
            dest.write(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="also write the context to a new directory")
    args = parser.parse_args()
    inputs = context()
    if args.out:
        write_context(args.out, inputs)
    print(inventory(inputs), end="")
