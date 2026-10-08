"""Post-score causal-map support diagnostic. GT solely in this evaluation file."""
from replay import *


def main():
    if (EXP/'results/support-diagnosis.json').exists():raise ValueError('DIAGNOSIS_ALREADY_SAVED')
    result=load(EXP/'results/utility-on.json')
    detail=load(RAW/'evaluation-details-on.json')
    truth=rows(EP/'eval_only/trajectory.jsonl');origin=np.r_[truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
    reports=[]
    for trial in range(3):
        key=f'own-{trial}';v=detail[key];pred=load(RAW/f'own-on-{trial}.json');g=load(snapshot_path('own',trial))
        cells={tuple(c[:2]):c[2] for c in g['cells']}
        actual=np.array([between(origin,p) for p in v['true_world']])
        states=[]
        for xy in actual[:,:2]:
            odds=cells.get(tuple(np.floor(xy/g['resolution_m']).astype(int)),0.)
            states.append('free' if odds<0 else 'occupied' if odds>0 else 'unknown')
        good=(np.array(v['xy_m'])<=.25)&(np.array(v['yaw_deg'])<=10)
        stable=np.array([r['stable_resolved'] for r in pred['rows']])
        falsely=np.array([bool(stable[i] and not good[max(0,i-4):i+1].all()) for i in range(len(good))])
        reports.append(dict(trial=trial,frames=len(states),true_body_center_snapshot_membership={k:states.count(k) for k in ('free','occupied','unknown')},
            final_center_membership=states[-1],false_stable_frames=int(falsely.sum()),
            false_when_current_center_unknown=int(sum(f and s=='unknown' for f,s in zip(falsely,states))),
            first_false_t=None if not falsely.any() else v['t'][int(np.flatnonzero(falsely)[0])],
            final_error_m=v['xy_m'][-1],final_std_xy_m=pred['rows'][-1]['global_std_xy_m'],
            note='GT membership is diagnostic only; no prior insertion/filter correction'))
    dump(EXP/'results/support-diagnosis.json',dict(own=reports,evaluation_only=True,retuning=0))
    print(json.dumps(reports,indent=2))


if __name__=='__main__':main()
