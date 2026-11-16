"""Shared, torch-free helpers of the carry-relocalization B1 measurement.

Reuses the VIS3 tag-free localizer unchanged (`experiments/2026-09-26-vision-loc/`): the frozen student config
(`selected_config_v3.json`, filter a1 = open interval ends, round-3 `robust` block empty), the TRAIN calibration
(`calibration_train.json`), the M1 particle filter loaded byte-for-byte from its commit, and the segmentation
checkpoint `seg-v2` (never retrained here). Nothing in this module reads `eval_only` fields except where a function
says so.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VL = ROOT / 'experiments' / '2026-09-26-vision-loc'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(VL))

import numpy as np  # noqa: E402

PRIMARY_OUT = Path('/Users/changmin/projects/ugrp/outputs/carry-relocalization-b1-20260929')
CHECKPOINT = Path('/Users/changmin/projects/ugrp/outputs/vision-loc-20260926/model/seg-v2/seg_lraspp_mbv3.pt')
CHECKPOINT_SHA256 = '348539030fda962cc5ba64e21c956619bc4db9321a99cd3ae6746611a9939fd9'
MAP_FILE = ROOT / 'maps' / 'zones' / 'zone_wide_door_geometry_v2.json'           # final environment map (walls_v3, no tags)
TRAIN_MAP_FILE = VL / 'maps' / 'zone_wide_door_walls_v3_notags.json'              # the map the VIS3 model was trained on
CONFIG_FILE = VL / 'selected_config_v3.json'
CALIBRATION_FILE = VL / 'calibration_train.json'
# PREGRASP_PANS_V2 of scripts/run_m2_pair.py: the frames the checkpoint sweep takes (the last repeats the first).
SWEEP_PANS = (1500, 1230, 970, 700, 1770, 2030, 2300, 1500)
# DOCK_STD of vision_loc_cli.py: the prior spread the VIS3 student starts with (x, y, yaw).
PRIOR_WIDE = (0.15, 0.15, math.radians(10.))
# Carry gate GATE_LOADED of harness/zone_own_guards.py (sigma_xy 0.07 m, sigma_yaw 3 deg) as a tight prior.
PRIOR_TIGHT = (0.07, 0.07, math.radians(3.))


def sha_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wrap(a):
    return (np.asarray(a) + math.pi) % (2 * math.pi) - math.pi


def load_json(path):
    return json.loads(Path(path).read_text())


def check_map_equivalence() -> dict:
    """The final-environment map and the map the VIS3 model was trained on: same geometry, different bookkeeping."""
    a, b = load_json(MAP_FILE), load_json(TRAIN_MAP_FILE)
    keys = ('bounds_m', 'obstacles', 'passages', 'regions', 'zone_slots', 'terrain', 'top_cameras', 'wall_profile')
    same = {k: a.get(k) == b.get(k) for k in keys}
    return {'final_map': str(MAP_FILE.relative_to(ROOT)), 'final_map_sha256': sha_file(MAP_FILE),
            'train_map': str(TRAIN_MAP_FILE.relative_to(ROOT)), 'train_map_sha256': sha_file(TRAIN_MAP_FILE),
            'geometry_keys_identical': same, 'all_identical': all(same.values()),
            'final_has_landmarks_key': 'landmarks' in a, 'train_landmark_tags': len(b.get('landmarks', {}).get('tags', []))}


class Context:
    """Frozen VIS3 student pieces (config, calibration, M1 filter module, map)."""

    def __init__(self):
        import vision_loc as vl
        self.vl = vl
        self.mp = vl.mp
        self.cfg = load_json(CONFIG_FILE)
        self.cal = load_json(CALIBRATION_FILE)
        # The final map has no landmark block at all; the M1 filter code only needs the (empty) list to run, exactly as in
        # the map the VIS3 model was trained on (`landmarks.tags == []`). Added in memory only; no tag exists anywhere.
        self.static = {**load_json(MAP_FILE), 'landmarks': {'tags': []}}
        self.m1 = self.mp.load_m1_localizer()
        m1_cal, self.m1_prov = self.mp.load_m1_calibration()
        self.params = m1_cal['params']
        self.obs_params = {**vl.DEFAULT_OBS, **self.cfg.get('obs', {})}
        self.infer_size = tuple(self.cfg.get('infer_size', (320, 240)))
        self.columns = vl.column_positions(int(self.obs_params['columns']), int(self.obs_params['strip_half_px']))

    def make_pf(self, seed: int):
        import vision_pf
        return vision_pf.make_robust_pf(self.m1, self.static, self.params, self.cfg.get('measurement', {}),
                                        self.cfg.get('obs', {}), self.cal['sag'], int(seed),
                                        self.cal.get('pan_base_yaw') if self.cfg.get('pan_coupling', True) else None,
                                        self.cfg.get('robust', {}))

    def provenance(self) -> dict:
        return {'map': check_map_equivalence(), 'config': {'path': str(CONFIG_FILE.relative_to(ROOT)), 'sha256': sha_file(CONFIG_FILE), 'value': self.cfg},
                'calibration': {'path': str(CALIBRATION_FILE.relative_to(ROOT)), 'sha256': sha_file(CALIBRATION_FILE)},
                'checkpoint': {'path': str(CHECKPOINT), 'sha256': CHECKPOINT_SHA256},
                'm1_localizer': {'source': f'{self.mp.M1_SHA}:{self.mp.M1_LOCALIZER}', 'sha256': self.mp.M1_LOCALIZER_SHA256},
                'm1_calibration': self.m1_prov,
                'module_sha256': {f: sha_file(VL / f) for f in ('vision_loc.py', 'vision_pf.py', 'seg_model.py')}}


def true_pose(row: dict) -> tuple[float, float, float]:
    """EVAL ONLY: the rendered base pose of a frame row."""
    x, y, yaw = row['eval_only']['base_gt']
    return float(x), float(y), float(yaw)


def offsets(cell: str, n: int, seed: int) -> np.ndarray:
    """Start-error draws (dx, dy, dyaw) in world axes / rad for one error cell, deterministic in (cell, n, seed).

    S: dx, dy ~ U(-0.05, 0.05) m, dyaw ~ U(-3, 3) deg          (task: position +-5 cm, heading +-3 deg)
    Y: dy = +-0.05 m alternating, dx = dyaw = 0                 (order-sheet rounding in y)
    L: dx, dy ~ U(-0.10, 0.10) m, dyaw ~ U(-6, 6) deg           (stress: twice S)
    """
    rng = np.random.default_rng(seed)
    if cell == 'S':
        return np.column_stack([rng.uniform(-.05, .05, n), rng.uniform(-.05, .05, n), np.radians(rng.uniform(-3., 3., n))])
    if cell == 'Y':
        sgn = np.where(np.arange(n) % 2 == 0, 1., -1.)
        return np.column_stack([np.zeros(n), .05*sgn, np.zeros(n)])
    if cell == 'L':
        return np.column_stack([rng.uniform(-.10, .10, n), rng.uniform(-.10, .10, n), np.radians(rng.uniform(-6., 6., n))])
    raise ValueError(cell)


def pctl(a, q):
    a = np.asarray(a, float)
    return float('nan') if a.size == 0 else float(np.percentile(a, q))
