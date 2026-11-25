"""Run the image's two wrist-camera checks when the native scene and renderer are available."""
from importlib.util import find_spec
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCENE = Path(os.environ.get("HANDOVER_SCENE_ROOT", ROOT / "handover/runtime/scene")) / "sim"


class DonorView(unittest.TestCase):
    @unittest.skipUnless(find_spec("mujoco") and find_spec("cv2")
                         and any((p / "masterpi_scene.xml").is_file() for p in (SCENE, ROOT / "exec/sim")),
                         "native MuJoCo, OpenCV and MasterPi scene required")
    def test_blue_and_red_donors_select_the_physical_box(self):
        for trial in (2, 1):
            with self.subTest(trial=trial):
                subprocess.run([sys.executable, "-B", str(ROOT / "handover/check_donor_view.py"), str(trial)],
                               check=True)
