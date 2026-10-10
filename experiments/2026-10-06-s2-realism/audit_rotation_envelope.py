"""s2v59 recorded own-RGB prefix audit, no physics/counterfactual trajectories.

Replay stops at the first newly blocked pulse. Original GT is read ONLY after
all control decisions and judges the unchanged admitted prefix through the
preceding pulse's full stopping horizon. A changed return path is not replayed.
"""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image
from harness import zone_solo_cyan_rotation_envelope as guard
from harness.zone_solo_cyan_pulse_cal import profile_key
from scripts.run_s2_unknown_start import runtime_factory
from harness import zone_solo_cyan_contract_v106 as c


def audit(raw):
    read=lambda name:json.loads((raw/name).read_text())
    b=read('bundle.json');b['options'].pop('active_localization')
    record=read('student_record.json')
    frames=[json.loads(line) for line in (raw/'robots/r3/frames.jsonl').read_text().splitlines()]
    times=np.array([q['sim_time'] for q in frames]);rows=[]
    runtime=runtime_factory(b)(c.hp.resolve(c.MAP_ID)[0],c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,**b['task'])
    try:
        for event in record['active_localization']['events']:
            pf=runtime.pose.provider.loc._pf;pf.load.loaded=event['state']=='carry'
            row=dict(t=event['t'],name=event['action']['name'],checks=[],observations=[],admitted_pulses=0)
            anchor=None;envelope=guard.RotationEnvelope();stop=None
            cmds=[q for q in record['commands'] if event['t']-1e-8<=q['t']<event['completed_t']-1e-8 and q['kind']=='mecanum']
            for command in cmds:
                t=command['t'];index=int(np.searchsorted(times,t+1e-8,side='right')-1)
                frame=frames[index];rgb=np.array(Image.open(raw/frame['path']).convert('RGB'))
                pose={int(k):v for k,v in frame['commanded_servo'].items()}
                if anchor is None:anchor=(frame['sim_time'],rgb)
                cm=pf.column_model_for(pose)
                obs=guard.yaw_measurement(anchor[1],rgb,cm,pose,runtime.flow.table)
                row['observations'].append(dict(t=t,from_t=anchor[0],**obs))
                reason=None
                if t-frame['sim_time']>guard.PARAMS['frame_max_age_s']+1e-8:reason='stale_rgb'
                elif not envelope.update(obs):reason=obs['status']
                else:
                    p=runtime.pulse_profiles[profile_key(command,pf.load.loaded)]
                    check=envelope.permit(p);row['checks'].append(dict(t=t,**check))
                    if not check['permitted']:reason='yaw_envelope'
                if reason:
                    stop=dict(t=t,reason=reason);break
                row['admitted_pulses']+=1;anchor=(frame['sim_time'],rgb)
            row.update(first_blocked=stop,prefix_end=stop['t'] if stop else event['completed_t'],
                       old_end=event['completed_t'],new_return_unknown=stop is not None)
            rows.append(row)
    finally:runtime.close()
    # Evaluation boundary: no truth object is visible above this line.
    truth=[json.loads(q) for q in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
    ts=np.array([q['t'] for q in truth]);yaw=np.unwrap([q['robot_yaw_rad'] for q in truth])
    for row in rows:
        y0=np.interp(row['t'],ts,yaw)
        for key,end in [('admitted_prefix_max_actual_deg',row['prefix_end']),('old_max_actual_deg',row['old_end'])]:
            selected=(ts>=row['t']-1e-8)&(ts<=end+1e-8)
            row[key]=float(np.max(abs(yaw[selected]-y0))*180/np.pi)
        row['prefix_violation']=row['admitted_prefix_max_actual_deg']>90.
    return dict(raw=str(raw),seed=b['task']['seed'],events=rows,physics_runs=0,
        gt='posthoc admitted-prefix evaluation only',counterfactual_post_stop_trajectory=False,
        violations=sum(q['prefix_violation'] for q in rows),
        all_events_have_admitted_motion=all(q['admitted_pulses']>0 for q in rows))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('raw',type=Path,nargs='+');a=p.parse_args()
    if a.output.exists():raise ValueError('preserve existing audit')
    results=[audit(raw) for raw in a.raw]
    out=dict(parameters=guard.PARAMS,runs=results,passed=all(q['violations']==0 and q['all_events_have_admitted_motion'] for q in results))
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(passed=out['passed'],runs=[{k:v for k,v in q.items() if k!='events'} for q in results])))
