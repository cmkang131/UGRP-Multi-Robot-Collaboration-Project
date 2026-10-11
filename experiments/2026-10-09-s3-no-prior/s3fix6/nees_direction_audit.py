"""Post-run covariance geometry audit; never imported by a controller."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--replays',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
result={}
for path in sorted(a.replays.glob('550*-*/frontend-covariances.jsonl')):
    receipt=json.loads((path.parent/'result.json').read_text());assert receipt['failure'] is None
    raw=Path(receipt['raw']); gtfile=raw/'eval_only/trajectory.jsonl';gt=rows(gtfile);pose=rows(path)
    by_t={round(r['t'],6):r for r in gt};origin=np.array(gt[0]['robot_xyz_m'][:2]);yaw=gt[0]['robot_yaw_rad'];co,si=math.cos(yaw),math.sin(yaw);rot=np.array([[co,-si],[si,co]])
    actual=np.array([rot.T@(np.array(by_t[round(r['t'],6)]['robot_xyz_m'][:2])-origin) for r in pose])
    delta=np.array([r['pose'][:2] for r in pose])-actual;cov=np.array([r['covariance'] for r in pose])[:,:2,:2]
    vals,vecs=np.linalg.eigh(cov);project=np.einsum('nji,nj->ni',vecs,delta);components=project**2/vals;nees=components.sum(1)
    top=np.argsort(nees)[-5:][::-1]
    result[path.parent.name]=dict(frames=len(pose),source_sha256=sha(path),truth_sha256=sha(gtfile),
        mean=float(nees.mean()),median=float(np.median(nees)),q95=float(np.quantile(nees,.95)),maximum=float(nees.max()),
        over_11_829_fraction=float(np.mean(nees>11.829)),
        scalar_3sigma_fraction=float(np.mean(np.linalg.norm(delta,axis=1)>3*np.sqrt(vals[:,-1]))),
        largest_five=[dict(t=pose[i]['t'],error_xy_m=float(np.linalg.norm(delta[i])),eigenvalues_m2=vals[i].tolist(),
            nees_eigencomponents=components[i].tolist(),nees=float(nees[i])) for i in top])
with a.output.open('x') as f:f.write(json.dumps(dict(evaluation_only=True,selection_rule_changed=False,rows=result),indent=2,allow_nan=False)+'\n')
print(json.dumps({k:{m:v[m] for m in ['mean','median','q95','over_11_829_fraction']} for k,v in result.items()}))
