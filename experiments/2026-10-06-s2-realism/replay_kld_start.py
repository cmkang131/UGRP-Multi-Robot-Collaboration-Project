"""One fixed off/on saved-RGB replay; GT is opened only after predictions close."""
import argparse,base64,copy,hashlib,json,os,subprocess,time
from pathlib import Path

import cv2
import numpy as np

from harness import zone_solo_cyan_contract_v106 as c
from harness import zone_pair_highpose_frame_gate as frame_gate
from harness.s2_stiff_camera_calibration import runtime_class
from harness.zone_solo_cyan_kld_start import Runtime,OPTION,PARAMS
from harness.zone_solo_cyan_augmented_start import OPTION as GLOBAL
from harness.zone_pair_highpose_exact_speedups import install
from scripts import agent_lock

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
CRITERIA=HERE/'kld-start-criteria.json'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def replay(option,out,criteria):
    raw=Path(criteria['raw']);bundle=read(raw/'setup_bundle.json')
    commands={}
    for row in read(raw/'fixed_commands.json'):commands.setdefault(round(row['t'],6),[]).append(row)
    frames=[json.loads(l) for l in (raw/'robots/r3/frames.jsonl').read_text().splitlines()]
    assert len(frames)==criteria['replay']['frames']
    omit=('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')
    kw={k:v for k,v in bundle['options'].items() if k not in omit}
    kw.update(global_localization=GLOBAL,particle_sampling=OPTION if option=='on' else 'off',
        camera_pitch=criteria['camera_pitch'],servo_stiffness=criteria['servo_stiffness'],
        stiff_camera_table=read(ROOT/'configs/calibration/s2_camera_stiff_target_v1.json'),
        motion_model=bundle['motion_model'],pulse_calibration=bundle['pulse_calibration'],
        extrinsic_calibration=bundle['extrinsic_calibration'],floor_appearance=bundle['floor_appearance'])
    _,undo=install('v98-exact-v6');wall=time.perf_counter();cpu=time.process_time()
    runtime=runtime_class(Runtime)(c.hp.resolve(c.MAP_ID)[0],ROOT/c.CALIBRATION,c.CALIBRATION_SHA,seed=criteria['seed'],**kw)
    provider=runtime.pose;pf=provider.provider.loc._pf;clouds=[];arrays={};poses=[]
    def snapshot(t):
        i=len(clouds);clouds.append(dict(t=t,index=i,n=pf.n))
        arrays[f'p{i}']=pf.px.copy();arrays[f'w{i}']=pf._weights().copy()
    snapshot(0.)
    try:
        provider.on_command(commands[round(frames[0]['sim_time'],6)].pop(0))
        for i,f in enumerate(frames):
            if time.perf_counter()-wall>criteria['replay']['wall_budget_per_condition_s']:
                raise TimeoutError('registered replay wall budget exceeded')
            now=f['sim_time'];data=(raw/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256']
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
            verdict,_=frame_gate.gate().assess({**f,'image':base64.b64encode(data).decode()},'r3',now,ob=False)
            before=len(runtime.amcl_audit['rows']);report=provider.on_frame(now,rgb if verdict==frame_gate.VALID else None)
            est=pf.estimate()
            poses.append(dict(t=now,x=report.x_m,y=report.y_m,yaw=report.yaw_rad,std_xy_m=report.std_xy_m,
                last_fix_t=report.last_fix_t,modes=copy.deepcopy(est.get('global_modes'))))
            if len(runtime.amcl_audit['rows'])!=before:snapshot(now)
            for cmd in commands.get(round(now,6),[]):
                assert not (cmd['kind'] in ('drive','mecanum') and any(cmd.get(k,0) for k in ('forward','left','turn')))
                provider.on_command(cmd)
            if i%70==0:print(option,i+1,'frames, N=',pf.n,flush=True)
        snapshot(frames[-1]['sim_time']);elapsed=time.perf_counter()-wall;cpu_elapsed=time.process_time()-cpu
        amcl=copy.deepcopy(runtime.amcl_audit)
        audit=copy.deepcopy(getattr(runtime,'kld_audit',None))
    finally:
        runtime.close();undo()
    np.savez_compressed(out/f'{option}-clouds.npz',**arrays)
    result=dict(option=option,poses=poses,clouds=clouds,amcl=amcl,kld=audit,
        wall_s=elapsed,cpu_s=cpu_elapsed,gt_inputs=False,physics_runs=0,model_calls=0,
        commands_fixed=True,active_rankings=False,source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        criteria_sha256=sha(CRITERIA),cloud_sha256=sha(out/f'{option}-clouds.npz'),
        input_hashes={str(p):sha(p) for p in [raw/'robots/r3/frames.jsonl',raw/'fixed_commands.json',raw/'setup_bundle.json',ROOT/'configs/calibration/s2_camera_stiff_target_v1.json']})
    (out/f'{option}.json').write_text(json.dumps(result)+'\n')
    return result


def score(out,criteria):
    # Predictions and options are already fixed on disk before this GT read.
    raw=Path(criteria['raw']);truth=[json.loads(l) for l in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
    def gt(t):
        r=min(truth,key=lambda q:abs(q['t']-t));return np.r_[r['robot_xyz_m'][:2],r['robot_yaw_rad']]
    metrics=[];baseline=read(raw.parent/'replay-start-on.json');off_equal=True
    for option in criteria['replay']['conditions']:
        pred=read(out/f'{option}.json');clouds=np.load(out/f'{option}-clouds.npz');near=[]
        errors=[float(np.linalg.norm(np.array([p['x'],p['y']])-gt(p['t'])[:2])) for p in pred['poses']]
        for i,q in enumerate(pred['clouds']):
            p,w=clouds[f'p{i}'],clouds[f'w{i}'];d=p-gt(q['t'])
            yaw=abs(np.arctan2(np.sin(d[:,2]),np.cos(d[:,2])));xy=np.linalg.norm(d[:,:2],axis=1)
            a=(xy<=.25)&(yaw<=np.deg2rad(15));b=(xy<=.1)&(yaw<=np.deg2rad(5))
            near.append(dict(t=q['t'],n=len(p),count=int(a.sum()),mass=float(w[a].sum()),
                tight_count=int(b.sum()),tight_mass=float(w[b].sum())))
            if option=='off':
                ref=baseline['clouds'][i]
                off_equal &= p.tobytes()==np.array(ref['px']).tobytes() and w.tobytes()==np.array(ref['w']).tobytes()
        if option=='off':off_equal &= json.dumps(pred['poses'],sort_keys=True)==json.dumps(baseline['poses'],sort_keys=True)
        false_resolved=any(p['modes']['resolved'] and e>.25 for p,e in zip(pred['poses'],errors))
        metrics.append(dict(option=option,final_error_m=errors[-1],rmse_m=float(np.sqrt(np.mean(np.square(errors)))),
            near_truth=near,final_modes=pred['poses'][-1]['modes'],updates=pred['amcl']['updates'],
            resamples=pred['amcl']['resamples'],wall_s=pred['wall_s'],cpu_s=pred['cpu_s'],false_resolved=false_resolved))
    off,on=metrics
    gates=dict(off_pose_and_cloud_bytes_equal=bool(off_equal),
        truth_mass_increases=on['near_truth'][-1]['mass']>off['near_truth'][-1]['mass'],
        final_position_error=on['final_error_m']<=criteria['gates']['final_position_error_m_max'],
        final_error_improves=on['final_error_m']<off['final_error_m'],
        truth_neighborhood_survives=all(q['count']>0 for q in on['near_truth']),
        no_false_resolved=not on['false_resolved'])
    result=dict(schema='ugrp.s2.kld_start.result.v1',criteria=criteria,conditions=metrics,gates=gates,
        admission_pass=all(gates.values()),physical_runs=0,model_calls=0,gt_use='scoring only after prediction files close',
        hashes={str(p):sha(p) for p in [CRITERIA,out/'off.json',out/'on.json',raw/'eval_only/trajectory.jsonl']})
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(gates=gates,metrics=[{k:q[k] for k in ('option','final_error_m','wall_s','cpu_s')} for q in metrics])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('new output required')
    criteria=read(CRITERIA)
    assert PARAMS['max_samples']==criteria['parameters']['max_samples']
    a.output.mkdir(parents=True)
    held=agent_lock.acquire(agent_lock.DEFAULT_ROOT,owner='codex',branch='codex/s2-realism',
        purpose='s2v33 offline KLD off/on computation timing; physics 0',pid=os.getpid(),expected_minutes=10,timing_sensitive=True)
    try:
        for option in criteria['replay']['conditions']:replay(option,a.output,criteria)
        score(a.output,criteria)
    finally:
        released=agent_lock.release(agent_lock.DEFAULT_ROOT,owner='codex')
        (a.output/'lock.json').write_text(json.dumps(dict(acquired=held,released=released,status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)),indent=2)+'\n')
