"""Post-run only: fixed criteria, actual settings, states and dev_light records."""
import collections,hashlib,importlib.util,json,math,pathlib,sys
import numpy as np
ROOT=pathlib.Path.cwd();RAW=pathlib.Path(sys.argv[1]);DEST=pathlib.Path(sys.argv[2])
spec=importlib.util.spec_from_file_location('s3_posthoc',ROOT/'experiments/2026-10-09-s3-no-prior/s3next/analyze_smoke.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
report=module.evaluate(RAW)
def read(name):return json.loads((RAW/name).read_text())
student=read('student_record.json');bundle=read('bundle.json');result=read('result.json')
report['status']=result['status'];report['host_failure']=result.get('failure');report['applied']=dict(bundle_heading=bundle['options']['heading_mode'],result_heading=result.get('heading_mode'),heading_scope=bundle['heading_scope'],camera_binding=bundle['s3_camera_binding'],runtime_speedups=result.get('runtime_speedups'),heading_by_localizer={r:s.get('heading_mode') for r,s in student['localizers'].items()});report['startup']=student.get('startup');report['startup_finished_at']=student.get('startup_finished_at');report['stage_reached']={};report['would_stop']={}
for rid,local in student['localizers'].items():
 rows=local.get('poses',[]);gt=list(module.lines(RAW/f'eval_only/{rid}/trajectory.jsonl'));t=[q['t'] for q in gt];xy=np.array([q['robot_xyz_m'][:2] for q in gt]);yaw=np.unwrap([q['robot_yaw_rad'] for q in gt]);first_sigma=first_correct=None
 for p in rows:
  if p['std_xy_m']>.05 or p.get('std_yaw_rad',math.inf)>math.radians(5):continue
  at=p['t_est'];err=math.dist([p['x'],p['y']],[np.interp(at,t,xy[:,i]) for i in (0,1)]);ey=abs(math.degrees(math.atan2(math.sin(p['yaw']-np.interp(at,t,yaw)),math.cos(p['yaw']-np.interp(at,t,yaw)))))
  point=dict(t=p['t'],from_first_frame_s=p['t']-rows[0]['t'],error_m=err,yaw_error_deg=ey,certificate_qualified=p.get('convergence_certificate',{}).get('qualified',False))
  if first_sigma is None:first_sigma=point
  if err<=.25 and ey<=15:first_correct=point;break
 report['localization'][rid].update(first_xy_yaw_sigma=first_sigma,first_correct_xy_yaw_sigma=first_correct)
 events=local.get('events',[]);states=[];seen=set()
 for event in events:
  if event.get('event')=='state' and event['state'] not in seen:
   seen.add(event['state']);states.append(dict(t=event['t'],state=event['state']))
 pair=student.get('pair',{}).get('robots',{}).get(rid,{})
 report['stage_reached'][rid]=dict(localizer_states=states,last_localizer_state=local.get('state'),pair_jobs=pair.get('jobs',[]),pair_job_events=[q for q in pair.get('events',[]) if q.get('event') in ('job_started','job_failed','job_finished','job_completed')],cargo_delivered=report['evaluation']['robots'][rid]['delivery_complete'])
 report['would_stop'][rid]=dict(local_counts=local.get('dev_light_would_stop',{}),first_per_code={})
 for event in events:
  if event.get('event')=='dev_light_would_stop':report['would_stop'][rid]['first_per_code'].setdefault(event['code'],event)
def nested(value,path='pair'):
 if isinstance(value,dict):
  if value.get('event')=='dev_light_would_stop' or value.get('kind')=='dev_light_would_stop':yield dict(path=path,row=value)
  for k,v in value.items():yield from nested(v,path+'/'+str(k))
 elif isinstance(value,list):
  for i,v in enumerate(value):yield from nested(v,path+'/'+str(i))
report['pair_would_stop_records']=list(nested(student.get('pair',{})))
report['pair_states']=[]
for pair in student.get('pair',{}).get('pair',[]):
 for rid,robot in pair.get('robots',{}).items():
  report['pair_states'].append(dict(robot=rid,events=robot.get('events',[])))
report['source_artifacts']=[dict(path=str(RAW/n),sha256=hashlib.sha256((RAW/n).read_bytes()).hexdigest()) for n in ['result.json','bundle.json','student_record.json','artifacts.sha256.json']]
if DEST.exists():raise FileExistsError(DEST)
DEST.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
print(json.dumps(dict(status=report['status'],robots=report['evaluation']['robots'],localization={r:{k:v[k] for k in ['first_xy_yaw_sigma','first_correct_xy_yaw_sigma','last']} for r,v in report['localization'].items()},would_stop={r:v['local_counts'] for r,v in report['would_stop'].items()},wall_s=report['evaluation']['wall_s'],sim_s=report['evaluation']['sim_s'],wall_per_sim=report['evaluation']['wall_per_sim']),ensure_ascii=False,indent=2))
