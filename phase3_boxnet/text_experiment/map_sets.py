"""Opt-in map-set parsing and isolated scaled-map enrolment.

Legacy maps remain in ``envs/``. A scaled map set has its own registry at
``envs-scaled/r<R>/`` so it cannot silently replace or mix published maps.
The five existing colours are retained: totals are divided as evenly as
possible in ``COLOURS`` order, with remainder boxes assigned to first colours.
Each box still receives an independently sampled target using the original
placement mechanism.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import random
import re

from board_sizes import SCALED_ONLY_SIZES
from env1_create import action_from_response, env_create
from map_events import event_path, map_assignment
from storage import ROOT, digest, local_path, locked, read_json, write_json

COLOURS = ("blue", "red", "green", "purple", "orange")
_SCALED = re.compile(r"scaled:([^:]+)\Z")


def _decimal_text(value):
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


@dataclass(frozen=True)
class MapSet:
    map_set: str
    boxes_per_robot: Decimal | None = None

    @property
    def registry_name(self):
        return "envs" if self.boxes_per_robot is None else f"envs-scaled/r{_decimal_text(self.boxes_per_robot)}"

    @property
    def directory(self):
        return ROOT / self.registry_name

    @property
    def metadata(self):
        return dict(map_set=self.map_set,
                    boxes_per_robot=None if self.boxes_per_robot is None else float(self.boxes_per_robot))


def parse_map_set(value=None):
    """Parse `legacy` or `scaled:R` without changing legacy defaults."""
    if value in (None, "", "legacy"):
        return MapSet("legacy")
    match = _SCALED.fullmatch(value)
    if not match:
        raise ValueError("--map-set must be legacy or scaled:R, where R is positive")
    try:
        rate = Decimal(match.group(1))
    except InvalidOperation as exc:
        raise ValueError("boxes-per-robot must be a positive finite number") from exc
    if not rate.is_finite() or rate <= 0:
        raise ValueError("boxes-per-robot must be a positive finite number")
    rate = rate.normalize()
    return MapSet(f"scaled:{_decimal_text(rate)}", rate)


def boxes_for_team(rows, cols, boxes_per_robot):
    """Task-defined Python ``round(R * robots)``, with a one-box minimum."""
    rate = boxes_per_robot if isinstance(boxes_per_robot, Decimal) else Decimal(str(boxes_per_robot))
    return max(1, int(round(rate * rows * cols)))


def colour_counts(total):
    """Balanced deterministic allocation across the original five colours."""
    base, remainder = divmod(total, len(COLOURS))
    return {colour: base + (index < remainder) for index, colour in enumerate(COLOURS)}


def scaled_env_create(rows, cols, boxes_per_robot, *, rng):
    total = boxes_for_team(rows, cols, boxes_per_robot)
    return env_create(rows, cols, rng=rng, box_counts=colour_counts(total))


def _write_scaled_event(path, root, state, rows, cols, seed, selected, manifest_hash):
    sidecar = event_path(path)
    event_manifest_path = root / "events-manifest.json"
    key = sidecar.relative_to(root).as_posix()
    events = read_json(event_manifest_path) if event_manifest_path.exists() else {}
    expected = dict(map_assignment(state, seed, manifest_hash, rows, cols, action_from_response),
                    map_set=selected.map_set, boxes_per_robot=float(selected.boxes_per_robot),
                    box_count=boxes_for_team(rows, cols, selected.boxes_per_robot))
    if key in events:
        if not sidecar.is_file() or digest(sidecar.read_bytes()) != events[key]:
            raise ValueError(f"Missing or modified enrolled scaled event: {key}")
        if read_json(sidecar) != expected:
            raise ValueError(f"Changed scaled event: {key}")
    else:
        if sidecar.exists() and read_json(sidecar) != expected:
            raise ValueError(f"Unregistered scaled event differs from seeded assignment: {key}")
        if not sidecar.exists():
            write_json(sidecar, expected)
        events[key] = digest(sidecar.read_bytes())
        write_json(event_manifest_path, events)


def saved_scaled_env(rows, cols, seed, selected):
    """Enrol exactly one map in an isolated scaled registry."""
    if not isinstance(selected, MapSet) or selected.boxes_per_robot is None:
        raise ValueError("saved_scaled_env requires a scaled MapSet")
    directory = local_path(selected.directory)
    directory.mkdir(parents=True, exist_ok=True)
    size = f"{rows}x{cols}"
    path = directory / size / f"env{seed}.json"
    # Each new board size has its own indexes alongside its maps. All published
    # rate-wide manifests retain their original contents and relative paths.
    root = path.parent if size in SCALED_ONLY_SIZES else directory
    relative = path.relative_to(root).as_posix()
    manifest_path = root / "manifest.json"
    with locked(directory / ".env.lock"):
        manifest = read_json(manifest_path) if manifest_path.exists() else {}
        if relative in manifest:
            if not path.is_file() or digest(path.read_bytes()) != manifest[relative]:
                raise ValueError(f"Missing or modified enrolled scaled environment: {relative}")
        else:
            if path.exists():
                raise ValueError(f"Unregistered scaled environment already exists: {relative}")
            state = scaled_env_create(rows, cols, selected.boxes_per_robot, rng=random.Random(seed))
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, state)
            manifest[relative] = digest(path.read_bytes())
            write_json(manifest_path, manifest)
        state = read_json(path)
        _write_scaled_event(path, root, state, rows, cols, seed, selected, manifest[relative])
    return path, manifest[relative], dict(selected.metadata,
                                           box_count=boxes_for_team(rows, cols, selected.boxes_per_robot))


def saved_map_env(rows, cols, seed, map_set=None):
    """Load/enrol selected maps, returning `(path, sha, per-map metadata)`."""
    selected = parse_map_set(map_set) if not isinstance(map_set, MapSet) else map_set
    if selected.boxes_per_robot is None:
        from env1_create import saved_env
        path, sha = saved_env(rows, cols, seed)
        count = sum(1 for items in read_json(path).values() for item in items if item.startswith("box_"))
        return path, sha, dict(selected.metadata, box_count=count)
    return saved_scaled_env(rows, cols, seed, selected)
