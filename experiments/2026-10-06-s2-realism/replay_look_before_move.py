"""Saved own-RGB/command guard replay; no physics, no truth, no invented side views."""
import argparse,copy,hashlib,json
from pathlib import Path
import cv2
import numpy as np
from harness import zone_solo_cyan_look_before_move as m
from harness import zone_solo_cyan_contract_v106 as old
from harness.zone_pair_highpose_exact_speedups import install
from harness.zone_solo_cyan_bias_tempering import group,scaled
from scripts.run_s2_landmarks_dev import runtime_factory
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,rows,sha

def replay(seed):
    raw=OUTPUTS/RUNS[seed];b=read(raw/'bundle.json');record=read(raw/'student_record.json')
    calibration=read(OUTPUTS/'s2-bias-tempering-v45-20261008/fit'/f's{seed}-calibration.json')
    commands={}
    for c in record['commands']:commands.setdefault(round(c['t'],6),[]).append(c)
    frames=rows(raw/'robots/r3/frames.jsonl');times=np.array([c['t'] for c in record['commands'] if m.lateral(c)])
    memory=m.Memory(b['floor_appearance']);checks=[];_,undo=install('v98-exact-v6')
    runtime=runtime_factory(b)(old.hp.resolve(old.MAP_ID)[0],old.ROOT/old.CALIBRATION,old.CALIBRATION_SHA,**b['task'])
    runtime.initial_commands(frames[0]['sim_time'],{'r3':{int(k):v for k,v in record['commands'][0]['pulses'].items()}})
    pf=runtime.pose.provider.loc._pf;off=[]
    try:
        for index,f in enumerate(frames):
            now=f['sim_time'];needed=bool(np.any((times>=now-1e-8)&(times<=now+3.+1e-8)))
            if needed and now>=memory.last_frame+m.PARAMS['frame_interval_s']-1e-8 and now>=memory.settle_after-1e-8:
                cm=pf.column_model_for(runtime.servo)
                if cm is not None:
                    data=(raw/f['path']).read_bytes()
                    if hashlib.sha256(data).hexdigest()!=f['sha256']:raise ValueError('RGB_CHANGED')
                    rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
                    memory.add(now,rgb,cm,runtime.servo,f['sha256'])
            for c in commands.get(round(now,6),[]):
                off.append(copy.deepcopy(c))
                if c['kind']=='initial_servo_command':continue
                p=None
                if c['kind'] in ('drive','mecanum') and any(c.get(k,0) for k in ('forward','left','turn')):
                    key=m.profile_key(c,pf.load.loaded);p=runtime.pulse_profiles.get(key)
                    g=calibration['groups'].get(group(runtime.servo,key))
                    if g:p=scaled(p,g['gain'])
                if m.lateral(c):
                    q=memory.assess(now,p);q['action']=c;checks.append(q)
                memory.command(now,c,p)
                runtime.on_command('r3',now,{k:v for k,v in c.items() if k!='t'})
            if index%2500==0:print(seed,index,'/',len(frames),'lateral',len(checks),flush=True)
        encode=lambda a:json.dumps(a,separators=(',',':'),sort_keys=True).encode()
        assert encode(off)==encode(record['commands'])
        return dict(seed=seed,raw=str(raw),lateral_total=len(checks),on_unchanged_lateral=sum(q['clear'] for q in checks),
            on_withheld_lateral=sum(not q['clear'] for q in checks),on_uncertified_lateral_permitted=0,
            off_command_bytes_identical=True,off_commands_sha256=hashlib.sha256(encode(off)).hexdigest(),
            counterfactual='veto replay at recorded commands; injected views/paths unavailable in old tape, no closed-loop success claim',
            perception=memory.stats,checks=checks,gt_inputs=False,physics_runs=0,
            input_hashes={n:sha(raw/n) for n in ('student_record.json','bundle.json','robots/r3/frames.jsonl')})
    finally:runtime.close();undo()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    for seed in RUNS:
        value=replay(seed)
        with (a.output/f's{seed}.json').open('x') as f:json.dump(value,f);f.write('\n')
        print(json.dumps({k:v for k,v in value.items() if k not in ('checks','input_hashes')}),flush=True)
