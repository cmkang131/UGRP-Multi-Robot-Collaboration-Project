"""Finite issued-command round trip; MJWarp physics then batched MJWarp RGB.

Reuses mapbuild4's scene/clean-start admission, wheel relay and MJWarp graph.
The fixed stimulus never reads truth; saved states are renderer/evaluation only.
No wall deadline, contact edits, model calls or CPU integration.
"""
import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from mapbuild4_pulse import bootstrap, dump


def plan():
    # All magnitudes/durations measured by mapbuild4. 400ms lateral persists
    # after its stop tail (~44mm warm); 60ms is deliberately absent. The 1s
    # cycle is the measured mapbuild4 pulse+stop interval, not an action cap.
    rows = [dict(t=1.+i, axis='forward', value=.35, duration_s=.1) for i in range(18)]
    rows += [dict(t=19.+i, axis='left', value=.35, duration_s=.4) for i in range(10)]
    rows += [dict(t=29.+i, axis='left', value=-.35, duration_s=.4) for i in range(10)]
    return rows, 40.


def run(a):
    a.backend = 'warp'; a.contact_profile = 'baseline_noslip10'
    a.case_filter = 'drive-forward-+1-100'
    m, xml, cases, initial, controls, admission = bootstrap(a)
    import numpy as np
    import cv2
    import mujoco
    import mujoco_warp as mjw
    import warp as wp
    from simalt_physics_compare import unused_efm
    from warp5_render import Renderer
    from sim.masterpi_drive_friction_v7 import DriveParameters
    from sim.masterpi_camera_profile import raw_fisheye_remap
    from harness.e2e_rgb_vo import between, K, D
    from mapbuild2_capture import quaternion_heading
    from mapbuild2_commands import increments
    queue = json.loads(a.queue.read_text())
    if queue.get('toggle') != 'mapbuild5_recording_v1' or queue.get('enabled') is not True:
        raise ValueError('EXPLICIT_RECORDING_TOGGLE_REQUIRED')
    lease = Path('/home/ugrp/ugrp-sim/leases/mapbuild5.json')
    if not lease.is_file():
        raise ValueError('OWN_LEASE_REQUIRED')
    a.output.mkdir(parents=True, exist_ok=False)
    dump(a.output/'RUN_META.json',dict(schema='ugrp.run_meta.v1',**{'class':'dev'},pr=556,
         branch='codex/mapbuild1',sha=queue['source_sha'],batch='mapbuild5'))
    commands, end = plan(); dump(a.output/'commands.json', commands)
    dump(a.output/'queue.json', queue); dump(a.output/'admissions.json', admission)
    dump(a.output/'camera-calibration.json', dict(K=K.tolist(), D=D.tolist(), width=640, height=480,
         source='fixed v3 K/D + harness.servo_camera_fk.transform_from_commands; own PWM only',
         servo=cases[0]['pwm'], renderer_sha='5974a181a2cec9731339a6ce3aadc0464b8dddcf'))
    wp.init(); wm = mjw.put_model(m); wm.opt.tolerance.fill_(float(m.opt.tolerance))
    d = mujoco.MjData(m)
    d.qpos[:]=initial[0];mujoco.mj_forward(m,d)
    with unused_efm(m, d):
        wd = mjw.put_data(m, d, nworld=1, nconmax=128, njmax=512)
    def reset():
        wp.copy(wd.qpos, wp.array(initial, dtype=wd.qpos.dtype))
        wp.copy(wd.ctrl, wp.array(controls, dtype=wd.ctrl.dtype))
    reset(); mjw.step(wm, wd); wp.synchronize()
    with unused_efm(m, d):
        wd = mjw.put_data(m, d, nworld=1, nconmax=128, njmax=512)
    reset()
    substeps = round(.01/m.opt.timestep)
    if substeps*m.opt.timestep != .01:
        raise ValueError('EXACT_10MS_REQUIRED')
    with wp.ScopedCapture() as capture:
        for _ in range(substeps):
            mjw.step(wm, wd)
    graph = capture.graph
    drive = DriveParameters(); relay = np.zeros(4, int)
    wheels = [m.actuator('r1__wheel_'+n+'_drive').id for n in ('fl', 'fr', 'rl', 'rr')]
    pattern = dict(forward=[1,1,1,1], left=[-1,1,1,-1], turn=[-1,1,-1,1])
    saved = []; t0 = time.monotonic(); error = None
    try:
        for tick in range(round(end*100)+1):
            t = tick/100
            if tick % 10 == 0:
                q = wd.qpos.numpy().copy()
                if np.any(wd.overflow.numpy()) or not np.isfinite(q).all():
                    raise RuntimeError('CAPACITY_OR_NONFINITE')
                saved.append(q[0]); print('physics', t, flush=True)
            if t == end:
                break
            u = np.zeros(4)
            for cmd in commands:
                if round(cmd['t']*100) <= tick < round((cmd['t']+cmd['duration_s'])*100):
                    u = cmd['value']*np.asarray(pattern[cmd['axis']]); break
            effective, relay = drive.command_step(u, relay)
            control = controls.copy(); control[:, wheels] = drive.torque_cap_nm*effective
            wp.copy(wd.ctrl, wp.array(control, dtype=wd.ctrl.dtype)); wp.capture_launch(graph)
    except BaseException as exc:
        error = repr(exc); raise
    finally:
        np.savez_compressed(a.output/'eval-state.npz', qpos=np.asarray(saved))
        dump(a.output/'physics.json', dict(status='HOST_ERROR' if error else 'cap_end', error=error,
             frames=len(saved), sim_s=(len(saved)-1)/10, wall_s=time.monotonic()-t0,
             physics_steps=max(0,len(saved)-1)*10*substeps))
    # Time indices become independent renderer worlds, never physical resets or
    # kinematic pose stimuli. n=16 is the existing project batch size; padding
    # in the final batch is discarded. Rendering cannot alter saved physics.
    n = 16
    with unused_efm(m, d):
        rd = mjw.put_data(m, d, nworld=n, nconmax=128, njmax=512)
    rc = Renderer(m, wm, rd, [('r1','r1__robot_cam',(640,480)), ('r2','r2__robot_cam',(640,480)),
                  ('overview','cctv_top',(640,480))], enabled=True, texture_after_lighting=True)
    mx, my = raw_fisheye_remap(640,480)
    body = m.body('r1__robot').id; adr = int(m.jnt_qposadr[int(m.body_jntadr[body])])
    pose = lambda q: np.r_[q[adr:adr+2], quaternion_heading(q[adr+3:adr+7])]
    origin = pose(saved[0]); own = []; labels = []; ring = deque(maxlen=101)
    folder = a.output/'roundtrip'; folder.mkdir()
    for begin in range(0,len(saved),n):
        batch = saved[begin:begin+n]; count = len(batch)
        batch = np.asarray(batch+[batch[-1]]*(n-count))
        wp.copy(rd.qpos, wp.array(batch, dtype=rd.qpos.dtype)); images = rc.render()
        for j in range(count):
            k = begin+j
            for camera in ('r1','r2','overview'):
                rgb = np.clip(images[camera][0][j],0,255).astype(np.uint8)
                if camera != 'overview':
                    rgb = cv2.remap(rgb,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
                path = folder/f'{camera}-{k:04d}.jpg'
                if not cv2.imwrite(str(path),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,82]):
                    raise RuntimeError('JPEG_WRITE_FAILED')
            path = folder/f'r1-{k:04d}.jpg'
            own.append(dict(sequence='roundtrip',robot_id='r1',frame_id=k,t=k/10,
                rgb=str(path.relative_to(a.output)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                servo={str(s):v for s,v in cases[0]['pwm'].items()},command_delta=[0.]*3,
                command_covariance=np.zeros((3,3)).tolist()))
            labels.append(dict(sequence='roundtrip',frame_id=k,t=k/10,pose=between(origin,pose(saved[k])).tolist()))
            ring.append(k)
        dump(a.output/'progress.json',dict(status='RENDERING',recorded=len(own),expected=len(saved)))
        print('rendered',len(own),flush=True)
    inc = increments(own,commands)
    own = [{**r,**inc[r['sequence'],r['frame_id']]} for r in own]
    dump(a.output/'own.json', dict(schema='ugrp.mapbuild1.own.v1',backend='mjwarp_render',physics_backend='mjwarp',
         scope='physical_fixed_command_roundtrip',frames=own))
    dump(a.output/'eval-only.json',dict(frames=labels,first_origin=[origin.tolist()],evaluation_only=True))
    dump(a.output/'summary.json',dict(status='cap_end',source_sha=queue['source_sha'],scene='walls_floor_contrast_v5_indigo110_s80',
         scene_xml_sha256=hashlib.sha256(xml.encode()).hexdigest(),frames=len(own),worlds=1,sim_s=end,
         recording=dict(hz=10,terminal_sim_s=10,retained=list(ring),bytes=sum(p.stat().st_size for p in folder.glob('*.jpg'))),
         renderer=rc.audit,physics_backend='mjwarp',wall_s=time.monotonic()-t0,
         input_audit=dict(top_actor_reads=0,truth_feedback=0,cpu_physics_steps=0),termination='cap_end'))
    dump(a.output/'rejection_table.json',dict(raw=str(a.output),reproduction=sys.argv,
         stages=[dict(stage='requested_frames',cumulative_pass_n=len(saved),rejected_n=0),
                 dict(stage='recorded_frames',cumulative_pass_n=len(own),rejected_n=len(saved)-len(own))],reasons={}))
    dump(a.output/'SHA256SUMS.json',{str(p.relative_to(a.output)):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in a.output.rglob('*') if p.is_file()})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('renderer-source','renderer-receipt','fixture','queue','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--mapbuild5-recording-v1',action='store_true'); a = p.parse_args()
    if not a.mapbuild5_recording_v1:
        p.error('default off; --mapbuild5-recording-v1 required')
    run(a)
