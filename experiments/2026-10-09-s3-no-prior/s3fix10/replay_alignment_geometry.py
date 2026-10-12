"""Saved own-RGB error proposals only; model prediction is not physical success."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from harness.zone_s3_visual_pose_servo import Selector, transform
from harness.zone_final_pair_vision import GRASP_RADIUS_M

p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
b=json.loads((a.raw/'bundle.json').read_text());s=json.loads((a.raw/'student_record.json').read_text())
profiles=b['controller_config']['pulse_calibration']['profiles'];selector=Selector(profiles);summary={}
for rid,rows in s['pair']['pair_heading']['alignment'].items():
    out=[]
    for row in rows:
        if 'errors' not in row:continue
        action,profile,score=selector(profiles,row['errors'])
        errors=np.array(row['errors']);grip=errors[:2]+[GRASP_RADIUS_M,0.]
        if profile is not None:
            q,angle=transform(grip,errors[2],profile['mean_delta'])
            first_error=[q[0]-GRASP_RADIUS_M,q[1],angle]
        else:first_error=errors.tolist()
        out.append(dict(t=row['t'],own_rgb_errors=errors.tolist(),old_action=row['issued'],
            proposed_action=action,model_first_error=first_error,model_horizon=score,
            gt_input=False,physical_success=None))
    path=a.output/(rid+'.jsonl');path.write_text(''.join(json.dumps(r)+'\n' for r in out))
    summary[rid]=dict(rows=len(out),changed=sum(r['old_action']!=r['proposed_action'] for r in out),
        model_horizon_within_original_tolerances=sum(r['model_horizon']['after']<=1e-12 for r in out),
        non_hold=sum(any(r['proposed_action'][k] for k in ('forward','left','turn')) for r in out),
        data_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
record=dict(host='oracle-a1',source_sha=b['source_sha'],scope='saved RGB error proposal replay; no closed-loop or physical convergence claim',
    candidate='existing visual_pose_mpc_v1; constants unchanged',summary=summary,
    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    inputs={n:hashlib.sha256((a.raw/n).read_bytes()).hexdigest() for n in ('bundle.json','student_record.json')})
(a.output/'report.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(summary))
