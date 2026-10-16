"""Saved own pose/command state-machine replay; GT and simulator never read."""
import argparse,copy,hashlib,json,math
from pathlib import Path
from types import SimpleNamespace as NS
from harness import zone_s2_goal_heading_contract as contract
from harness import zone_solo_cyan_contract_v106 as legacy
from harness.zone_solo_cyan_pulse_cal import profile_key
from harness.zone_solo_cyan_look_before_move import attach
from scripts.run_s2_look_before_move import runtime_factory
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,sha

def replay(seed):
    raw=OUTPUTS/f's2-realism-88f5fbbb-s{seed}-v135-look-before-move';r=read(raw/'student_record.json')
    poses={round(p['t'],6):p for p in r['poses']};checks=[]
    end_scan=r['look_before_move']['scans'][-1]['observed_at']+2
    for c in r['pulse_motion_model']['transformations']:
        p=poses[round(c['t'],6)];d=math.dist([p['x'],p['y']],c['waypoint'])
        if c['t']>=end_scan and c.get('look_before_move_withheld') and d<=.03 and abs(p['yaw'])>.06:
            checks.append((c,p,d))
    assert checks
    b=contract.bundle('a'*40,seed,look_before_move='rgb_sweep_v1')
    runtime=runtime_factory(b)(legacy.hp.resolve(legacy.MAP_ID)[0],legacy.ROOT/legacy.CALIBRATION,legacy.CALIBRATION_SHA,**b['task'])
    c,p,d=checks[0]
    try:
        runtime.initial_commands(0,{'r3':{int(k):v for k,v in r['commands'][0]['pulses'].items()}})
        runtime.state='search_move';runtime.path=[c['waypoint']];runtime.path_goal=tuple(c['waypoint'])
        runtime.cal_until=None;runtime.cal_settled_at=-math.inf
        runtime.last_report=NS(initialized=True,x_m=p['x'],y_m=p['y'],yaw_rad=p['yaw'],
            std_xy_m=p['std_xy_m'],std_yaw_rad=p['std_yaw_rad'],last_fix_t=p['last_fix_t'],t_est=p['t_est'])
        actions=runtime.step(c['t']);moving=[a for _,a in actions if a.get('turn')]
        assert len(moving)==1 and not any(a.get('left') or a.get('forward') for _,a in actions)
        prof=runtime.pulse_profiles[profile_key(moving[0],False)]
        predicted_yaw=p['yaw']+prof['mean_delta'][2]
        # Component test using a fixed own-command prediction, not a claim of
        # new images, true motion or closed-loop physical success.
        runtime.last_report.yaw_rad=predicted_yaw;runtime.last_report.x_m+=.04
        after,arrived=runtime.drive(c['waypoint'],c['t']+prof['times'][-1]+.2)
        assert arrived and after==[dict(kind='hold')]
        return dict(seed=seed,raw=str(raw),t=c['t'],recorded_state=c['state'],recorded_waypoint=c['waypoint'],
            detour_xy_exit=d<=.035,goal_xy_ok=d<=.03,goal_yaw_ok=abs(p['yaw'])<=.06,
            distance_m=d,yaw_rad=p['yaw'],old_candidate=c['issued'],old_next='unknown veto -> detour XY done -> same search_move',
            new_candidate=moving[0],new_next='XY latched -> final heading rotation',
            repeated_old_veto_opportunities=len(checks),new_transition_observed=True,
            fixed_command_prediction_yaw_rad=predicted_yaw,stateful_component_arrived_with_4cm_drift=arrived,
            goal_trace=copy.deepcopy(runtime.goal_heading['rows']),
            source_hashes={'student_record.json':sha(raw/'student_record.json')},gt_inputs=False,physics_runs=0)
    finally:runtime.close()

def off_replay():
    result=[]
    for seed,name in RUNS.items():
        r=read(OUTPUTS/name/'student_record.json');by_t={}
        for c in r['commands']:by_t.setdefault(c['t'],[]).append(c)
        class Tape:
            def step(self,t):return copy.deepcopy(by_t[t])
            def record(self):return copy.deepcopy(r)
        runtime=Tape();before=(runtime.step,runtime.record);wrapped=attach(runtime)
        assert wrapped is runtime and before==(runtime.step,runtime.record)
        emitted=[c for t in by_t for c in wrapped.step(t)]
        encode=lambda q:json.dumps(q,sort_keys=True,separators=(',',':')).encode()
        assert encode(emitted)==encode(r['commands']) and encode(wrapped.record())==encode(r)
        result.append(dict(seed=seed,commands=len(emitted),command_bytes_equal=True,record_bytes_equal=True,
            command_sha256=hashlib.sha256(encode(emitted)).hexdigest(),scope='off adapter exact identity over existing tapes; PF not recomputed'))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=dict(schema='ugrp.s2.goal_heading_replay.v1',runs=[replay(s) for s in (1054,1055)],off=off_replay(),
        physics_runs=0,gt_inputs=False,full_admitted=True,
        scope='real runtime.step at saved own pose; post-turn arrival is fixed motion-model component check, not simulated success')
    with a.output.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(value,indent=2))
