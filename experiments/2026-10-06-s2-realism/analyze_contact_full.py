"""S1051 closed-run audit. Ground truth is used only below for scoring."""
import json,hashlib,sys,cv2,numpy as np
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,'experiments/2026-10-06-s2-realism')
import audit_s1050_projection as a
from harness.zone_solo_cyan_visibility import Visibility
from harness.zone_solo_cyan_observed_amcl import install as observed
from harness.zone_solo_cyan_floor_contact import install as appearance
from harness.zone_solo_cyan_likelihood_field import endpoints
p=Path('/Users/changmin/projects/ugrp/outputs/s2-realism-c26e9afd-s1051-P1-2-place');out=p.parent/'s2-contact-audit-20261007'
read=lambda f:json.loads((p/f).read_text());lines=lambda f:[json.loads(l) for l in (p/f).read_text().splitlines()]
r=read('result.json');b=read('bundle.json');rec=read('student_record.json');managed=json.loads(Path(str(p)+'-managed/manifest.json').read_text())
assert managed['status']=='process_completed' and managed['exit_code']==0
assert not managed['source_changed_during_run'] and not managed['inputs_changed_during_run']
assert r['options']==b['options'] and len(r['options'])==25
assert b['options']['idle_robot_contacts']=='freeze_v1' and b['options']['contact_filter']=='floor_appearance_v1'
frames=lines('robots/r3/frames.jsonl');ft={round(f['sim_time'],6):f for f in frames};gt={round(g['t'],6):g for g in lines('eval_only/trajectory.jsonl')};ca={round(g['t'],6):g for g in lines('eval_only/camera-pose.jsonl')}
for f in frames:assert hashlib.sha256((p/f['path']).read_bytes()).hexdigest()==f['sha256']
assert len(rec['commands'])==r['commands_issued']+1
vl=a.vp.load_vis3()[0];cols=vl.column_positions(96,2);static=a.c.hp.resolve(a.c.MAP_ID)[0];seg=a.geo.wall_segments(static)
models=a.approximate(b['extrinsic_calibration']);v=Visibility();observed(v);audit=appearance(v,b['floor_appearance'])
contacts=[];images=[];lo,hi=r['posthoc_evaluation']['carry_window']
for q in rec['amcl_update']['rows']:
 if not (lo<=q['t']<hi and q['visual_weight_update']):continue
 t=q['t'];f=ft[round(t,6)];servo={int(k):x for k,x in f['commanded_servo'].items()};key=','.join(str(servo[k]) for k in (3,4,5,6))
 cm=a.measured_column_model(vl.mp,a.floor_camera(models['loaded'][key]),cols)
 bgr=cv2.imread(str(p/f['path']));ob=a.observations(vl,bgr,cm,a.own_image_gates()['values'])
 v.on_rgb(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB));masked=v.apply(NS(column_model_for=lambda pose:cm),ob,servo,t)
 points=endpoints(cm,masked);assert len(points)==q['columns'],(t,len(points),q['columns'])
 opt=(np.c_[points,np.zeros(len(points))]-cm.origin)@cm._rot;uv=opt@a.geo.K.T;uv=uv[:,:2]/uv[:,2,None]
 # Only now open GT pose values for semantic scoring, never passed to mask.
 g=gt[round(t,6)];c=ca[round(t,6)];rot=a.geo.rz(g['robot_yaw_rad']);base=np.r_[g['robot_xyz_m'][:2],0.]
 actual=NS(origin=rot.T@(np.array(c['camera_cached_xyz_m'])-base),_rot=rot.T@np.array(c['camera_cached_optical_rotation']),columns=uv[:,0]);pose=np.r_[g['robot_xyz_m'][:2],g['robot_yaw_rad']]
 true,_,_=a.geo.bottom_projection(actual,pose,seg);floor=[]
 for offset in (-4,4):
  rays=a.geo.pixel_rays(actual,uv[:,0],uv[:,1]+offset);z=-actual.origin[2]/rays[:,2];wall=a.geo.wall_depths(actual,pose,rays,static);floor.append((z>0)&(wall>=z-1e-6))
 ff=floor[0]&floor[1]&(abs(uv[:,1]-true)>10);ww=~ff&(abs(uv[:,1]-true)<=4)
 contacts.append(dict(t=t,points=len(uv),floor_color=int(ff.sum()),wall=int(ww.sum()),ambiguous=int((~ff&~ww).sum()),kl=q['kl'],removed=audit['rows'][-1]['removed']))
 image=vl.mp.undistort(bgr)
 for (u,y),floor_hit in zip(uv,ff):cv2.circle(image,(round(u),round(y)),3,(0,0,255) if floor_hit else (0,255,0),-1)
 cv2.putText(image,f"{t:.2f}s floor{ff.sum()} wall{ww.sum()}",(8,470),0,.65,(255,255,255),2)
 images.append(cv2.resize(image,(320,240)))
for i in range(0,len(images),12):
 batch=images[i:i+12]+[np.zeros_like(images[0])]*(12-len(images[i:i+12]));cv2.imwrite(str(out/f's1051-updates-{i//12}.jpg'),np.vstack([np.hstack(batch[j:j+4]) for j in range(0,12,4)]))
post=dict(r['posthoc_evaluation']);post['actual_visibility']={k:v for k,v in post['actual_visibility'].items() if k!='rows'}
original=['result.json','bundle.json','student_record.json','robots/r3/frames.jsonl','eval_only/trajectory.jsonl','eval_only/camera-pose.jsonl']
summary=dict(schema='ugrp.s2.contact_full.v1',raw=str(p),source_sha=r['source_sha'],seed=1051,execution_bundle_id=r['execution_bundle_id'],physics_runs=1,additional_physics_runs=0,model_calls=0,
    status=r['status'],failure=r['failure'],evaluation=r['evaluation'],options=r['options'],posthoc_evaluation=post,
    wall_s=r['wall_s'],sim_s=r['total_sim_s'],wall_per_sim=r['wall_per_sim'],commands=r['commands_issued'],would_stop=r['dev_light_would_stop'],
    hold_status=r['hold_status'],pickup_site_status=r['pickup_site_status'],regrasp_count=r['regrasp_count'],frames_verified=len(frames),
    measurement_contacts=contacts,total_update_points=sum(x['points'] for x in contacts),floor_update_points=sum(x['floor_color'] for x in contacts),wall_update_points=sum(x['wall'] for x in contacts),ambiguous_update_points=sum(x['ambiguous'] for x in contacts),
    gt_usage='posthoc score only, actual Runtime already closed; RGB mask replay has no GT inputs',
    source_changed_during_run=False,source_hashes={str(p/f):hashlib.sha256((p/f).read_bytes()).hexdigest() for f in original},
    contact_audit=dict(attempts=len(rec['contact_filter']['rows']),removed=sum(x['removed'] for x in rec['contact_filter']['rows']),kept=sum(x['kept'] for x in rec['contact_filter']['rows'])))
path=out/'full-summary.json';assert not path.exists();path.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k not in ['source_hashes','measurement_contacts','options']}))
