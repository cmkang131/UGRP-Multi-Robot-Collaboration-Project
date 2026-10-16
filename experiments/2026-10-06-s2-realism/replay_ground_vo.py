"""S1051 own-RGB replay with noninterfering PF weighting/resampling audit. No GT."""
import argparse,base64,copy,hashlib,json,subprocess
from pathlib import Path
import cv2
import numpy as np
from harness import zone_solo_cyan_contract_v106 as c
from harness.zone_solo_cyan_ground_vo import Runtime,OPTION
from harness.zone_solo_cyan_observed_amcl import OPTION as OBSERVED
from harness.zone_pair_highpose_exact_speedups import install
from harness import zone_pair_highpose_frame_gate as frame_gate

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
CRITERIA=json.loads((HERE/'ground-vo-criteria.json').read_text())
RAW=Path(CRITERIA['legacy_raw'])
EXCLUDE=('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')


def replay(option,out):
    assert not out.exists()
    read=lambda name:json.loads((RAW/name).read_text())
    record=read('student_record.json');bundle=read('bundle.json')
    commands={}
    for cmd in record['commands']:commands.setdefault(round(cmd['t'],6),[]).append(cmd)
    frames=[json.loads(l) for l in (RAW/'robots/r3/frames.jsonl').read_text().splitlines()]
    kwargs={k:v for k,v in bundle['options'].items() if k not in EXCLUDE}
    kwargs.update(odom_source=OPTION if option=='candidate' else 'off',
        slip_detection='slip_detect_v1' if option=='candidate' else 'off',
        slip_recovery='slip_recovery_v1' if option=='candidate' else 'off',
        ground_vo_calibration=dict(servo_stiffness='off',scope='legacy_replay_only',pitch_scale_bound_deg=2.8),
        floor_appearance=json.loads((ROOT/'configs/calibration/s2_floor_appearance_v1.json').read_text()),
        motion_model=bundle['motion_model'],pulse_calibration=bundle['pulse_calibration'],
        extrinsic_calibration=bundle['extrinsic_calibration'])
    _,undo=install('v98-exact-v6')
    runtime=Runtime(c.hp.resolve(c.MAP_ID)[0],ROOT/c.CALIBRATION,c.CALIBRATION_SHA,seed=1051,**kwargs)
    provider=runtime.pose;provider.on_command(commands[round(frames[0]['sim_time'],6)].pop(0))
    poses=[];max_delta=0.;first_mismatch=None
    from harness import zone_solo_cyan_amcl_update as amcl_module
    original_likelihood=amcl_module.likelihood;original_resample=amcl_module.resample
    pf=provider.provider.loc._pf;measurements=[]
    def mean(px,w):
        return [float(w@px[:,0]),float(w@px[:,1]),float(np.arctan2(w@np.sin(px[:,2]),w@np.cos(px[:,2])))]
    def traced_likelihood(field,px,points):
        value=original_likelihood(field,px,points)
        w0=pf._weights();ll=np.log(value);post=w0*np.exp(ll-ll.max());post/=post.sum()
        measurements.append(dict(t=float(pf.t),prior_mean=mean(px,w0),
            weighted_mean=mean(px,post),points_local_m=np.asarray(points).tolist(),
            prior_estimate=copy.deepcopy(pf.estimate())))
        return value
    def traced_resample(current_pf):
        assert current_pf is pf
        measurements[-1]['weighted_estimate']=copy.deepcopy(pf.estimate())
        original_resample(pf)
        measurements[-1]['resampled_mean']=mean(pf.px,pf._weights())
        measurements[-1]['resampled_estimate']=copy.deepcopy(pf.estimate())
    amcl_module.likelihood=traced_likelihood;amcl_module.resample=traced_resample
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
        contacts=copy.deepcopy(getattr(runtime,'contact_audit',None));progress=copy.deepcopy(runtime.flow.audit) if option=='candidate' else None
    finally:
        amcl_module.likelihood=original_likelihood;amcl_module.resample=original_resample
        runtime.close();undo()
    result=dict(schema='ugrp.s2.ground_vo.replay.v1',option=option,seed=1051,
        physics_runs=0,model_calls=0,gt_inputs=False,commands_fixed=True,
        source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_raw=str(RAW),frames=len(poses),trailing_poses=len(record['poses'])-len(poses),
        baseline_max_delta=max_delta,first_mismatch=first_mismatch,poses=poses,amcl=amcl,visibility=mask,measurements=measurements,contact_filter=contacts,ground_vo=progress,
        criteria_sha256=hashlib.sha256((HERE/'ground-vo-criteria.json').read_bytes()).hexdigest(),
        candidate_sha256=hashlib.sha256((ROOT/'harness/zone_solo_cyan_ground_vo.py').read_bytes()).hexdigest(),
        replay_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_hashes={p:hashlib.sha256((RAW/p).read_bytes()).hexdigest() for p in ('bundle.json','student_record.json','robots/r3/frames.jsonl')})
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result)+'\n')
    print(json.dumps(dict(option=option,complete=True,frames=len(poses),baseline_max_delta=max_delta,updates=amcl['updates'])),flush=True)
    if option=='baseline':
        assert max_delta==0. and amcl==record['amcl_update'] and mask==record['visibility_mask'], 'off replay differs'
        assert contacts==record['contact_filter']
        print('Default-off poses/amcl/visibility/contact exact',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--option',choices=['baseline','candidate'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();replay(a.option,a.output)
