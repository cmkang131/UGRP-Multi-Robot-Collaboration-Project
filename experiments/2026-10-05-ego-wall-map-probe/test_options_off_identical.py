"""Every #405 change is an explicit option and its default is the behaviour before #405. Refs #216.

Standalone: ``python test_options_off_identical.py`` (the golden test needs the local recordings and takes ~30 s;
it skips itself when they are absent; set ``UGRP_OUTPUTS`` to the outputs directory of the main checkout).

Options and defaults (README, "Options"): ``load_rule`` = ``s3`` (``gripper`` is the fix),
``floor_patch_max_m`` = 0 (``FLOOR_PATCH_DIAGONAL_M`` is the fix), ``clamp_horizon`` = False,
``run_step_window`` = 1. ``--gt-camera true|model`` is scoring only and is the one exception: ``model`` is the
earlier ground truth.

What is pinned:
  * the detector with default parameters equals the detector with every option passed explicitly at its off
    value, on synthetic scenes (wall and bare floor);
  * ``recorded_params()`` leaves the options out while they are off (a run records what it recorded before) and
    lists them when on;
  * the full scorer, run with only ``--gt-camera model``, reproduces the previous session's ``harness-full/``
    byte for byte: ``segments.jsonl`` identical, ``per_frame.csv`` cell for cell on its old columns (columns the
    scorer added since are evaluation only), ``summary.json`` on its old keys.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE / 'code'))
import height_free_wall as hfw  # noqa: E402
import wall_probe as wp  # noqa: E402
from test_floor_patch_extent import POSE_508, POSE_740  # noqa: E402

OUTPUTS = Path(os.environ.get('UGRP_OUTPUTS', '/Users/changmin/projects/ugrp/outputs'))
GOLDEN = OUTPUTS / 'ego-wall-map-probe' / 'harness-full'
EPISODE = OUTPUTS / 'v98-dev-align_to_carry-a3415342-s911-wtA' / 'zone_wide_door_geometry_v3'


def same(a, b, path='') -> list[str]:
    """Differences between two nested structures of arrays, lists, dicts and scalars (exact equality)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = [f'{path}: keys {sorted(a)} != {sorted(b)}'] if set(a) != set(b) else []
        for k in a.keys() & b.keys():
            out += same(a[k], b[k], f'{path}.{k}')
        return out
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return [f'{path}: len {len(a)} != {len(b)}']
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in same(x, y, f'{path}[{i}]')]
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return [] if np.array_equal(np.asarray(a), np.asarray(b), equal_nan=True) else [f'{path}: arrays differ']
    return [] if (a == b or (a != a and b != b)) else [f'{path}: {a!r} != {b!r}']


class DetectorOffStateTest(unittest.TestCase):
    def test_option_defaults_are_the_off_values(self):
        for k, off in hfw.OPTION_PARAMS_OFF.items():
            self.assertEqual(hfw.PARAMS[k], off, k)

    def test_default_detector_equals_every_option_passed_off(self):
        off = dict(hfw.OPTION_PARAMS_OFF)
        for name, scene, plane in (('740 wall', POSE_740, 1.9), ('740 floor', POSE_740, None),
                                   ('508 wall', POSE_508, 1.5), ('508 floor', POSE_508, None)):
            img, _ = scene.render(plane_x=plane)
            top = np.full(len(scene.cols), img.shape[0], int)
            a = hfw.detect(img, scene.cm, self_top=top, loaded=False)
            b = hfw.detect(img, scene.cm, params=off, self_top=top, loaded=False)
            self.assertEqual(same(a, b), [], name)
            self.assertEqual(same(hfw.link_segments(a, {}), hfw.link_segments(b, off)), [], name)

    def test_each_option_on_changes_the_output(self):
        # not vacuous: the floor-patch option does change a scene that has the horizon above the image
        img, _ = POSE_740.render(plane_x=1.9)
        top = np.full(len(POSE_740.cols), img.shape[0], int)
        a = hfw.detect(img, POSE_740.cm, self_top=top, loaded=False)
        on = hfw.detect(img, POSE_740.cm, params={'floor_patch_max_m': hfw.FLOOR_PATCH_DIAGONAL_M}, self_top=top, loaded=False)
        self.assertNotEqual(same(a, on), [])

    def test_recorded_params_hides_options_that_are_off(self):
        rec = hfw.recorded_params()
        for k in hfw.OPTION_PARAMS_OFF:
            self.assertNotIn(k, rec)
        self.assertEqual(rec, {k: v for k, v in hfw.PARAMS.items() if k not in hfw.OPTION_PARAMS_OFF})
        self.assertEqual(hfw.recorded_params({'floor_patch_max_m': 0.}), rec, 'an explicit off value is still off')
        on = hfw.recorded_params({'floor_patch_max_m': 0.81, 'run_step_window': 3, 'clamp_horizon': True})
        self.assertEqual((on['floor_patch_max_m'], on['run_step_window'], on['clamp_horizon']), (0.81, 3, True))


@unittest.skipUnless(GOLDEN.is_dir() and EPISODE.is_dir(), 'local recordings (harness-full golden, v98 dev episode) not present')
class ScorerOffStateGoldenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / 'run'
        cmd = [sys.executable, '-I', str(HERE / 'code' / 'score_harness.py'), '--episode', str(EPISODE), '--robot', 'r1',
               '--output', str(cls.out), '--every', '2', '--gt-camera', 'model']      # every other option at its default
        cls.proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_run_succeeded(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-2000:])

    def test_segments_are_byte_identical(self):
        self.assertEqual((self.out / 'segments.jsonl').read_bytes(), (GOLDEN / 'segments.jsonl').read_bytes())

    def test_per_frame_csv_old_columns_identical(self):
        old = list(csv.DictReader((GOLDEN / 'per_frame.csv').read_text().splitlines()))
        new = list(csv.DictReader((self.out / 'per_frame.csv').read_text().splitlines()))
        self.assertEqual(len(old), len(new))
        cols = list(old[0])
        self.assertEqual([c for c in new[0] if c in cols], cols, 'old columns keep their order')
        bad = [(i, c) for i, (a, b) in enumerate(zip(old, new)) for c in cols if a[c] != b[c]]
        self.assertEqual(bad[:5], [])

    def test_summary_old_keys_identical(self):
        old = json.loads((GOLDEN / 'summary.json').read_text())
        new = json.loads((self.out / 'summary.json').read_text())

        def old_keys(o, n, path=''):
            if isinstance(o, dict):
                return [d for k in o for d in (old_keys(o[k], n[k], f'{path}.{k}') if isinstance(n, dict) and k in n else [f'{path}.{k} missing'])]
            return [] if o == n else [f'{path}: {o!r} != {n!r}']
        self.assertEqual(old_keys(old, new), [])
        self.assertNotIn('floor_patch_max_m', new['height_free_params'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
