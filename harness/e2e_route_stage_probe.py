"""Saved PRIVATE mapping-state replay through the actual route compiler, no physics.

Reuses pair_stage_probe labels/hash convention. Its teacher physical staging is
not applicable to GoalRoute; this adapter restores only the planner's own state.
Evaluation is deliberately a separate entry point, called AFTER both planners.
"""
import copy
import math
from types import SimpleNamespace
import numpy as np
from harness.pair_stage_probe import LABELS, digest
from harness.own_map_navigation import ObservedGrid
from harness.e2e_goal_route import IntegratedGoalRoute
from harness.zone_study_contract import ContractViolation
from harness import e2e_own_inputs as own

SCHEMA='ugrp.e2e_route_stage_snapshot.v1'
ATTRS=('route_guard','route_coverage','route_extent','route_cost','beam_axis','carrier_axes')


def capture(goal,beam,*,now,profiles,pulse_budget='off'):
    """Call at a mapping boundary on the execution host; never capture a world."""
    grid=goal.explorer.grid
    state=dict(schema=SCHEMA,robot_id=goal.robot_id,t_sim=now,
        resolution_m=grid.resolution,
        odds=[[int(x),int(y),v] for (x,y),v in sorted(grid.odds.items())],
        floor_frames=[[int(x),int(y),sorted(ids)] for (x,y),ids in sorted(grid.floor_frames.items())],
        wall_frames=[[int(x),int(y),sorted(ids)] for (x,y),ids in sorted(grid.wall_frames.items())],
        support=[list(c) for c in sorted(grid.support)],
        map_to_odom=np.asarray(goal.explorer.map_to_odom).tolist(),
        local_pose=np.asarray(goal.explorer.local_pose).tolist(),
        covariance=np.asarray(goal.pose_covariance()).tolist(),
        beam=copy.deepcopy(beam),entities=copy.deepcopy(goal.entities),
        B_reference=copy.deepcopy(goal.e2e_gate.references.get('B',{}).get('ref')),
        observed=copy.deepcopy(goal.e2e_observed),options=copy.deepcopy(goal.e2e_options),
        attrs={k:getattr(goal,'e2e_'+k,'off') for k in ATTRS},
        version=goal.e2e_version,dev_light=goal.dev_light,
        profiles=copy.deepcopy(profiles),pulse_budget=pulse_budget)
    # options contain no covariance training data: pose covariance is already applied.
    own.scan(state)
    return state


def restore(state):
    own.scan(state)
    required={'schema','robot_id','t_sim','resolution_m','odds','floor_frames','wall_frames','support',
              'map_to_odom','local_pose','covariance','beam','entities','B_reference','observed','options',
              'attrs','version','dev_light','profiles','pulse_budget'}
    if set(state)!=required or state['schema']!=SCHEMA or state['robot_id']!='r1':
        raise ValueError('PRIVATE_ROUTE_SNAPSHOT_REQUIRED')
    g=ObservedGrid('r1',state['resolution_m'])
    for key in ('odds','floor_frames','wall_frames'):
        setattr(g,key,{(x,y):v if key=='odds' else set(v) for x,y,v in state[key]})
    g.support={tuple(c) for c in state['support']}
    c=IntegratedGoalRoute.__new__(IntegratedGoalRoute)
    c.robot_id='r1';c.dev_light=state['dev_light'];c.e2e_version=state['version']
    c.explorer=SimpleNamespace(grid=g,map_to_odom=np.asarray(state['map_to_odom']),local_pose=np.asarray(state['local_pose']))
    c.pose_covariance=lambda:copy.deepcopy(state['covariance'])
    c.entities=copy.deepcopy(state['entities']);c.e2e_observed=copy.deepcopy(state['observed'])
    c.e2e_gate=SimpleNamespace(references={'B':{'ref':state['B_reference']}} if state['B_reference'] else {})
    c.e2e_options=copy.deepcopy(state['options']);c.e2e_route_diagnostics={}
    for k,v in state['attrs'].items():setattr(c,'e2e_'+k,v)
    c.event=lambda *a,**kw:None
    return c


def replay(state,option='off'):
    if option not in ('off','frontier_v1'):raise ValueError('UNKNOWN_ROUTE_RECOVERY')
    c=restore(state)
    # No navigator or motion is run by this one-call stage probe.
    c.e2e_route_recovery=option
    packet=None;failure=None
    try:
        packet=c.route_to_B(state['beam'],now=state['t_sim'],profiles=state['profiles'],pulse_budget=state['pulse_budget'])
    except (ContractViolation,ValueError) as exc:
        failure=str(exc)
    return dict(option=option,generated=packet is not None,
        observed_complete=bool(packet and packet.get('observed_coverage_complete',True)),
        failure=failure,diagnostics=c.e2e_route_diagnostics,
        route=None if packet is None else packet['route'],
        input_sha256=digest(state),input_sim_s=state['t_sim'],
        physical_pass=None,labels=LABELS,stage='route_generation',
        scope='offline_saved_state_route_compiler; no SIM advancement or exploration rollout')


def evaluate(result, state, evaluation):
    """Independent swept-polygon SAT against evaluation-only rectangular obstacles.

    own_to_world and obstacles are never handed to restore/replay. This is
    geometric collision evidence, not contact/traction/loaded physical passage.
    """
    from harness.self_odom_grid import transform
    from scipy.spatial import ConvexHull
    if evaluation['input_sha256']!=result['input_sha256']:
        raise ValueError('EVALUATION_SNAPSHOT_MISMATCH')
    if evaluation['schema']!='ugrp.route_eval_rectangles.v1':raise ValueError('INVALID_EVALUATION_SCHEMA')
    if not result['generated']:return dict(collision_free=None,physical_pass=None)
    tf=evaluation['own_to_world'];yaw=tf[2]+state['beam']['pose_own_m'][2]
    route=transform(result['route']['waypoints'],tf)
    c,s=math.cos(yaw),math.sin(yaw)
    rotation=np.array([[c,-s],[s,c]])
    corners=np.array([[-.625,-.2],[.625,-.2],[.625,.2],[-.625,.2]])@rotation.T
    def overlap(poly,rect):
        edges=np.diff(np.vstack([poly,poly[0]]),axis=0)
        axes=np.vstack([np.column_stack((-edges[:,1],edges[:,0])),np.eye(2)])
        for axis in axes:
            a,b=poly@axis,rect@axis
            if a.max()<b.min()-1e-10 or b.max()<a.min()-1e-10:return False
        return True
    xmin,ymin,xmax,ymax=evaluation['bounds_xyxy']
    for a,b in zip(route,route[1:]):
        cloud=np.vstack((corners+a,corners+b));poly=cloud[ConvexHull(cloud).vertices]
        if (poly[:,0].min()<xmin or poly[:,0].max()>xmax or poly[:,1].min()<ymin or poly[:,1].max()>ymax):
            return dict(collision_free=False,physical_pass=None,reason='OUTSIDE_EVALUATION_BOUNDS')
        for x0,y0,x1,y1 in evaluation['obstacles_xyxy']:
            if overlap(poly,np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]])):
                return dict(collision_free=False,physical_pass=None,reason='SWEPT_CARRIER_COLLISION')
    return dict(collision_free=True,physical_pass=None)
