"""Own-image gate values calibrated for the floor_light_v1 render profile.

One file, configs/calibration/own_image_gates_floor_light_v1.json, holds every own-image threshold that was
tuned on a render profile, with the rule and the data that produced it. ``load`` returns the values and the
file sha256; the provider writes both into its runtime contract, so a run identifies the gate values it used.
``LEGACY`` are the values hard-coded before 2026-10-03 (older bundles keep them). Procedure and acceptance
rules: docs/own_image_gate_calibration.md.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = 'configs/calibration/own_image_gates_floor_light_v1.json'
SCHEMA = 'ugrp.own_image_gates.v1'
LEGACY = {'wall_band_saturation_max': 80, 'wall_edge_step_min': 0.,
          'frame_contrast_spread_min': 15., 'frame_value_std_min': 3.}


def load(path=None, expected_sha256=None):
    """Return {'path', 'sha256', 'values'}; fail closed on a hash, schema, profile or key mismatch."""
    path = Path(path) if path is not None else ROOT/PATH
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError('own-image gates hash mismatch')
    doc = json.loads(raw)
    if (doc.get('schema') != SCHEMA or doc.get('render_profile') != 'floor_light_v1'
            or set(doc.get('values', {})) != set(LEGACY)):
        raise ValueError('own-image gates schema/profile/keys mismatch')
    values = {key: float(doc['values'][key]) for key in LEGACY}
    if not all(v >= 0. for v in values.values()):
        raise ValueError('own-image gates must be non-negative')
    return {'path': str(Path(PATH)), 'sha256': digest, 'values': values}
