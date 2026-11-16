"""Independent saved-state action replays. No simulator, images or GT needed."""
import copy, hashlib, json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
from harness import zone_solo_cyan_slip_recovery as m
from harness.zone_solo_cyan_pulse_cal import select_pulse
from harness.zone_solo_cyan_contract_v106 import MAP_ID
from harness.zone_solo_cyan_v106 import hp

HERE=Path(__file__).resolve().parent
OUT=Path('/Users/changmin/projects/ugrp/outputs/s2-ground-vo-20261007')
def main():
    criteria=json.loads((HERE/'ground-vo-criteria.json').read_text())
    raw=Path(criteria['recovery_raw']);s=json.loads((raw/'student_record.json').read_text())
    b=json.loads((raw/'bundle.json').read_text());profiles=b['pulse_calibration']['profiles']
    events=s['slip_recovery']['rows'];block=next(x['block'] for x in events if x['event']=='progress_failed_stop')
    end=next(x for x in events if x['event']=='backup_end');path=next(x['path'] for x in events if x['event']=='replan')
    pose=s['poses'][-1];r=m.Runtime.__new__(m.Runtime)
    r.last_report=NS(x_m=pose['x'],y_m=pose['y'],yaw_rad=pose['yaw'])
    r.slip_blocks=[copy.deepcopy(block)];r.slip_attempts=1;r.slip_progress=m.SlipProgress()
    r.slip_recovery_rows=[];r.slip_replan=True;r.path=copy.deepcopy(path);r.path_goal=tuple(path[-1])
    r.map=hp.resolve(MAP_ID)[0];r.soft=lambda *a:None
    error=m.rot(-pose['yaw'])@(np.array(path[0])-[pose['x'],pose['y']])
    before={k:p for k,p in profiles.items() if not r._forbidden(m.action_of(p))}
    old,old_cost=select_pulse(before,True,error,pose['yaw'])
    # Calls real post-recovery clear + replan; retry counter survives.
    r._replan_slip(path[-1],end['t'])
    after={k:p for k,p in profiles.items() if not r._forbidden(m.action_of(p))}
    new,new_cost=select_pulse(after,True,error,pose['yaw'])
    # Replay each saved suppression state independently. Counterfactual motion
    # changes subsequent RGB, so these are not a synthetic closed-loop run.
    samples=[];times=np.array([p['t'] for p in s['poses']])
    for event in events:
        if event['event']!='blocked_translation_suppressed':continue
        p=s['poses'][max(0,np.searchsorted(times,event['t'],side='right')-1)]
        r.last_report=NS(x_m=p['x'],y_m=p['y'],yaw_rad=p['yaw'])
        samples.append(dict(t=event['t'],still_vetoed=any(r._forbidden(a) for a in event['proposed'])))
    gates=dict(old_deadlock_reproduced=old is None,new_progress_action=new is not None,
        all_saved_vetoes_cleared=bool(samples) and not any(x['still_vetoed'] for x in samples),
        temporary_blocks_empty=not r.slip_blocks,retry_budget_preserved=r.slip_attempts==1)
    out=dict(schema='ugrp.s2.recovery_clear.replay.v1',criteria_commit='a4db20e6',
        source_sha256=hashlib.sha256((raw/'student_record.json').read_bytes()).hexdigest(),
        old_action=old,new_action=None if new is None else m.action_of(new),old_cost=old_cost,new_cost=new_cost,
        recovery_end=end,clear_events=r.slip_recovery_rows,saved_suppressed=len(samples),
        remaining_vetoes=sum(x['still_vetoed'] for x in samples),gates=gates,pass_=all(gates.values()),
        gt_inputs=False,physics_runs=0,model_calls=0,closed_loop_escape_proven=False)
    with (OUT/'recovery-clear.json').open('x') as f:json.dump(out,f,indent=2)
    print(json.dumps(out))
if __name__=='__main__':main()
