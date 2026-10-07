"""Fixed RGB/command replay of initial scan. GT read only after source closes."""
import argparse,base64,copy,hashlib,json
from pathlib import Path
import cv2
import numpy as np
from harness import zone_solo_cyan_contract_v106 as c
from harness.zone_solo_cyan_real_carry_dev import Runtime
from harness.zone_pair_highpose_exact_speedups import install
from harness import zone_pair_highpose_frame_gate as frame_gate

ROOT=Path(__file__).resolve().parents[2]
RAW=Path('/Users/changmin/projects/ugrp/outputs')
RUNS={1047:'1a2dbf5e',1049:'a8ab38b8'}
EXCLUDE=('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')
EXTRA=dict(carry_pose='real_delivery_v1',camera_calibration='v3_unloaded_sag_v1',
           measurement_model='amcl_likelihood_field_v1',visibility_mask='command_geometry_v1')


def replay(seed,variant,out,*,rng_seed=None,candidate=False):
    raw=RAW/f's2-realism-{RUNS[seed]}-s{seed}-P1-2-place'
    read=lambda name:json.loads((raw/name).read_text())
    record=read('student_record.json');bundle=read('bundle.json')
    commands={}
    for cmd in record['commands']:commands.setdefault(round(cmd['t'],6),[]).append(cmd)
    first_wheel=min(x['t'] for x in record['commands'] if x['kind']=='mecanum' and any(x.get(k,0) for k in ('forward','left','turn')))
    frames=[json.loads(l) for l in (raw/'robots/r3/frames.jsonl').read_text().splitlines()]
    frames=[f for f in frames if f['sim_time']<=first_wheel]
    options={k:v for k,v in bundle['options'].items() if k not in EXCLUDE}
    if variant!='saved':options.update(EXTRA)
    if variant=='legacy':options.update({k:'off' for k in EXTRA})
    if variant.startswith('without_'):options[variant[8:]]='off'
    if variant=='without_measurement_model':options['visibility_mask']='off'
    kwargs=dict(options,motion_model=bundle['motion_model'],pulse_calibration=bundle['pulse_calibration'])
    kwargs['extrinsic_calibration']=json.loads((ROOT/'configs/calibration/s2_camera_v3_unloaded_sag_v1.json').read_text())
    cls=Runtime
    if candidate:
        from harness.zone_solo_cyan_amcl_update import Runtime as cls
        kwargs['amcl_update']='ros_motion_v1'
    _,undo=install('v98-exact-v6')
    runtime=cls(c.hp.resolve(c.MAP_ID)[0],ROOT/c.CALIBRATION,c.CALIBRATION_SHA,
                seed=seed if rng_seed is None else rng_seed,**kwargs)
    provider=runtime.pose;pf=provider.provider.loc._pf
    audits=[];apply=pf.apply_scan;update=pf.update_obs
    def scan(t,obs,pose):
        audit['scan_calls']+=1
        return apply(t,obs,pose)
    def observe(t,obs,pose):
        nonlocal audit
        before=pf.estimate();n=pf.stats.get('resamples',0)
        audit=dict(t=t,obs=obs is not None,scan_calls=0)
        r=update(t,obs,pose)
        after=pf.estimate()
        audit.update(resamples=pf.stats.get('resamples',0)-n,
                     quality=copy.deepcopy(getattr(pf,'partial_fix_last',None)))
        audits.append(audit)
        return r
    pf.apply_scan=scan;pf.update_obs=observe
    provider.on_command(commands[round(frames[0]['sim_time'],6)].pop(0))
    poses=[];delta=0.;audit={}
    try:
        for f,old in zip(frames,record['poses']):
            now=f['sim_time'];data=(raw/f['path']).read_bytes()
            assert hashlib.sha256(data).hexdigest()==f['sha256']
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
            verdict,_=frame_gate.gate().assess({**f,'image':base64.b64encode(data).decode()},'r3',now,ob=False)
            p=provider.on_frame(now,rgb if verdict==frame_gate.VALID else None)
            row=dict(t=now,t_est=old['t_est'],x=p.x_m,y=p.y_m,yaw=p.yaw_rad,last_fix_t=p.last_fix_t)
            poses.append(row)
            delta=max(delta,*(abs(row[k]-old[k]) for k in ('x','y','yaw')))
            for cmd in commands.get(round(now,6),[]):provider.on_command(cmd)
        stats=copy.deepcopy(pf.stats);amcl=copy.deepcopy(getattr(runtime,'amcl_audit',None))
    finally:runtime.close();undo()
    if variant=='saved' and rng_seed is None and not candidate:assert delta<1e-9,delta
    # Evaluation owner: first access to saved truth is after runtime.close().
    gt=[json.loads(l) for l in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
    times=np.array([r['t'] for r in gt]);xy=np.array([r['robot_xyz_m'][:2] for r in gt])
    for p in poses:
        actual=np.array([np.interp(p['t_est'],times,xy[:,j]) for j in (0,1)])
        p['eval_xy_error_m']=float(np.linalg.norm(actual-[p['x'],p['y']]))
    result=dict(seed=seed,rng_seed=seed if rng_seed is None else rng_seed,variant=variant,candidate=candidate,
        physics_runs=0,gt_inputs=False,source_raw=str(raw),options=options,frames=len(poses),
        baseline_max_delta=delta,first_wheel_t=first_wheel,max_error_m=max(p['eval_xy_error_m'] for p in poses),
        end_error_m=poses[-1]['eval_xy_error_m'],stats=stats,audits=audits,poses=poses,amcl=amcl,
        source_hashes={n:hashlib.sha256((raw/n).read_bytes()).hexdigest() for n in ('bundle.json','student_record.json','robots/r3/frames.jsonl','eval_only/trajectory.jsonl')})
    out.mkdir(exist_ok=True,parents=True)
    dest=out/f's{seed}-{variant}-rng{result["rng_seed"]}{"-candidate" if candidate else ""}.json'
    assert not dest.exists();dest.write_text(json.dumps(result)+'\n')
    print(json.dumps({k:result[k] for k in ('seed','rng_seed','variant','candidate','frames','baseline_max_delta','max_error_m','end_error_m')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,choices=RUNS,required=True)
    p.add_argument('--variant',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--rng-seed',type=int);p.add_argument('--candidate',action='store_true');a=p.parse_args()
    replay(a.seed,a.variant,a.output,rng_seed=a.rng_seed,candidate=a.candidate)
