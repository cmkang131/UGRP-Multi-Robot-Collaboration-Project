"""Only egomap22 own saved detections/commands; seal before GT evaluation."""
import sys,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from harness.self_wall_memory_robust import SelfWallMemory
from harness.active_wall_mapping import OPTIONS
from harness.rbpf_motion_gate import install,OPTION
from harness.self_odom_grid import transform
from scripts.run_active_wall_map import dump
RAW=Path('/Users/changmin/projects/ugrp/outputs/active-wall-map-v1')
OUT=Path('/Users/changmin/projects/ugrp/outputs/rbpf-motion-gate-v1/offline')
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def replay(case):
 ep=RAW/case;out=OUT/case;out.mkdir(parents=True,exist_ok=False)
 commands=sorted(rows(ep/'robots/r3/commands.jsonl'),key=lambda r:r['t'])
 memory=SelfWallMemory('r3',**OPTIONS,self_map_options={'start_time':commands[0]['t']})
 g=install(memory.self_map,rbpf_update=OPTION);cursor=0;poses=[]
 for row in rows(ep/'own-contacts.jsonl'):
  t=row['t']
  while cursor<len(commands) and commands[cursor]['t']<t-1e-8:memory.command(commands[cursor]);cursor+=1
  g.odom.advance(t)
  if row['segments']:g.observe_contacts_confident(t=t,frame_id=row['frame_id'],robot_id='r3',segments=row['segments'],features=row['features'],camera_xy=row['camera'])
  poses.append(dict(t=t,pose=list(g.odom.pose),covariance=g.odom.covariance.tolist()))
 dump(out/'prediction.json',dict(grid=g.export(),poses=poses,decisions=g.decisions))
 digest=hashlib.sha256((out/'prediction.json').read_bytes()).hexdigest();dump(out/'seal.json',dict(sha256=digest,gt_read=False))
 assert 'mujoco' not in sys.modules
 # The following is evaluation-only, after the own prediction is written.
 truth={round(r['t'],6):r for r in rows(ep/'eval_only/trajectory.jsonl')};origin=truth[min(truth)]
 pred=transform([r['pose'][:2] for r in poses],[*origin['robot_xyz_m'][:2],origin['robot_yaw_rad']])
 actual=np.array([truth[round(r['t'],6)]['robot_xyz_m'][:2] for r in poses]);errors=np.linalg.norm(pred-actual,axis=1)
 sigma=np.array([np.sqrt(np.linalg.eigvalsh(np.array(r['covariance'])[:2,:2]).max()) for r in poses])
 ancestry=np.arange(100)
 for d in g.decisions:
  if d.get('resampled'):ancestry=ancestry[d['parent_indices']]
 result=dict(case=case,option=OPTION,gate=g.export()['motion_gate'],matches=sum(d.get('matching_attempted',False) for d in g.decisions),resamples=g.resamples,ancestors=len(set(ancestry)),sigma_xy_end=float(sigma[-1]),path_rmse_m=float(np.sqrt(np.mean(errors**2))),end_error_m=float(errors[-1]),over_3sigma=int((errors>3*sigma).sum()),pose_n=len(poses),prediction_sha256=digest,qualification='Same stored input frontend replay; new physical path or graph comparison is not implied.')
 dump(Path(__file__).resolve().parents[1]/f'results/{case}-on.json',result)
 print(json.dumps(result),flush=True)
if __name__=='__main__':
 for case in ['photo','speckle']:replay(case)
