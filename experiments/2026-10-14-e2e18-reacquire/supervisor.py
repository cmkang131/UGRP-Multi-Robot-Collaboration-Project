"""Finite VM-local sampling, independent of the Mac/SSH lifetime."""
import argparse,json,os,signal,time,math,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--wall-cap-s',type=int,default=2400);a=p.parse_args()
assert a.batch.startswith('stage-track-') and 0<a.wall_cap_s<=3600
root=Path.home()/'ugrp-sim/runs';out=Path.home()/'ugrp-sim/stage-inputs'/(a.batch+'-watch.jsonl');deadline=time.monotonic()+a.wall_cap_s;last=time.time()
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return {}
def rows(p):
 if not p.exists():return []
 out=[]
 for s in p.read_text().splitlines():
  try:out.append(json.loads(s))
  except json.JSONDecodeError:pass
 return out
while time.monotonic()<deadline:
 now=time.time();record={'unix':now,'monitor_gap_s':now-last,'gap_over_300':now-last>300,'runs':[]};last=now
 for run in sorted(root.glob(a.batch+'-*')):
  if read(run/'RUN_META.json').get('pr')!=483:continue
  entry={'name':run.name,'exit':(run/'EXIT').read_text().strip() if (run/'EXIT').exists() else None,'startup':read(run/'raw/startup-progress.json'),'progress':read(run/'raw/progress.json'),'result':read(run/'raw/result.json'),'robots':{}}
  reason=None
  if entry['exit'] is None and read(run/'STAGE_PLAN.json').get('condition')=='v441':
   try:
    urllib.request.urlopen('http://127.0.0.1:18093/health',timeout=3)
    relay_ok=True
   except urllib.error.HTTPError as exc:relay_ok=exc.code==501
   except Exception:relay_ok=False
   entry['relay_transport_ok']=relay_ok
   if not relay_ok and entry['progress'].get('sim_s',0)>0:
    reason={'reason':'MODEL_RELAY_UNREACHABLE','scope':'owned candidate termination; no silent fallback comparison'}
  for rid in ['r1','r2']:
   oo=rows(run/f'raw/robots/{rid}/ownmap.jsonl')
   if not oo:continue
   x=oo[-1];status=(x.get('carrier_approach') or {}).get('status');tail=[]
   for z in reversed(oo):
    if (z.get('carrier_approach') or {}).get('status')!=status:break
    tail.append(z)
   duration=x['t']-tail[-1]['t'];gt=rows(run/f'raw/eval_only/{rid}/trajectory.jsonl');still=None
   if gt:
    lastgt=gt[-1];start=lastgt['t']
    for z in reversed(gt):
     if math.dist(z['robot_xyz_m'],lastgt['robot_xyz_m'])>.002 or abs(math.atan2(math.sin(z['robot_yaw_rad']-lastgt['robot_yaw_rad']),math.cos(z['robot_yaw_rad']-lastgt['robot_yaw_rad'])))>.004:break
     start=z['t']
    still=lastgt['t']-start
   entry['robots'][rid]={'frame_id':x['frame_id'],'t':x['t'],'status':status,'same_status_s':duration,'eval_only_still_s':still,'beam_visible':bool((x.get('own_beam_observation') or {}).get('result',{}).get('visible')),'command':x.get('command')}
   camera_views={json.dumps((z.get('beam_tracking') or {}).get('servo'),sort_keys=True) for z in tail if x['t']-z['t']<=20}
   entry['robots'][rid]['camera_views_last20_s']=len(camera_views)
   if not (status=='beam_scan' and len(camera_views)>1) and status in ('acquire_scan','beam_skill_pending','beam_return','beam_turn','beam_scan') and duration>=20 and still is not None and still>=20:
    reason={'reason':'KNOWN_SAME_SKILL_NO_BODY_PROGRESS_20_SIM_S','robot_id':rid,'status':status,'duration_s':duration,'eval_only_still_s':still,'scope':'diagnostic termination; no evaluator state supplied to controller'}
  if reason and entry['exit'] is None:
   proc=read(run/'PROCESS.json');pid=proc.get('pid');stat=Path(f'/proc/{pid}/stat')
   if (stat.exists() and proc.get('boot_id')==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
       and stat.read_text().split()[21]==proc.get('start') and str(run).encode() in Path(f'/proc/{pid}/cmdline').read_bytes()):
    reason.update(checked_unix=now,process=proc);(run/'SUPERVISOR_STOP.json').write_text(json.dumps(reason)+'\n');os.kill(pid,signal.SIGINT);entry['stop']=reason
  record['runs'].append(entry)
 with out.open('a') as f:f.write(json.dumps(record)+'\n')
 if record['runs'] and all(x['exit'] is not None for x in record['runs']):break
 time.sleep(45)
