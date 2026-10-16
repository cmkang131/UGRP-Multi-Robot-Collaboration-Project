"""gcp6 benchmark fixtures from frozen command tapes, not a teacher policy.

All state snapshots are setup/evaluation only. The fixture records their source
and hash, and every profile receives the identical snapshot and command tape.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from scripts.warpfit import dump, digest, host


def finish(root):
    import numpy as np
    import mujoco
    from scripts.simalt_compiled_compat import export_geometry,export_reference
    for name in ('box','beam','drive'):
        folder=root/name;meta=json.loads((folder/'fixture.json').read_text())
        os.chdir(meta['asset_cwd'])
        m=mujoco.MjModel.from_xml_path(str(folder/'scene.xml'))
        export_geometry(m,folder/'scene.xml',mujoco.__version__,folder/'geometry312.npz')
        export_reference(m,folder/'scene.xml',mujoco.__version__,folder/'actuator312.json')
    drive=root/'drive';archive=np.load(drive/'fixture.npz');arrays={k:archive[k] for k in archive.files}
    meta=json.loads((drive/'fixture.json').read_text());groups=[meta['cases'][:9],meta['cases'][9:]]
    for i,group in enumerate(groups):
        length=max(len(arrays[r['id']]) for r in group)
        arrays[f'group{i}']=np.stack([np.concatenate([arrays[r['id']],np.tile(arrays[r['id']][-1],(length-len(arrays[r['id']]),1))]) for r in group],axis=1)
    np.savez_compressed(drive/'fixture-batched.npz',**arrays)
    # Preserve the original generated archive while making the finalized input
    # explicit. No benchmark has consumed it before this preparation finishes.
    (drive/'fixture-unbatched.npz').write_bytes((drive/'fixture.npz').read_bytes())
    (drive/'fixture.npz').write_bytes((drive/'fixture-batched.npz').read_bytes())
    meta['groups']={f'group{i}':[r['id'] for r in group] for i,group in enumerate(groups)}
    dump(drive/'fixture.json',meta)
    dump(root/'fixtures-final.json',{name:{p.name:digest(p) for p in (root/name).iterdir() if p.is_file()}
                                    for name in ('box','beam','drive')})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--teacher-source',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--enabled',action='store_true')
    p.add_argument('--finish-only',action='store_true')
    a=p.parse_args()
    if not a.enabled:p.error('--enabled required')
    host()
    source=a.teacher_source.resolve();root=a.root.resolve()
    own=Path(__file__).resolve().parents[1]
    import numpy as np
    import mujoco
    if mujoco.__version__!='3.12.0':raise ValueError('frozen C3.12 fixture source required')
    if a.finish_only:
        finish(root)
        return
    sys.path.insert(0,str(source));sys.path.insert(1,str(own/'scripts'))
    import scripts
    scripts.__path__.insert(0,str(source/'scripts'))
    os.chdir(source)
    from simalt_physics_compare import prepare
    out=root/'box-full';out.mkdir()
    prepare(SimpleNamespace(plan=own/'experiments/2026-10-15-simalt1/plan.json',
        trace=own/'experiments/2026-10-15-simalt1/trace.jsonl',out=out,sha='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'))
    f=np.load(out/'fixture.npz');m=mujoco.MjModel.from_xml_path(str(out/'scene.xml'));d=mujoco.MjData(m)
    d.qpos[:]=f['qpos'];d.qvel[:]=f['qvel'];mujoco.mj_forward(m,d)
    meta=json.loads((out/'fixture.json').read_text());phases=next(r for r in meta['cases'] if r['name']=='grip')['phases']
    stride=round(.1/m.opt.timestep);begin=phases.index('close')*stride
    end=(max(i for i,x in enumerate(phases) if x=='hold')+1)*stride
    # C trajectory is used ONLY to construct the common grasp-ready starting
    # snapshot. No profile receives C state after this boundary.
    for j in range(begin):d.ctrl[:]=f['grip'][j];mujoco.mj_step(m,d)
    out2=root/'box';out2.mkdir()
    (out2/'scene.xml').write_bytes((out/'scene.xml').read_bytes())
    np.savez_compressed(out2/'fixture.npz',qpos=d.qpos,qvel=d.qvel,ctrl=d.ctrl,
        qacc_warmstart=d.qacc_warmstart,tape=f['grip'][begin:end])
    target=[m.geom(i).name for i in range(m.ngeom) if m.body(m.geom_bodyid[i]).name=='cargo_cyan_2']
    dump(out2/'fixture.json',dict(kind='box',asset_cwd=str(source),original=meta,
        crop_control_rows=[begin//stride,end//stride],phases=phases[begin//stride:end//stride],
        hold_start_s=(phases.index('hold')*stride-begin)*m.opt.timestep,
        target_body='cargo_cyan_2',target_geoms=target,
        finger_geoms=['r1__left_finger','r1__right_finger'],
        start_state_source='C3.12 pre-close fixed tape replay; no subsequent state feedback',
        control_sha256=digest(out2/'fixture.npz'),physics_feedback=0))
    print('box ready',m.nv,(end-begin)*m.opt.timestep,flush=True)
    # Beam: a successful MJWarp world's recorded pre-pick state and its issued
    # commands; never choose new actions from the saved ground truth.
    inp=root/'inputs'
    beam=inp/'runs/warp8-success-w028-0750/derived-terminal-v2-world-028'
    raw=beam/'world-000/raw'
    assets=inp/'src/drivecheck-renderer-5974a181'
    os.chdir(assets)
    xml=(raw/'scene.xml').read_text();m=mujoco.MjModel.from_xml_string(xml)
    states=np.load(beam/'world-000-states.npz')
    start_tick=111  # Saved warp8 transition ready→pick at 11.1s (diagnostic crop).
    stop_tick=171  # 6s fixed lift + early hold, not a new acceptance timeout.
    si=list(states['ticks']).index(start_tick)
    qpos=states['qpos'][si];qvel=states['qvel'][si]
    from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
    from sim.masterpi_drive_friction_v7 import DriveParameters
    fake=SimpleNamespace(physical_params={'servo6_center_pwm':1500.})
    params=DriveParameters();dt=float(m.opt.timestep);stride=round(.1/dt)
    ctrl=np.zeros(m.nu);tape=np.zeros(((stop_tick-start_tick)*stride,m.nu))
    for i in range(m.nu):
        if '__servo_' in m.actuator(i).name:ctrl[i]=qpos[int(m.jnt_qposadr[int(m.actuator_trnid[i,0])])]
    initial_ctrl=ctrl.copy()
    servo_map={1:['servo_gripper_left','servo_gripper_right'],3:['servo_wrist'],4:['servo_elbow'],5:['servo_shoulder'],6:['servo_arm_yaw']}
    keys={1:'gripper',3:'wrist',4:'elbow',5:'shoulder',6:'yaw'}
    for rid in ('r1','r2'):
        rows=[json.loads(x) for x in subprocess.check_output(['zstd','-dc',str(raw/f'teacher-{rid}.jsonl.zst')],text=True).splitlines()]
        rows=sorted(rows,key=lambda x:x['applied_command']['t'])
        # Replay the issued PWM accumulator from the first recorded command,
        # including pre-crop history. Only the already-fixed command clock is read.
        applied={int(k):float(v) for k,v in rows[0]['applied_command']['pwm'].items()}
        rel=np.zeros(4,int);last=rows[0]['applied_command']['t'];row_i=0
        wheels=[m.actuator(f'{rid}__wheel_{n}_drive').id for n in ('fl','fr','rl','rr')]
        for tick in range(round(last/dt),round(stop_tick*.1/dt)):
            at=tick*dt
            while row_i+1<len(rows) and rows[row_i+1]['applied_command']['t']<=at+1e-8:row_i+=1
            command=rows[row_i]['applied_command'];target={int(k):v for k,v in command['pwm'].items()}
            for servo in applied:applied[servo]+=np.clip(target[servo]-applied[servo],-2000.*dt,2000.*dt)
            targets=MasterPiDynamicsV2.pulse_to_joint_targets(fake,{k:int(np.rint(v)) for k,v in applied.items()})
            values=ctrl.copy()
            for servo,names in servo_map.items():
                for name in names:
                    aid=m.actuator(f'{rid}__{name}').id;jid=int(m.actuator_trnid[aid,0])
                    lo,hi=m.jnt_range[jid] if m.jnt_limited[jid] else (-np.inf,np.inf)
                    values[aid]=np.clip(targets[keys[servo]],lo,hi)
            elapsed=at-command['t'];u=np.array(command['wheels'])*np.array([elapsed<dur for dur in command['duration_s']])
            effective,rel=params.command_step(u,rel);values[wheels]=params.torque_cap_nm*effective
            if at>=start_tick*.1:
                index=tick-round(start_tick*.1/dt)
                columns=wheels+[m.actuator(f'{rid}__{name}').id for names in servo_map.values() for name in names]
                tape[index,columns]=values[columns]
    # Idle r3 servo columns retain the saved initial command, rather than zero.
    owned=[i for i in range(m.nu) if m.actuator(i).name.startswith(('r1__','r2__'))]
    for i in range(m.nu):
        if i not in owned:tape[:,i]=initial_ctrl[i]
    out=root/'beam';out.mkdir();(out/'scene.xml').write_text(xml)
    np.savez_compressed(out/'fixture.npz',qpos=qpos,qvel=qvel,ctrl=tape[0],tape=tape)
    target=[m.geom(i).name for i in range(m.ngeom) if m.body(m.geom_bodyid[i]).name=='cargo_beam_1']
    if not target:raise ValueError('beam cargo mapping missing')
    dump(out/'fixture.json',dict(kind='beam',asset_cwd=str(assets),crop_ticks=[start_tick,stop_tick],
        original_raw=str(raw),source_states_sha256=digest(beam/'world-000-states.npz'),
        target_body='cargo_beam_1',target_geoms=target,
        finger_geoms=[f'{rid}__{side}_finger' for rid in ('r1','r2') for side in ('left','right')],
        hold_start_s=5.7,physics_feedback=0,servo_rate_basis='frozen CameraRobotPort 2000 PWM/s',
        source_command_sha256={rid:digest(raw/f'teacher-{rid}.jsonl.zst') for rid in ('r1','r2')}))
    print('beam ready',m.nv,len(tape)*dt,flush=True)
    # Unmodified drivecheck fixture, including its original overlap. No cause
    # ablation is duplicated here; drivecheck owns that separate experiment.
    drive=root/'drive';drive.mkdir()
    orig=inp/'runs/drivecheck/fixture-v3'
    (drive/'scene.xml').write_bytes((orig/'scene.xml').read_bytes())
    f=np.load(orig/'fixture.npz');arrays={k:f[k] for k in f.files}
    meta=json.loads((orig/'fixture.json').read_text());meta.update(kind='drive',asset_cwd=str(assets),
        target_geoms=[],finger_geoms=[],original=str(orig),physics_feedback=0)
    groups=[meta['cases'][:9],meta['cases'][9:]]
    for i,group in enumerate(groups):
        length=max(len(f[r['id']]) for r in group)
        arrays[f'group{i}']=np.stack([np.concatenate([f[r['id']],np.tile(f[r['id']][-1],(length-len(f[r['id']]),1))]) for r in group],axis=1)
    np.savez_compressed(drive/'fixture.npz',**arrays)
    meta['groups']={f'group{i}':[r['id'] for r in group] for i,group in enumerate(groups)}
    dump(drive/'fixture.json',meta)
    dump(root/'fixtures.json',{name:{p.name:digest(p) for p in (root/name).iterdir() if p.is_file()}
                              for name in ('box','beam','drive')})
    finish(root)


if __name__=='__main__':main()
