"""Full s1050 own-RGB/own-command replay. Never opens evaluation truth."""
import argparse,base64,copy,hashlib,json,subprocess
from pathlib import Path
import cv2
import numpy as np
from harness import zone_solo_cyan_contract_v106 as c
from harness.zone_solo_cyan_observed_amcl import Runtime,OPTION
from harness.zone_pair_highpose_exact_speedups import install
from harness import zone_pair_highpose_frame_gate as frame_gate

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
CRITERIA=json.loads((HERE/'observed-amcl-criteria.json').read_text())
RAW=Path(CRITERIA['source_raw'])
EXCLUDE=('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')


def replay(option,out):
    assert not out.exists()
    read=lambda name:json.loads((RAW/name).read_text())
    record=read('student_record.json');bundle=read('bundle.json')
    commands={}
    for cmd in record['commands']:commands.setdefault(round(cmd['t'],6),[]).append(cmd)
    frames=[json.loads(l) for l in (RAW/'robots/r3/frames.jsonl').read_text().splitlines()]
    kwargs={k:v for k,v in bundle['options'].items() if k not in EXCLUDE}
    kwargs.update(visibility_policy=option,motion_model=bundle['motion_model'],
        pulse_calibration=bundle['pulse_calibration'],extrinsic_calibration=bundle['extrinsic_calibration'])
    _,undo=install('v98-exact-v6')
    runtime=Runtime(c.hp.resolve(c.MAP_ID)[0],ROOT/c.CALIBRATION,c.CALIBRATION_SHA,seed=1050,**kwargs)
    provider=runtime.pose;provider.on_command(commands[round(frames[0]['sim_time'],6)].pop(0))
    poses=[];max_delta=0.;first_mismatch=None
    try:
        for i,(f,old) in enumerate(zip(frames,record['poses'])):
            now=f['sim_time'];data=(RAW/f['path']).read_bytes()
            assert hashlib.sha256(data).hexdigest()==f['sha256']
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
            verdict,_=frame_gate.gate().assess({**f,'image':base64.b64encode(data).decode()},'r3',now,ob=False)
            p=provider.on_frame(now,rgb if verdict==frame_gate.VALID else None)
            row=dict(t=now,t_est=p.t_est,x=p.x_m,y=p.y_m,yaw=p.yaw_rad,std_xy_m=p.std_xy_m,last_fix_t=p.last_fix_t)
            poses.append(row)
            delta=max(abs(row[k]-old[k]) for k in ('x','y','yaw'))
            max_delta=max(max_delta,delta)
            if delta>1e-9 and first_mismatch is None:first_mismatch=dict(i=i,t=now,delta=delta)
            for cmd in commands.get(round(now,6),[]):provider.on_command(cmd)
            if i%500==0:print(json.dumps(dict(option=option,frames=i,t=now,max_delta=max_delta)),flush=True)
        amcl=copy.deepcopy(runtime.amcl_audit);mask=copy.deepcopy(runtime.visibility.audit)
    finally:runtime.close();undo()
    result=dict(schema='ugrp.s2.observed_amcl.replay.v1',option=option,seed=1050,
        physics_runs=0,model_calls=0,gt_inputs=False,commands_fixed=True,
        source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_raw=str(RAW),frames=len(poses),trailing_poses=len(record['poses'])-len(poses),
        baseline_max_delta=max_delta,first_mismatch=first_mismatch,poses=poses,amcl=amcl,visibility=mask,
        criteria_sha256=hashlib.sha256((HERE/'observed-amcl-criteria.json').read_bytes()).hexdigest(),
        candidate_sha256=hashlib.sha256((ROOT/'harness/zone_solo_cyan_observed_amcl.py').read_bytes()).hexdigest(),
        replay_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_hashes={p:hashlib.sha256((RAW/p).read_bytes()).hexdigest() for p in ('bundle.json','student_record.json','robots/r3/frames.jsonl')})
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result)+'\n')
    print(json.dumps(dict(option=option,complete=True,frames=len(poses),baseline_max_delta=max_delta,updates=amcl['updates'])),flush=True)
    if option=='off':assert max_delta<=CRITERIA['baseline_replay_max_pose_delta'],first_mismatch


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--option',choices=['off',OPTION],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();replay(a.option,a.output)
