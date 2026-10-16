"""gcp5 fixed-frame OFF/ON/RBPF replay; predictions sealed before evaluation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(root/'scripts'),str(a.vision),str(a.vision/'scripts')]
    import harness,sim
    harness.__path__.append(str(a.vision/'harness'));sim.__path__.append(str(a.vision/'sim'))
    import numpy as np
    from harness.selfmap_map_correction import SelfMapCorrection,OPTION
    from harness.mapbuild_rbpf import MapbuildRBPF,OPTION as RBPF
    from harness.mapbuild_camera import CommandCamera
    from harness.servo_camera_fk import CARRY_OPTION
    from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
    def read(p):return json.loads(p.read_text())
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    if not a.rejection_table.is_file():raise ValueError('PRIOR_FUNNEL_REQUIRED')
    a.output.mkdir(parents=True,exist_ok=False)
    frames=read(a.input/'own.json')['frames'];static=read(a.input/'static-map.json')
    off=SelfMapCorrection(static);on=SelfMapCorrection(static,option=OPTION)
    rbpf=MapbuildRBPF({int(k):v for k,v in frames[0]['servo'].items()},option=RBPF)
    camera=CommandCamera(camera_pose=CARRY_OPTION);previous=None
    calibration=a.vision/'experiments/2026-10-16-reloc16/colour-calibration.json'
    if sha(calibration)!='a37cf96551abbfb8b38df3efc1cd61f3f357ac9eb3a1dcd0b4d9947242e4e24f':raise ValueError('COLOUR_CHANGED')
    state=ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',read(calibration),option=RELOC16_OPTION)
    saved_path=(a.saved/('trajectory.json' if (a.saved/'trajectory.json').is_file() else 'online-trajectory.json')) if a.saved else None
    saved_rows=read(saved_path) if a.saved else None;saved_scans=read(a.saved/'scans.json') if a.saved else None
    if saved_rows and [r['frame_id'] for r in saved_rows]!=[f['frame_id'] for f in frames]:raise ValueError('FRAME_JOIN_REQUIRED')
    rows=[];scans=[];events=[];raw_lk=np.zeros(3)
    registration_times={e['t']:e['event'] for e in read(a.input/'events.json') if e['event'] in ('prescan','rescan','postpickup','postsetdown')}
    from harness.e2e_rgb_vo import compose
    for i,f in enumerate(frames):
        file=a.input/f['rgb']
        if sha(file)!=f['sha256']:raise ValueError('RGB_CHANGED')
        servo={int(k):v for k,v in f['servo'].items()}
        if saved_rows:flow=saved_rows[i]['lk'];scan=saved_scans[i]
        else:
            import cv2
            cv2.setNumThreads(1);rgb=cv2.cvtColor(cv2.imread(str(file)),cv2.COLOR_BGR2RGB)
            flow,scan=camera.observe(f['t'],previous,rgb,servo,state);previous=rgb
        raw_lk=compose(raw_lk,flow['delta'] if flow['status']=='measured' else f['command_delta'])
        no,e0=off.step(f['t'],f['frame_id'],f['command_delta'],f['command_covariance'],flow,scan)
        yes,e1=on.step(f['t'],f['frame_id'],f['command_delta'],f['command_covariance'],flow,scan)
        rb,e2=rbpf.step(f['t'],f['frame_id'],e0['motion_delta'],e0['motion_covariance'],scan,servo=servo)
        rows.append(dict(t=f['t'],frame_id=f['frame_id'],off_pose=no,on_pose=yes,lk_pose=raw_lk.tolist(),rbpf_pose=rb,
            motion_delta=e0['motion_delta'],motion_covariance=e0['motion_covariance'],lk=flow,servo=f['servo']))
        scans.append(scan);events.append(dict(t=f['t'],correction=e1,rbpf=e2))
        if f['t'] in registration_times:
            result=on.initialize_static();events[-1]['registration']=dict(label=registration_times[f['t']],**result)
        if i%100==0:print(json.dumps(dict(frame=i,t=f['t'],inserted=len(on.frames),accepted=sum(e['accepted'] for e in on.ledger))),flush=True)
    dump(a.output/'trajectory.json',rows);dump(a.output/'scans.json',scans);dump(a.output/'events.json',events)
    dump(a.output/'submaps.json',dict(active=on.frames,ledger=on.ledger))
    # Initialization is reported independently. Rejected transforms stay None;
    # a successful end-of-recording anchor is NOT backfilled into past frames.
    registration=on.initialize_static();dump(a.output/'static-registration.json',registration)
    sources=[a.input/'own.json',a.input/'commands.json',a.input/'static-map.json',a.rejection_table,Path(__file__),root/'harness/selfmap_map_correction.py',root/'harness/self_map_csm.py']
    if a.saved:sources.extend([saved_path,a.saved/'scans.json'])
    sources.append(a.input/'events.json')
    dump(a.output/'prediction-seal.json',dict(scale=1,truth_inputs=0,input_sha256={str(p):sha(p) for p in sources},
        prediction_sha256={p.name:sha(p) for p in a.output.glob('*.json')}))
    eligible=[e for e in on.ledger if e['attempted']];accepted=[e for e in eligible if e['accepted']]
    reasons=Counter(e['reason'] for e in on.ledger);matchreasons=Counter(v['reason'] for e in on.ledger for v in (e['self_match'],e['static_match']) if v)
    stages=[dict(stage='recorded',cumulative_pass_n=len(rows),rejected_n=0),
        dict(stage='visible_wall',cumulative_pass_n=sum(bool(s['segments']) for s in scans),rejected_n=sum(not s['segments'] for s in scans)),
        dict(stage='scheduled_supported',cumulative_pass_n=len(eligible),rejected_n=sum(bool(s['segments']) for s in scans)-len(eligible)),
        dict(stage='map_reference_and_unique_score',cumulative_pass_n=len(accepted),rejected_n=len(eligible)-len(accepted))]
    funnel=dict(raw=str(a.input),reproduction=sys.argv,stages=stages,distribution=[dict(category='map_correction',reason=k,n=v,blocked_object='own_observed_wall',minimum_gap_m=None,gap_status='not_measured') for k,v in reasons.items()],match_reasons=dict(matchreasons))
    dump(a.output/'rejection_table.json',funnel)
    summary=dict(raw=str(a.input),frames=len(rows),sim_s=frames[-1]['t'],map_correction=OPTION,attempts=len(eligible),accepted=len(accepted),
        ambiguous_rejections=sum(v for k,v in matchreasons.items() if 'ambiguous' in k),motion_status=dict(Counter(r['lk']['status'] for r in rows)),
        reasons=dict(reasons),registration=registration,truth_inputs=0,scale_fitting=0,reproduction=sys.argv,rejection_table=str(a.output/'rejection_table.json'))
    dump(a.output/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('input','vision','output','rejection-table'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--saved',type=Path);main(p.parse_args())
