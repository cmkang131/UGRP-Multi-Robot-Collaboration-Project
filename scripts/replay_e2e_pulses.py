#!/usr/bin/env python3
"""Offline command replay only. collect reads ARM originals; never starts a world."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

RUNS=['s4live11-'+c+'-s601-v182' for c in ('leader_ko','peer_ko','structured','no_comm')]


def collect(root):
    rows=[]
    for name in RUNS:
        raw=Path(root)/name/'raw';path=raw/'student_record.json'
        data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
        manifest=json.loads((raw/'artifacts.sha256.json').read_text())
        # Archived manifests are lists of path/sha rows on this cohort.
        if isinstance(manifest,dict):
            expected=manifest.get('files',manifest)
        else:expected=manifest
        if isinstance(expected,list):expected={r['path']:r['sha256'] for r in expected}
        value=expected['student_record.json']
        if isinstance(value,dict):value=value['sha256']
        if sha!=value:raise ValueError('ARCHIVE_SHA_MISMATCH: '+name)
        episode=json.loads(data)['pair']['pair'][0]
        robots={}
        for rid in ('r1','r2'):
            events=episode['robots'][rid]['events'];segments=[]
            for plan in (r for r in events if r['event']=='synchronized_carry_plan'):
                commands=[e for e in events if e['event']=='integer_carry_pulse' and e['seg']==plan['seg']
                          and any(e['command'].values())]
                if any(e['command']!=plan['cmd'] for e in commands):raise ValueError('COMMAND_CHANGED')
                segments.append(dict(seg=plan['seg'],t=plan['sim_s'],distance_m=plan['distance_m'],
                    duration_s=plan['duration_s'],period_s=plan['period_s'],calibrated_step_m=plan['calibrated_step_m'],
                    cmd=plan['cmd'],planned=plan['pulses'],issued_ticks=[e['tick'] for e in commands]))
            robots[rid]=segments
        rows.append(dict(name=name,raw=str(raw),student_record_sha256=sha,robots=robots))
    return dict(schema='ugrp.e2e_saved_carry_commands.v1',new_physics=0,runs=rows)


def replay(saved,diagnosis,profiles):
    from harness.e2e_pulse_budget import pulse_schedule
    outcomes=[]
    for run in saved['runs']:
        old=diagnosis['runs'][run['name']]
        for option in ('off','fractional_duration_v1','tick_duration_v1'):
            delta=[0.,0.];segments=[]
            for a,b in zip(run['robots']['r1'],run['robots']['r2']):
                # Every issued command and peer clock must match the saved plan.
                if (a['seg']!=b['seg'] or a['issued_ticks']!=b['issued_ticks'] or
                        any(a['cmd'][k]!=-b['cmd'][k] for k in a['cmd'])):raise ValueError('PAIR_TRAJECTORY_MISMATCH')
                axis=1 if a['cmd']['left'] else 0
                end=[0.,0.];end[axis]=math.copysign(a['distance_m'],a['cmd']['left' if axis else 'forward'])
                ctl=SimpleNamespace(rid='r1',seg=0,v3_plan={'route':[[0.,0.],end]},claims={},log=lambda *a,**k:None)
                schedule,base_duration=pulse_schedule(ctl,a['t'],profiles,option=option)
                row=ctl.claims['segments'][0]
                if row['calibrated_step_m']!=a['calibrated_step_m'] or row['pulses']!=a['planned']:
                    raise ValueError('SAVED_CALIBRATION_MISMATCH')
                expected=[round(start*20) for start,_,c in schedule if any(c.values())]
                if a['issued_ticks']!=expected[:len(a['issued_ticks'])]:raise ValueError('SAVED_DISPATCH_MISMATCH')
                durations=row.get('pulse_durations_s',[base_duration]*a['planned'])[:len(a['issued_ticks'])]
                before=len(durations)*a['calibrated_step_m']
                after=sum(durations)/base_duration*a['calibrated_step_m']
                delta[axis]+=math.copysign(1.,end[axis])*(after-before)
                segments.append(dict(seg=a['seg'],planned=a['planned'],issued=len(durations),last_duration_s=durations[-1] if durations else None,
                    old_model_distance_m=before,new_model_distance_m=after))
            error=[e+d for e,d in zip(old['final_error_xy'],delta)]
            completed=all(x['issued']==x['planned'] for x in segments) and len(segments)==8
            outcomes.append(dict(run=run['name'],option=option,complete_saved_route=completed,
                saved_error_m=math.hypot(*old['final_error_xy']),predicted_error_xy_m=error,predicted_error_m=math.hypot(*error),
                command_delta_xy_m=delta,segments=segments))
    selected=[r for r in outcomes if r['complete_saved_route'] and r['option']!='off']
    return dict(schema='ugrp.e2e_pulse_replay.v1',new_physics=0,
        scope='Actual saved integer dispatch ticks replayed with calibrated linear duration response; other observed errors frozen. Counterfactual, not physical validation.',
        improved=sum(r['predicted_error_m']<r['saved_error_m'] for r in selected),N=len(selected),rows=outcomes)


def main():
    p=argparse.ArgumentParser();p.add_argument('--collect',type=Path);p.add_argument('--commands',type=Path)
    p.add_argument('--diagnosis',type=Path);p.add_argument('--profiles',type=Path,default=Path('configs/s2_v133_full_template.json'))
    a=p.parse_args()
    if a.collect:result=collect(a.collect)
    else:
        result=replay(json.loads(a.commands.read_text()),json.loads(a.diagnosis.read_text()),json.loads(a.profiles.read_text())['pulse_calibration']['profiles'])
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':main()
