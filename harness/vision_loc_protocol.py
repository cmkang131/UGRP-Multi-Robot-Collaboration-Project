"""Versioned contract of the tag-free vision pose provider ``vision_zero_tag_v1`` (issue #216).

One place for everything the sim side (``harness.vision_pose_source``, no torch) and the torch
worker (``scripts/vision_loc_worker.py``, the existing ACT environment) must agree on:

* the pinned VIS3 runtime (PR #233): ``vision_loc.py`` / ``vision_pf.py`` / ``seg_model.py``,
  the selected config, the TRAIN camera calibration, the M1 PF, all loaded by path and
  sha256-checked against ``experiments/2026-09-26-vision-loc/prereg_v3.json`` (the scored student);
* the JSON-lines worker protocol (schema, closed request/reply keys, validation);
* the worker configuration file ``configs/vision_loc_worker.json``.

Robot inputs only: the request carries exactly one own wrist RGB frame. The reply carries the
per-column interval observations of that frame (``vision_loc.ColumnObs``), nothing else.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import math
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIS3_DIR = ROOT / 'experiments' / '2026-09-26-vision-loc'
CONFIG_FILE = ROOT / 'configs' / 'vision_loc_worker.json'
PROVIDER_PIN_FILE = ROOT / 'configs' / 'vision_loc_provider_p03.json'
CONFIG_SCHEMA = 'ugrp.vision_loc_worker_config.v1'
SCHEMA = 'ugrp.vision_loc_worker.v1'
PROVIDER_ID = 'vision_zero_tag_v1'
# m1_contract / m1_owncam_contract allow-list: own-camera estimators start with 'owncam_pf'.
SOURCE_LABEL_PREFIX = 'owncam_pf_vision_zero_tag_v1'
WIDTH, HEIGHT = 640, 480
FRAME_BYTES = WIDTH * HEIGHT * 3
REQUEST_KEYS = frozenset({'schema', 'seq', 'bgr_b64', 'bgr_sha256'})
REPLY_KEYS = frozenset({'schema', 'seq', 'bgr_sha256', 'obs', 'obs_sha256', 'infer_ms'})
REJECT_KEYS = frozenset({'schema', 'seq', 'bgr_sha256', 'rejected'})
READY_KEYS = frozenset({'schema', 'ready', 'runtime_inputs', 'checkpoint_sha256', 'config_sha256', 'obs_params',
                        'columns', 'device', 'torch_threads', 'deterministic', 'versions'})
OBS_KEYS = ('b_kind', 'b_lo', 'b_hi', 't_kind', 't_lo', 't_hi')
# VIS3 files the provider runs (prereg_v3.json ``student.frozen_files_sha256`` + model/config/calibration).
FROZEN_FILES = ('vision_loc.py', 'vision_pf.py', 'seg_model.py', 'calibration_train.json',
                'maps/zone_wide_door_walls_v3_notags.json', '../2026-09-26-markerless-probe/markerless_probe.py')


class ProtocolError(ValueError):
    """A request, reply, configuration or pinned file that breaks the contract."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def load_json(path):
    return json.loads(Path(path).read_text())


# ----------------------------------------------------------------------------- pinned VIS3 runtime
def prereg_student() -> dict:
    return json.loads((VIS3_DIR / 'prereg_v3.json').read_text())['student']


def check_frozen() -> dict:
    """sha256 of every pinned VIS3 file; raises unless each equals the registered (scored) student."""
    student = prereg_student()
    want = dict(student['frozen_files_sha256'])
    want['selected_config_v3.json'] = student['config']['sha256']
    got = {}
    for rel in FROZEN_FILES + ('selected_config_v3.json',):
        got[rel] = file_sha256(VIS3_DIR / rel)
        if got[rel] != want[rel]:
            raise ProtocolError(f'{rel}: sha256 {got[rel]} differs from the registered VIS3 student {want[rel]}')
    return got


def load_vis3():
    """(vision_loc, vision_pf) modules of PR #233, loaded by path after the hash check (never forked)."""
    check_frozen()
    if str(VIS3_DIR) not in sys.path:
        sys.path.insert(0, str(VIS3_DIR))
    mods = []
    for name in ('vision_loc', 'vision_pf'):
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, VIS3_DIR / f'{name}.py')
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        mods.append(sys.modules[name])
    return tuple(mods)


def selected_config() -> dict:
    return json.loads((VIS3_DIR / 'selected_config_v3.json').read_text())


def obs_params() -> dict:
    vl, _ = load_vis3()
    return {**vl.DEFAULT_OBS, **selected_config().get('obs', {})}


def columns():
    vl, _ = load_vis3()
    p = obs_params()
    return vl.column_positions(int(p['columns']), int(p['strip_half_px']))


# ----------------------------------------------------------------------------- worker configuration
def load_config(path=CONFIG_FILE) -> dict:
    cfg = json.loads(Path(path).read_text())
    need = {'schema', 'provider_id', 'python', 'model', 'device', 'torch_threads', 'startup_timeout_s',
            'frame_timeout_s', 'sim_time_charge'}
    if cfg.get('schema') != CONFIG_SCHEMA or cfg.get('provider_id') != PROVIDER_ID or not need <= set(cfg):
        raise ProtocolError(f'{path}: not a {CONFIG_SCHEMA} file for {PROVIDER_ID}')
    for key in ('startup_timeout_s', 'frame_timeout_s'):
        if not finite_positive(cfg[key]):
            raise ProtocolError(f'{path}: {key} must be a positive finite number')
    if cfg['device'] != 'cpu' or cfg['torch_threads'] != 1:
        raise ProtocolError('the SYNC SIM provider runs the network on CPU with one thread (determinism)')
    if cfg['sim_time_charge'].get('charged') is not False:
        raise ProtocolError('inference SIM-time charging is not part of the study design (record only)')
    return cfg


def finite_positive(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0


def provider_runtime_contract(*, map_id, calibration=None, cfg=None, root=ROOT) -> dict:
    """Read-only P03 combination pin; no model bytes are loaded or executed.

    The candidate C_mix_rgb is preparation only. It cannot be selected by a
    cfg override while retaining seg-v2 camera/robot validation labels.
    """
    root = Path(root)
    path = root / PROVIDER_PIN_FILE.relative_to(ROOT)
    pin = load_json(path)
    active = pin['active']
    if map_id not in active['map_ids'] or (calibration is not None and calibration != active['motion_calibration']):
        raise ProtocolError('P03 model/robot/render/camera combination is not pinned for this map/calibration')
    cfg = load_config() if cfg is None else cfg
    for key, value in active['model'].items():
        if cfg['model'].get(key) != value:
            raise ProtocolError(f'P03 model {key} differs from the active seg-v2 pin; C_mix_rgb is preparation only')
    hashes = {rel: file_sha256(root / rel) for rel in active['files_sha256']}
    if hashes != active['files_sha256']:
        raise ProtocolError('P03 pinned model/robot/render/camera source hash mismatch')
    registry = load_json(root / 'configs/model_artifacts.json')
    artifact = next((a for a in registry['artifacts'] if a['id'] == active['model']['artifact_id']), None)
    if artifact is None or artifact['status'] != 'available' or artifact['release']['tag'] != active['model']['release']:
        raise ProtocolError('active segmentation Release is missing from model_artifacts')
    entry = next((f for f in artifact['files'] if f['path'] == active['model']['entrypoint']), None)
    if entry is None or (entry['sha256'], entry['bytes']) != (active['model']['sha256'], active['model']['bytes']):
        raise ProtocolError('active segmentation Release file/hash differs from worker pin')
    from harness.zone_study_pose_delay import delay_contract
    return {'schema': pin['schema'], 'pin_file_sha256': file_sha256(path), 'active': active,
            'model_release_spec': artifact['release'], 'model_registry_entry_sha256': sha256_bytes(canonical(artifact)),
            'delay': delay_contract(cfg['sim_time_charge']), 'candidate_opt_in': pin['candidate_opt_in'],
            'verification': 'contract only; Release download/load and final calibration not verified in P03'}


# ----------------------------------------------------------------------------- requests
def encode_request(seq: int, bgr) -> tuple[str, str]:
    """(one JSON line, frame sha256): exactly one own 640x480 BGR uint8 frame (lossless, no re-encoding)."""
    data = check_frame(bgr).tobytes()
    digest = sha256_bytes(data)
    line = json.dumps({'schema': SCHEMA, 'seq': int(seq), 'bgr_b64': base64.b64encode(data).decode('ascii'),
                       'bgr_sha256': digest}) + '\n'
    return line, digest


def check_frame(bgr):
    """The frame as a C-contiguous (480, 640, 3) uint8 array; anything else raises ``ProtocolError``."""
    import numpy as np
    if not isinstance(bgr, np.ndarray) or bgr.dtype != np.uint8 or bgr.shape != (HEIGHT, WIDTH, 3):
        raise ProtocolError(f'own frame must be a ({HEIGHT}, {WIDTH}, 3) uint8 array, got '
                            f'{getattr(bgr, "shape", None)} {getattr(bgr, "dtype", type(bgr).__name__)}')
    return np.ascontiguousarray(bgr)


def decode_request(request) -> tuple[int, 'object', str]:
    """(seq, BGR array, sha256) of a worker request; closed keys, hash and size checked."""
    import numpy as np
    if not isinstance(request, Mapping) or set(request) != REQUEST_KEYS or request['schema'] != SCHEMA:
        raise ProtocolError('request keys must be exactly ' + ', '.join(sorted(REQUEST_KEYS)))
    seq = request['seq']
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
        raise ProtocolError(f'seq must be a non-negative integer, got {seq!r}')
    if not isinstance(request['bgr_b64'], str) or len(request['bgr_b64']) > 2 * FRAME_BYTES:
        raise ProtocolError('invalid frame payload')
    data = base64.b64decode(request['bgr_b64'], validate=True)
    if len(data) != FRAME_BYTES or sha256_bytes(data) != request['bgr_sha256']:
        raise ProtocolError('frame payload size or sha256 mismatch')
    return seq, np.frombuffer(data, np.uint8).reshape(HEIGHT, WIDTH, 3), request['bgr_sha256']


# ----------------------------------------------------------------------------- replies
def obs_reply(seq: int, bgr_sha256: str, obs_dict: Mapping, infer_ms: float) -> dict:
    obs = {k: list(obs_dict[k]) for k in OBS_KEYS}
    return {'schema': SCHEMA, 'seq': int(seq), 'bgr_sha256': bgr_sha256, 'obs': obs,
            'obs_sha256': sha256_bytes(canonical(obs)), 'infer_ms': round(float(infer_ms), 3)}


def check_ready(reply, cfg: Mapping) -> dict:
    """The worker's startup line must pin the configured checkpoint, config and deterministic CPU runtime."""
    if not isinstance(reply, Mapping) or set(reply) != READY_KEYS or reply['schema'] != SCHEMA \
            or reply['ready'] is not True or reply['runtime_inputs'] != ['own_bgr']:
        raise ProtocolError(f'invalid worker startup line: {str(reply)[:200]}')
    want = {'checkpoint_sha256': cfg['model']['sha256'], 'config_sha256': prereg_student()['config']['sha256'],
            'device': cfg['device'], 'torch_threads': cfg['torch_threads'], 'deterministic': True,
            'obs_params': obs_params(), 'columns': [int(c) for c in columns()]}
    for key, value in want.items():
        if reply[key] != value:
            raise ProtocolError(f'worker startup {key} {str(reply[key])[:80]} != {str(value)[:80]}')
    return dict(reply)


def check_reply(reply, *, seq: int, bgr_sha256: str, n_columns: int):
    """``('obs', ColumnObs, infer_ms)`` or ``('rejected', reason, None)``; any other reply raises."""
    import numpy as np
    vl, _ = load_vis3()
    if not isinstance(reply, Mapping) or reply.get('schema') != SCHEMA \
            or not isinstance(reply.get('seq'), int) or isinstance(reply.get('seq'), bool) or reply.get('seq') != seq \
            or reply.get('bgr_sha256') != bgr_sha256:
        raise ProtocolError(f'reply does not answer request {seq}: {str(reply)[:200]}')
    if set(reply) == REJECT_KEYS:
        if not isinstance(reply['rejected'], str) or not reply['rejected']:
            raise ProtocolError('rejected reply needs a reason')
        return 'rejected', reply['rejected'][:200], None
    if set(reply) != REPLY_KEYS:
        raise ProtocolError('reply keys must be exactly ' + ', '.join(sorted(REPLY_KEYS)))
    obs = reply['obs']
    if not isinstance(obs, Mapping) or set(obs) != set(OBS_KEYS):
        raise ProtocolError('reply observation keys mismatch')
    for key in OBS_KEYS:
        col = obs[key]
        if not isinstance(col, list) or len(col) != n_columns:
            raise ProtocolError(f'obs.{key} must be a list of {n_columns} values')
        for v in col:
            if key.endswith('kind'):
                if v not in (vl.NONE, vl.EDGE, vl.INTERVAL) or isinstance(v, bool):
                    raise ProtocolError(f'obs.{key} has an unknown kind {v!r}')
            elif v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)):
                raise ProtocolError(f'obs.{key} has a non-finite or non-numeric row {v!r}')
    for edge in ('b', 't'):
        kind, lo, hi = (obs[f'{edge}_{s}'] for s in ('kind', 'lo', 'hi'))
        for k, a, b in zip(kind, lo, hi):
            if k == vl.NONE and (a is not None or b is not None):
                raise ProtocolError(f'{edge}: a NONE column carries rows')
            if k != vl.NONE and (a is None or b is None or a > b):
                raise ProtocolError(f'{edge}: an observed column needs lo <= hi')
            if k == vl.EDGE and a != b:
                raise ProtocolError(f'{edge}: an EDGE column needs lo == hi')
    if sha256_bytes(canonical({k: obs[k] for k in OBS_KEYS})) != reply['obs_sha256']:
        raise ProtocolError('reply observation sha256 mismatch')
    infer_ms = reply['infer_ms']
    if not isinstance(infer_ms, (int, float)) or isinstance(infer_ms, bool) or not math.isfinite(infer_ms) \
            or infer_ms < 0:
        raise ProtocolError('infer_ms must be a non-negative finite number')
    return 'obs', vl.ColumnObs.from_dict(obs, np.asarray(columns())), float(infer_ms)
