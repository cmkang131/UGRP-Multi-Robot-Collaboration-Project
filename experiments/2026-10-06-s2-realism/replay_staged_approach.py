"""Replay recorded proposed commands and own RGB through the new stage guard.

No physics or GT. This does not rerun PF or invent new views after new actions.
"""
import argparse,copy,hashlib,json,math,runpy
from pathlib import Path
from types import SimpleNamespace as NS
import cv2
import numpy as np
from harness import zone_solo_cyan_staged_approach as stage
from harness import zone_solo_cyan_look_before_move as look
from harness import zone_s2_staged_approach_contract as contract
from harness import zone_solo_cyan_contract_v106 as old
from scripts.run_s2_staged_approach import runtime_factory
BASE=Path('/Users/changmin/projects/ugrp/outputs')
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

class Tape:
    def __init__(self,reference,state,action,servo):
        self.robot_id='r3';self.state=state;self.action=copy.deepcopy(action);self.servo=servo
        self.pose=reference.pose;self.pulse_profiles=reference.pulse_profiles
        self.cal_until=None;self.cal_settled_at=0.;self.cal_rows=[];self.terminal=False;self.path=[]
    def step(self,t):return [('r3',copy.deepcopy(self.action))]
    def drive(self,*a,**kw):return [],False
    def on_frames(self,*a):pass
    def on_command(self,*a):pass
    def record(self):return {}
    def soft(self,*a):pass

def image(raw,f):
    p=raw/f['path'];assert sha(p)==f['sha256']
    return cv2.cvtColor(cv2.imread(str(p)),cv2.COLOR_BGR2RGB)

def replay(seed):
    raw=BASE/f's2-realism-4436222c-s{seed}-v136-goal-heading';record=read(raw/'student_record.json')
    checks=[r for r in record['look_before_move']['checks'] if r['state']=='align'];check=checks[-1]
    fs=[json.loads(s) for s in (raw/'robots/r3/frames.jsonl').read_text().splitlines()]
    f=min(fs,key=lambda r:abs(r['sim_time']-check['t']));assert abs(f['sim_time']-check['t'])<.051
    servo={int(k):v for k,v in f['commanded_servo'].items()};now=f['sim_time']
    b=contract.bundle('a'*40,seed,look_before_move=look.OPTION,final_approach=stage.OPTION)
    reference=runtime_factory(b)(old.hp.resolve(old.MAP_ID)[0],old.ROOT/old.CALIBRATION,old.CALIBRATION_SHA,**b['task'])
    try:
        cm=reference.pose.provider.loc._pf.column_model_for(servo);rgb=image(raw,f)
        r=look.attach(Tape(reference,'align',check['action'],servo),look_before_move=look.OPTION,
            floor_table=b['floor_appearance'],final_approach=stage.OPTION)
        r.final_approach_monitor.observe(now,rgb,cm,servo,f['sha256'])
        proposed=r.step(now);passed=proposed==[('r3',check['action'])]
        if passed:r.on_command('r3',now,proposed[0][1])
        nav=look.attach(Tape(reference,'search_move',check['action'],servo),look_before_move=look.OPTION,
            floor_table=b['floor_appearance'],final_approach=stage.OPTION)
        blocked=not any(look.lateral(a) for _,a in nav.step(now))
        return dict(seed=seed,raw=str(raw),state='align',t=now,old_unknown=check['unknown'],
            action=check['action'],new_proposals=proposed,original_pulse_preserved=passed,
            observation=r.final_approach_monitor.last,navigation_unknown_still_vetoed=blocked,
            input_hashes={n:sha(raw/n) for n in ('student_record.json','robots/r3/frames.jsonl')})
    finally:reference.close()

def positive():
    raw=BASE/'s2-realism-32776381-s1054-v134-side-scan';record=read(raw/'student_record.json')
    observed=next(f for f in record['side_scan']['frames'] if f['detected'])
    fs=[json.loads(s) for s in (raw/'robots/r3/frames.jsonl').read_text().splitlines()]
    f=next(f for f in fs if f['frame_id']==observed['frame_id']);servo={int(k):v for k,v in f['commanded_servo'].items()}
    b=contract.bundle('a'*40,1054,look_before_move=look.OPTION,final_approach=stage.OPTION)
    r=runtime_factory(b)(old.hp.resolve(old.MAP_ID)[0],old.ROOT/old.CALIBRATION,old.CALIBRATION_SHA,**b['task'])
    try:
        m=stage.Monitor();m.observe(f['sim_time'],image(raw,f),r.pose.provider.loc._pf.column_model_for(servo),servo,f['sha256'])
        result=m.assess(f['sim_time']);return dict(raw=str(raw),frame=f['path'],observation=m.last,check=result)
    finally:r.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    off=runpy.run_path('experiments/2026-10-06-s2-realism/replay_goal_heading.py')['off_replay']()
    runs=[replay(s) for s in (1054,1055)];pos=positive()
    passed=all(r['original_pulse_preserved'] and r['navigation_unknown_still_vetoed'] for r in runs) and pos['check']['reason']=='OBSERVED_PEER_APPEARANCE'
    value=dict(schema='ugrp.s2.staged_approach_replay.v1',runs=runs,positive=pos,off=off,gate_pass=passed,physics_runs=0,gt_inputs=False,
        scope='recorded controller proposals plus exact own RGB through stage guard; not PF recomputation or closed-loop completion')
    with a.output.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(value,indent=2))
