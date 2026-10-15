"""Offline fresh v7 gate setup with finite proposal counts and rejection evidence."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random

from harness.static_keepouts import keepout_rects,rect_distance,pose_clear,polygons_overlap,rect_corners
from harness.zone_final_environment import resolve
from sim.zone_cargo import kind
from sim.zone_arena import BOX_HALF,COLORS
from scripts.audit_beampair1 import dump

ROOT=Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/2026-10-15-beampair1'


def segment_hits_rect(a,b,rect):
    # Existing exact SAT overlap also applies to a zero-width segment. No
    # sampled ray spacing or extra visibility tolerance is introduced.
    return polygons_overlap([a,b],rect_corners(rect))


def prepare(seed=8318600):
    data=(EXP/'scenario-v7.json').read_bytes();scenario=json.loads(data)
    static,_,_=resolve(scenario['map_id']);rects=keepout_rects(static,perimeter=True)
    bounds=static['bounds_m'];cx,cy=static['regions']['pickup']['center_m']
    hx,hy=static['regions']['pickup']['half_extents_m']
    beam=kind('long_beam');bhx,bhy=beam.landing_half_extents_m
    # Existing search18 low-chassis rectangle: 185x160mm, matching authored
    # v3 geometry. Its circumscribed radius is a mathematical enclosure,
    # not a new empirical clearance. Zero gap means no enclosure overlap.
    radius=math.hypot(.185/2,.160/2)
    cargo=[p for p in scenario['eval']['setup']['placements'] if p['item_id']!='beam_1']
    others=[(p['item_id'],p['pose_m'][:2],math.hypot(*(BOX_HALF[:2] if p['kind'] in COLORS else kind(p['kind']).landing_half_extents_m))) for p in cargo]
    footprint=[(-bhx,-bhy),(bhx,-bhy),(bhx,bhy),(-bhx,bhy)]
    rejected=[];episodes=[];stage_passes=Counter();attempts=0
    def reject(stage,obj,gap,**kw):
        rejected.append(dict(proposal=attempts,population='main_proposals',reason_category=stage,blocked_object=obj,min_gap_m=gap,**kw))
    def robot_gap(point):
        gaps=[('bounds',min(point[0]-bounds[0],bounds[1]-point[0],point[1]-bounds[2],bounds[3]-point[1])-radius)]
        gaps += [(f'static_wall_{j}',rect_distance(point,r)-radius) for j,r in enumerate(rects)]
        gaps += [(name,math.dist(point,p)-radius-r) for name,p,r in others]
        return min(gaps,key=lambda v:v[1])
    for i in range(40):
        rng=random.Random(seed+i);end='teal' if i%2==0 else 'blue'
        # Preserve the existing make_grasp_act_plan design envelope (0.5..2m,
        # 12 yaw/bearing strata, heading +/-60deg, pan500..2500). Distribution
        # choices are not acceptance tolerances. 5000 proposals is the same
        # existing finite computation cap, never a wall-time deadline.
        for attempt in range(5000):
            attempts+=1;a=2*math.pi*((i%12+rng.random())/12)
            pose=[rng.uniform(cx-hx+bhx,cx+hx-bhx),rng.uniform(cy-hy+bhy,cy+hy-bhy),a]
            if not pose_clear(pose,footprint,rects,bounds=bounds,margin=0.):
                # Exact polygon rejection; report a geometric lower bound,
                # explicitly labelled because a rotated-box signed gap is
                # not reconstructed from this point-distance diagnostic.
                gaps=[(f'static_wall_{j}',rect_distance(pose[:2],r)-math.hypot(bhx,bhy)) for j,r in enumerate(rects)]
                obj,gap=min(gaps,key=lambda x:x[1]);reject('beam_static_overlap',obj,gap,gap_scope='circumscribed_envelope_lower_bound');continue
            stage_passes['beam_static']+=1
            obj,gap=min([(name,math.dist(pose[:2],p)-math.hypot(bhx,bhy)-r) for name,p,r in others],key=lambda x:x[1])
            if gap<0:reject('beam_cargo_overlap',obj,gap);continue
            stage_passes['beam_cargo']+=1
            r=.5+1.5*(((i+attempt)%10+rng.random())/10)
            az=a+2*math.pi*(((i*7+attempt)%12+rng.random())/12)
            own=[pose[0]+r*math.cos(az),pose[1]+r*math.sin(az)]
            heading=a+(math.pi if end=='blue' else 0.)
            case=('other_end','approaching','near_own')[i%3]
            pa=heading if case=='other_end' else heading+math.pi+.65 if case=='near_own' else a+rng.uniform(0,2*math.pi)
            # .27m assigned band offset + existing .203m teacher station.
            pr=abs(beam.grasps[0].grip_xyz[0])+.203 if case=='other_end' else rng.uniform(.65,1.4)
            peer=[pose[0]+pr*math.cos(pa),pose[1]+pr*math.sin(pa)]
            points=[own,peer];bad=None
            for rid,p in zip(('r1','r2'),points):
                obj,gap=robot_gap(p)
                if gap<0:bad=(obj,gap,rid);break
                gap=math.dist(p,pose[:2])-math.hypot(bhx,bhy)-radius
                if gap<0:bad=('beam_1',gap,rid);break
            if bad:reject('robot_environment_overlap',bad[0],bad[1],robot=bad[2]);continue
            stage_passes['robot_environment']+=1
            gap=math.dist(own,peer)-2*radius
            if gap<0:reject('robot_peer_overlap','r2',gap,robot='r1');continue
            stage_passes['robot_peer']+=1
            roles={'r1':end,'r2':'blue' if end=='teal' else 'teal'}
            blocked=False
            for rid,p in zip(roles,points):
                d=beam.grasps[0 if roles[rid]=='teal' else 1].grip_xyz[0]
                target=[pose[0]+d*math.cos(a),pose[1]+d*math.sin(a)]
                hit=next((j for j,rect in enumerate(rects) if segment_hits_rect(p,target,rect)),None)
                if hit is not None:
                    reject('initial_static_los',f'static_wall_{hit}',0.,robot=rid,gap_scope='intersecting_center_ray');blocked=True;break
            if blocked:continue
            stage_passes['initial_static_los']+=1
            # Park r3 by the same finite geometry checks; it remains visible
            # physical scene inventory, never a removed obstacle.
            park=None
            for parking_trial in range(5000):
                p=[rng.uniform(bounds[0]+radius,bounds[1]-radius),rng.uniform(bounds[2]+radius,bounds[3]-radius)]
                obj,gap=robot_gap(p)
                gaps=[(obj,gap),('r1',math.dist(p,own)-2*radius),('r2',math.dist(p,peer)-2*radius),
                      ('beam_1',math.dist(p,pose[:2])-math.hypot(bhx,bhy)-radius)]
                if min(g for _,g in gaps)>=0:park=p;break
                obj,gap=min(gaps,key=lambda v:v[1])
                rejected.append(dict(proposal=attempts,population='parking_trials',trial=parking_trial,
                    reason_category='parking_overlap',blocked_object=obj,min_gap_m=gap))
            if park is None:raise ValueError('parking computation budget exhausted')
            stage_passes['parking']+=1
            ownyaw=math.atan2(pose[1]-own[1],pose[0]-own[0])+rng.uniform(-math.pi/3,math.pi/3)
            peeryaw=math.atan2(pose[1]-peer[1],pose[0]-peer[0])
            episodes.append(dict(episode_id=f'beampair1-gate-{seed+i}',batch='beampair1-gate40',seed=seed+i,
                split='fresh_gate40',scenario_id=scenario['scenario_id'],scenario_source_sha256=hashlib.sha256(data).hexdigest(),
                map_id=scenario['map_id'],cargo_scene='cargo_v7',beam_pose=pose,
                spawns={'r1':[*own,.032355118817659255,ownyaw],'r2':[*peer,.032355118817659255,peeryaw],
                        'r3':[*park,.032355118817659255,0.]},roles=roles,target_item='beam_1',object_kind='long_beam',
                assignment_source='demo_rule_color_balanced',end_color_scene='grasp_act_teal_blue_v1',peer_case=case,
                initial_pan={r:rng.randint(500,2500) for r in roles},burst_ticks=1+i%12,proposal_attempts=attempt+1))
            break
        else:raise ValueError('finite setup proposal budget exhausted')
    stages=['beam_static','beam_cargo','robot_environment','robot_peer','initial_static_los','parking']
    entered=attempts;funnel=[]
    for stage in stages:
        passed=stage_passes[stage];funnel.append(dict(gate=stage,entered=entered,passed=passed,rejected=entered-passed));entered=passed
    dump(EXP/'gate-plan.json',dict(schema='ugrp.beampair1.gate_setup.v1',episodes=episodes,
        training_rgb=False,setup_only=True,physical_success_verified=False,proposal_count=attempts))
    dump(EXP/'setup-funnel.json',dict(schema='ugrp.beampair1.setup_funnel.v1',funnel=funnel,rejections=rejected,
        source_scenario_sha256=hashlib.sha256(data).hexdigest(),reproduce=f'python -m scripts.prepare_beampair1 --seed {seed}',
        scope='static initialization only; finite strata and enclosures do not prove physical success'))
    print(json.dumps(dict(planned_N=len(episodes),proposals=attempts,rejections=len(rejected))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=8318600);a=p.parse_args();prepare(a.seed)
