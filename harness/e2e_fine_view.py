"""Switch from visible-landmark staging to the assigned grasp's camera view.

The RGB far band remains a navigation landmark, never a substitute grasp.
Only own station distance selects the view; fresh RGB still gates alignment.
"""
import math
import numpy as np
from harness.owncam_pair_beam_v2 import look_posture,pose_of

OPTIONS=('stage08_v1','stage20_v1','inspect40_v1','inspect60_v1')
VERSIONS=dict(zip(OPTIONS,(257,258,259,260)))
RADII=dict(zip(OPTIONS,(.08,.20,.40,.60)))
PARAMS=dict(release_hysteresis_m=.08,fresh_alignment_required=True)


def parameters(option):
    result={**PARAMS,'staging_radius_m':RADII[option]}
    if option.startswith('inspect'):
        result.update(fixed_posture='inspect',latch_station_radius_m=.25)
    return result


def active(tr,rid,state):
    mode=getattr(tr,'fine_view','off')
    if mode=='off':return False
    if mode not in OPTIONS:raise ValueError('UNKNOWN_FINE_VIEW')
    if 'station' not in state:
        state.pop('inspect_station',None)
        return False
    pose=np.asarray(tr.robots[rid].goal.explorer.local_pose,float)
    distance=float(np.linalg.norm(np.asarray(state['station'])[:2]-pose[:2]))
    if mode.startswith('inspect'):
        anchor=state.get('inspect_station')
        if anchor is not None and np.linalg.norm(np.asarray(state['station'])[:2]-anchor)>.25:
            state.pop('inspect_station',None)
        if math.isfinite(distance) and distance<=RADII[mode]:
            state.setdefault('inspect_station',np.asarray(state['station'])[:2].copy())
        return 'inspect_station' in state
    threshold=RADII[mode]+(PARAMS['release_hysteresis_m'] if state.get('fine_view_active') else 0.)
    state['fine_view_active']=math.isfinite(distance) and distance<=threshold
    return state['fine_view_active']


def view(tr,rid,state,grip_distance):
    if not active(tr,rid,state):return None
    if tr.fine_view.startswith('inspect'):return 'inspect',pose_of('inspect')
    return look_posture(grip_distance)


def compose(bundle,option):
    if option=='off':return ()
    if option not in OPTIONS or bundle['execution_bundle_id']!='e2e18-v254':
        raise ValueError('FINE_VIEW_REQUIRES_V254')
    v=VERSIONS[option];bundle['e2e_options']['fine_view']=option
    bundle['fine_view_parameters']=parameters(option)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{v}',execution_bundle_id=f'e2e18-v{v}',workflow_version=f'7.{v-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{v}.json',)
