"""Same saved own inputs, frozen LK/RBPF. No evaluation file is opened here."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]


def dump(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def run(a):
    if not a.enabled or not platform.node().startswith('ugrp-act-l4-gcp5'):
        raise ValueError('EXPLICIT_GCP5_ONLY')
    q=json.loads(a.queue.read_text())
    if not Path(q['rejection_table']).is_file():raise ValueError('EXISTING_FUNNEL_REQUIRED')
    sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(a.vision),str(a.vision/'scripts')]
    import harness,sim
    harness.__path__.append(str(a.vision/'harness'));sim.__path__.append(str(a.vision/'sim'))
    import numpy as np
    import cv2
    from harness.mapbuild_rbpf import virtual_scan,MapbuildRBPF,OPTION
    from harness.e2e_rgb_vo import ground_pair,compose
    from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
    from mapbuild1_replay import read_frame
    from mapbuild5_replay import predicted
    cv2.setNumThreads(1)
    calibration=a.vision/'experiments/2026-10-16-reloc16/colour-calibration.json'
    if hashlib.sha256(calibration.read_bytes()).hexdigest()!='a37cf96551abbfb8b38df3efc1cd61f3f357ac9eb3a1dcd0b4d9947242e4e24f':
        raise ValueError('FROZEN_COLOUR_REQUIRED')
    state=ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',json.loads(calibration.read_text()),option=RELOC16_OPTION)
    data=json.loads((a.input/'own.json').read_text());meta=json.loads((a.input/'summary.json').read_text())
    if data['physics_backend']!='mjwarp' or meta['contact_profile']['noslip_iterations']!=0:
        raise ValueError('NATIVE_NOSLIP0_RECORDING_REQUIRED')
    a.output.mkdir(parents=True,exist_ok=False);rows=[];events=[];scans=[];previous=None;old=None;last_servo=None
    pose=np.zeros(3);rbpf=None
    for frame in data['frames']:
        rgb=read_frame(a.input,frame);servo={int(k):v for k,v in frame['servo'].items()}
        if rbpf is None:rbpf=MapbuildRBPF(servo,option=OPTION)
        flow=dict(status='bootstrap')
        if previous is not None:
            if frame['t']<=old['t']:raise ValueError('CAUSAL_FRAMES_REQUIRED')
            flow=ground_pair(previous,rgb,servo) if servo==last_servo else dict(status='unknown_servo_change')
        delta=np.array(flow['delta']) if flow['status']=='measured' else np.array(frame['command_delta'])
        covariance=np.array(flow['covariance']) if flow['status']=='measured' else np.array(frame['command_covariance'])
        pose=compose(pose,delta)
        scan=virtual_scan(rgb,servo,state)
        # The previous fixed-camera adapter never had moving-arm intervals.
        # During a declared command-pose change, do not admit a wall update.
        # No new fitted delay/count: exact adjacent-command equality is the
        # existing LK qualification, shared by both methods on this recording.
        if last_servo is not None and servo!=last_servo:
            scan={**scan,'segments':[],'features':[],'qualification':'unknown_servo_change'}
        estimate,event=rbpf.step(frame['t'],frame['frame_id'],delta,covariance,scan)
        rows.append(dict(t=frame['t'],frame_id=frame['frame_id'],lk_pose=pose.tolist(),rbpf_pose=estimate,
            lk=flow,motion_source='measured_LK' if flow['status']=='measured' else 'historical_nominal_command_prediction',
            motion_delta=delta.tolist(),motion_covariance=covariance.tolist(),prior_pose=event['prior_pose']))
        scans.append(dict(t=frame['t'],frame_id=frame['frame_id'],**scan));events.append(event)
        previous=rgb;old=frame;last_servo=servo
        if frame['frame_id']%50==0:print('replay',frame['t'],flow['status'],event['reason'],flush=True)
    dump(a.output/'trajectory.json',rows);dump(a.output/'events.json',events);dump(a.output/'scans.json',scans)
    dump(a.output/'rbpf-map.json',predicted(rbpf.grid))
    inputs=[a.input/'own.json',a.input/'commands.json',calibration]
    dump(a.output/'prediction-seal.json',dict(input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        prediction_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output.glob('*.json')},
        scale=1,initial_gauge=[0,0,0],truth_inputs=0,top_inputs=0,held_world_reads=0))
    visible=sum(bool(s['segments']) for s in scans);inserted=sum(bool(e.get('inserted')) for e in events)
    reasons=Counter(r['lk']['status'] for r in rows)
    dump(a.output/'rejection_table.json',dict(raw=str(a.input),reproduction=sys.argv,
        stages=[dict(stage='recorded_frames',cumulative_pass_n=len(rows),rejected_n=0),
            dict(stage='qualified_wall_scan',cumulative_pass_n=visible,rejected_n=len(rows)-visible),
            dict(stage='inserted_keyframe',cumulative_pass_n=inserted,rejected_n=visible-inserted)],
        motion_reasons=dict(reasons),scan_reasons=dict(Counter(e['reason'] for e in events)),
        column_reasons=dict(Counter(c['reason'] for s in scans for c in s['columns'])),
        reasons=[dict(category='motion_observation',reason=k,count=v,blocked_object='own_camera_support',
            minimum_gap_m=None,gap_status='not_measured') for k,v in reasons.items()],
        constants='mapbuild5 unchanged; moving servo updates use exact same adjacent PWM equality as LK; no GT calibration',
        work=dict(particles=30,colour_line_pair_checks=sum(s['work']['line_pair_checks'] for s in scans),
            proposal_candidates=sum(p.get('candidates',0) for e in events for p in e.get('particle_events',[])))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    for name in ('input','vision','output','queue'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
