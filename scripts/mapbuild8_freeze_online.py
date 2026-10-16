"""Freeze the actually executed ON estimates and same-motion OFF integral.

gcp5 only. Verifies original recording hashes before copying predictions. Reads
own inputs, commands, runtime estimates/scans/decision ledger only: never truth,
setup/spawn, measured joints or eval files. No estimator tuning or rerender.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    import numpy as np
    from harness.e2e_rgb_vo import compose
    from harness.selfmap_map_correction import SelfMapCorrection
    from harness.rbpf_rejection import motion_variance
    def read(p):return json.loads(p.read_text())
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    if not a.rejection_table.is_file():raise ValueError('PRIOR_FUNNEL_REQUIRED')
    raw_manifest=read(a.input/'SHA256SUMS.json')
    # Truth files are hashed as bytes for integrity ONLY; never parsed/read as
    # observations or selected using their values.
    for name,h in raw_manifest.items():
        if sha(a.input/name)!=h:raise ValueError('ORIGINAL_RECORDING_CHANGED:'+name)
    own=read(a.input/'own.json')['frames'];online=read(a.input/'online-trajectory.json');route=read(a.input/'events.json')
    scans=read(a.input/'scans.json') if (a.input/'scans.json').is_file() else None
    if [r['frame_id'] for r in online]!=[r['frame_id'] for r in own]:raise ValueError('FRAME_JOIN_REQUIRED')
    a.output.mkdir(parents=True,exist_ok=False);off=np.zeros(3);rows=[];events=[]
    nominal=SelfMapCorrection(read(a.input/'static-map.json')) if a.nominal_ablation else None
    reg={e['t']:e for e in route if e['event'] in ('prescan','rescan','postpickup','postsetdown')}
    for r,f in zip(online,own):
        off=compose(off,r['motion_delta']);e=dict(t=r['t'],correction=r['map_event'],rbpf=r['wall_event'])
        if r['t'] in reg:e['registration']=reg[r['t']]
        rows.append(dict(t=r['t'],frame_id=r['frame_id'],off_pose=off.tolist(),on_pose=r['corrected_pose'],lk_pose=r['lk_pose'],rbpf_pose=r['rbpf_pose'],
            motion_delta=r['motion_delta'],motion_covariance=r['motion_covariance'],lk=r['lk'],servo=f['servo']))
        if nominal is not None:
            delta=f.get('command_delta_nominal',f['command_delta'])
            value,_=nominal.step(r['t'],r['frame_id'],delta,np.diag(motion_variance(delta)),r['lk'],dict(segments=[],camera=[0,0]))
            rows[-1]['nominal_off_pose']=value
        events.append(e)
    dump(a.output/'trajectory.json',rows);dump(a.output/'events.json',events)
    if scans is not None:dump(a.output/'scans.json',scans)
    sources=[a.input/n for n in ('SHA256SUMS.json','own.json','commands.json','online-trajectory.json','events.json','static-map.json','map-correction.json')]
    if scans is not None:sources.append(a.input/'scans.json')
    sources.extend([Path(__file__),a.rejection_table])
    dump(a.output/'prediction-seal.json',dict(scale=1,truth_inputs=0,method='executed ON vs same fused increments OFF; no rescaling or future anchoring',
        input_sha256={str(p):sha(p) for p in sources},prediction_sha256={p.name:sha(p) for p in a.output.glob('*.json')}))
    es=[e['correction'] for e in events];visible=sum(bool(s['segments']) for s in scans) if scans is not None else sum(e['reason']!='no_visible_scan' for e in es)
    n=len(es);eligible=sum(e['attempted'] for e in es);accepted=sum(e['accepted'] for e in es)
    funnel=dict(raw=str(a.input),reproduction=sys.argv,stages=[dict(stage='frames',cumulative_pass_n=n,rejected_n=0),dict(stage='visible_wall',cumulative_pass_n=visible,rejected_n=n-visible),
        dict(stage='scheduled_supported',cumulative_pass_n=eligible,rejected_n=visible-eligible),dict(stage='adopted_pose_correction',cumulative_pass_n=accepted,rejected_n=eligible-accepted)],
        distribution=[dict(category='map_correction',reason=k,n=v,blocked_object='own_observed_wall',minimum_gap_m=None,gap_status='not_measured') for k,v in Counter(e['reason'] for e in es).items()],
        raw_manifest_sha256=sha(a.input/'SHA256SUMS.json'),original_files_verified=len(raw_manifest))
    dump(a.output/'rejection_table.json',funnel)
    dump(a.output/'summary.json',dict(raw=str(a.input),frames=n,sim_s=rows[-1]['t'],attempts=eligible,accepted=accepted,original_files_verified=len(raw_manifest),
        motion_status=dict(Counter(r['lk']['status'] for r in rows)),reasons=dict(Counter(e['reason'] for e in es)),rejection_table=str(a.output/'rejection_table.json'),reproduction=sys.argv))
    print(json.dumps(read(a.output/'summary.json')))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('input','output','rejection-table'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--nominal-ablation',action='store_true',help='same own frames, own_command_motion_v1 OFF; all other motion code unchanged, no map re-fit')
    main(p.parse_args())
