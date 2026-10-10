"""Own RGB/command replay only. No world construction, stepping, or eval input."""
import argparse, base64, collections, copy, hashlib, io, json, pathlib, time
import numpy as np
from PIL import Image
from harness import zone_s3_no_prior_contract as c
from harness.zone_s3_no_prior import solo_factory
from harness.zone_pair_highpose_exact_speedups import install
from harness.zone_solo_cyan_bias_tempering import closure,replace_cell
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_landmarks import Measurement

P=argparse.ArgumentParser();P.add_argument('--raw',type=pathlib.Path,required=True);P.add_argument('--out',type=pathlib.Path,required=True);P.add_argument('--robot',required=True);P.add_argument('--seed',type=int);P.add_argument('--until',type=float,default=43.55);P.add_argument('--packets',type=pathlib.Path);P.add_argument('--recorded-mount',action='store_true');P.add_argument('--certify',action='store_true');P.add_argument('--sensor',choices=['original','wall-only'],default='original');a=P.parse_args();a.out.mkdir(parents=True,exist_ok=False)
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def save(n,v): (a.out/n).write_text(json.dumps(v,indent=2)+'\n')
b=json.loads((a.raw/'bundle.json').read_text());static=c.hp.resolve(b['map_id'])[0]
config=b.get('controller_config') or {k:b[k] for k in ['options','floor_appearance_config','motion_profile_config','extrinsic_profile_config','camera_profile_config','pulse_calibration_config','flow_config'] if k in b}
if 'controller_config' not in b:
 config=c.controller_config() # verified identical sensor/motion fields; only irrelevant idle freeze differs
if a.recorded_mount:config['options']['recorded_camera_mount']='legacy_centered_replay_v1'
if a.certify:config['options']['localization_certification']='posterior_consensus_v1'
seed=a.seed if a.seed is not None else b['seed']+int(a.robot[-1])-1
_,undo=install('v98-exact-v6'); own=None;start=time.monotonic();packets=[];likelihood_rows=[];snapshots={}
replacement=None if a.packets is None else json.loads(a.packets.read_text())
try:
 own=solo_factory(config)(static,c.ROOT/b.get('calibration',c.old.solo.CALIBRATION),b['calibration_sha256'],seed=seed,robot_id=a.robot,pickup_slot=next(o['initial_location']['slot'] for o in c.inputs()[2]['orders'] if o['kind']=='cyan'),destination='B')
 pf=own.pose.provider.loc._pf;wrapper=pf.update_obs;selected=closure(wrapper)['selected'];measure=selected.__globals__['endpoints'];score=selected.__globals__['likelihood'];state=closure(wrapper)['state']
 def measured(cm,obs):
  packet=measure(cm,obs);i=len(packets)
  if replacement is not None and str(round(state['t'],3)) in replacement:
   z=replacement[str(round(state['t'],3))];packet=Measurement(np.array(z['wall_points']).reshape(-1,2),copy.deepcopy(z['features']))
  packets.append(dict(t=state['t'],pose=copy.deepcopy(state['pose']),wall_points=packet.wall.tolist(),features=copy.deepcopy(packet.features),origin=cm.origin.tolist(),rotation=cm._rot.tolist()))
  return packet
 def scored(field,px,packet):
  v=score(field,px,packet)
  if a.sensor=='wall-only':
   from harness.zone_solo_cyan_amcl_sensor import likelihood
   v=likelihood(field,px,packet.wall)
  i=len(likelihood_rows);snapshots[f'px_{i}']=px.copy();snapshots[f'w_{i}']=pf._weights().copy();snapshots[f'likelihood_{i}']=v.copy()
  likelihood_rows.append(dict(t=pf.t,n=pf.n));return v
 pf.update_obs=replace_cell(wrapper,'selected',bind(selected,endpoints=measured,likelihood=scored))
 commands=rows(a.raw/f'robots/{a.robot}/commands.jsonl');by=collections.defaultdict(list)
 for x in commands[1:]:by[round(x['t'],9)].append(x)
 initial=commands[0];own.initial_commands(round(initial['t'],9),{a.robot:{int(k):v for k,v in initial['pulses'].items()}})
 for i,f in enumerate(rows(a.raw/f'robots/{a.robot}/frames.jsonl')):
  now=f['sim_time']
  if now>a.until+1e-8:break
  jpeg=(a.raw/f['path']).read_bytes();assert hashlib.sha256(jpeg).hexdigest()==f['sha256']
  obs={k:v for k,v in f.items() if k not in ('path','commanded_servo')};obs['image']=base64.b64encode(jpeg).decode()
  own.on_frames(now,{a.robot:(obs,np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB')))})
  for x in by[round(now,9)]:own.on_command(a.robot,now,{k:v for k,v in x.items() if k!='t'})
 record=own.record(); save('record.json',record);save('packets.json',packets);save('likelihood.json',likelihood_rows)
 snapshots['final_px']=pf.px.copy();snapshots['final_weights']=pf._weights().copy();np.savez_compressed(a.out/'clouds.npz',**snapshots)
 save('receipt.json',dict(raw=str(a.raw),robot=a.robot,seed=seed,frames=i+1,until=a.until,wall_s=time.monotonic()-start,simulation_runs=0,gt_input=False,sensor=a.sensor,certification=a.certify,recorded_mount=a.recorded_mount,measurement_replacement=None if a.packets is None else str(a.packets)))
 print(json.dumps(dict(robot=a.robot,seed=seed,poses=len(record['poses']),packets=len(packets),last=record['poses'][-1]['std_xy_m'],wall_s=time.monotonic()-start)),flush=True)
finally:
 if own:own.close()
 undo()
