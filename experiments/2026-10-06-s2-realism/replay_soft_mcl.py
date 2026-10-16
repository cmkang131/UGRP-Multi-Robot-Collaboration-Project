"""Frozen own-RGB/command replay; evaluation truth is never opened here."""
import argparse,base64,copy,hashlib,json,subprocess,sys
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import replay_unloaded_sag as old
from harness.zone_solo_cyan_likelihood_field import Runtime,OPTION,PARAMS

CRITERIA=json.loads((old.HERE/'soft-mcl-criteria.json').read_text())
assert PARAMS==CRITERIA['parameters']


def replay(seed,output):
    run=old.RAW/f's2-realism-{old.RUNS[seed]}-s{seed}-P1-2-place'
    output.mkdir(parents=True,exist_ok=True);dest=output/f's{seed}-{OPTION}.json'
    if dest.exists():raise FileExistsError(dest)
    record=json.loads((run/'student_record.json').read_text());bundle=json.loads((run/'bundle.json').read_text())
    frames=[json.loads(l) for l in (run/'robots/r3/frames.jsonl').read_text().splitlines()]
    _,undo=old.install('v98-exact-v6')
    excluded=('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')
    kwargs={k:v for k,v in bundle['options'].items() if k not in excluded}
    kwargs.update(motion_model=bundle['motion_model'],provider_factory=old.factory_for(CRITERIA['camera_variant']),measurement_model=OPTION)
    if 'pulse_calibration' in bundle:kwargs['pulse_calibration']=bundle['pulse_calibration']
    runtime=Runtime(old.contract.hp.resolve(old.contract.MAP_ID)[0],old.ROOT/old.contract.CALIBRATION,
                    old.contract.CALIBRATION_SHA,seed=seed,**kwargs)
    provider=runtime.pose;commands={};rows=[]
    for cmd in record['commands']:commands.setdefault(round(cmd['t'],6),[]).append(cmd)
    provider.on_command(commands[round(frames[0]['sim_time'],6)].pop(0))
    try:
        for i,(f,p) in enumerate(zip(frames,record['poses'])):
            now=f['sim_time'];data=(run/f['path']).read_bytes()
            assert hashlib.sha256(data).hexdigest()==f['sha256']
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
            verdict,_=old.frame_gate.gate().assess({**f,'image':base64.b64encode(data).decode()},'r3',now,ob=False)
            report=provider.on_frame(now,rgb if verdict==old.frame_gate.VALID else None)
            rows.append(dict(t=now,t_est=report.t_est,x=report.x_m,y=report.y_m,yaw=report.yaw_rad,
                last_fix_t=report.last_fix_t))
            for cmd in commands.get(round(now,6),[]):provider.on_command(cmd)
            if i%1000==0:print(seed,i,now,flush=True)
        result=dict(schema='ugrp.s2.soft_mcl.replay.v1',seed=seed,variant=OPTION,
            source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=old.ROOT,text=True).strip(),
            physics_runs=0,model_calls=0,gt_inputs=False,commands_fixed=True,
            frames=len(rows),trailing_pose_without_rgb=len(record['poses'])-len(rows),
            source_raw=str(run),criteria_sha256=old.digest(old.HERE/'soft-mcl-criteria.json'),
            source_hashes={p:old.digest(run/p) for p in ('bundle.json','student_record.json','robots/r3/frames.jsonl')},
            approximation=old.approximation(CRITERIA['camera_variant']),
            carry_window=list(old.carry_window(record)),soft_measurement=runtime.soft_measurement,rows=rows)
        with dest.open('x') as f:json.dump(result,f)
        print(seed,'complete',len(rows),runtime.soft_measurement['updates'],flush=True)
    finally:runtime.close();undo()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,required=True,choices=old.RUNS)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();replay(a.seed,a.output)
