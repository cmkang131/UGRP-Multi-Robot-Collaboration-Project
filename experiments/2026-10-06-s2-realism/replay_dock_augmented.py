"""s1052 fixed-command stationary own-RGB replay; no evaluation inputs."""
import argparse,base64,copy,hashlib,json
from pathlib import Path
import cv2
import numpy as np
from harness import zone_solo_cyan_contract_v106 as c
from harness.zone_solo_cyan_augmented_start import Runtime,OPTION,rank_views
from harness.zone_pair_highpose_exact_speedups import install
from harness import zone_pair_highpose_frame_gate as frame_gate
from harness.zone_solo_cyan_likelihood_field import endpoints
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent


def replay(option,out):
    if out.exists():raise ValueError('new output required')
    criteria=json.loads((HERE/'dock-augmented-criteria.json').read_text());raw=Path(criteria['raw'])
    record=json.loads((raw/'student_record.json').read_text());bundle=json.loads((raw/'bundle.json').read_text())
    commands={}
    for row in record['commands']:commands.setdefault(round(row['t'],6),[]).append(row)
    frames=[json.loads(l) for l in (raw/'robots/r3/frames.jsonl').read_text().splitlines()]
    frames=[f for f in frames if f['sim_time']<criteria['window_sim_s'][1]]
    exclude=('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')
    kwargs={k:v for k,v in bundle['options'].items() if k not in exclude}
    kwargs.update(global_localization=option,motion_model=bundle['motion_model'],
        pulse_calibration=bundle['pulse_calibration'],extrinsic_calibration=bundle['extrinsic_calibration'],
        floor_appearance=bundle['floor_appearance'])
    _,undo=install('v98-exact-v6')
    runtime=Runtime(c.hp.resolve(c.MAP_ID)[0],ROOT/c.CALIBRATION,c.CALIBRATION_SHA,seed=1052,**kwargs)
    provider=runtime.pose;pf=provider.provider.loc._pf
    clouds=[];views=[];seen=set();update=pf.update_obs
    def snapshot(t,event):clouds.append(dict(t=t,event=event,px=pf.px.tolist(),w=pf._weights().tolist()))
    snapshot(0.,'initial')
    def observed(t,obs,pose):
        old=len(runtime.amcl_audit['rows']);key=tuple(sorted(pose.items()))
        if obs is not None and pf.settled(t) and key not in seen:
            seen.add(key);cm=pf.column_model_for(pose)
            views.append(dict(t=t,pose=pose.copy(),columns=obs.columns.tolist(),
                b_kind=obs.b_kind.tolist(),b_lo=obs.b_lo.tolist(),points=endpoints(cm,obs).tolist()))
        result=update(t,obs,pose)
        if len(runtime.amcl_audit['rows'])!=old:snapshot(t,'after_update')
        return result
    pf.update_obs=observed
    provider.on_command(commands[round(frames[0]['sim_time'],6)].pop(0))
    poses=[];max_delta=0.;rankings=[]
    try:
        for f,old in zip(frames,record['poses']):
            now=f['sim_time'];data=(raw/f['path']).read_bytes()
            assert hashlib.sha256(data).hexdigest()==f['sha256']
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
            verdict,_=frame_gate.gate().assess({**f,'image':base64.b64encode(data).decode()},'r3',now,ob=False)
            n=len(runtime.amcl_audit['rows'])
            report=provider.on_frame(now,rgb if verdict==frame_gate.VALID else None)
            est=pf.estimate()
            row=dict(t=now,x=report.x_m,y=report.y_m,yaw=report.yaw_rad,std_xy_m=report.std_xy_m,
                last_fix_t=report.last_fix_t,modes=copy.deepcopy(est.get('global_modes')))
            poses.append(row)
            max_delta=max(max_delta,*(abs(row[k]-old[k]) for k in ('x','y','yaw','std_xy_m')))
            if option!='off' and len(runtime.amcl_audit['rows'])!=n:
                rankings.append(dict(t=now,rankings=rank_views(pf)))
            for cmd in commands.get(round(now,6),[]):
                assert not (cmd['kind'] in ('drive','mecanum') and any(cmd.get(k,0) for k in ('forward','left','turn')))
                provider.on_command(cmd)
        snapshot(frames[-1]['sim_time'],'final')
        audit=copy.deepcopy(runtime.amcl_audit)
    finally:runtime.close();undo()
    result=dict(option=option,poses=poses,clouds=clouds,views=views,amcl=audit,active_rankings=rankings,
        gt_inputs=False,physics_runs=0,model_calls=0,commands_fixed=True,baseline_max_delta=max_delta,
        frame_count=len(frames),raw=str(raw),registration_commit='59870709',
        source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ('harness/zone_solo_cyan_augmented_start.py','harness/zone_solo_cyan_amcl_update.py',
             'experiments/2026-10-06-s2-realism/replay_dock_augmented.py')})
    out.write_text(json.dumps(result)+'\n')
    if option=='off':assert max_delta==0.,'default-off differs from saved execution'
    print(json.dumps(dict(option=option,frames=len(frames),updates=audit['updates'],max_delta=max_delta)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--option',choices=['off',OPTION],default='off')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();replay(args.option,args.output)
