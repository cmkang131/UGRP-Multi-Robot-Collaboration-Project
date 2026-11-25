"""Build-time checks in the derived image, using the same interpreter and imports as the trial."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parent
    layer = json.loads((root / "layer.json").read_bytes())
    for name, expected in layer["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"layer hash mismatch: {name}")
    if (root / "exec/DEPLOYED_COMMIT").read_text().strip() != layer["base_exec"]:
        raise ValueError("unexpected baked executor")
    model = Path(os.environ["HANDOVER_ACT_MODEL"])
    if not (root / "handover/runtime/act").samefile(model):
        raise ValueError("default ACT path differs from worker model")
    scene = Path(os.environ["HANDOVER_SCENE_ROOT"]) / "sim"
    for name in ("masterpi_scene.xml", "assets/masterpi_drive_friction_v2/fuji_roller.stl",
                 "assets/masterpi_drive_friction_v2/source.json"):
        if not (scene / name).is_file():
            raise FileNotFoundError(scene / name)
    for program in ("tar", "zstd", "curl"):
        if not shutil.which(program):
            raise FileNotFoundError(program)
    from worker import parent_worker
    parent = parent_worker()
    if not callable(parent.make_tar) or not callable(parent.gcs_upload):
        raise ValueError("parent worker lacks archive/upload helpers")

    from handover import layout, run_trial
    sys.addaudithook(run_trial.offline)
    trials = layout.trials()
    if set(trials) != set(range(1, 13)):
        raise ValueError("expected the twelve preselected trials")
    # Each World also checks the two robot trees and zero welds on its actual compiled model.
    for number in (2, 1):
        subprocess.run([sys.executable, "-B", str(root / "handover/check_donor_view.py"), str(number)], check=True)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        scene_map = folder / "map.json"
        scene_map.write_text(json.dumps(layout.map_config(trials[1])))
        # robot_tags_v1 and overhead_v1 read the map at import time.
        os.environ["UGRP_MAP_SCENE"] = str(scene_map)
        import sim
        sim.__path__.insert(0, str(scene))
        import cv2
        import torch
        from harness import overhead_v1 as overhead
        from harness.grasp_act_policy import GraspActor
        from scripts.handover_card_check import check_centre_card
        cv2.setNumThreads(1)
        torch.set_num_threads(1)
        check_centre_card(overhead)
        GraspActor.load(model, device="cpu")
    print(f"hand-over image check OK: {layer['exec_commit']}")


if __name__ == "__main__":
    main()
