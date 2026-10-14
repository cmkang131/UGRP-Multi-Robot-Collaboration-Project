"""Offline map-to-ACT handoff starts; the wide physical gate stays separate."""
import argparse,json,math,random
from collections import Counter
from pathlib import Path
from scripts.make_grasp_act_plan import prepare,ROOT
from harness.zone_final_environment import resolve
from harness.static_keepouts import keepout_rects,rect_distance


def handoff_plan(*,count,seed,split):
    if split=='teacher_gate':raise ValueError('wide gate and local training starts must remain separate')
    plan=prepare(count=count,seed=seed,split=split);rejects=Counter()
    for row in plan['episodes']:
        rng=random.Random(row['seed']+10000000);static,_,_=resolve(row['map_id'])
        bounds=static['bounds_m'];rects=keepout_rects(static,perimeter=True)
        scenario=json.loads((ROOT/'configs/zone_study_scenarios_v4'/f"{row['scenario_id']}.json").read_text())
        cargo=[p['pose_m'][:2] for p in scenario['eval']['setup']['placements'] if p['item_id']!='beam_1']
        bx,by,a=row['beam_pose'];selected=[];jitters={}
        for rid,end in row['roles'].items():
            d=-.27 if end=='teal' else .27;target=[bx+d*math.cos(a),by+d*math.sin(a)]
            for attempt in range(5000):
                bearing=rng.uniform(0,2*math.pi);distance=rng.uniform(.3,.8)
                nominal=[target[0]+distance*math.cos(bearing),target[1]+distance*math.sin(bearing)]
                tail=rng.random()<.1;sigma=.18 if tail else .055
                jitter=[rng.gauss(0,sigma),rng.gauss(0,sigma)];xy=[x+j for x,j in zip(nominal,jitter)]
                if not .3<=math.dist(xy,target)<=.8:rejects['range_after_jitter']+=1;continue
                if not (bounds[0]+.18<=xy[0]<=bounds[1]-.18 and bounds[2]+.18<=xy[1]<=bounds[3]-.18) or any(rect_distance(xy,r)<.18 for r in rects):rejects['wall']+=1;continue
                # Preserve the same physical non-overlap constraints as the wide plan.
                if math.dist(xy,[bx,by])<.46 or any(math.dist(xy,p)<.24 for p in cargo) or any(math.dist(xy,p)<.37 for p in selected):rejects['cargo_or_peer']+=1;continue
                heading_error=max(-60.,min(60.,rng.gauss(0,30. if tail else 10.)))
                heading=math.atan2(target[1]-nominal[1],target[0]-nominal[0])+math.radians(heading_error)
                row['spawns'][rid]=[*xy,row['spawns'][rid][2],heading];selected.append(xy)
                jitters[rid]={'nominal_xy':nominal,'xy_error_m':jitter,'heading_error_deg':heading_error,'tail':tail,'accepted_distance_m':math.dist(xy,target)}
                break
            else:raise ValueError('no admissible local handoff start')
        row['handoff_distribution']=jitters;row['purpose']='local ACT training/development; not physical gate'
    plan['handoff_rejected_proposals']=dict(rejects)
    plan['distribution']={'assigned_end_distance_m':[.3,.8],'xy_jitter':'90% N(0,.055m)^2 + 10% N(0,.18m)^2; radial median about .07m before rejection',
        'heading_jitter_deg':'90% N(0,10)^2 / tail N(0,30)^2, clipped +/-60 deg','render':'unchanged; separate DR toggle owned by release task',
        'accepted_range_and_nonoverlap_rejection_logged':True}
    return plan


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--count',type=int,default=50);p.add_argument('--seed',type=int,required=True)
    p.add_argument('--split',choices=('train','development','heldout_start','heldout_map'),required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=handoff_plan(count=a.count,seed=a.seed,split=a.split)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
