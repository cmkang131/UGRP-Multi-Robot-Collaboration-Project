"""Frozen v133 own RGB/commands; evaluate GT only after six predictions seal."""
import argparse
import base64
import copy
import hashlib
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

from harness import zone_solo_cyan_contract_v106 as c
from harness import zone_pair_highpose_frame_gate as gate
from harness.zone_pair_highpose_exact_speedups import install
from harness.zone_solo_cyan_rotation_left import attach, OPTION, calibration
from scripts.run_s2_landmarks_dev import runtime_factory
from scripts.audit_s2_formal_stops import RUNS, OUTPUTS, read, rows, sha, decisions, uncertain, pose_audit, truth_at, wrap

HERE = Path(__file__).resolve().parent
CRITERIA = HERE/'rotation-left-criteria.json'


def replay(seed, option, out, max_frames=None):
    target = out/f's{seed}-{option}.json'
    if target.exists(): raise FileExistsError(target)
    raw = OUTPUTS/RUNS[seed]; b = read(raw/'bundle.json'); old = read(raw/'student_record.json')
    frames = rows(raw/'robots/r3/frames.jsonl')
    if max_frames: frames = frames[:max_frames]
    commands = {}
    for q in old['commands']: commands.setdefault(round(q['t'], 6), []).append(q)
    _, undo = install('v98-exact-v6')
    runtime = attach(runtime_factory(b)(c.hp.resolve(c.MAP_ID)[0], c.ROOT/c.CALIBRATION,
        c.CALIBRATION_SHA, **b['task']), rotation_calibration=OPTION if option=='on' else 'off',
        servo_stiffness=b['options']['servo_stiffness'])
    initial = commands[round(frames[0]['sim_time'], 6)].pop(0)
    runtime.initial_commands(initial['t'], {'r3': {int(k):v for k,v in initial['pulses'].items()}})
    pred = []; cloud = hashlib.sha256(); max_delta = 0.; first_mismatch = None
    reference = {round(p['t'], 6):p for p in old['poses']}
    fields = ('t_est','x','y','yaw','std_xy_m','std_yaw_rad','last_fix_t')
    try:
        for i,f in enumerate(frames):
            now = f['sim_time']; data = (raw/f['path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != f['sha256']: raise ValueError('RGB_CHANGED')
            rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
            verdict,_ = gate.gate().assess({**f,'image':base64.b64encode(data).decode()},'r3',now,ob=False)
            p = runtime.pose.on_frame(now,rgb if verdict==gate.VALID else None)
            q = dict(t=now,t_est=p.t_est,x=p.x_m,y=p.y_m,yaw=p.yaw_rad,
                     std_xy_m=p.std_xy_m,std_yaw_rad=p.std_yaw_rad,last_fix_t=p.last_fix_t,
                     observation_quality=copy.deepcopy(p.observation_quality))
            pred.append(q); ref = reference[round(now,6)]
            delta = max(abs(q[k]-ref[k]) if q[k] is not None and ref[k] is not None
                        else float(q[k]!=ref[k]) for k in fields)
            max_delta = max(max_delta,delta)
            if delta>1e-9 and first_mismatch is None: first_mismatch=dict(t=now,delta=delta)
            pf=runtime.pose.provider.loc._pf
            cloud.update(pf.px.tobytes()); cloud.update(pf._weights().tobytes())
            for cmd in commands.get(round(now,6),[]):
                runtime.on_command('r3',now,{k:v for k,v in cmd.items() if k!='t'})
            if i%500==0: print(seed,option,i,'/',len(frames),'max_delta',max_delta,flush=True)
        result = dict(seed=seed,option=option,poses=pred,amcl=copy.deepcopy(runtime.amcl_audit),
            slip=copy.deepcopy(runtime.flow.audit),rotation=copy.deepcopy(getattr(runtime,'rotation_left_audit',None)),
            max_delta_from_record=max_delta,first_mismatch=first_mismatch,
            particle_trajectory_sha256=cloud.hexdigest(),partial=bool(max_frames),
            source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            criteria_sha256=sha(CRITERIA),gt_inputs=False,commands_fixed=True,physics_runs=0,
            input_hashes={name:sha(raw/name) for name in ('bundle.json','student_record.json','robots/r3/frames.jsonl')})
    finally:
        runtime.close(); undo()
    out.mkdir(parents=True,exist_ok=True); target.write_text(json.dumps(result)+'\n')
    if option=='off': assert max_delta<=1e-9, first_mismatch
    print(seed,option,'SEALED',len(pred),'updates',result['amcl']['updates'],flush=True)


def score(out):
    # All predictions must exist first; neither prediction nor control reads GT.
    for seed in RUNS:
        for opt in ('off','on'):
            assert not read(out/f's{seed}-{opt}.json')['partial']
    result = dict(schema='ugrp.s2.rotation_left_replay.v1',criteria=read(CRITERIA),
                  gt_use='posthoc only, after all off/on predictions sealed',physics_runs=0,runs=[])
    totals = {opt:dict(carry_squared_error_sum=0.,carry_frames=0,alarms=0,
                      nees_above=0,nees_available=0,unflagged_above_25cm=0,
                      eligible_yaw_squared_error_sum=0.,eligible_count=0) for opt in ('off','on')}
    for seed,name in RUNS.items():
        raw=OUTPUTS/name; record=read(raw/'student_record.json'); truth=rows(raw/'eval_only/trajectory.jsonl')
        times=np.array([q['t'] for q in truth]); xy=np.array([q['robot_xyz_m'][:2] for q in truth])
        navigation=decisions(record); case=dict(seed=seed,conditions={})
        begin=next(e['t'] for e in record['events'] if e['event']=='state' and e['state']=='carry')
        end=next(e['t'] for e in record['events'] if e['event']=='state' and e['state']=='real_carry_return')
        eligible_times={round(q['t'],6) for q in (read(out/f's{seed}-on.json')['rotation'] or {})['rows']}
        for opt in ('off','on'):
            pred=read(out/f's{seed}-{opt}.json'); poses=pred['poses']; by_t={round(p['t'],6):p for p in poses}
            # Same recorded drive-decision opportunities, not counterfactual closed-loop commands.
            synthetic=copy.deepcopy(record); synthetic['poses']=poses
            synthetic['events']=[e for e in record['events'] if not (e.get('event')=='dev_light_would_stop' and e.get('code')=='POSE_UNCERTAIN')]
            synthetic['dev_light_would_stop']['POSE_UNCERTAIN']=sum(uncertain(by_t[round(q['t'],6)]) for q in navigation)
            audit=pose_audit(synthetic,truth)
            window=[p for p in poses if begin<=p['t']<end]
            errors=[float(np.linalg.norm(np.array([p['x'],p['y']])-[np.interp(p['t_est'],times,xy[:,j]) for j in (0,1)])) for p in window]
            pulses=[]
            for q in record['pulse_motion_model']['transformations']:
                action=q['issued']
                if not action.get('turn'):continue
                prof=record['pulse_motion_model']['model']['profiles'][q['profile_key']]
                t=q['t']; at=t+prof['times'][-1]; gt0=truth_at(truth,t); gt1=truth_at(truth,at)
                p=min(poses,key=lambda x:abs(x['t_est']-at)); delta=wrap(gt1[2]-gt0[2])
                eligible=round(t,6) in eligible_times
                expected=prof['mean_delta'][2]*(calibration()['gain'] if opt=='on' and eligible else 1.)
                pulses.append(dict(t=t,profile=q['profile_key'],eligible=eligible,actual_yaw_delta_deg=float(np.degrees(delta)),
                    command_model_residual_deg=float(np.degrees(wrap(expected-delta))),report_t_est=p['t_est'],
                    report_yaw_residual_deg=float(np.degrees(wrap(p['yaw']-truth_at(truth,p['t_est'])[2])))))
            n=audit['all_alarms']; metrics=dict(carry_rmse_m=float(np.sqrt(np.mean(np.square(errors)))),
                carry_frames=len(errors),pose_uncertain=n['count'],nees_above=n['nees']['above_chi2_95'],
                nees_available=n['nees']['available'],nees_exceedance_rate=n['nees']['above_chi2_95']/n['nees']['available'],
                unflagged_above_25cm=audit['no_alarm']['count']-audit['no_alarm']['below_budget']['0.25'],
                phases=audit['phases'],pulses=pulses,pose_audit={k:v for k,v in audit.items() if k!='decision_rows'},
                baseline_max_delta=pred['max_delta_from_record'],updates=pred['amcl']['updates'],
                calibrated_pulses=len(eligible_times),carry_window=[begin,end])
            case['conditions'][opt]=metrics; total=totals[opt]
            total['carry_squared_error_sum']+=float(np.square(errors).sum());total['carry_frames']+=len(errors)
            total['alarms']+=n['count']; total['nees_above']+=metrics['nees_above'];total['nees_available']+=metrics['nees_available']
            total['unflagged_above_25cm']+=metrics['unflagged_above_25cm']
            eligible=[p['command_model_residual_deg'] for p in pulses if p['eligible']]
            total['eligible_yaw_squared_error_sum']+=float(np.square(eligible).sum());total['eligible_count']+=len(eligible)
        off,on=(read(out/f's{seed}-{opt}.json') for opt in ('off','on'))
        case['unchanged_particle_trajectory']=off['particle_trajectory_sha256']==on['particle_trajectory_sha256']
        result['runs'].append(case)
    for t in totals.values():
        t['carry_rmse_m']=(t['carry_squared_error_sum']/t['carry_frames'])**.5
        t['eligible_yaw_rmse_deg']=(t['eligible_yaw_squared_error_sum']/t['eligible_count'])**.5
        t['nees_exceedance_rate']=t['nees_above']/t['nees_available']
    a,b=totals['off'],totals['on']; result['totals']=totals
    result['gates']=dict(off_reproduced=all(q['conditions']['off']['baseline_max_delta']<=1e-9 for q in result['runs']),
        unexposed1054_identical=result['runs'][2]['unchanged_particle_trajectory'],
        eligible_ccw_bias_reduced=b['eligible_yaw_rmse_deg']<a['eligible_yaw_rmse_deg'],
        pose_warnings_reduced=b['alarms']<a['alarms'],nees_rate_reduced=b['nees_exceedance_rate']<a['nees_exceedance_rate'],
        unflagged_large_errors_nonincrease=b['unflagged_above_25cm']<=a['unflagged_above_25cm'],
        carry_rmse_nonincrease=b['carry_rmse_m']<=a['carry_rmse_m'])
    result['physical_admitted']=all(result['gates'].values())
    result['hashes']={p.name:sha(p) for p in out.glob('s*-*.json')}
    with (out/'result.json').open('x') as f: json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(gates=result['gates'],totals=totals)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,choices=RUNS)
    p.add_argument('--option',choices=('off','on'));p.add_argument('--score',action='store_true');p.add_argument('--max-frames',type=int)
    a=p.parse_args()
    if a.score:score(a.output)
    else:replay(a.seed,a.option,a.output,a.max_frames)
