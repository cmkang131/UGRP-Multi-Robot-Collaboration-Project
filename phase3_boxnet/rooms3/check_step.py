"""Check a fixed synchronous round of three native box moves, or probe the approach without a model."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import sys

from rooms3.maps import ROOT
from rooms3.checks import request_rounds
from rooms3.runtime import configure
from rooms3.steps import resolve, run_step, snapshot

ACT_FILES = ("SHA256.json", "model.safetensors", "adapter.json", "config.json")
DEFAULT_BUDGET_S = 1500  # local runs; the cloud step job passes its own budget from rooms3.checks.LIMITS


def run(bundle, out, scene, result, approach_robot):
    import cv2
    import mujoco
    from rooms3.motors import MotionWorld, NativeBackend
    cv2.setNumThreads(1)
    seed = scene["source"]["seed"]
    rounds = request_rounds(seed)
    checkpoint = Path(os.environ.get("HANDOVER_ACT_MODEL", ROOT / "handover/runtime/act"))
    missing = [n for n in ACT_FILES if not (checkpoint / n).is_file()]
    result.update(mujoco=mujoco.__version__, opencv=cv2.__version__, stage="compile_and_bind",
                  requested_rounds=rounds, missing_actor_files=missing, station_tilt="ignore")
    with ExitStack() as stack:
        w = MotionWorld(bundle, scene, out, stack)
        backend = NativeBackend(w)
        result.update(calibration_status=w.calibration_status, stage="initial_survey")
        try:
            for _ in range(10):
                w.tick({})
            initial = snapshot(scene, backend)
            (out / "initial.json").write_text(json.dumps(initial, indent=2, allow_nan=False) + "\n")
            result["initial_differences"] = initial["differences"]
            if approach_robot:
                result["stage"] = "approach"
                track, reason = resolve(scene, initial["perceived"], approach_robot, rounds[0][approach_robot])
                if reason:
                    raise ValueError(f"approach selection: {reason}")
                start = w.actual_pose(approach_robot)
                p = backend.prepare(approach_robot, track)
                p.approach(approach_robot, "donor", 1)
                result.update(status="partial", stage="before_grasp", robot=approach_robot, selected_track=track,
                              chassis_start=start, chassis_end=w.actual_pose(approach_robot))
                return 3
            result["stage"] = "load_local_grasp_actor"
            if missing:
                raise FileNotFoundError("missing local hand-over actor files: " + ", ".join(missing))
            import torch
            from harness.grasp_act_policy import GraspActor
            torch.set_num_threads(1)
            torch.manual_seed(seed)
            backend.actor = GraspActor.load(checkpoint, device="cpu")
            result["actor_inventory_sha256"] = hashlib.sha256((checkpoint / "SHA256.json").read_bytes()).hexdigest()
            result["stage"] = "execute_round"
            before = initial
            outcomes, result["rounds"] = [], []
            for i, moves in enumerate(rounds, 1):
                step = run_step(scene, moves, backend, before=before)
                (out / f"step-{i}.json").write_text(json.dumps(step, indent=2, allow_nan=False) + "\n")
                result["rounds"].append(step["actions"])
                outcomes.extend(step["actions"][rid]["status"] for rid in moves)
                before = step["after"]
            passed = all(status == "moved" for status in outcomes)
            result.update(status="passed" if passed else "failed", stage="complete",
                          final_differences=before["differences"])
            return 0 if passed else 1
        finally:
            w.stop()
            result.update(sim_s=w.record.now, physics_substeps=w.substeps, min_room_margin_m=w.min_margin,
                          final_witnesses={n: w.measure(n) for n in w.cargo})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--approach-only", choices=("r1", "r2", "r3"),
                        help="stop before the first grasp command; returns 3 for a completed component probe")
    parser.add_argument("--budget-s", type=int, default=DEFAULT_BUDGET_S,
                        help="wall-clock budget for the whole check in seconds (default %(default)s)")
    args = parser.parse_args(argv)
    if args.budget_s < 1:
        parser.error("--budget-s must be a positive number of seconds")
    bundle, out = args.scene.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    result = {"schema": "rooms3.step-check.v1", "scene": bundle.name, "status": "error", "stage": "inputs",
              "budget_s": args.budget_s}
    def timeout(_sig, _frame):
        raise TimeoutError(f"{args.budget_s} s step-check budget")
    cwd = Path.cwd()
    old = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(args.budget_s)
    rc = 2
    try:
        scene = json.loads((bundle / "map.json").read_bytes())
        result.update(seed=scene["source"]["seed"], xml_sha256=hashlib.sha256((bundle / "scene.xml").read_bytes()).hexdigest())
        configure(bundle, out)
        os.chdir(out)
        rc = run(bundle, out, scene, result, args.approach_only)
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
        os.chdir(cwd)
        (out / "check.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(result["status"], result.get("reason", result["stage"]))
    return rc


if __name__ == "__main__":
    sys.exit(main())
