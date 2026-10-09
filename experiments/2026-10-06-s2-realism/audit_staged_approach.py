"""Post-replay appearance false-stop audit; RGB only, no controller changes."""
import argparse,hashlib,json
from pathlib import Path
import cv2
import numpy as np
from harness.zone_solo_cyan_side_scan import APPEARANCE
from harness import vision_loc_protocol as vp

def audit(replay):
    result=[]
    cases=[dict(seed=r['seed'],raw=r['raw'],observation=r['observation']) for r in replay['runs']]
    cases.append(dict(seed=1054,raw=replay['positive']['raw'],observation=replay['positive']['observation']))
    for case in cases:
        raw=Path(case['raw']);obs=case['observation']
        frames=[json.loads(s) for s in (raw/'robots/r3/frames.jsonl').read_text().splitlines()]
        frame=next(f for f in frames if f['sha256']==obs['image_sha256']);p=raw/frame['path']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==obs['image_sha256']
        bgr=vp.load_vis3()[0].mp.undistort(cv2.imread(str(p)))
        mask=cv2.inRange(cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV),tuple(APPEARANCE['hsv_lower']),tuple(APPEARANCE['hsv_upper']))
        mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8))
        mask=cv2.dilate(mask,np.ones((5,5),np.uint8))
        _,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
        result.append(dict(seed=case['seed'],image=str(p),image_sha256=obs['image_sha256'],
            points=int(np.count_nonzero(mask)),components=[dict(bbox=q[:4].tolist(),pixels=int(q[4])) for q in stats[1:]],
            interpretation='posthoc visual inspection: remote orange horizontal floor/edge through doorway, no peer visible' if 'v136' in str(raw) else 'posthoc visual inspection: standing peer at left edge',
            interpretation_role='evaluation only; not fed back into detector or controller'))
    return dict(cases=result,physics_runs=0,gt_inputs=False,controller_changes_after_outcome=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=audit(json.loads(a.replay.read_text()))
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))
