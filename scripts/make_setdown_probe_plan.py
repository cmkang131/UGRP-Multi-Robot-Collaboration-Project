"""Offline set-down-and-look probe starts beside a door (G2/G6); no simulator.

The held beam starts in the E-W door-crossing formation (beam axis along the
passage axis, lateral offset within a few cm of the door centre line) either
just before the door (west side, about to cross) or just after it (east side).
Robots start at grasp stations 0.203 m from each beam end, facing it, so the
unchanged observable_v2 grasp prefix is short. Seeds: carry_probe range
(75100+), configs/grasp_act_seed_splits.json.
"""
import argparse,hashlib,json,math,random
from collections import Counter
from pathlib import Path
from harness.zone_final_environment import resolve
from harness.static_keepouts import keepout_rects,rect_distance,pose_clear
from scripts.make_grasp_act_plan import BASE_Z
from harness.grasp_act_seed_splits import check_range

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=(('s1_normal_mixed_v4','door_1'),('s3_late_rendezvous_v4','door_1'),('s6_novel_relation_v4','door_narrow'))
CASES=('door_before','door_after')
STATION_M=.203
HALF_FORMATION_M=.473+.18       # beam centre -> outer edge of a robot footprint
GAP_M=(.25,.50)                 # door wall face -> nearest robot footprint edge (>= back-off 0.15 + 0.10)
BACKOFF_M=.15                   # sim/grasp_act_release_teacher.OBSERVE_BACKOFF_M
LATERAL_M=.03                   # door margin is about 3 cm for the 0.44 m formation
YAW_DEG=3.


def door_points(passage,*,inset=.01,heights=(.05,.12)):
    """Floor-standing landmark points on both wall faces next to each jamb (evaluation visibility only)."""
    (cx,cy),(hx,hy)=passage['center_m'],passage['half_extents_m']
    if passage.get('axis','x')!='x':raise ValueError('only x-axis doors')
    pts={'west':[],'east':[]}
    for side,x in (('west',cx-hx-inset),('east',cx+hx+inset)):
        for jy in (cy-hy-.03,cy+hy+.03):
            for z in heights:pts[side].append((x,jy,z))
    return pts


def prepare(*,count=6,seed=75100,split='carry_probe'):
    check_range(split,seed,count)
    episodes=[];rejects=Counter()
    for i in range(count):
        rng=random.Random(seed+i);(scenario_id,door_id)=SCENARIOS[(i//2)%len(SCENARIOS)];case=CASES[i%2]
        path=ROOT/'configs/zone_study_scenarios_v4'/f'{scenario_id}.json'
        scenario=json.loads(path.read_text());static,_,_=resolve(scenario['map_id'])
        door=next(p for p in static['passages'] if p['id']==door_id)
        bounds=static['bounds_m'];rects=keepout_rects(static,perimeter=True)
        others=[p for p in scenario['eval']['setup']['placements'] if p['item_id']!='beam_1']
        (dx,dy),(hx,_)=door['center_m'],door['half_extents_m']
        def free(p,r):
            return bounds[0]+r<=p[0]<=bounds[1]-r and bounds[2]+r<=p[1]<=bounds[3]-r and all(rect_distance(p,rect)>=r for rect in rects)
        for attempt in range(5000):
            gap=rng.uniform(*GAP_M);y=dy+rng.uniform(-LATERAL_M,LATERAL_M);yaw=math.radians(rng.uniform(-YAW_DEG,YAW_DEG))
            x=dx-hx-gap-HALF_FORMATION_M if case=='door_before' else dx+hx+gap+HALF_FORMATION_M
            beam=[x,y,yaw];c,s=math.cos(yaw),math.sin(yaw)
            if not pose_clear(beam,[(-.3,-.02),(.3,-.02),(.3,.02),(-.3,.02)],rects,bounds=bounds,margin=.005):rejects['beam_wall']+=1;continue
            if any(math.dist(beam[:2],p['pose_m'][:2])<.5 for p in others):rejects['beam_other_cargo']+=1;continue
            teal=(x-.27*c,y-.27*s);blue=(x+.27*c,y+.27*s)
            r1=[teal[0]-STATION_M*c,teal[1]-STATION_M*s];r2=[blue[0]+STATION_M*c,blue[1]+STATION_M*s]
            if any(not free(p,.18) for p in (r1,r2)):rejects['robot_wall']+=1;continue
            backed=([r1[0]-BACKOFF_M*c,r1[1]-BACKOFF_M*s],[r2[0]+BACKOFF_M*c,r2[1]+BACKOFF_M*s])
            if any(not free(p,.18) for p in backed):rejects['backoff_wall']+=1;continue
            if any(math.dist(p,q['pose_m'][:2])<.35 for p in (r1,r2) for q in others):rejects['robot_other_cargo']+=1;continue
            parking=None
            for _ in range(2000):
                p=[rng.uniform(bounds[0]+.2,bounds[1]-.2),rng.uniform(bounds[2]+.2,bounds[3]-.2)]
                if free(p,.18) and all(math.dist(p,q)>.8 for q in (r1,r2,beam[:2])) and all(math.dist(p,q['pose_m'][:2])>.3 for q in others):parking=p;break
            if parking is None:rejects['no_parking']+=1;continue
            episodes.append({'episode_id':f'{split}-{seed+i}','batch':f'grasp-act-{split}-setdown-{seed}','seed':seed+i,'split':split,
                'scenario_id':scenario_id,'scenario_source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'map_id':scenario['map_id'],'beam_pose':beam,'door_id':door_id,'door':door,'case':case,'door_gap_m':gap,
                'spawns':{'r1':[*r1,BASE_Z,yaw],'r2':[*r2,BASE_Z,yaw+math.pi],'r3':[*parking,BASE_Z,0.]},
                'roles':{'r1':'teal','r2':'blue'},'target_item':'beam_1','object_kind':'long_beam','skill':'setdown_look_probe',
                'end_color_scene':'grasp_act_teal_blue_v1','assignment_source':'demo_rule_fixed_r1_teal',
                'initial_pan':{'r1':1500,'r2':1500},'destination_region':'zone_A','proposal_attempts':attempt+1})
            break
        else:raise ValueError(f'no start for index {i}; {dict(rejects)}')
    return {'schema':'ugrp.grasp_act.setdown_probe_plan.v1','episodes':episodes,'rejected_proposals':dict(rejects),
        'distribution':{'cases':CASES,'gap_m':GAP_M,'lateral_m':LATERAL_M,'yaw_deg':YAW_DEG,
            'prefix':'unchanged observable_v2 grasp teacher from grasp stations; prefix failures reported separately'},
        'student_evaluation':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,default=6)
    p.add_argument('--seed',type=int,default=75100);a=p.parse_args()
    result=prepare(count=a.count,seed=a.seed)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'episodes':len(result['episodes']),'rejected':result['rejected_proposals']}))
if __name__=='__main__':main()
