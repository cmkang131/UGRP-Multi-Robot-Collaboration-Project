"""Path-only adapter to the frozen egomap14 replay. No new detector/settings."""
from pathlib import Path
import sys
import json
from collections import Counter
import cv2
ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/2026-10-07-wall-parallax/code'))
import replay as frozen
c=frozen.c
c.EXP=EXP
c.OUT=Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-strafe-v1/replay')
c.EPISODES={'strafe-north':c.OUT.parent/'strafe-north-host-retry1',
            'strafe-south':c.OUT.parent/'strafe-south'}

def verify():
    freeze=c.read(ROOT/'experiments/2026-10-07-wall-parallax/freeze.json')
    assert freeze['hashes']==frozen.hashes()
    assert freeze['settings']==json.loads(json.dumps(frozen.settings()))

def prepare():
    verify()
    assert not (EXP/'cohort.json').exists()
    cohort=dict(role='new_data_only_final_confirmation',cases={})
    labels=[]
    for case,ep in c.EPISODES.items():
        rows=list(c.stream(case))
        eligible=[f for f,cm,reason,pose,cov in rows if cm is not None]
        cohort['cases'][case]=dict(episode=str(ep),sources={str(p):c.sha(p) for p in
            [ep/'robots/r3/frames.jsonl',ep/'robots/r3/commands.jsonl']},
            eligible_frames=[f['frame_id'] for f in eligible],counts=dict(Counter(r[2] for r in rows)))
        for k in range(6):
            f=eligible[(2*k+1)*len(eligible)//12]
            rgb=ep/f['path']
            assert c.sha(rgb)==f['sha256']
            image=c.OUT.parent/'annotations'/f'{case}-{k}.png'
            image.parent.mkdir(parents=True,exist_ok=True)
            cv2.imwrite(str(image),c.old.mp.undistort(cv2.imread(str(rgb))))
            labels.append(dict(case=case,k=k,frame_id=f['frame_id'],t=f['sim_time'],
                raw_path=str(rgb),sha256=f['sha256'],image=str(image),undistorted_sha256=c.sha(image),
                polylines=[],ignore=[],status='pending_manual_rgb_annotation'))
    c.dump(EXP/'cohort.json',cohort)
    c.dump(EXP/'new-annotations.json',dict(rule='six_mid_quantiles_per_case',rows=labels))
    print(json.dumps(cohort,indent=2))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('stage',choices=['prepare','predict','score'])
    a=p.parse_args()
    verify()
    if a.stage=='prepare':prepare()
    elif a.stage=='predict':
        assert all(r['status']=='sealed_before_parallax_predictions' for r in c.read(EXP/'new-annotations.json')['rows'])
        for case in c.EPISODES:frozen.predict(case,'parallax_v1')
    else:
        # Both independent prediction receipts must exist BEFORE any score.
        assert all((c.OUT/'parallax_v1'/case/'receipt.json').is_file() for case in c.EPISODES)
        for case in c.EPISODES:frozen.score(case,'parallax_v1')
