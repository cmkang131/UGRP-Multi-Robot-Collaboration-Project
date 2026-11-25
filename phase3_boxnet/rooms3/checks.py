"""Names and receipts shared by the staged worker and its offline collector."""
import json
from pathlib import Path

SEEDS = (0, 3, 6)
MODES = {
    "rooms3-camera": ("rooms3.check_camera", "rooms3.camera-check.v1"),
    "rooms3-step": ("rooms3.check_step", "rooms3.step-check.v1"),
}
# Wall-clock limits in seconds. Each one sits inside the next: the check's own alarm (budget) is shorter than the
# worker's child timeout (driver), which is shorter than the Cloud Run task limit. A mode without a task limit
# runs under the job's own limit, the hand-over gate's 1,800 s.
LIMITS = {
    "rooms3-camera": {"driver": 1620},
    "rooms3-step": {"budget": 5400, "driver": 5400 + 120, "task": 7200},
}
# Fixed before running. On seed 3 the robots first use opposite pads, then r1 requests the arriving red.
FIRST_ROUND = {
    0: (("red", "r2"), ("blue", "target"), ("red", "r2")),
    3: (("blue", "r2"), ("red", "r1"), ("red", "target")),
    6: (("red", "target"), ("red", "target"), ("blue", "r2")),
}


def request_rounds(seed):
    robots = ("r1", "r2", "r3")
    first = {r: {"colour": colour, "to": dest} for r, (colour, dest) in zip(robots, FIRST_ROUND[seed])}
    return [first, {"r1": {"colour": "red", "to": "target"}}] if seed == 3 else [first]


def selection(seeds):
    seeds = tuple(seeds)
    if not seeds or any(type(s) is not int or s not in SEEDS for s in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError(f"choose distinct staged seeds from {SEEDS}")
    return seeds


def scene_path(seed):
    return f"rooms3/scenes/seed-{seed}"


def result_status(row, mode, seed, xml_hash, rc):
    row = Path(row)
    record = json.loads((row / "check.json").read_bytes())
    expected = (MODES[mode][1], f"seed-{seed}", seed, xml_hash)
    if tuple(record.get(k) for k in ("schema", "scene", "seed", "xml_sha256")) != expected:
        raise ValueError("check.json identifies a different check or scene")
    if rc not in (0, 1, 2) or {0: "passed", 1: "failed", 2: "error"}[rc] != record["status"]:
        raise ValueError("check.json disagrees with the driver exit")
    if rc == 0 and mode == "rooms3-camera":
        frames = ["top.png", "top_1.png"]
        for rid in ("r1", "r2", "r3"):
            view = record["robots"][rid]
            if any(view["checks"].get(k) is not True for k in ("ceiling_pose", "sign", "first_wrist", "own_selection")):
                raise ValueError(f"incomplete camera checks for {rid}")
            sign_frame = view["sign_frame"]
            if Path(sign_frame).name != sign_frame or not sign_frame.startswith(rid + "-sign-"):
                raise ValueError("unexpected sign frame name")
            frames.extend((rid + "-first.jpg", sign_frame))
        if any(not (row / name).is_file() or (row / name).stat().st_size == 0 for name in frames):
            raise ValueError("missing camera capture")
    if mode == "rooms3-step" and rc in (0, 1):
        before = json.loads((row / "initial.json").read_bytes())
        requests = request_rounds(seed)
        if len(record["rounds"]) != len(requests):
            raise ValueError("incomplete step evidence")
        outcomes = []
        for i, moves in enumerate(requests, 1):
            step = json.loads((row / f"step-{i}.json").read_bytes())
            if step["before"] != before or step["actions"] != record["rounds"][i-1]:
                raise ValueError("step evidence differs from the recorded summary")
            for rid in ("r1", "r2", "r3"):
                action = step["actions"][rid]
                if action["requested"] != moves.get(rid) or (rid not in moves and action["status"] != "idle"):
                    raise ValueError("archived requests differ from the selected seed's check")
                if rid in moves:
                    outcomes.append(action["status"])
            before = step["after"]
        if all(status == "moved" for status in outcomes) != (rc == 0):
            raise ValueError("step outcomes disagree with acceptance")
    return record["status"]
