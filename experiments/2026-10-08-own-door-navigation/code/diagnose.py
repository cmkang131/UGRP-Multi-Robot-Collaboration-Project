"""Post-seal cause tables only. No detector/navigation parameters are fitted."""
from offline import *
from harness.own_door_memory import geometry
from collections import Counter


def diagnose():
    output=[]
    for case in COHORT:
        path=RAW/case/'prediction.json'
        if not path.exists():continue
        p=load(path);r=load(EXP/'results'/f'{case}.json');ep=COHORT[case]
        own={round(x['t'],6):x for x in rows(ep/'own-controller.jsonl') if x.get('pose') is not None}
        gt={round(x['t'],6):x for x in rows(ep/'eval_only/trajectory.jsonl')}
        static=load(ep/'inputs/static_map.json');ds=static['passages'];truth=[]
        for d in p['tracks']:
            key=round(d['first_t'],6)
            if key not in gt or key not in own:continue
            q=copy.deepcopy(d);pose=own[key].get('local_pose',own[key]['pose']);actual=[*gt[key]['robot_xyz_m'][:2],gt[key]['robot_yaw_rad']]
            q['endpoints']=transform(transform(d['endpoints'],inverse(pose)),actual).tolist();truth.append(q)
        scored=metrics(truth,ds,[0,0,0],[])
        output.append(dict(case=case,types=dict(Counter(d['kind'] for d in p['tracks'])),
            first_geometry_with_actual_frame_pose=dict(tp=scored['tp'],fp=scored['fp'],n=scored['n'],
                geometrically_matching_including_duplicates=sum(x['match'] is not None for x in scored['matches'])),
            first_geometry_with_saved_pose=dict(tp=r['metrics']['on']['tp'],n=r['metrics']['on']['n'],
                geometrically_matching_including_duplicates=sum(x['match'] is not None for x in r['metrics']['on']['matches'])),
            confirmed=p['confirmed'],reasons=p['reasons']))
    dump(EXP/'results/diagnosis.json',dict(cases=output,qualification='EVALUATION ONLY GT pose placement; no control use; no retuning'))

if __name__=='__main__':diagnose()
