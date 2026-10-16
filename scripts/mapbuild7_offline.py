"""Same saved own inputs: explicit carry FK + global static-wall registration."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sys


def main(a):
    if not a.enabled or not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_EXPLICIT_ONLY')
    root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(root/'scripts'),str(a.vision),str(a.vision/'scripts')]
    import harness,sim
    harness.__path__.append(str(a.vision/'harness'));sim.__path__.append(str(a.vision/'sim'))
    import numpy as np
    import cv2
    from harness.mapbuild_camera import adapters
    from harness.servo_camera_fk import CARRY_OPTION,transform_from_commands
    from harness.mapbuild_static_registration import StaticRegistration,OPTION
    from harness.mapbuild_rbpf import MapbuildRBPF,OPTION as RBPF
    from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
    from harness.e2e_rgb_vo import compose
    from harness.self_odom_grid import transform
    q=json.loads(a.queue.read_text())
    if not Path(q['rejection_table']).is_file():raise ValueError('PRIOR_FUNNEL_REQUIRED')
    cv2.setNumThreads(1);pair,scan=adapters(CARRY_OPTION)
    calibration=a.vision/'experiments/2026-10-16-reloc16/colour-calibration.json'
    if hashlib.sha256(calibration.read_bytes()).hexdigest()!='a37cf96551abbfb8b38df3efc1cd61f3f357ac9eb3a1dcd0b4d9947242e4e24f':raise ValueError('COLOUR_CHANGED')
    state=ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',json.loads(calibration.read_text()),option=RELOC16_OPTION)
    frames=json.loads((a.input/'own.json').read_text())['frames'];old=None;last=None;pose=np.zeros(3);rows=[];segments=[];scans=[];events=[]
    rbpf=MapbuildRBPF({int(k):v for k,v in frames[0]['servo'].items()},option=RBPF)
    a.output.mkdir(parents=True,exist_ok=False)
    def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    for frame in frames:
        jpg=a.input/frame['rgb']
        if hashlib.sha256(jpg.read_bytes()).hexdigest()!=frame['sha256']:raise ValueError('RGB_CHANGED')
        rgb=cv2.cvtColor(cv2.imread(str(jpg)),cv2.COLOR_BGR2RGB);servo={int(k):v for k,v in frame['servo'].items()}
        flow=dict(status='bootstrap') if old is None else pair(old,rgb,servo) if servo==last else dict(status='unknown_servo_change')
        delta=flow['delta'] if flow['status']=='measured' else frame['command_delta']
        cov=flow['covariance'] if flow['status']=='measured' else frame['command_covariance'];pose=compose(pose,delta)
        view=scan(rgb,servo,state)
        if last is not None and servo!=last:view={**view,'segments':[],'features':[],'qualification':'unknown_servo_change'}
        estimate,event=rbpf.step(frame['t'],frame['frame_id'],delta,cov,view)
        # Collect at existing 1SIM second scan schedule, never use scoring data.
        if event.get('inserted'):
            segments.extend([transform(s,pose).tolist() for s in view['segments']])
        rows.append(dict(t=frame['t'],frame_id=frame['frame_id'],lk_pose=pose.tolist(),rbpf_pose=estimate,lk=flow,motion_delta=delta,motion_covariance=cov))
        scans.append(dict(t=frame['t'],**view));events.append(event);old=rgb;last=servo
    dump(a.output/'trajectory.json',rows);dump(a.output/'scans.json',scans);dump(a.output/'events.json',events)
    dump(a.output/'own-gauge-segments.json',segments)
    # Prediction written before any evaluator opens eval-only files.
    dump(a.output/'prediction-seal.json',dict(scale=1,truth_inputs=0,input_sha256={str(a.input/'own.json'):hashlib.sha256((a.input/'own.json').read_bytes()).hexdigest()},
        prediction_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output.glob('*.json')}))
    reg=StaticRegistration(json.loads((a.input/'static-map.json').read_text()),option=OPTION)
    result=reg.register(segments);dump(a.output/'static-registration.json',result)
    reasons=Counter(r['lk']['status'] for r in rows)
    dump(a.output/'summary.json',dict(raw=str(a.input),frames=len(rows),camera_option=CARRY_OPTION,registration=result,
        motion_status=dict(reasons),wall_visible_frames=sum(bool(s['segments']) for s in scans),
        inserted=sum(bool(e.get('inserted')) for e in events),truth_inputs=0,parameter_tuning=0,
        loaded_physical_qualification='not established by unladen/failed-pickup recordings',reproduction=sys.argv))
    dump(a.output/'rejection_table.json',dict(raw=str(a.input),reproduction=sys.argv,motion_status=dict(reasons),
        stages=[dict(stage='recorded',cumulative_pass_n=len(rows),rejected_n=0),dict(stage='unchanged_servo',cumulative_pass_n=sum(r['lk']['status']!='unknown_servo_change' for r in rows),rejected_n=sum(r['lk']['status']=='unknown_servo_change' for r in rows))],
        registration=result))
    print(json.dumps(json.loads((a.output/'summary.json').read_text())))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    for name in ('input','vision','queue','output'):p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
