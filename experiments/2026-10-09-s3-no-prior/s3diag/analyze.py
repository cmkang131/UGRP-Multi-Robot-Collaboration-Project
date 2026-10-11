import json,math,pathlib
import numpy as np
from harness.zone_s3_no_prior_contract import hp,old
from harness.zone_solo_cyan_landmarks import MapFeatures,landmark_likelihood,wrap,PARAMS
from harness.zone_solo_cyan_amcl_sensor import likelihood
from harness.zone_solo_cyan_likelihood_field import Field
B=pathlib.Path(__file__).parent;RAW=B.parent/'s3-no-prior-6c657124-s14201-v142';S2=B.parent/'s2-realism-99d81d8c-s1065-v141-graduation'
static=hp.resolve(old.solo.MAP_ID)[0];mapped=MapFeatures(static);field=Field(static)
def read(p):return json.loads(p.read_text())
def lines(p):return [json.loads(s) for s in p.read_text().splitlines()]
def gt(raw,r,t):
 p=raw/f'eval_only/{r}/trajectory.jsonl';q=lines(p if p.exists() else raw/'eval_only/trajectory.jsonl');z=min(q,key=lambda q:abs(q['t']-t));return np.array([*z['robot_xyz_m'][:2],z['robot_yaw_rad']])
def matched_features(packet,true):
 rows=[];c,s=np.cos(true[2]),np.sin(true[2]);rot=np.array([[c,-s],[s,c]])
 for f in packet['features']:
  if f['kind']!='floor_line':continue
  world=np.array(f['endpoints'])@rot.T+true[:2];angle=true[2]+np.arctan2(f['normal'][1],f['normal'][0]);m=[]
  for e in mapped.edges:
   hd=abs(e['hue']-f['hue']);hd=min(hd,180-hd)
   if hd>PARAMS['hue_tolerance']:continue
   v=e['b']-e['a'];u=np.clip((world-e['a'])@v/(v@v),0,1);closest=e['a']+u[:,None]*v
   dist=float(np.sqrt(np.mean(np.sum((world-closest)**2,axis=1))));ang=float(abs(wrap(angle-np.arctan2(e['normal'][1],e['normal'][0]))));m.append((dist**2/.1**2+ang**2/np.deg2rad(5)**2,dist,math.degrees(ang),e['region']))
  rows.append(dict(world_endpoints=world.tolist(),best_same_hue=min(m) if m else None,own_pixels=f['pixels']))
 return rows
results={}
for rid,folder,raw in [('r1','baseline-r1-v3',RAW),('r2','baseline-r2',RAW),('r3','baseline-r3',RAW),('s2r3','s2-1065',S2)]:
 r='r3' if rid=='s2r3' else rid;p=read(B/folder/'packets.json');rec=read(B/folder/'record.json');lik=read(B/folder/'likelihood.json');cloud=np.load(B/folder/'clouds.npz');truth=gt(raw,r,1.3);out=[]
 for i,l in enumerate(lik):
  q=next(z for z in p if abs(z['t']-l['t'])<1e-8);px=cloud[f'px_{i}'];w=cloud[f'w_{i}'];v=cloud[f'likelihood_{i}'];correct=(np.linalg.norm(px[:,:2]-truth[:2],axis=1)<=.25)&(abs(wrap(px[:,2]-truth[2]))<=np.deg2rad(15));post=w*v;post/=post.sum()
  best=px[np.argmax(post)];vt=float(likelihood(field,truth[None],q['wall_points'])[0]*landmark_likelihood(mapped,truth[None],q['features'])[0]);vb=float(likelihood(field,best[None],q['wall_points'])[0]*landmark_likelihood(mapped,best[None],q['features'])[0]);clusters=next((z for z in rec['pose_estimate']['rows'] if abs(z['t']-q['t'])<1e-8),None)
  out.append(dict(t=q['t'],pan=q['pose']['6'],walls=len(q['wall_points']),features=len(q['features']),n=len(px),unique_xyz=len(np.unique(px,axis=0)),correct_support=int(correct.sum()),correct_prior_mass=float(w[correct].sum()),correct_posterior_mass=float(post[correct].sum()),max_posterior_particle=best.tolist(),true_sensor_score=vt,best_sensor_score=vb,best_to_true_score=vb/vt,feature_fit_eval_only=matched_features(q,truth),clusters=clusters))
 conv=[]
 for x in rec['poses']:
  if x['std_xy_m']<=.05:
   truthat=gt(raw,r,x['t_est']);err=float(np.linalg.norm([x['x']-truthat[0],x['y']-truthat[1]]));yaw=math.degrees(abs(wrap(x['yaw']-truthat[2])));conv.append(dict(t=x['t'],error_m=err,yaw_error_deg=yaw));break
 results[rid]=dict(start_gt_eval_only=truth.tolist(),observations=out,first_sigma_convergence=conv[:1])
 print(rid,[(x['t'],x['walls'],x['features'],x['correct_support'],round(x['correct_prior_mass'],6),round(x['correct_posterior_mass'],6),round(x['best_to_true_score'],2)) for x in out])
 print('fit',[[round(f['best_same_hue'][1],3) for f in x['feature_fit_eval_only']] for x in out])
(B/'sensor-analysis.json').write_text(json.dumps(results,indent=2)+'\n')
