"""Offline pair release start plan; does not construct or step a simulator.

The beam starts held-ready next to the destination zone (map code handoff
within 0.8 m of the zone centre), oriented so that it can land in the zone
(zone A of the v4 study scenarios needs a roughly N-S beam: landing half
length 0.30 m vs zone half width 0.30 m in x). Strata: already inside,
and outside by 0-0.15 / 0.15-0.30 / 0.30-0.44 m along the beam axis, both
sides. Seeds come from configs/grasp_act_seed_splits.json.
"""
import argparse,hashlib,json,math,random
from collections import Counter
from pathlib import Path
from harness.zone_final_environment import resolve
from harness.static_keepouts import keepout_rects,pose_clear,rect_distance
from scripts.make_grasp_act_plan import BASE_Z
from harness.grasp_act_seed_splits import check_range

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=('s1_normal_mixed_v4','s3_late_rendezvous_v4','s6_novel_relation_v4')
STATION_M=.203
HANDOFF_MAX_M=.8
POSE_ERROR=(.05,math.radians(2.))     # map-code own-pose estimate error (provisional, frozen per episode)
STRATA=((-.30,-.02),(0.,.15),(.15,.30),(.30,.44))


def prepare(*,count=40,seed=74000,split='release_gate',destination='A'):
    check_range(split,seed,count)
    episodes=[];rejects=Counter()
    for i in range(count):
        rng=random.Random(seed+i)
        scenario_id=SCENARIOS[i%len(SCENARIOS)]
        path=ROOT/'configs/zone_study_scenarios_v4'/f'{scenario_id}.json'
        scenario=json.loads(path.read_text());static,_,_=resolve(scenario['map_id'])
        bounds=static['bounds_m'];rects=keepout_rects(static,perimeter=True)
        zone=static['regions']['zone_'+destination];(cx,cy),(hx,hy)=zone['center_m'],zone['half_extents_m']
        others=[p for p in scenario['eval']['setup']['placements'] if p['item_id']!='beam_1']
        teal_south=i%2==0;lo,hi=STRATA[(i//2)%len(STRATA)]
        def free(p,r):
            return bounds[0]+r<=p[0]<=bounds[1]-r and bounds[2]+r<=p[1]<=bounds[3]-r and all(rect_distance(p,rect)>=r for rect in rects)
        for attempt in range(5000):
            dyaw=rng.uniform(-math.radians(8),math.radians(8))
            yaw=(math.pi/2 if teal_south else -math.pi/2)+dyaw
            ey=.30*abs(math.sin(yaw))+.02*abs(math.cos(yaw))   # landing_fits extent along y
            admissible=hy-ey-.04
            d=rng.uniform(lo,hi);side=1 if rng.random()<.5 else -1
            y=cy+side*(admissible+d);x=cx+rng.uniform(-.2,.2)
            beam=[x,y,yaw]
            if math.dist(beam[:2],(cx,cy))>HANDOFF_MAX_M:rejects['handoff_distance']+=1;continue
            footprint=[(-.3,-.02),(.3,-.02),(.3,.02),(-.3,.02)]
            if not pose_clear(beam,footprint,rects,bounds=bounds,margin=.005):rejects['beam_wall']+=1;continue
            if any(math.dist(beam[:2],p['pose_m'][:2])<.5 for p in others):rejects['beam_other_cargo']+=1;continue
            c,s=math.cos(yaw),math.sin(yaw)
            teal=(x-.27*c,y-.27*s);blue=(x+.27*c,y+.27*s)
            r1=[teal[0]-STATION_M*c,teal[1]-STATION_M*s];r2=[blue[0]+STATION_M*c,blue[1]+STATION_M*s]
            if any(not free(p,.18) for p in (r1,r2)):rejects['robot_wall']+=1;continue
            if any(math.dist(p,q['pose_m'][:2])<.3 for p in (r1,r2) for q in others):rejects['robot_other_cargo']+=1;continue
            parking=None
            for _ in range(2000):
                p=[rng.uniform(bounds[0]+.2,bounds[1]-.2),rng.uniform(bounds[2]+.2,bounds[3]-.2)]
                if free(p,.18) and all(math.dist(p,q)>.7 for q in (r1,r2,beam[:2])) and all(math.dist(p,q['pose_m'][:2])>.3 for q in others):
                    parking=p;break
            if parking is None:rejects['no_parking']+=1;continue
            err={rid:[rng.gauss(0,POSE_ERROR[0]),rng.gauss(0,POSE_ERROR[0]),rng.gauss(0,POSE_ERROR[1])] for rid in ('r1','r2')}
            episodes.append({'episode_id':f'{split}-{seed+i}','batch':f'grasp-act-{split}-{seed}','seed':seed+i,'split':split,
                'scenario_id':scenario_id,'scenario_source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'map_id':scenario['map_id'],'beam_pose':beam,
                'spawns':{'r1':[*r1,BASE_Z,yaw],'r2':[*r2,BASE_Z,yaw+math.pi],'r3':[*parking,BASE_Z,0.]},
                'roles':{'r1':'teal','r2':'blue'},'target_item':'beam_1','object_kind':'long_beam','skill':'release',
                'destination_region':'zone_'+destination,'end_color_scene':'grasp_act_teal_blue_v1',
                'assignment_source':'demo_rule_fixed_r1_teal','initial_pan':{'r1':1500,'r2':1500},
                'stratum':{'axial_outside_m':[lo,hi],'sampled_outside_m':d,'side':'north' if side>0 else 'south','teal_south':teal_south},
                'handoff_pose_error':err,'beam_to_zone_center_m':math.dist(beam[:2],(cx,cy)),'proposal_attempts':attempt+1})
            break
        else:raise ValueError(f'no admissible release start for index {i}; {dict(rejects)}')
    return {'schema':'ugrp.grasp_act.release_plan.v1','episodes':episodes,'rejected_proposals':dict(rejects),
        'distribution':{'beam_yaw':'N-S +-8 deg, teal end south/north alternating','lateral_offset_m':[-.2,.2],
            'axial_strata_outside_m':STRATA,'handoff_max_m':HANDOFF_MAX_M,'handoff_pose_error_sigma':{'xy_m':POSE_ERROR[0],'yaw_rad':POSE_ERROR[1]},
            'prefix':'unchanged observable_v2 grasp teacher from grasp stations; prefix failures excluded from release outcomes and reported',
            'fixed':['floor_light_v1','camera review v3 runtime binding','native v7','weld off','teal/blue end scene']},
        'criteria':{'teacher_target_rate':.95,'minimum_episodes':40,
            'success':'landing rectangle inside zone, z<0.05, no finger contact, speed<0.01 m/s, tilt<3 deg, both grippers open (>=1900) and grip site >=4 cm from beam axis, for 2 s'},
        'student_evaluation':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,default=40)
    p.add_argument('--seed',type=int,default=74000);p.add_argument('--split',default='release_gate');a=p.parse_args()
    result=prepare(count=a.count,seed=a.seed,split=a.split)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'episodes':len(result['episodes']),'rejected':result['rejected_proposals']}))
if __name__=='__main__':main()
