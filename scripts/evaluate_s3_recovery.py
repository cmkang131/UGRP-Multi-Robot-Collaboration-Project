"""Post-run lease wait analysis; never an input to a robot controller."""
import json
import math
import numpy as np
from scripts.evaluate_s3_no_prior import metrics as previous, load_lines


def lease_deadlocks(protocol, trajectories, end):
    """Continuous wait survives revoke/regrant epoch churn; fixed 120s test."""
    active={r:None for r in ('r1','r2','r3')}
    waits=[]
    for event in protocol.get('events',[]):
        states={s['robot_id']:s['state'] for s in event['signals']}
        for rid,state in states.items():
            if state=='REQUEST' and active[rid] is None: active[rid]=event['sim_s']
            if state!='REQUEST' and active[rid] is not None:
                waits.append((rid,active[rid],event['sim_s'])); active[rid]=None
    waits.extend((r,t,end) for r,t in active.items() if t is not None)
    result=[]
    grants=[e for e in protocol.get('lease_events',[]) if e['event']=='grant']
    for rid,begin,until in waits:
        if until-begin<120:continue
        owners=next((g['team'] for g in reversed(grants) if g['sim_s']<=until and rid not in g['team']),[])
        stationary=bool(owners)
        for owner in owners:
            samples=[q for q in trajectories[owner] if until-120<=q['t']<=until]
            if not samples or samples[-1]['t']-samples[0]['t']<119.9:
                stationary=False;continue
            xy=np.asarray([q['robot_xyz_m'][:2] for q in samples])
            yaw=np.unwrap([q['robot_yaw_rad'] for q in samples])
            stationary &= float(np.linalg.norm(np.ptp(xy,axis=0)))<.01 and np.ptp(yaw)<math.radians(5)
        if stationary:
            same=next((r for r in result if r['owners']==owners and
                       abs(r['end']-until)<1e-6),None)
            if same:same['waiters'].append(rid)
            else:result.append(dict(start=until-120,end=until,duration_s=120,
                owners=owners,waiters=[rid],continuous_wait_start=begin))
    return result


def metrics(out):
    result=previous(out)
    student=json.loads((out/'student_record.json').read_text())
    protocol=student.get('door_yield',{})
    if protocol.get('profile')!='door_lease_v2':return result
    raw=json.loads((out/'result.json').read_text())
    end=raw.get('reset_sim_s',0)+raw.get('check_sim_s',0)
    trajectories={r:list(load_lines(out/f'eval_only/{r}/trajectory.jsonl')) for r in ('r1','r2','r3')}
    result['legacy_unchanged_status_deadlocks']=result['door_deadlocks']
    result['door_deadlocks']=lease_deadlocks(protocol,trajectories,end)
    result['failure_counts']['DOOR_DEADLOCK_EPISODES']=len(result['door_deadlocks'])
    result['door_lease']=dict(events=protocol['lease_events'],
        expiration_is_clearance=False,continuous_wait_diagnostic=True)
    return result
