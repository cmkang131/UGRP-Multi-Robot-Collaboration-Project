"""Exercise donor box selection with the trial cameras and frozen survey, before the first grasp."""
import argparse
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from handover import layout, run_trial
from handover.records import Recorder


def check(number):
    expected = {2: "cyan", 1: "red"}[number]
    trial = layout.trials()[number]
    sys.addaudithook(run_trial.offline)
    with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
        folder = Path(tmp).resolve()
        scene_map = folder / "map.json"
        scene_map.write_text(json.dumps(layout.map_config(trial)))
        # Both calibrated readers load their trial's map at import. Run each check in a fresh process.
        os.environ["UGRP_MAP_SCENE"] = str(scene_map)
        native = Path(os.environ.get("HANDOVER_SCENE_ROOT", ROOT / "handover/runtime/scene")).resolve() / "sim"
        os.environ.update(TMPDIR=str(folder), XDG_CACHE_HOME=str(folder), MESA_SHADER_CACHE_DISABLE="true")
        os.environ.setdefault("MUJOCO_GL", "egl")
        stack.callback(os.chdir, Path.cwd())
        os.chdir(folder)
        import sim
        if "HANDOVER_SCENE_ROOT" in os.environ or native.is_dir():
            sim.__path__.insert(0, str(native))
        import cv2
        from harness.handover_policy import Policy, absolute
        from scripts.handover_world import World

        cv2.setNumThreads(1)
        record = Recorder(folder, trial, stack)
        world = World(trial, record, stack)
        policy = Policy(world, None)
        donor = trial["donor"]
        policy.idle(donor, 10)
        origin = policy.pose(donor)
        approach = policy.box_survey(origin, "donor")
        jpg = world.frame(donor)
        first = approach.student.Survey(approach.baseline)
        first.observe(jpg, {int(k): v for k, v in world.pwm[donor].items()})
        first_xy = [absolute(origin, *track["points"][0]) for track in first._tracks if track["kind"] == expected]
        blobs = approach.baseline.components(jpg, expected)
        print(f"trial {number} first wrist frame, {donor} {expected}: "
              f"components={blobs} projected_xy={first_xy}", flush=True)

        # A list entry requires independent frames. Run the actual stationary pan and chooser.
        for _ in range(100):  # The frozen fast survey selects on tick 89.
            row = approach.step(world.frame(donor) if approach.needs_frame() else b"", record.now)
            world.control(donor, row)
            if approach.index is not None or approach.arrived:
                break
        print(f"trial {number} survey: {approach.entries}, selected={approach.index}, "
              f"evidence={approach.survey.evidence}", flush=True)
        target = trial["box_start"][:2]  # Comparison only, after the controller has made its selection.
        tolerance = approach.baseline.POS_GATE_M
        if not any(math.dist(p, target) <= tolerance for p in first_xy):
            raise ValueError(f"trial {number}: first wrist frame did not locate the {expected} box at {target}")
        if approach.index is None:
            raise ValueError(f"trial {number}: donor could not select the {expected} box")
        entry = approach.entries[approach.index]
        selected_xy = absolute(origin, entry["x"], entry["y"])
        if entry["kind"] != expected or math.dist(selected_xy, target) > tolerance:
            raise ValueError(f"trial {number}: incorrect selection {entry['kind']} at {selected_xy}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial", type=int, choices=(2, 1))
    check(parser.parse_args().trial)
