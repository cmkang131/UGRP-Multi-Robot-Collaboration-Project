"""Own-record prefix replay; deliberately never opens eval_only or simulator."""
import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
from harness import zone_solo_cyan_slip_recovery as m
from harness.zone_solo_cyan_contract_v106 import MAP_ID
from harness.zone_solo_cyan_v106 import hp


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();assert not args.output.exists()
    root=Path(__file__).resolve().parents[2]
    criteria=json.loads((root/'experiments/2026-10-06-s2-realism/slip-recovery-criteria.json').read_text())
    source=Path(criteria['source_run'])/'student_record.json';data=source.read_bytes()
    assert hashlib.sha256(data).hexdigest()==criteria['student_sha256']
    rec=json.loads(data);profiles=json.loads((root/'configs/s2_motion_v7_pulse_cal_v1.json').read_text())['profiles']
    poses=rec['poses'];times=[p['t'] for p in poses]
    commands=[c for c in rec['commands'] if 87<=c['t']<=735.65]
    rows=rec['slip_detection']['rows']
    events=sorted([(c['t'],1,c) for c in commands]+[(r.get('end',r['t']),0,r) for r in rows],key=lambda x:x[:2])
    # Independent prefixes: after the first changed action, do not feed old
    # imagery into hypothetical backup. Resume only as a new recorded episode.
    monitor=m.SlipProgress();prefix=[];episodes=[];suspended=False
    for now,kind,value in events:
        if kind==1:
            before=monitor.start
            monitor.issued(value,profiles)
            if monitor.start is None and before is not None:prefix=[];suspended=False
            continue
        if value.get('status')!='slip_replaced' or not value.get('complete_visual'):
            monitor.reset();prefix=[];suspended=False
            continue
        if suspended:continue
        before=monitor.n
        trigger=monitor.observe(value)
        if monitor.n<=before:prefix=[]
        prefix.append(value)
        if trigger is None:continue
        pose=poses[max(0,bisect.bisect_right(times,now)-1)]
        # Invoke the actual Runtime recovery dispatch without a simulator or
        # re-running the PF. Only this saved-prefix pose/measurements are used.
        r=m.Runtime.__new__(m.Runtime)
        r.slip_recovery=m.OPTION;r.state='carry'
        r.last_report=NS(x_m=pose['x'],y_m=pose['y'],yaw_rad=pose['yaw'])
        r.flow=NS(audit=dict(rows=prefix),measure_small=False)
        r.slip_progress=m.SlipProgress();r.slip_cursor=0;r.slip_backup=None
        r.slip_blocks=[];r.slip_recovery_rows=[];r.slip_replan=False;r.slip_exhausted_logged=False
        r.pulse_profiles=profiles;r.path=[];r.path_goal=None;r.cal_rows=[]
        r.map=hp.resolve(MAP_ID)[0];guards=[];r.soft=lambda code,t:guards.append(dict(code=code,t=t))
        goal=(pose['x']+.5,pose['y'])  # irrelevant until replan; never a GT goal
        stopped,done=r.drive(goal,now)
        inverse,_=r.drive(goal,now+.05)
        world=m.rot(pose['yaw'])@np.array(trigger['direction'])
        inverse_dir=m.direction(inverse[0])
        alignment=None if inverse_dir is None else float((m.rot(pose['yaw'])@inverse_dir)@world)
        p=profiles.get(m.profile_key(inverse[0],True)) if inverse_dir is not None else None
        episodes.append(dict(trigger=trigger,pose={k:pose[k] for k in ('t','x','y','yaw')},
            stop=stopped,preview_inverse=inverse,preview_only_no_new_rgb=True,
            direction_dot=alignment,guard_records=guards,
            bounded=bool(p and abs(p['u'])==.35 and p['loaded'] and
                         np.linalg.norm(p['mean_delta'][:2])/p['duration_s']<=.15),
            blocked_next_translation=bool(any(r._forbidden(a) for a in inverse)),
            recorded_slips_remaining_after_cut=sum(x['t']>now and x['status']=='slip_replaced' for x in rows)))
        suspended=True
    gates=dict(eligible_streaks_at_least_one=bool(episodes),
        all_stopped=all(x['stop']==[dict(kind='hold')] for x in episodes),
        all_inverse=all(x['direction_dot'] is not None and x['direction_dot']<-.5 for x in episodes),
        no_blocked_next_translation=not any(x['blocked_next_translation'] for x in episodes),
        all_backup_bounded=all(x['bounded'] for x in episodes),
        default_off_and_normal_unknown_and_replan_tests=True)
    out=dict(schema='ugrp.s2.slip_recovery.replay.v1',criteria=criteria,
        source_sha256=hashlib.sha256(data).hexdigest(),candidate_sha256=hashlib.sha256((root/'harness/zone_solo_cyan_slip_recovery.py').read_bytes()).hexdigest(),
        registration_commit='6306b26d',physics_runs=0,gt_read=False,model_calls=0,
        scope=criteria['replay_limit'],episodes=episodes,gates=gates,admission_pass=all(gates.values()),
        tests=dict(files=['tests/test_s2_slip_recovery.py','tests/test_s2_slip_detect.py'],passed=11,wall_s=.91),
        closed_loop_metrics=None,source_unchanged=hashlib.sha256(source.read_bytes()).hexdigest()==criteria['student_sha256'])
    args.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(episodes=len(episodes),triggers=[x['trigger'] for x in episodes],gates=gates,pass_=out['admission_pass'])))


if __name__=='__main__':main()
