"""Retrieve complete, execution-specific trial folders for handover/score.py."""
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from worker import BUCKET, file_hash, object_prefix, row_name, trial_number
from handover import layout


def sources(execution, trial):
    prefix = f"gs://{BUCKET}/{object_prefix(execution, trial)}"
    return [prefix + "/" + name for name in ("meta.json", "full.tar.zst")]


def extract(archive, destination, name):
    # Only materialize directories and regular files beneath this trial's root.
    with subprocess.Popen(["zstd", "-qdc", "--", str(archive)], stdout=subprocess.PIPE) as proc:
        with proc.stdout as pipe:
            with tarfile.open(fileobj=pipe, mode="r|") as bundle:
                for member in bundle:
                    rel = PurePosixPath(member.name)
                    if rel.parts[:1] != (name,) or ".." in rel.parts:
                        raise ValueError(f"archive member outside {name}: {member.name}")
                    target = destination / rel
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    elif member.isreg():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with bundle.extractfile(member) as src, target.open("xb") as dest:
                            shutil.copyfileobj(src, dest)
                    else:
                        raise ValueError(f"unexpected archive member type: {member.name}")
            while pipe.read(1024 * 1024):
                pass
        if proc.wait() != 0:
            raise ValueError("zstd did not finish decoding the archive")


def check_marker(meta, execution, image, layer_hash, first, count, index, table_name=layout.TABLE.name, table_hash=None):
    expected = {"schema": "handover.cloud.v1", "execution": execution, "image": image,
                "layer_sha256": layer_hash, "trial": trial_number(first, count, index), "first_trial": first,
                "task_count": count, "task_index": index, "attempt": 0}
    for key, value in expected.items():
        if meta.get(key) != value:
            raise ValueError(f"marker {key} differs from this execution")
    if meta.get("trial_table", layout.TABLE.name) != table_name:
        raise ValueError("worker trial table differs from cohort")
    if table_hash is not None and meta.get("trials_sha256") != table_hash:
        raise ValueError("worker trial table digest differs from cohort")
    if meta.get("uploaded") is not True or not re.fullmatch("[0-9a-f]{64}", meta.get("archive_sha256", "")):
        raise ValueError("worker did not confirm a complete archive")


def fetch_one(results, execution, image, layer_hash, first, count, index, download, table_name=layout.TABLE.name,
              table_hash=None):
    trial = trial_number(first, count, index)
    name = row_name(trial)
    dest = results / name
    if dest.exists():
        meta = json.loads((dest / "cloud-meta.json").read_bytes())
        check_marker(meta, execution, image, layer_hash, first, count, index, table_name, table_hash)
        print(f"{name} already fetched from {execution}")
        return
    with tempfile.TemporaryDirectory(dir=results, prefix="." + name + "-") as tmp:
        staging = Path(tmp)
        marker, archive = staging / "meta.json", staging / "full.tar.zst"
        meta_uri, archive_uri = sources(execution, trial)
        download(meta_uri, marker)
        meta = json.loads(marker.read_bytes())
        check_marker(meta, execution, image, layer_hash, first, count, index, table_name, table_hash)
        download(archive_uri, archive)
        if archive.stat().st_size != meta["archive_bytes"] or file_hash(archive) != meta["archive_sha256"]:
            raise ValueError("archive size or SHA-256 mismatch")
        extract(archive, staging, name)
        row = staging / name
        if meta["task_exit"] == 0:
            run = json.loads((row / "run.json").read_bytes())
            definition = json.loads((row / "trial.json").read_bytes())
            if definition.get("trial_table", layout.TABLE.name) != table_name:
                raise ValueError("archived trial table differs from cohort")
            if definition != layout.trials(table_name)[trial]:
                raise ValueError("archived trial definition differs from selected table")
            if (run["trial"], definition["trial"], run["status"]) != (trial, trial, meta["driver_status"]):
                raise ValueError("archived trial identity or status differs from marker")
        with (row / "cloud-meta.json").open("xb") as receipt:
            receipt.write(marker.read_bytes())
        row.rename(dest)
    print(f"{name} driver={meta['driver_exit']} task={meta['task_exit']} verified -> {dest}")


def fetch_rows(results, execution, image, layer_hash, selection, download, *,
               table_name=layout.TABLE.name, table_hash=None):
    first, count = selection
    results.mkdir(exist_ok=True)
    failed = []
    for i in range(count):
        try:
            fetch_one(results, execution, image, layer_hash, first, count, i, download, table_name, table_hash)
        except (OSError, ValueError, KeyError, TypeError, EOFError, tarfile.TarError, subprocess.SubprocessError) as exc:
            name = row_name(trial_number(first, count, i))
            failed.append(name)
            print(f"{execution}/{name}: {exc}", file=sys.stderr)
    if failed:
        raise ValueError("incomplete fetch: " + ", ".join(failed))
