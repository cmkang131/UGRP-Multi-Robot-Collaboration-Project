"""Run one preselected local two-room trial. All inputs are files, including the ACT checkpoint."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
import traceback

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "exec"))
from handover import layout
from handover.records import Recorder, StopTrial, write_json


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trial", required=True, type=int, choices=range(1, 13), metavar="1..12")
    p.add_argument("--trial-table", choices=layout.TRIAL_TABLES, default=layout.TABLE.name)
    p.add_argument("--station-tilt", choices=layout.STATION_TILT_MODES, default="strict",
                   help="allow a tilted, gripped box to start placement with 'ignore'")
    p.add_argument("--out", required=True, type=Path, help="new directory, created exclusively")
    p.add_argument("--wall-seconds", type=int, default=1080, help="local wall budget including initialization")
    return p


def offline(event, args):
    if event == "socket.__new__" and args[1] in (socket.AF_INET, socket.AF_INET6):
        raise PermissionError("hand-over trials use local files and in-process controllers")


def run(trial, out, wall_seconds, *, station_tilt="strict"):
    start = time.monotonic()
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "trial.json", trial)
    write_json(out / "map.json", layout.map_config(trial))
    tmp = out / "scratch"
    tmp.mkdir()
    native = Path(os.environ.get("HANDOVER_SCENE_ROOT", BASE / "handover/runtime/scene")).resolve()
    model = Path(os.environ.get("HANDOVER_ACT_MODEL", BASE / "handover/runtime/act")).resolve()
    os.environ.update(TMPDIR=str(tmp), XDG_CACHE_HOME=str(tmp), HF_HUB_OFFLINE="1",
                      TRANSFORMERS_OFFLINE="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                      MKL_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", MESA_SHADER_CACHE_DISABLE="true",
                      UGRP_MAP_SCENE=str(out / "map.json"))
    os.environ.setdefault("MUJOCO_GL", "egl")
    sys.addaudithook(offline)
    alarm_stage = "setup"
    def timeout(_sig, _frame):
        raise StopTrial("wall_timeout", f"{wall_seconds} s wall budget during {alarm_stage}")

    with ExitStack() as stack:
        # Native warnings and temporary compiler/render files also belong to this invocation.
        stack.callback(os.chdir, Path.cwd())
        os.chdir(tmp)
        record = Recorder(out, trial, stack)
        record.event("start", trial=trial["trial"], seed=trial["seed"])
        old = signal.signal(signal.SIGALRM, timeout)
        signal.setitimer(signal.ITIMER_REAL, max(.01, wall_seconds-(time.monotonic()-start)))
        world = policy = None
        dt = None
        stage, reason, status = "setup", "", "error"
        try:
            use_staged = "HANDOVER_SCENE_ROOT" in os.environ or (native / "sim").is_dir()
            sim_dir = native / "sim" if use_staged else BASE / "exec/sim"
            missing = [p for p in ("mujoco", "cv2", "numpy", "torch", "lerobot", "safetensors", "draccus")
                       if importlib.util.find_spec(p) is None]
            files = [sim_dir/"masterpi_scene.xml", sim_dir/"assets/masterpi_drive_friction_v2/fuji_roller.stl",
                     sim_dir/"assets/masterpi_drive_friction_v2/source.json",
                     *[model / name for name in ("SHA256.json", "model.safetensors", "adapter.json", "config.json")]]
            missing.extend(str(path) for path in files if not path.is_file())
            if missing:
                raise RuntimeError("missing local runtime inputs: " + ", ".join(missing))
            import sim
            sim.__path__.insert(0, str(sim_dir))
            import cv2
            import torch
            from harness.grasp_act_policy import GraspActor
            from harness.handover_policy import Policy
            from scripts.handover_world import World
            cv2.setNumThreads(1)
            torch.set_num_threads(1)
            torch.manual_seed(trial["seed"])
            actor = GraspActor.load(model, device="cpu")
            inventory = (model/"SHA256.json").read_bytes()
            record.event("checkpoint", inventory_sha256=hashlib.sha256(inventory).hexdigest(),
                         model_sha256=json.loads(inventory)["model.safetensors"],
                         directory=str(model), scene_root=str(sim_dir), backend="local_cpu_act")
            world = World(trial, record, stack)
            dt = world.dt
            policy = Policy(world, actor, station_tilt=station_tilt)
            alarm_stage = "script"
            policy.run()
            stage, status = "complete", "finished"
            record.event("complete", pose=world.witness())
        except StopTrial as exc:
            stage, reason, status = exc.stage, str(exc), "failed"
            if stage == "wall_timeout":
                stage = policy.stage if policy else "setup"
                reason += " (" + stage + ")"
            record.event("failure", stage=stage, reason=reason)
        except Exception as exc:
            stage = policy.stage if policy is not None else "setup"
            reason = f"{type(exc).__name__}: {exc}"
            record.event("error", stage=stage, reason=reason)
            with (out / "error.txt").open("x") as stream:
                traceback.print_exc(file=stream)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
            if world is not None:
                world.stop()
            record.flush()
            summary = {"schema": "handover.run.v1", "trial": trial["trial"], "status": status, "stage": stage,
                       "reason": reason, "sim_s": record.now, "wall_s": time.monotonic()-start,
                       "dt": dt, "last_step": record.step, "wall_budget_s": wall_seconds, "station_tilt": station_tilt}
            write_json(out / "run.json", summary)
    print(f"trial {trial['trial']:02d}  {status}  {stage}  sim {record.now:.2f} s  wall {summary['wall_s']:.2f} s")
    if reason:
        print(reason, file=sys.stderr)
    return {"finished": 0, "failed": 1, "error": 2}[status]


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if not 0 < args.wall_seconds < 1200:
        p.error("--wall-seconds must be between 1 and 1199")
    try:
        return run(layout.trials(args.trial_table)[args.trial], args.out, args.wall_seconds,
                   station_tilt=args.station_tilt)
    except FileExistsError:
        p.error("output already exists: " + str(args.out))


if __name__ == "__main__":
    sys.exit(main())
