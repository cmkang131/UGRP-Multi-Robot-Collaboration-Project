"""s2v41 read-only RGB audit; writes a new diagnostic file, no simulation."""
import argparse,json,sys,math,hashlib
from pathlib import Path
from collections import Counter
from types import SimpleNamespace as NS
import numpy as np
import cv2
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,rows,sha
from scripts.run_s2_landmarks_dev import runtime_factory
from harness.zone_solo_cyan_contract_v106 import hp,MAP_ID,ROOT,CALIBRATION,CALIBRATION_SHA
from harness import vision_loc_protocol as vp
from harness import zone_solo_cyan_landmarks as lm
from harness import zone_color_boxes as colors
from harness.zone_solo_cyan_amcl_sensor import endpoints
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.output.exists():raise FileExistsError(args.output)
args.output.parent.mkdir(parents=True,exist_ok=True)
vl=vp.load_vis3()[0];result=[]
for seed,name in RUNS.items():
 raw=OUTPUTS/name;b=read(raw/'bundle.json');rec=read(raw/'student_record.json');frames=rows(raw/'robots/r3/frames.jsonl');fd={round(f['sim_time'],6):f for f in frames};poses={round(p['t'],6):p for p in rec['poses']}
 r=runtime_factory(b)(hp.resolve(MAP_ID)[0],ROOT/CALIBRATION,CALIBRATION_SHA,**b['task']);pf=r.pose.provider.loc._pf
 door=[]
 for a in rec['sensor_landmarks']['rows']:
  f=fd[round(a['t'],6)];servo={int(k):v for k,v in f['commanded_servo'].items()};pf.load.loaded=servo[1]==1500;cm=pf.column_model_for(servo);K=np.linalg.inv(vl.mp.K_INV)
  pts=np.array(a['wall_points']).reshape(-1,2);lo=np.full(len(cm.columns),np.nan);kinds=np.zeros(len(cm.columns),int);projerr=0.
  if len(pts):
   uv=lm.project(cm,np.c_[pts,np.zeros(len(pts))],K);idx=np.argmin(abs(uv[:,0,None]-cm.columns),axis=1);projerr=float(np.max(abs(uv[:,0]-cm.columns[idx])));assert projerr<1e-6,(seed,a['t'],projerr)
   assert len(set(idx))==len(idx);lo[idx]=uv[:,1];kinds[idx]=1
  obs=vl.ColumnObs(cm.columns.copy(),kinds,lo,lo.copy(),np.zeros_like(kinds),lo.copy(),lo.copy())
  np.testing.assert_allclose(endpoints(cm,obs),pts,atol=1e-7)
  data=(raw/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256'];und=vl.mp.undistort(cv2.imdecode(np.frombuffer(data,np.uint8),1))
  count=Counter();captured={}
  # Trace the unchanged original function; count each gate's passed line.
  import inspect
  source,start=inspect.getsourcelines(lm.door_features)
  line_for={start+i:tag for i,s in enumerate(source) for token,tag in [('a,b=points[i],points[j]','separation_pass'),('inside=ranges','width_pass'),('supports=[]','interior_pass'),('center=(a+b)/2','edge_pass')] if token in s}
  def trace(frame,event,arg):
   if frame.f_code is lm.door_features.__code__:
    if event=='line' and frame.f_lineno in line_for:count[line_for[frame.f_lineno]]+=1
    if event=='return':captured.update(frame.f_locals)
    return trace
   return None
  sys.settrace(trace)
  try:features=lm.door_features(und,cm,obs,K,np.ones(und.shape[:2],bool))
  finally:sys.settrace(None)
  door.append(dict(t=a['t'],wall_count=len(pts),column_roundtrip_error_px=projerr,
   valid_6m_columns=int(captured['valid'].sum()),left_jumps=len(captured['left']),right_jumps=len(captured['right']),
   total_pairs=len(captured['left'])*len(captured['right']),**{k:count[k] for k in ('separation_pass','width_pass','interior_pass','edge_pass')},
   upper_bound_detections=len(features),scope='saved postfilter endpoints; all-clear mask optimistic upper bound; original unchanged door function'))
 # Search exhaustion alternates search_i=1 normal retry and soft-fail reset.
 search=[];move_events=[e for e in rec['events'] if e['event']=='state' and e['state']=='search_move' and e['t']>10.4]
 fail_times=[e['t'] for i,e in enumerate(move_events) if i%2==1]
 assert len(fail_times)==rec['dev_light_would_stop'].get('CYAN_NOT_UNIQUELY_VISIBLE',0)
 for t in fail_times:
  f=fd[round(t,6)];servo={int(k):v for k,v in f['commanded_servo'].items()};data=(raw/f['path']).read_bytes();frame=cv2.imdecode(np.frombuffer(data,np.uint8),1)
  components,clipped=colors._colour_components(frame,'cyan',colors.OWN_PROFILE_ZONE)
  det=r.vision._detect(data,servo,kinds=('cyan',),profile=colors.OWN_PROFILE_ZONE)
  p=poses[round(t,6)];c,s=math.cos(p['yaw']),math.sin(p['yaw']);kept=[]
  for d in det['detections']:
   x,y=d['estimated_box_center_base_m'][:2];mx,my=p['x']+c*x-s*y,p['y']+s*x+c*y
   if r.slot['x_range_m'][0]-.15<=mx<=r.slot['x_range_m'][1]+.15 and r.slot['y_range_m'][0]-.15<=my<=r.slot['y_range_m'][1]+.15:kept.append(d)
  mask=colors._mask(cv2.cvtColor(frame,cv2.COLOR_BGR2HSV),colors.OWN_ZONE_CYAN_HSV);ys,xs=np.nonzero(mask)
  search.append(dict(t=t,path=f['path'],sha256=f['sha256'],cyan_px=int(np.count_nonzero(mask)),bbox=None if not len(xs) else [int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())],components=len(components),clipped=clipped,fit_count=len(det['detections']),slot_kept=len(kept),detections=det['detections']))
 inhand=[]
 for check in rec['scene_grasp_check']['checks']:
  inhand.append(dict(status=check['status'],reason=check['reason'],hits=check['hits'],areas={k:[s['area_px'] for s in v] for k,v in check['samples'].items()},first_samples={k:v[0] for k,v in check['samples'].items()},iou=check['mask_iou'],shift=check['centroid_shift_px']))
 r.close();res=dict(seed=seed,door_rows=door,door_stage_sums=dict(sum_count=0),cyan_exhaustion=search,inhand=inhand)
 res['door_stage_sums']={k:sum(a[k] for a in door) for k in ('wall_count','valid_6m_columns','left_jumps','right_jumps','total_pairs','separation_pass','width_pass','interior_pass','edge_pass','upper_bound_detections')}
 result.append(res);print(seed,res['door_stage_sums'],search,flush=True)
args.output.write_text(json.dumps(dict(scope='offline saved RGB/commands/calibration; no physics, thresholds unchanged; door necessary-condition upper bound',runs=result),indent=2)+'\n')
