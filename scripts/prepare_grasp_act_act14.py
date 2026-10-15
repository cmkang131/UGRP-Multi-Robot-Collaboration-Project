"""Bounded static setup sampling using the ACT11/12 frozen teacher distribution.

No simulator. All geometric truth stays in setup/rejection evidence, outside
student requests. Thresholds below are unchanged 6f057f7e plan constants.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import random

from harness.grasp_act_data import sha256, write_json
from scripts.run_grasp_act_recovery import dependency_modules


def sample(i,kind,seed,p,ledger,counts):
    rng=random.Random(seed)
    pool=p.candidates(kind)
    def reject(stage,blocker,gap):
        ledger.append({'seed':seed,'category':stage,'blocking_object':blocker,'minimum_gap_m':gap})
    for attempt in range(400):  # frozen plan proposal count, not wall time
        sid,path,scenario,placement=pool[(i+attempt)%len(pool)]
        counts['candidate']+=1
        static,_,_=p.resolve(scenario['map_id'])
        bounds,rects=static['bounds_m'],p.keepout_rects(static,perimeter=True)
        others=[q for q in scenario['eval']['setup']['placements'] if q['item_id']!=placement['item_id']]
        cx,cy=placement['pose_m'][:2]; station=p.cargo(kind).station_m or .2002
        def nearest(point):
            distances=[('map_boundary',min(point[0]-bounds[0],bounds[1]-point[0],point[1]-bounds[2],bounds[3]-point[1]))]
            distances += [('static_rect_'+str(j),p.rect_distance(point,r)) for j,r in enumerate(rects)]
            distances += [(q['item_id'],math.dist(point,q['pose_m'][:2])) for q in others]
            return min(distances,key=lambda q:q[1])
        def free(point):
            return (bounds[0]+p.FREE_ROBOT_M<=point[0]<=bounds[1]-p.FREE_ROBOT_M and
                bounds[2]+p.FREE_ROBOT_M<=point[1]<=bounds[3]-p.FREE_ROBOT_M and
                all(p.rect_distance(point,r)>=p.FREE_ROBOT_M for r in rects))
        final=(cx-station,cy)
        if not free(final) or any(math.dist(final,q['pose_m'][:2])<.25 for q in others):
            reject('station_blocked',*nearest(final));continue
        counts['station_clear']+=1
        radius=rng.uniform(*p.START_RANGE_M);phi=rng.uniform(-math.radians(55),math.radians(55))
        start=(cx-radius*math.cos(phi),cy+radius*math.sin(phi))
        if not free(start) or any(math.dist(start,q['pose_m'][:2])<.35 for q in others):
            reject('start_blocked',*nearest(start));continue
        counts['start_clear']+=1
        if not p.line_of_sight(start,(cx,cy),rects,others):
            # The frozen predicate samples every .02m with .05m cargo clearance.
            n=max(2,int(math.dist(start,(cx,cy))/.02))
            points=[(start[0]+(cx-start[0])*j/n,start[1]+(cy-start[1])*j/n) for j in range(n)]
            blocker,gap=min((nearest(point) for point in points),key=lambda x:x[1])
            reject('target_hidden_from_start',blocker,gap);continue
        counts['line_of_sight']+=1
        yaw=math.atan2(cy-start[1],cx-start[0])+rng.uniform(-p.FACING_JITTER,p.FACING_JITTER)
        parking=[]
        for _ in range(2):
            for _try in range(2000):  # same bounded parking computation
                point=(rng.uniform(bounds[0]+.2,bounds[1]-.2),rng.uniform(bounds[2]+.2,bounds[3]-.2))
                if free(point) and all(math.dist(point,q)>.7 for q in [start,final,(cx,cy),*parking]) and all(math.dist(point,q['pose_m'][:2])>.35 for q in others):
                    parking.append(point);break
        if len(parking)<2:reject('no_parking',*nearest(point));continue
        counts['parking_clear']+=1
        error=[rng.gauss(0,p.POSE_ERROR[0]),rng.gauss(0,p.POSE_ERROR[0]),rng.gauss(0,p.POSE_ERROR[1])]
        bearing=math.atan2(cy-start[1],cx-start[0])-yaw
        return {'seed':seed,'skill':'grasp','object_kind':kind,'kind':kind,'role':'west','robot_id':'r1',
                'scenario_id':sid,'setup_source_sha256':sha256(path),'item_id':placement['item_id'],
                'target_setup_xy':[cx,cy],'cargo_pose_m':placement['pose_m'],
                'spawns':{'r1':[*start,p.BASE_Z,yaw],'r2':[*parking[0],p.BASE_Z,0.],'r3':[*parking[1],p.BASE_Z,0.]},
                'handoff_pose_error':error,'proposal_attempts':attempt+1,'start_bearing_deg_setup_only':math.degrees(bearing)}
    raise ValueError('no admissible frozen-distribution start')


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--dependency-root',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    args=a.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    ledger=[];counts=Counter();plans=[]
    with dependency_modules(args.dependency_root):
        from scripts import make_solo_teacher_plan as p
        for j,seed in enumerate(range(91420,91443)):
            plans.append(sample(j//4,('cyan','red','green','yellow')[j%4],seed,p,ledger,counts))
    for e in plans:write_json(args.output/(str(e['seed'])+'.json'),e)
    # Fresh IDs cannot literally reuse difficult ACT11 seeds. Prioritize their
    # high-bearing stratum while preserving freshly sampled poses and seeds.
    main_plans=sorted(plans[:20],key=lambda e:-abs(e['start_bearing_deg_setup_only']))
    pilots=sorted(plans[20:],key=lambda e:-abs(e['start_bearing_deg_setup_only']))
    write_json(args.output/'plan.json',{'pilot_seeds':[e['seed'] for e in pilots],
        'main_seeds':[e['seed'] for e in main_plans],'episodes':plans,
        'scene_dependency_sha':'6f057f7e97c1a3aec9e8c398b8d9068e27b25df8',
        'ordering':'fresh seeds by descending absolute starting bearing; ACT11 hard stratum, never reused gate seeds',
        'external_perturbations':'off; ACT alone issues commands'})
    write_json(args.output/'setup-funnel.json',{'schema':'ugrp.act14.setup_funnel.v1','counts':dict(counts),
        'rejections':ledger,'rejection_distribution':dict(Counter(e['category'] for e in ledger)),
        'source':str(args.output/'plan.json'),'reproduce':'python -m scripts.prepare_grasp_act_act14 --dependency-root '+str(args.dependency_root)+' --output NEW_DIR'})


if __name__=='__main__':main()
