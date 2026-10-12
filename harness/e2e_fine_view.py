"""Switch from visible-landmark staging to the assigned grasp's camera view.

The RGB far band remains a navigation landmark, never a substitute grasp.
Only own station distance selects the view; fresh RGB still gates alignment.
"""
import math
import numpy as np
from harness.owncam_pair_beam_v2 import look_posture

OPTIONS=('stage08_v1','stage20_v1')
VERSIONS=dict(zip(OPTIONS,(257,258)))
RADII=dict(zip(OPTIONS,(.08,.20)))
PARAMS=dict(release_hysteresis_m=.08,fresh_alignment_required=True)


def active(tr,rid,state):
    mode=getattr(tr,'fine_view','off')
    if mode=='off':return False
    if mode not in OPTIONS:raise ValueError('UNKNOWN_FINE_VIEW')
    if 'station' not in state:return False
    pose=np.asarray(tr.robots[rid].goal.explorer.local_pose,float)
    distance=float(np.linalg.norm(np.asarray(state['station'])[:2]-pose[:2]))
    threshold=RADII[mode]+(PARAMS['release_hysteresis_m'] if state.get('fine_view_active') else 0.)
    state['fine_view_active']=math.isfinite(distance) and distance<=threshold
    return state['fine_view_active']


def view(tr,rid,state,grip_distance):
    return look_posture(grip_distance) if active(tr,rid,state) else None


def compose(bundle,option):
    if option=='off':return ()
    if option not in OPTIONS or bundle['execution_bundle_id']!='e2e18-v254':
        raise ValueError('FINE_VIEW_REQUIRES_V254')
    v=VERSIONS[option];bundle['e2e_options']['fine_view']=option
    bundle['fine_view_parameters']={**PARAMS,'staging_radius_m':RADII[option]}
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{v}',execution_bundle_id=f'e2e18-v{v}',workflow_version=f'7.{v-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{v}.json',)
