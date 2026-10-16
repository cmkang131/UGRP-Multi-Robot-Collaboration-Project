"""Setup-only zero-grasp-support filter, user decision 2026-10-16.

Certification family/body_clearance/FRESH_MARGIN_M are the existing
beampair6/9 (PR542) algorithm. No runtime state or teacher outcome is input.
The rejection boundary zero is the user's explicit criterion, not tuning.
"""
from collections import Counter
import math

MODE='placement_graspable_filter_v1'


class PlacementRejected(ValueError):
    pass


def certify(pose,rects,family,body_clearance,margin,*,offset=.27,mode='off'):
    if mode not in ('off',MODE):raise ValueError('unknown placement filter')
    ends={}
    for end,d in (('teal',-offset),('blue',offset)):
        x,y=pose[0]+d*math.cos(pose[2]),pose[1]+d*math.sin(pose[2])
        free=0;blocks=[]
        for angle,distance,_,certificate in family:
            yaw=pose[2]+(math.pi if end=='blue' else 0.)+angle
            goal=(x-distance*math.cos(yaw),y-distance*math.sin(yaw),yaw)
            gaps=[(name,body_clearance(goal,[],[rect])) for name,rect in rects]
            name,gap=min(gaps,key=lambda v:v[1]) if gaps else ('none:no_static_or_cargo_obstacle',math.inf)
            if gap>=margin:free+=1
            else:blocks.append((name,gap))
        names=Counter(name for name,gap in blocks)
        ends[end]=dict(certified_N=len(family),free_goal_N=free,
            blocked_object=names.most_common(1)[0][0] if names else 'none:all_certified_stances_clear',
            min_gap_m=min((gap for _,gap in blocks),default=None))
    return dict(mode=mode,accepted=mode=='off' or all(v['free_goal_N']>0 for v in ends.values()),
        ends=ends,criterion='assigned end must have >0 existing certified poses',
        basis='user 2026-10-16 zero-pose rejection; PR542/beampair6/9 certified family',
        setup_only=True,runtime_truth_used=False)


def scene_admission(plan,scene,*,mode='off'):
    from sim.grasp_act_search24 import reachability_map
    from sim.grasp_act_search18 import body_clearance
    from sim.grasp_act_search21 import FRESH_MARGIN_M
    from sim.zone_cargo import kind
    from sim.zone_arena import BOX_HALF,COLORS
    static=scene.config['static_map']
    rects=[(o['id'],(*o['center_m'],*o['half_extents_m'],o.get('yaw_rad',0.))) for o in static['obstacles']]
    for item in scene.cargo:
        if item.item_id=='beam_1':continue
        half=BOX_HALF[:2] if item.kind in COLORS else item.spec().landing_half_extents_m
        rects.append((item.item_id,(*item.pose[:2],*half,item.pose[2])))
    beam=kind('long_beam')
    family=reachability_map(beam.grasps[0].grip_xyz[2])
    return certify(plan['beam_pose'],rects,family,body_clearance,FRESH_MARGIN_M,
        offset=abs(beam.grasps[0].grip_xyz[0]),mode=mode)
