"""Local result files, published atomically on the same filesystem."""
import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parent


def local_path(path):
    path = (ROOT / path).resolve()
    if not path.is_relative_to(ROOT) or path == ROOT:
        raise ValueError(f"Expected a path inside {ROOT}")
    return path


def digest(data):
    return hashlib.sha256(data).hexdigest()


@contextmanager
def locked(path):
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


@contextmanager
def atomic_file(path):
    with NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent,
                            prefix="." + path.name + "-", delete=False) as handle:
        temp = Path(handle.name)
        try:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"


def write_json(path, value):
    with atomic_file(path) as handle:
        handle.write(json_text(value))


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def snapshot(source, destination, expected):
    raw = source.read_bytes()
    if digest(raw) != expected:
        raise ValueError(f"Input changed during snapshot: {source}")
    if destination.exists():
        if destination.read_bytes() != raw:
            raise ValueError(f"Saved input differs: {destination}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with atomic_file(destination) as handle:
            handle.buffer.write(raw)


PROTOCOL_SOURCES = ("run_chen2d.py", "env1-box-arrange.py", "env1_create.py", "prompt_env1.py",
                    "LLM.py", "limits.py", "episode.py", "map_events.py", "plan_parse.py",
                    "fake_model.py", "storage.py", "summarize.py", "enrol_maps.py", "relay.py", "paired.py",
                    "analysis_runs.py", "cost.py", "audit_news.py", "rescues.py", "free_messages.py",
                    "failure_causes.py", "output_demand.py", "horizon.py", "planning_metrics.py",
                    "map_sets.py", "matched_protocol.py", "board_sizes.py")


def source_hashes():
    return {name: digest((ROOT / name).read_bytes()) for name in PROTOCOL_SOURCES}


def version_from_hashes(hashes):
    return digest(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode())[:12]


@lru_cache(maxsize=1)
def code_version():
    return version_from_hashes(source_hashes())
