"""Condition A guard replay on saved proposals; no new physics/GT/PF fitting."""
import argparse,copy,hashlib,json,runpy
from pathlib import Path
from harness import zone_solo_cyan_look_before_move as look
from harness.zone_solo_cyan_staged_approach import FINAL_STATES
from harness import zone_s2_staging_only_contract as contract
from harness import zone_solo_cyan_contract_v106 as old
from scripts.run_s2_staging_only import runtime_factory
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,sha
Tape=runpy.run_path('experiments/2026-10-06-s2-realism/replay_staged_approach.py')['Tape']
encode=lambda x:json.dumps(x,sort_keys=True,separators=(',',':')).encode()

def replay():
    b=contract.bundle('a'*40,1054,look_before_move=look.OPTION,final_approach='staging_v133_v1')
    ref=runtime_factory(b)(old.hp.resolve(old.MAP_ID)[0],old.ROOT/old.CALIBRATION,old.CALIBRATION_SHA,**b['task'])
    servo={1:2000,3:740,4:2320,5:1320,6:1500};results=[]
    try:
        for seed in (1054,1055):
            raw=OUTPUTS/f's2-realism-4436222c-s{seed}-v136-goal-heading';r=read(raw/'student_record.json')
            checks=[c for c in r['look_before_move']['checks'] if c['state']=='align'];emitted=[]
            t=Tape(ref,'align',checks[-1]['action'],servo)
            w=look.attach(t,look_before_move=look.OPTION,final_approach='staging_v133_v1',floor_table=b['floor_appearance'])
            for c in checks:
                t.action=c['action'];a=w.step(c['t']);assert a==[('r3',c['action'])]
                w.on_command('r3',c['t'],a[0][1]);emitted.append(a)
            w.state='search_move';nav=w.step(checks[-1]['t']+10)
            assert not any(look.lateral(a) for _,a in nav) and not hasattr(w,'final_approach_monitor')
            results.append(dict(seed=seed,proposals=len(checks),original_final_commands_preserved=len(emitted),
                navigation_unknown_veto=True,monitor_created=False,source=str(raw),student_record_sha256=sha(raw/'student_record.json')))
        success=[]
        for seed,name in RUNS.items():
            raw=OUTPUTS/name;r=read(raw/'student_record.json');events=[e for e in r['events'] if e['event']=='state'];i=0;state='init';groups={}
            for c in r['commands']:
                while i<len(events) and events[i]['t']<=c['t']+1e-8:state=events[i]['state'];i+=1
                if state in FINAL_STATES:groups.setdefault((c['t'],state),[]).append({k:v for k,v in c.items() if k!='t'})
            t=Tape(ref,'align',{'kind':'hold'},servo);current=[]
            t.step=lambda now:copy.deepcopy(current)
            w=look.attach(t,look_before_move=look.OPTION,final_approach='staging_v133_v1',floor_table=b['floor_appearance'])
            wanted=[];actual=[]
            for (now,state),actions in groups.items():
                w.state=state;current[:]=[('r3',a) for a in actions]
                got=w.step(now);assert encode(got)==encode(current)
                wanted.extend(current);actual.extend(got)
            assert encode(wanted)==encode(actual)
            success.append(dict(seed=seed,final_command_count=len(actual),command_bytes_equal=True,sha256=hashlib.sha256(encode(actual)).hexdigest(),student_record_sha256=sha(raw/'student_record.json')))
        off=runpy.run_path('experiments/2026-10-06-s2-realism/replay_goal_heading.py')['off_replay']()
        return dict(schema='ugrp.s2.staging_only_replay.v1',recorded_stalls=results,success_final_tapes=success,off=off,
            gate_pass=True,physics_runs=0,gt_inputs=False,scope='saved v133 controller proposals through condition A guard; no PF recomputation or new closed-loop success claim')
    finally:ref.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();r=replay()
    with a.output.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps(r,indent=2))
