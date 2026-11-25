"""Select the frozen simulator assets before importing the native controller modules."""
import os
from pathlib import Path
import sys

from rooms3.maps import ROOT


def configure(bundle, out):
    from handover.run_trial import offline

    sys.addaudithook(offline)
    os.environ.update(UGRP_MAP_SCENE=str(bundle / "map.json"), XDG_CACHE_HOME=str(out),
                      TMPDIR=str(out), MESA_SHADER_CACHE_DISABLE="true", HF_HUB_OFFLINE="1",
                      TRANSFORMERS_OFFLINE="1")
    os.environ.setdefault("MUJOCO_GL", "osmesa")
    os.environ.setdefault("PYOPENGL_PLATFORM", os.environ["MUJOCO_GL"])
    sys.path.insert(0, str(ROOT / "exec"))
    import sim
    native = Path(os.environ.get("HANDOVER_SCENE_ROOT", ROOT / "exec-repo")) / "sim"
    if not (native / "masterpi_scene.xml").is_file():
        raise FileNotFoundError(native / "masterpi_scene.xml")
    sim.__path__.insert(0, str(native))


def calibration_file():
    bundled = Path(__file__).with_name("masterpi_dynamics_calibration.json")
    return bundled if bundled.is_file() else ROOT / "exec-repo/sim/masterpi_dynamics_calibration.json"
