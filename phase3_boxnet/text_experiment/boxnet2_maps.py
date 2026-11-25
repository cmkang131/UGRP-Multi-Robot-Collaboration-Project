"""Isolated BoxNet2 registries; BoxNet1 controls are always opened read-only."""
import random

from boxnet2 import create_board
from map_events import EVENT_FILE_VERSION, agent_at, boxes, event_path
from map_sets import COLOURS, boxes_for_team, colour_counts
from storage import ROOT, digest, json_text, local_path, locked, read_json, write_json


def scaled_control(rows, cols, seed, selected):
    """Return a verified registered control or None for a new size/seed/density."""
    directory = selected.directory
    size = f"{rows}x{cols}"
    path = directory / size / f"env{seed}.json"
    index = path.parent if (path.parent / "manifest.json").is_file() else directory
    manifest = index / "manifest.json"
    expected = read_json(manifest).get(str(path.relative_to(index))) if manifest.is_file() else None
    if expected is None and not path.exists():
        return None
    if not path.is_file() or digest(path.read_bytes()) != expected:
        raise ValueError(f"Missing or modified BoxNet1 control: {size}/env{seed}.json")
    return read_json(path), expected


def saved_corner_env(rows, cols, seed, selected):
    if selected.boxes_per_robot is None:
        raise ValueError("BoxNet2 requires --map-set scaled:R")
    total = boxes_for_team(rows, cols, selected.boxes_per_robot)
    control = scaled_control(rows, cols, seed, selected)
    counts = colour_counts(total)
    if control is not None:
        registered = boxes(control[0])
        if registered.total() != total or set(registered) - set(COLOURS):
            raise ValueError("Unexpected colour inventory in the registered BoxNet1 control")
        counts = {colour: registered[colour] for colour in COLOURS}
    board, redraws = create_board(rows, cols, counts, random.Random(seed))
    sha = digest(json_text(board).encode())
    fields = dict(selected.metadata, box_count=total)
    # Static matched writers require a named central speaker. Changed-order fields are unused.
    assignment = dict(env="boxnet2", event_file_version=EVENT_FILE_VERSION, seed=seed, env_sha256=sha,
                      boxnet1_control_sha256=control[1] if control else None, placement_redraws=redraws,
                      colour_counts=counts, L=agent_at((.5, .5)), M=None, L2=None, A=None, A2=None,
                      D=None, D2=None, S=None, event_step=None, stratum=None, member_position=None,
                      wording=1, **fields)
    rate = selected.map_set.removeprefix("scaled:")
    directory = local_path(ROOT / "envs-boxnet2" / f"r{rate}" / f"{rows}x{cols}")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"env{seed}.json"
    manifest_path = directory / "manifest.json"
    with locked(directory / ".env.lock"):
        manifest = read_json(manifest_path) if manifest_path.exists() else {}
        entries = ((path, board), (event_path(path), assignment))
        additions = {}
        for file, value in entries:
            expected = digest(json_text(value).encode())
            if file.name in manifest and (manifest[file.name] != expected or not file.is_file()):
                raise ValueError(f"Changed BoxNet2 registration: {file.name}")
            if file.exists() and digest(file.read_bytes()) != expected:
                raise ValueError(f"Modified BoxNet2 input: {file.name}")
            additions[file.name] = expected
        for file, value in entries:
            if not file.exists():
                write_json(file, value)
        if additions.items() - manifest.items():
            write_json(manifest_path, {**manifest, **additions})
    return path, sha, fields
