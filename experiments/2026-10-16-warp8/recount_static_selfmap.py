"""Independent stdlib recount from per-robot CSM outputs and evaluation truth."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import socket
import subprocess


def read(p):
    return json.loads(p.read_text() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst']))


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('input','output','owner','requirements','metadata-index'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    assert socket.gethostname().split('.')[0]=='ugrp-act-l4-gcp3'
    seal=read(a.output/'prediction-seal.json')
    for name,h in seal['files'].items():assert sha(a.output/name)==h
    own=read(a.input/'own-inputs.json');truth=read(a.input/'eval-only.json')['rows']
    req=read(a.requirements)['handoff'];reasons=Counter();totals={}
    counted=[]
    for phase in ('before','after'):
        count=Counter(attempts=0,accepted=0,ambiguous_none=0,rejected_none=0,wrong_acceptances=0,requirement_pass=0)
        for w in own['worlds']:
            for rid,frames in w['robots'].items():
                folder=a.output/f"world-{w['world']:03d}-{rid}";r=read(folder/(phase+'.json'))
                count['attempts']+=1;reason=r['registration']['reason'];reasons[reason]+=1
                target=next(t['truth_pose'] for t in truth if t['world']==w['world'] and t['rid']==rid and t['view']==r['views']-1)
                anchor=r['registration']['static_from_own'];passed=False
                assert (anchor is not None)==r['accepted']
                assert (r['map_pose'] is not None)==r['accepted']
                if anchor is not None:
                    q=r['own_pose'];c,s=math.cos(anchor[2]),math.sin(anchor[2])
                    pose=[anchor[0]+c*q[0]-s*q[1],anchor[1]+s*q[0]+c*q[1],anchor[2]+q[2]]
                    error=math.dist(pose[:2],target[:2]);angle=abs(math.atan2(math.sin(pose[2]-target[2]),math.cos(pose[2]-target[2])))
                    passed=error<=req['position_error_m'] and angle+math.atan2(error,req['nominal_target_range_m']-error)<=req['yaw_error_rad']
                    count['accepted']+=1;count['wrong_acceptances']+=not passed;count['requirement_pass']+=passed
                else:
                    count['rejected_none']+=1;count['ambiguous_none']+=reason=='ambiguous_modes'
                counted.append(dict(world=w['world'],rid=rid,phase=phase,reason=reason,accepted=anchor is not None,requirement_pass=passed))
        totals[phase]=dict(count)
    original=read(a.output/'summary.json')
    assert totals==original['counts']
    assert dict(reasons)==original['reason_counts']
    files=0
    for w in own['worlds']:
        for frames in w['robots'].values():
            for f in frames:
                assert sha(a.input/f['rgb'])==f['rgb_sha256']==f['recorded_rgb_sha256'];files+=1
    manifest=read(a.owner/'OWNER_BYTES.json')
    for n,r in manifest['files'].items():assert sha(a.owner/n)==r['sha256']
    corrections=read(a.metadata_index)
    for r in corrections['files']:
        file=Path(r['path']);assert file.stat().st_size==r['bytes'] and sha(file)==r['sha256']
    result=dict(counts=totals,reason_counts=dict(reasons),robot_phase_recounts=len(counted),
        count_agreement=True,prediction_files_rehashed=len(seal['files']),
        input_JPEG_rehashed=files,owner_files_rehashed=len(manifest['files']),
        metadata_corrections_rehashed=len(corrections['files']),original_files_overwritten=0,
        corrections_sha256=sha(a.metadata_index),truth_scope='independent evaluation only',rows=counted)
    (a.output/'independent-recount.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
