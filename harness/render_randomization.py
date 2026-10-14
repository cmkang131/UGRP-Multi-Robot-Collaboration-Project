"""Opt-in render domain randomization for ACT recording runs (default off).

Applied to a built MjModel before the first render, per episode, from a seeded
draw that is written into the run record (``record``) with a sha256. It edits
only appearance arrays: light diffuse/ambient, the floor material tint
(``groundmat`` multiplies the floor_light_v1 checker texture) and the colour of
static walls (``zone_wall_*``). Robots, cargo, the teal/blue end bands, zone
floor markings, camera pose/FOV, geometry and physics are never touched
(AGENTS.md: keep real camera placement and robot/object appearance).
docs/act_execution_decisions.md fixes render to floor_light_v1 for data; turning
this on needs a decision there first. Ranges are first guesses (no room
measurement exists), recorded so a cohort can be split by them.
"""
from __future__ import annotations
import hashlib, json

SCHEMA = 'ugrp.render_randomization.v1'
PROFILES = ('off', 'on_v1')
RANGES = {'light_diffuse_scale': (.75, 1.25), 'light_diffuse_jitter': (.9, 1.1), 'light_ambient_add': (0., .05),
          'floor_rgb_scale': (.85, 1.15), 'wall_rgb_delta': (-.06, .06)}
FLOOR_MATERIAL = 'groundmat'
WALL_PREFIX = 'zone_wall_'
SEED_OFFSET = 7_000_000          # keeps the appearance draw independent of the episode's other draws


def draw(seed, n_lights):
    import numpy as np
    rng = np.random.default_rng(int(seed)+SEED_OFFSET); r = RANGES
    return {'schema': SCHEMA, 'profile': 'on_v1', 'seed': int(seed),
            'light_diffuse_scale': float(rng.uniform(*r['light_diffuse_scale'])),
            'light_diffuse_jitter': [float(rng.uniform(*r['light_diffuse_jitter'])) for _ in range(n_lights)],
            'light_ambient_add': float(rng.uniform(*r['light_ambient_add'])),
            'floor_rgb_scale': [float(rng.uniform(*r['floor_rgb_scale'])) for _ in range(3)],
            'wall_rgb_delta': [float(rng.uniform(*r['wall_rgb_delta'])) for _ in range(3)]}


def apply(model, params):
    """Edit appearance arrays in place; returns the record (before/after values, touched names)."""
    import mujoco, numpy as np
    if params is None or params.get('profile') == 'off':
        return {'schema': SCHEMA, 'profile': 'off'}
    before = {'light_diffuse': model.light_diffuse.tolist(), 'light_ambient': model.light_ambient.tolist()}
    for i in range(model.nlight):
        model.light_diffuse[i] = np.clip(model.light_diffuse[i]*params['light_diffuse_scale']*params['light_diffuse_jitter'][i], 0., 1.)
        model.light_ambient[i] = np.clip(model.light_ambient[i]+params['light_ambient_add'], 0., 1.)
    touched = {'materials': [], 'geoms': []}
    mid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_MATERIAL, FLOOR_MATERIAL)
    if mid >= 0:
        before['floor_rgba'] = model.mat_rgba[mid].tolist()
        model.mat_rgba[mid, :3] = np.clip(model.mat_rgba[mid, :3]*np.array(params['floor_rgb_scale']), 0., 1.)
        touched['materials'].append(FLOOR_MATERIAL)
    for g in range(model.ngeom):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) or ''
        if name.startswith(WALL_PREFIX):
            model.geom_rgba[g, :3] = np.clip(model.geom_rgba[g, :3]+np.array(params['wall_rgb_delta']), 0., 1.)
            touched['geoms'].append(name)
    after = {'light_diffuse': model.light_diffuse.tolist(), 'light_ambient': model.light_ambient.tolist()}
    if mid >= 0:
        after['floor_rgba'] = model.mat_rgba[mid].tolist()
    return {'schema': SCHEMA, 'profile': 'on_v1', 'params': params, 'params_sha256': sha256(params),
            'ranges': RANGES, 'touched': touched, 'before': before, 'after': after}


def sha256(params):
    return hashlib.sha256(json.dumps(params, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
