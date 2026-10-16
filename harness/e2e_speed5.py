"""Opt-in E2E18 bottleneck fixes: static views and bounded partial-fit work."""
import copy
from contextlib import contextmanager
from contextvars import ContextVar
import functools
import hashlib
import json
from pathlib import Path

OPTIONS=('cache_v1','lean_v1','lean_v2','lean_v3')
ACTIVE=ContextVar('e2e_speed5',default='off')
STATIC='configs/e2e18_static_views_v1.json'
INPUTS=('harness/e2e_b_standoff.py','harness/active_camera.py','harness/servo_camera_fk.py',
 'harness/visual_arm.py','harness/floor_goal_self_mask.py','harness/floor_goal.py',
 'harness/e2e_rgb_gate.py','harness/public_navigation/costmap.py','sim/masterpi_camera_profile.py',
 'harness/data/servo_camera_v3_chain.json','harness/data/floor_goal_self_geometry.json',
 'maps/zones_e2e/zone_wide_door_e2e_b80_v1.json')

@contextmanager
def using(option):
    if option not in ('off',*OPTIONS):raise ValueError('UNKNOWN_SPEED5')
    token=ACTIVE.set(option)
    try:yield
    finally:ACTIVE.reset(token)


def source_hashes(root):
    return {p:hashlib.sha256((Path(root)/p).read_bytes()).hexdigest() for p in INPUTS}


@functools.lru_cache(maxsize=1)
def static_views():
    root=Path(__file__).resolve().parents[1]
    record=json.loads((root/STATIC).read_text())
    if record['source_sha256']!=source_hashes(root):raise ValueError('STATIC_VIEW_INPUT_CHANGED')
    if record['top']!=100:raise ValueError('STATIC_VIEW_COUNT_MISMATCH')
    return record['views']


def plan_views():
    return copy.deepcopy(static_views())


def rectangle_grid_cost(points, centers, yaw, half, trunc, *, interior=False):
    """Squared rectangle distance: outside dx^2+dy^2; inside max(dx,dy)^2.

    The coarse search consumes squared/truncated costs, so sqrt/hypot and
    N*2 broadcast temporaries can be eliminated algebraically.
    """
    import math
    import numpy as np
    c,s=math.cos(yaw),math.sin(yaw)
    dtype=np.float32 if ACTIVE.get()=='lean_v3' else np.float64
    points=np.asarray(points,dtype=dtype);centers=np.asarray(centers,dtype=dtype)
    half=np.asarray(half,dtype=dtype)
    ex=np.abs((c*points[:,0]+s*points[:,1])[None,:]-(c*centers[:,0]+s*centers[:,1])[:,None])-half[0]
    ey=np.abs((-s*points[:,0]+c*points[:,1])[None,:]-(-s*centers[:,0]+c*centers[:,1])[:,None])-half[1]
    d=np.maximum(ex,0)**2+np.maximum(ey,0)**2
    if not interior:d+=np.minimum(np.maximum(ex,ey),0)**2
    return np.minimum(d,trunc**2).mean(axis=1)
