"""Offline loaded-motion probe start plan (G1 rotation, G7 carry); no simulator.

Robots start at grasp stations 0.203 m from each beam end, facing it (as the
release plan), so the unchanged observable_v2 grasp prefix is short. Every
start keeps a clear circle around the beam centre large enough for a full
loaded rotation about the centre (beam-centre -> robot 0.473 m + footprint
0.18 m, plus margin) and away from other cargo. Seeds: carry_probe range in
configs/grasp_act_seed_splits.json.
"""
import argparse,hashlib,json,math,random
from collections import Counter
from pathlib import Path
from harness.zone_final_environment import resolve
from harness.static_keepouts import keepout_rects,rect_distance
from scripts.make_grasp_act_plan import BASE_Z
from harness.grasp_act_seed_splits import check_range

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=('s1_normal_mixed_v4','s3_late_rendezvous_v4','s6_novel_relation_v4')
STATION_M=.203
CLEAR_RADIUS_M=.75          # 0.473 + 0.18 = 0.653 swept, + ~0.1 margin
CARGO_CLEAR_M=.95


def prepare(*,count=3,seed=75000,split='carry_probe'):
    check_range(split,seed,count)
    episodes=[];rejects=Counter()
    for i in range(count):
        rng=random.Random(seed+i);scenario_id=SCENARIOS[i%len(SCENARIOS)]
        path=ROOT/'configs/zone_study_scenarios_v4'/f'{scenario_id}.json'
        scenario=json.loads(path.read_text());static,_,_=resolve(scenario['map_id'])
        bounds=static['bounds_m'];rects=keepout_rects(static,perimeter=True)
        others=[p for p in scenario['eval']['setup']['placements'] if p['item_id']!='beam_1']
        def free(p,r):
            return bounds[0]+r<=p[0]<=bounds[1]-r and bounds[2]+r<=p[1]<=bounds[3]-r and all(rect_distance(p,rect)>=r for rect in rects)
        for attempt in range(20000):
            x=rng.uniform(bounds[0]+CLEAR_RADIUS_M,bounds[1]-CLEAR_RADIUS_M);y=rng.uniform(bounds[2]+CLEAR_RADIUS_M,bounds[3]-CLEAR_RADIUS_M)
            yaw=rng.uniform(-math.pi,math.pi)
            if not free((x,y),CLEAR_RADIUS_M):rejects['clear_circle']+=1;continue
            if any(math.dist((x,y),p['pose_m'][:2])<CARGO_CLEAR_M for p in others):rejects['other_cargo']+=1;continue
            c,s=math.cos(yaw),math.sin(yaw);teal=(x-.27*c,y-.27*s);blue=(x+.27*c,y+.27*s)
            r1=[teal[0]-STATION_M*c,teal[1]-STATION_M*s];r2=[blue[0]+STATION_M*c,blue[1]+STATION_M*s]
            parking=None
            for _ in range(2000):
                p=[rng.uniform(bounds[0]+.2,bounds[1]-.2),rng.uniform(bounds[2]+.2,bounds[3]-.2)]
                if free(p,.18) and math.dist(p,(x,y))>CLEAR_RADIUS_M+.3 and all(math.dist(p,q['pose_m'][:2])>.3 for q in others):parking=p;break
            if parking is None:rejects['no_parking']+=1;continue
            episodes.append({'episode_id':f'{split}-{seed+i}','batch':f'grasp-act-{split}-{seed}','seed':seed+i,'split':split,
                'scenario_id':scenario_id,'scenario_source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'map_id':scenario['map_id'],'beam_pose':[x,y,yaw],
                'spawns':{'r1':[*r1,BASE_Z,yaw],'r2':[*r2,BASE_Z,yaw+math.pi],'r3':[*parking,BASE_Z,0.]},
                'roles':{'r1':'teal','r2':'blue'},'target_item':'beam_1','object_kind':'long_beam','skill':'carry_probe',
                'end_color_scene':'grasp_act_teal_blue_v1','assignment_source':'demo_rule_fixed_r1_teal',
                'initial_pan':{'r1':1500,'r2':1500},'clear_radius_m':CLEAR_RADIUS_M,
                'min_wall_distance_m':min(rect_distance((x,y),rect) for rect in rects),'proposal_attempts':attempt+1})
            break
        else:raise ValueError(f'no clear start for index {i}; {dict(rejects)}')
    return {'schema':'ugrp.grasp_act.carry_probe_plan.v1','episodes':episodes,'rejected_proposals':dict(rejects),
        'distribution':{'beam_yaw':'uniform','clear_radius_m':CLEAR_RADIUS_M,'cargo_clear_m':CARGO_CLEAR_M,
            'prefix':'unchanged observable_v2 grasp teacher from grasp stations; prefix failures reported separately'},
        'student_evaluation':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,default=3)
    p.add_argument('--seed',type=int,default=75000);a=p.parse_args()
    result=prepare(count=a.count,seed=a.seed)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'episodes':len(result['episodes']),'rejected':result['rejected_proposals']}))
if __name__=='__main__':main()
