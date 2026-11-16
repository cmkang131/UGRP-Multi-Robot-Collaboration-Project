"""Predetermined RGB-only annotation sample. No GT or detector invocation."""
import json
from pathlib import Path
import sys
import hashlib
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code')]
import v3_confidence_replay as old
OUT=Path('/Users/changmin/projects/ugrp/outputs/wall-floor-boundary-v1')
EXP=ROOT/'experiments/2026-10-07-wall-floor-boundary'


def main():
    OUT.mkdir(exist_ok=False)
    annotation=[]
    for case,ep in old.EPISODES.items():
        frames,_=old.own_inputs(ep,'r3')
        byid={f['frame_id']:f for f in frames}
        events=old.base.read_rows(old.OUT/case/'v3_unloaded_extrinsic_v1/extraction.jsonl')
        valid=[e for e in events if e['reason']=='calibrated_unloaded']
        canvas=np.full((2*520,3*640,3),245,np.uint8)
        for k in range(6):
            event=valid[int((k+.5)*len(valid)/6)]
            f=byid[event['frame_id']]
            path=ep/f['path']
            assert old.base.sha(path)==f['sha256']
            und=old.mp.undistort(cv2.imread(str(path)))
            dest=OUT/f'{case}-{k}.png'
            cv2.imwrite(str(dest),und)
            annotation.append(dict(case=case,k=k,frame_id=f['frame_id'],t=f['sim_time'],image=str(dest),
                raw_path=str(path),sha256=f['sha256'],undistorted_sha256=old.base.sha(dest),
                polylines=[],ignore=[],status='unannotated'))
            x,y=(k%3)*640,(k//3)*520
            canvas[y+30:y+510,x:x+640]=und
            cv2.putText(canvas,f'{case} k{k} frame{f["frame_id"]}',(x+8,y+21),0,.6,(0,0,0),1)
            for u in range(0,640,100):
                cv2.putText(canvas,str(u),(x+u,y+520-2),0,.35,(0,0,0),1)
            # grid overlays only for coordinate reading; individual PNG has no marks
            for v in range(100,480,100):
                cv2.putText(canvas,str(v),(x+2,y+30+v),0,.38,(0,255,255),1)
        cv2.imwrite(str(OUT/f'{case}-sheet.jpg'),canvas)
        print(case,'eligible',len(valid),'sample',[r['frame_id'] for r in annotation if r['case']==case])
    old.base.dump(EXP/'annotation-sample.json',dict(rule='six_mid_quantiles_per_case',rows=annotation,
        source_sha='dd8fb5dc',annotator='Codex RGB-only visual annotation; no detector overlay',
        warning='manual single-rater annotations, not simulator semantic masks'))

if __name__=='__main__':main()
