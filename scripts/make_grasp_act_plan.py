"""Offline stratified episode plan; does not construct or step a simulator."""
import argparse,hashlib,json,math,random
from collections import Counter
from pathlib import Path
from harness.zone_final_environment import resolve
from harness.static_keepouts import keepout_rects,pose_clear,rect_distance

ROOT=Path(__file__).resolve().parents[1]
SCENARIOS=('s1_normal_mixed_v4','s3_late_rendezvous_v4','s6_novel_relation_v4')
HELDOUT='s4_narrow_door_standoff_v4'
BASE_Z=.032355118817659255


def prepare(*,count=40,seed=71000,split='teacher_gate',pair=True):
    episodes=[];rejects=Counter()
    for i in range(count):
        rng=random.Random(seed+i)
        scenario_id=HELDOUT if split=='heldout_map' else SCENARIOS[i%len(SCENARIOS)]
        path=ROOT/'configs/zone_study_scenarios_v4'/f'{scenario_id}.json'
        scenario=json.loads(path.read_text());static,_,_=resolve(scenario['map_id'])
        bounds=static['bounds_m'];rects=keepout_rects(static,perimeter=True)
        pickup=static['regions']['pickup'];cx,cy=pickup['center_m'];hx,hy=pickup['half_extents_m']
        end='teal' if i%2==0 else 'blue'
        peer=('other_end','approaching','near_own')[i%3] if pair else 'absent'
        def free(p,r):
            return bounds[0]+r<=p[0]<=bounds[1]-r and bounds[2]+r<=p[1]<=bounds[3]-r and all(rect_distance(p,rect)>=r for rect in rects)
        placements=scenario['eval']['setup']['placements']
        others=[p for p in placements if p['item_id']!='beam_1']
        for attempt in range(5000):
            # Each block spans the angle/range bins; rejection is counted, never hidden.
            a=2*math.pi*((i%12+rng.random())/12)
            beam=[rng.uniform(cx-hx+.05,cx+hx-.05),rng.uniform(cy-hy+.05,cy+hy-.05),a]
            footprint=[(-.3,-.02),(.3,-.02),(.3,.02),(-.3,.02)]
            if not pose_clear(beam,footprint,rects,bounds=bounds,margin=.005):rejects['beam_wall']+=1;continue
            if any(math.dist(beam[:2],p['pose_m'][:2])<.38 for p in others):rejects['beam_other_cargo']+=1;continue
            r=.5+1.5*(((i+attempt)%10+rng.random())/10);az=a+2*math.pi*(((i*7+attempt)%12+rng.random())/12)
            own=[beam[0]+r*math.cos(az),beam[1]+r*math.sin(az)]
            facing=math.atan2(beam[1]-own[1],beam[0]-own[0]);ownyaw=facing+rng.uniform(-math.pi/3,math.pi/3)
            heading=a+(math.pi if end=='blue' else 0.)
            # The peer's opposite assigned end does not change when it starts near our end.
            if peer=='other_end':pa=heading
            elif peer=='near_own':pa=heading+math.pi+.65
            else:pa=a+rng.uniform(0,2*math.pi)
            pr=.473 if peer=='other_end' else rng.uniform(.65,1.4)
            other=[beam[0]+pr*math.cos(pa),beam[1]+pr*math.sin(pa)]
            otheryaw=math.atan2(beam[1]-other[1],beam[0]-other[0])
            active=[own,other] if pair else [own]
            if any(not free(p,.18) for p in active):rejects['robot_wall']+=1;continue
            if any(math.dist(p,q['pose_m'][:2])<.24 for p in active for q in others):rejects['robot_other_cargo']+=1;continue
            if pair and math.dist(own,other)<.37:rejects['robot_overlap']+=1;continue
            if any(math.dist(p,beam[:2])<.46 for p in active):rejects['robot_beam']+=1;continue
            # Park inactive robots in valid free cells away from all task bodies.
            parking=[]
            for _ in range(2000):
                p=[rng.uniform(bounds[0]+.2,bounds[1]-.2),rng.uniform(bounds[2]+.2,bounds[3]-.2)]
                if free(p,.18) and all(math.dist(p,q)>.6 for q in active+parking+[beam[:2]]) and all(math.dist(p,q['pose_m'][:2])>.3 for q in others):parking.append(p)
                if len(parking)==(1 if pair else 2):break
            if len(parking)!=(1 if pair else 2):rejects['no_parking']+=1;continue
            spawns={'r1':[*own,BASE_Z,ownyaw],'r2':[*other,BASE_Z,otheryaw] if pair else [*parking[0],BASE_Z,0.],
                    'r3':[*parking[-1],BASE_Z,0.]}
            roles={'r1':end,**({'r2':'blue' if end=='teal' else 'teal'} if pair else {})}
            row={'episode_id':f'{split}-{seed+i}','batch':f'grasp-act-{split}-{seed}','seed':seed+i,'split':split,
                 'scenario_id':scenario_id,'scenario_source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                 'map_id':scenario['map_id'],'beam_pose':beam,'spawns':spawns,'roles':roles,
                 'target_item':'beam_1','object_kind':'long_beam','assignment_source':'demo_rule_color_balanced',
                 'end_color_scene':'grasp_act_teal_blue_v1','peer_case':peer,
                 'initial_pan':{rid:rng.randint(500,2500) for rid in roles},
                 'initial_scene_context':'original scenario inventory; task beam/setup spawns randomized',
                 'proposal_attempts':attempt+1,'near_wall':min(rect_distance(beam,rect) for rect in rects)<.45}
            episodes.append(row);break
        else:raise ValueError(f'no admissible start for index {i}; rejection counts {rejects}')
    return {'schema':'ugrp.grasp_act.plan.v1','episodes':episodes,'rejected_proposals':dict(rejects),
        'distribution':{'beam_yaw_deg':[0,360],'robot_center_distance_m':[.5,2.],
        'robot_axis_bearing_deg':[0,360],'robot_heading_error_deg':[-60,60],'initial_pan_pwm':[500,2500],
        'ends':'50:50 by index','fixed':['floor_light_v1','camera review v3','native v7','cargo_noslip_v1','weld off'],
        'limits':'static rejection alters accepted strata; accepted plan is the source of actual coverage. Intermediate placed objects and moving work peers are a later collection stage.'},
        'criteria':{'teacher_target_rate':.95,'minimum_episodes':40,'single_end':'bilateral >=0.5N each and end rise >=12mm for >=1s',
        'pair':'both bilateral + whole beam lower surface >=12mm above floor for >=1s',
        'first_attempt':'no teacher regrasp in this gate','phase_cap_s':60,'episode_cap_s':60,'target_pair_sim_s':40},
        'stage_order':['long_beam','solo boxes/can/tile grasp and release','heavy_crate','tri_frame'],
        'student_evaluation':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--count',type=int,default=40)
    p.add_argument('--seed',type=int,default=71000);p.add_argument('--split',choices=('teacher_gate','train','development','heldout_start','heldout_map'),default='teacher_gate')
    p.add_argument('--single',action='store_true');a=p.parse_args()
    result=prepare(count=a.count,seed=a.seed,split=a.split,pair=not a.single)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'episodes':len(result['episodes']),'rejected':result['rejected_proposals']}))
if __name__=='__main__':main()
