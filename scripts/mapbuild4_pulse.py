"""Default-off, same-model pulse experiment. CPU integration is comparison only.

All measurements stay on gcp5. No control decision consumes simulator truth.
The requested 60/100/200/400 ms matrix is a diagnostic design, not a threshold.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def dump(p, x):
    Path(p).write_text(json.dumps(x, indent=2, allow_nan=False)+'\n')


def cases():
    return [dict(name=f'{pose}-{axis}-{sign:+d}-{ms}', pose=pose, axis=axis,
                 u=.35*sign, ms=ms)
            for pose in ('drive', 'high')
            for axis, durations, signs in [('left', (60, 100, 200, 400), (1, -1)),
                                           ('forward', (100,), (1,)), ('turn', (100,), (1,))]
            for ms in durations for sign in signs]


def bootstrap(a):
    if platform.system() != 'Linux' or not platform.node().startswith('ugrp-act-l4-gcp5'):
        raise ValueError('GCP5_ONLY')
    queue = json.loads(a.queue.read_text())
    if not Path(queue['rejection_table']).is_file():
        raise ValueError('FUNNEL_REQUIRED')
    if not (ROOT/'SOURCE_SHA').is_file() or (ROOT/'SOURCE_SHA').read_text().strip()!=queue['source_sha']:
        raise ValueError('PINNED_ARCHIVE_REQUIRED')
    for p, h in json.loads((ROOT/'SOURCE_FILES.json').read_text()).items():
        if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h:
            raise ValueError('SOURCE_BYTES_CHANGED:'+p)
    receipt=json.loads(a.renderer_receipt.read_text())
    for p,h in receipt['files'].items():
        if hashlib.sha256((a.renderer_source/p).read_bytes()).hexdigest()!=h:
            raise ValueError('RENDERER_BYTES_CHANGED:'+p)
    sys.path[:0]=[str(a.renderer_source),str(a.renderer_source/'scripts'),str(ROOT),str(ROOT/'scripts')]
    import sim, scripts
    sim.__path__.append(str(ROOT/'sim'));scripts.__path__.append(str(ROOT/'scripts'))
    os.chdir(a.renderer_source)
    import mujoco
    import numpy as np
    from scripts import probe_scene_tex2 as st
    from scripts.generate_scene_textures import MAPS
    from mapbuild3_prepare import load_fixture, named_sets
    from sim.spawn_overlap_check import check, OPTION
    m,scene,hardware,xml,audit=st.build_model(MAPS[0],'walls_floor_contrast_v5_indigo110_s80')
    from scripts.warp_act_core import runtime_sleep_policy
    en=mujoco.mjtSleepPolicy
    m.tree_sleep_policy[:]=runtime_sleep_policy(m.tree_sleep_policy.copy(),auto=int(en.mjSLEEP_AUTO),
        auto_never=int(en.mjSLEEP_AUTO_NEVER),auto_allowed=int(en.mjSLEEP_AUTO_ALLOWED),
        never=int(en.mjSLEEP_NEVER),allowed=int(en.mjSLEEP_ALLOWED))
    fixture=load_fixture(a.fixture,xml)
    meta=json.loads((a.fixture/'fixture.json').read_text())
    rows=cases()
    if getattr(a,'case_filter',None):
        requested=a.case_filter.split(',')
        if len(set(requested))!=len(requested) or not set(requested)<={r['name'] for r in rows}:
            raise ValueError('EXACT_CASE_NAMES_REQUIRED')
        rows=[r for r in rows if r['name'] in requested]
    initial=[];controls=[];admissions=[]
    d=mujoco.MjData(m)
    for row in rows:
        d.qpos[:]=fixture[row['pose']+'_qpos'];d.qvel[:]=0
        admission=check(m,d,**named_sets(m),option=OPTION)
        if not admission['accepted']:raise ValueError('OVERLAPPING_START')
        initial.append(d.qpos.copy());controls.append(fixture[row['pose']+'_ctrl'].copy())
        row['pwm']=meta['selected'][row['pose']]['pwm']
        admissions.append(admission)
    return m,xml,rows,np.stack(initial),np.stack(controls),admissions


def run(a):
    m,xml,rows,initial,controls,admissions=bootstrap(a)
    import numpy as np
    import mujoco
    from sim.masterpi_drive_friction_v7 import DriveParameters
    from harness.e2e_rgb_vo import between
    from mapbuild2_capture import quaternion_heading
    a.output.mkdir(parents=True,exist_ok=False)
    dump(a.output/'queue.json',json.loads(a.queue.read_text()))
    dump(a.output/'admissions.json',admissions)
    drive=DriveParameters();wheel=[m.actuator('r1__wheel_'+n+'_drive').id for n in ('fl','fr','rl','rr')]
    body=m.body('r1__robot').id;adr=int(m.jnt_qposadr[int(m.body_jntadr[body])])
    qadr=[int(m.jnt_qposadr[m.joint('r1__wheel_'+n+'_joint').id]) for n in ('fl','fr','rl','rr')]
    patterns=dict(left=[-1,1,1,-1],forward=[1,1,1,1],turn=[-1,1,-1,1])
    ticks=200 if not a.after_forward else 300
    onset=100 if not a.after_forward else 200
    substeps=round(.01/m.opt.timestep)
    if substeps*m.opt.timestep!=.01 or m.opt.noslip_iterations!=10:raise ValueError('10MS_NOSLIP10_REQUIRED')
    t0=time.monotonic();qstates=[];vstates=[];contacts=[]
    if a.backend=='warp':
        import warp as wp
        import mujoco_warp as mjw
        from simalt_physics_compare import unused_efm
        wp.init();wm=mjw.put_model(m);wm.opt.tolerance.fill_(float(m.opt.tolerance))
        d=mujoco.MjData(m);d.qpos[:]=initial[0];mujoco.mj_forward(m,d)
        def fresh():
            with unused_efm(m,d):wd=mjw.put_data(m,d,nworld=len(rows),nconmax=128,njmax=512)
            wp.copy(wd.qpos,wp.array(initial,dtype=wd.qpos.dtype))
            wp.copy(wd.ctrl,wp.array(controls,dtype=wd.ctrl.dtype))
            return wd
        wd=fresh();mjw.step(wm,wd);wp.synchronize();wd=fresh()
        with wp.ScopedCapture() as cap:
            for _ in range(substeps):mjw.step(wm,wd)
        graph=cap.graph
    else:
        data=[]
        for q,c in zip(initial,controls):
            d=mujoco.MjData(m);d.qpos[:]=q;d.ctrl[:]=c;mujoco.mj_forward(m,d);data.append(d)
    relay=np.zeros((len(rows),4),int)
    error=None
    try:
        for tick in range(ticks+1):
            if a.backend=='warp':
                qs=wd.qpos.numpy();vs=wd.qvel.numpy()
                if np.any(wd.overflow.numpy()) or not np.isfinite(qs).all():raise RuntimeError('CAPACITY_OR_NONFINITE')
            else:qs=np.stack([d.qpos.copy() for d in data]);vs=np.stack([d.qvel.copy() for d in data])
            qstates.append(qs);vstates.append(vs)
            if tick%10==0:
                print(a.backend,tick/100,flush=True)
                dump(a.output/'progress.json',dict(status='RUNNING',t=tick/100))
            if tick==ticks:break
            cs=controls.copy()
            for i,row in enumerate(rows):
                axis=row['axis'];u=row['u'] if onset<=tick<onset+row['ms']//10 else 0.
                if a.after_forward and 100<=tick<110:axis='forward';u=.35
                eff,relay[i]=drive.command_step(u*np.asarray(patterns[axis]),relay[i])
                cs[i,wheel]=drive.torque_cap_nm*eff
            if a.backend=='warp':
                wp.copy(wd.ctrl,wp.array(cs,dtype=wd.ctrl.dtype));wp.capture_launch(graph)
            else:
                for d,c in zip(data,cs):d.ctrl[:]=c;mujoco.mj_step(m,d,nstep=substeps)
    except BaseException as exc:
        error=repr(exc);raise
    finally:
        qs=np.asarray(qstates);vs=np.asarray(vstates)
        np.savez_compressed(a.output/'eval-state.npz',qpos=qs,qvel=vs)
        metrics=[]
        for i,row in enumerate(rows):
            if len(qs)<=onset:continue
            def pose(q):return np.r_[q[adr:adr+2],quaternion_heading(q[adr+3:adr+7])]
            start=pose(qs[onset,i]);delta=between(start,pose(qs[-1,i]));end=onset+row['ms']//10
            at_end=between(start,pose(qs[min(end,len(qs)-1),i]))
            d=mujoco.MjData(m);d.qpos[:]=qs[onset,i];d.qvel[:]=vs[onset,i];mujoco.mj_forward(m,d)
            contact=[dict(g1=m.geom(int(c.geom1)).name,g2=m.geom(int(c.geom2)).name,
                dist=float(c.dist),friction=c.friction.tolist()) for c in d.contact]
            metrics.append(dict(**row,delta=delta.tolist(),during_delta=at_end.tolist(),
                wheel_phase=qs[onset,i,qadr].tolist(),wheel_rotation=(qs[min(end,len(qs)-1),i,qadr]-qs[onset,i,qadr]).tolist(),
                subtree_com=d.subtree_com[body].tolist(),mass=float(m.body_subtreemass[body]),contacts_at_onset=contact))
        dump(a.output/'metrics.json',metrics)
        dump(a.output/'summary.json',dict(status='HOST_ERROR' if error else 'cap_end',error=error,
            backend=a.backend,worlds=len(rows),sim_s=(len(qs)-1)/100,wall_s=time.monotonic()-t0,
            mujoco=mujoco.__version__,scene_xml_sha256=hashlib.sha256(xml.encode()).hexdigest(),
            noslip_iterations=int(m.opt.noslip_iterations),after_forward=a.after_forward,
            physics_steps_per_world=(len(qs)-1)*substeps,torque_nm=drive.torque_cap_nm*(.35-drive.kinetic_fraction),
            input_audit=dict(truth_feedback=0,top_actor_reads=0),command_grid_s=.01))
        dump(a.output/'rejection_table.json',dict(raw=str(a.output),reproduction=sys.argv,
            stages=[dict(stage='requested',cumulative_pass_n=len(rows),rejected_n=0),
                    dict(stage='nonpenetrating',cumulative_pass_n=len(admissions),rejected_n=0),
                    dict(stage='completed',cumulative_pass_n=0 if error else len(rows),rejected_n=len(rows) if error else 0)],
            reasons=[] if not error else [dict(category='HOST_ERROR',reason=error,blocked_object='physics',minimum_gap_m=None,gap_status='not_measured')]))
    if a.backend=='warp' and a.record:
        # Render saved MJWarp qpos, including the complete 10Hz terminal ring;
        # rendering cannot alter the completed physics trajectory.
        import cv2
        from warp5_render import Renderer
        from sim.masterpi_camera_profile import raw_fisheye_remap
        mx,my=raw_fisheye_remap(640,480)
        rc=Renderer(m,wm,wd,[('r1','r1__robot_cam',(640,480)),('r2','r2__robot_cam',(640,480)),
            ('overview','cctv_top',(640,480))],enabled=True,texture_after_lighting=True)
        selected=[i for i,r in enumerate(rows) if r['name'] in
            ('drive-left-+1-60','drive-left-+1-400','high-left-+1-60','drive-forward-+1-100')]
        for tick in range(0,len(qs),10):
            wp.copy(wd.qpos,wp.array(qs[tick],dtype=wd.qpos.dtype));images=rc.render()
            for i in selected:
                folder=a.output/rows[i]['name'];folder.mkdir(exist_ok=True)
                for camera in ('r1','r2','overview'):
                    rgb=np.clip(images[camera][0][i],0,255).astype(np.uint8)
                    if camera!='overview':rgb=cv2.remap(rgb,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                    cv2.imwrite(str(folder/f'{camera}-{tick//10:04d}.jpg'),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,82])
        dump(a.output/'recording.json',dict(hz=10,sim_range=[0,ticks/100],selected=[rows[i]['name'] for i in selected],
            bytes=sum(p.stat().st_size for p in a.output.rglob('*.jpg')),renderer=rc.audit))
    dump(a.output/'SHA256SUMS.json',{str(p.relative_to(a.output)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in a.output.rglob('*') if p.is_file()})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('renderer-source','renderer-receipt','fixture','queue','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--backend',choices=('warp','cpu'),required=True)
    p.add_argument('--record',action='store_true');p.add_argument('--after-forward',action='store_true')
    p.add_argument('--case-filter',help='comma-separated exact registered case names; no new stimulus')
    p.add_argument('--mapbuild4-pulse-v1',action='store_true');a=p.parse_args()
    if not a.mapbuild4_pulse_v1:p.error('default off: --mapbuild4-pulse-v1 required')
    run(a)
