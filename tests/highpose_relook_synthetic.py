"""Synthetic closed loop of the v98 pair runtime at the dock (simulator-free; test-only).

The real v98 ``Runtime`` (both actors, ``HighPoseSource`` + PF with the measured dev-pilot camera models, the
0.16 s pose delay, frame gate, look-around guard, admission, ``PairTeam``) is driven at the pair tick (0.05 s).
Only the OpenCV wall detector is replaced: each own frame's column observation is the provider's own expected
bottom/top edge rows at the robot's ASSUMED TRUE dock pose for the servo pulses of that frame, plus a residual
model from the calibration split of the r2 accuracy note (per view a common offset, sd ``C`` px, and per column
sd ``S`` px; seeded). The image bytes are one recorded own floor frame (frame gate only).

The true pose is a test assumption that never enters the controller: it only generates observations. Bases are
assumed not to move; any base command before both robots are admitted is a test failure (``BaseMoved``).
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import numpy as np

from harness import zone_pair_highpose_contract as contract
from harness.zone_final_pair_contract import ROBOTS, TICK_S

ROOT = Path(__file__).resolve().parents[1]
# The admitted DEV calibration of the v98 probes (measured camera models); its sibling dev input manifest
# (1.9 MB) stays in outputs/, so tests re-root the provenance on a small test manifest and admit that copy
# through the documented ``dev_pilot_admission`` monkeypatch. Camera models and params are byte-identical.
CALIBRATION = ROOT/'experiments'/'2026-10-03-v92-dev-pilot'/'calibration_dev_pilot.json'
CALIBRATION_SHA256 = '398372ae6b9b0fef7344d7f29146ce75b309d334b3ce31af527bc071c0e582f5'
IMAGE = Path(__file__).resolve().parent/'fixtures'/'highpose_blind_close'/'r1_1011_standoff.jpg'
DOCK_X = -.8982
TRUE_DOCK = {'r1': (DOCK_X, .55, 0.), 'r2': (DOCK_X, -.85, 0.)}       # recorded probes: r1 row 0.55, r2 row -0.85
LOOK_POSE = {1: 2000, 3: 1072, 4: 2400, 5: 1482, 6: 1500}
MAP_ID = 'zone_wide_door_geometry_v3'


class BaseMoved(AssertionError):
    pass


def _obs(rid, frame_id, t, servo, jpeg):
    return {'robot_id': rid, 'frame_id': frame_id, 'sim_time': t, 'image': base64.b64encode(jpeg).decode(),
            'sha256': hashlib.sha256(jpeg).hexdigest(), 'camera': 'robot_cam',
            'actuator_state': {'motor_commands': [0., 0., 0., 0.], 'servo_pulses': {str(k): v for k, v in servo.items()}}}


def synthetic_observe(src, true_pose, rng, C, S):
    """Replace ``src.worker.observe`` (OpenCV wall detector) by expected rows at ``true_pose`` + residuals."""
    from harness import vision_loc_protocol as vp
    vl, _ = vp.load_vis3()
    pf = src.loc._pf
    true = np.asarray(true_pose, float)[None]
    state = {'key': None, 'noise': None}

    def observe(_bgr):
        servo = dict(src.servo)
        b, t = pf.expected(true, servo)
        b, t = b[0], t[0]
        key = tuple(sorted(servo.items()))
        if key != state['key']:                   # a new view: new common offset and column residuals
            c = rng.normal()*C
            state['key'], state['noise'] = key, (c + rng.normal(size=b.size)*S, c + rng.normal(size=b.size)*S)
        nb, nt = state['noise']
        okb = np.isfinite(b) & (b >= 0) & (b <= 479)
        okt = okb & np.isfinite(t) & (t >= 0)
        bo = np.where(okb, b + nb, np.nan)
        to = np.where(okt, t + nt, np.nan)
        return vl.ColumnObs(np.asarray(pf.columns), np.where(okb, vl.EDGE, vl.NONE), bo, bo.copy(),
                            np.where(okt, vl.EDGE, vl.NONE), to, to.copy())

    src.worker.observe = observe


def admitted_copy(tmp_path, monkeypatch):
    """A copy of the DEV calibration whose provenance points at a test manifest; admitted by monkeypatch only."""
    import copy as _copy
    assert contract.base.sha(CALIBRATION) == CALIBRATION_SHA256
    cal = json.loads(CALIBRATION.read_text())
    manifest = {'schema': 'ugrp.v92_dev_pilot_inputs.v1', 'execution_source_sha': cal['source_sha'],
                'working_tree_dirty': False, 'script_sha256': '0'*64,
                'qualification': 'test-only re-rooted provenance of experiments/2026-10-03-v92-dev-pilot/'
                                 'calibration_dev_pilot.json (sha256 ' + CALIBRATION_SHA256 + ')'}
    (tmp_path/'input_manifest_dev.json').write_text(json.dumps(manifest))
    cal['dev_manifest_sha256'] = contract.base.sha(tmp_path/'input_manifest_dev.json')
    path = tmp_path/'calibration_dev_pilot.json'
    path.write_text(json.dumps(cal))
    sha = contract.base.sha(path)
    admission = _copy.deepcopy(contract.dev_pilot_admission())
    admission['admitted_calibration_sha256'] = [*admission['admitted_calibration_sha256'], sha]
    monkeypatch.setattr(contract, 'dev_pilot_admission', lambda: admission)
    return path, sha


def build(calibration, seed=0, *, C=.3, S=.7, true=None):
    from harness.zone_pair_highpose_runtime import Runtime
    static = contract.resolve(MAP_ID)[0]
    path, sha = calibration
    runtime = Runtime(static, str(path), sha, seed=seed)
    rng = np.random.default_rng(1000 + seed)
    for rid in ROBOTS:
        synthetic_observe(runtime.providers[rid].provider, (true or TRUE_DOCK)[rid], rng, C, S)
    return runtime


def run(runtime, *, until_s=60., stop=None):
    """Drive the runtime like ``scripts/run_pair_highpose.py`` (frames, step, arm_step) at the 0.05 s tick."""
    import cv2
    jpeg = IMAGE.read_bytes()
    rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    servo = {rid: dict(LOOK_POSE) for rid in ROBOTS}
    runtime.initial_commands(0., {rid: dict(LOOK_POSE) for rid in ROBOTS})
    issued_log, fid, now = [], {rid: 0 for rid in ROBOTS}, 0.
    steps = round(until_s/TICK_S)
    for i in range(steps + 1):
        now = round(i*TICK_S, 6)
        frames = {}
        for rid in ROBOTS:
            fid[rid] += 1
            o = _obs(rid, fid[rid], now, servo[rid], jpeg)
            frames[rid] = (o, rgb)
        runtime.on_frames(now, frames)
        if i == steps:
            break
        for rid, action in list(runtime.step(now)) + list(runtime.arm_step(now)):
            kind = action.get('kind')
            if kind == 'arm':
                servo[rid][int(action['servo_id'])] = int(action['pulse'])
            elif kind == 'look':
                servo[rid][6] = int(action['pan_pulse'])
            elif kind not in ('hold',) and len(runtime.submitted) < len(ROBOTS):
                raise BaseMoved(f'{rid} issued {action} before both robots were admitted at {now}')
            issued_log.append((now, rid, json.loads(json.dumps(action))))
            runtime.on_command(rid, now, action)
        if stop is not None and stop(runtime, now):
            break
    return {'t_end': now, 'issued': issued_log}


def admitted(runtime, now):
    return set(runtime.submitted) == set(ROBOTS)
