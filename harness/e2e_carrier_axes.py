"""Own-RGB beam frame for arbitrary robot start headings; no scene input."""
import copy
import math
import numpy as np
from harness.self_odom_grid import transform

OPTION='beam_v1'
ROUTE_SCHEMA='ugrp.e2e_own_route.v2'
WIRE_SCHEMA='ugrp.e2e_route_message.v2'
WORKFLOW='configs/simulation_workflows.d/e2e18_v224.json'
RULE='toward_B_projection_v1'


def basis(beam,target):
    center=np.asarray(beam['pose_own_m'][:2],float);yaw=float(beam['pose_own_m'][2])
    u=np.array([math.cos(yaw),math.sin(yaw)])
    if np.dot(np.asarray(target)-center,u)<0:yaw+=math.pi
    yaw=math.atan2(math.sin(yaw),math.cos(yaw))
    return dict(yaw_rad=yaw,center_m=center.tolist(),rgb=copy.deepcopy(beam['rgb']),rule=RULE)


def validate(value,rid,now,observed,start):
    from harness import e2e_own_inputs as own
    own.closed(value,('yaw_rad','center_m','rgb','rule'),'CARRIER_BASIS')
    own.numbers([value['yaw_rad']],1,'CARRIER_YAW');own.numbers(value['center_m'],2,'CARRIER_CENTER')
    own.rgb_ref(value['rgb'],rid,now,observed)
    if value['rule']!=RULE or not -math.pi<=value['yaw_rad']<=math.pi or math.dist(value['center_m'],start)>1e-8:
        raise own.ContractViolation('OBSERVED_CARRIER_BASIS_REQUIRED')


def to_axes(points,b):
    # Rotation only: retain the private own-start origin and metric distances.
    return transform(points,[0.,0.,-b['yaw_rad']]).tolist()


def from_axes(points,b):return transform(points,[0.,0.,b['yaw_rad']]).tolist()


def station(beam,target,rid):
    rid={'end_neg':'r1','end_pos':'r2'}.get(rid,rid)
    if rid not in ('r1','r2'):raise ValueError('PAIR_ROLE_REQUIRED')
    from harness.zone_s3_coarse_fine import arm,PARAMS
    b=basis(beam,target);yaw=b['yaw_rad']+(math.pi if rid=='r2' else 0.)
    yaw=math.atan2(math.sin(yaw),math.cos(yaw));u=np.array([math.cos(b['yaw_rad']),math.sin(b['yaw_rad'])])
    grip=np.array(b['center_m'])+(-.27 if rid=='r1' else .27)*u
    reach=arm.MOUNT_X_M+PARAMS['pair_radius_m']
    xy=grip-reach*np.array([math.cos(yaw),math.sin(yaw)])
    return np.r_[xy,yaw],grip,b


def compose(bundle,option,approach):
    if option=='off' and approach=='off':return ()
    if option!=OPTION or approach!='standoff_v1' or bundle['execution_bundle_id']!='e2e18-v223':
        raise ValueError('CARRIER_AXES_REQUIRES_V223')
    bundle['e2e_options'].update(carrier_axes=option,carrier_approach=approach)
    bundle.update(schema='ugrp.e2e_ownmap_live.v224',execution_bundle_id='e2e18-v224',workflow_version='7.117.0')
    return (WORKFLOW,)
