"""gcp2 terminal evidence, no simulation/rendering. GT is evaluator-only."""
import argparse,collections,hashlib,importlib.util,json,math,platform,shutil,subprocess
from pathlib import Path
import numpy as np
import cv2
R=Path('/home/ugrp/ugrp-sim/runs');ROOT=Path(__file__).resolve().parents[2]
def obj(p):return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst']))
def rows(p):return [json.loads(s) for s in (p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'])).splitlines()]
def mod(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def gap(points,obstacle):
 p=cv2.convexHull(np.asarray(points,np.float32)).reshape(-1,2).astype(float);c=np.array(obstacle['center_m']);h=np.array(obstacle['half_extents_m']);a=obstacle.get('yaw_rad',0.);rot=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
 q=np.array([[x,y] for x,y in ((h[0],h[1]),(-h[0],h[1]),(-h[0],-h[1]),(h[0],-h[1]))])@rot.T+c
 axes=[rot[:,0],rot[:,1]]
 for e in np.roll(p,-1,axis=0)-p:
  if np.linalg.norm(e)>1e-12:axes.append(np.array([-e[1],e[0]])/np.linalg.norm(e))
 return max(max(float((p@n).min()-(q@n).max()),float((q@n).min()-(p@n).max())) for n in axes)

def intervals(times,mask,details):
 out=[];last=-2
 for i in np.flatnonzero(mask):
  dt=times[i+1]-times[i]
  if i!=last+1:out.append(dict(start_t=float(times[i]),end_t=float(times[i+1]),sim_s=0.,ticks=0,minimum_gap_m=math.inf,blocked_object=details[i][1]))
  v=out[-1];v['end_t']=float(times[i+1]);v['sim_s']+=float(dt);v['ticks']+=1;v['minimum_gap_m']=min(v['minimum_gap_m'],details[i][0]);last=i
 return out

def main(n,media=False):
 assert platform.node().startswith('ugrp-sim-gcp2')
 b=R/f'reloc20-round{n}';assert (b/'DONE').exists()
 summary=mod('reloc20_summary',ROOT/'experiments/2026-10-16-reloc20/summarize.py');summary.main(n)
 q=obj(b/'queue.json');d=obj(b/'summary.json');verify=mod('verify',ROOT/'experiments/2026-10-16-reloc17/baseline_analyzer.py').verify
 review=mod('review',ROOT/'experiments/2026-10-16-reloc18/review.py');integrity=[];tables=[]
 declarations=obj(ROOT/'experiments/2026-10-16-reloc20/fixed-floor-map.json')['scenarios']
 for t,r in zip(q['runs'],d['runs']):
  raw=Path(t['raw']);result=obj(raw/'result.json');v=verify(raw);integrity.append(dict(run=t['name'],raw=str(raw),integrity=v));assert v['verified'],v
  reason=r.get('termination') or result.get('error') or result.get('termination_reason')
  normalized='HOST_ERROR' if result.get('status')=='HOST_ERROR' else 'cap_end' if reason in ('cap_end','phase_timeout','sim_cap') else reason
  r['termination_normalized']=normalized
  if t['kind']=='carry' and r.get('errors'):
   c=rows(raw/'teacher-commands.jsonl');ev=rows(raw/'eval-only.jsonl');by={round(e['t'],5):e for e in ev};pairs=[(x,by[round(x['t'],5)]) for x in c if round(x['t'],5) in by];times=np.array([x['t'] for x,e in pairs]);phase=[x.get('phase_before',x['phase']) for x,e in pairs]
   static=obj(raw/'carry-static-map.json');plan=obj(raw/'plan.json');beam=declarations[plan['scenario_id']]['obstacles'];details=[]
   for x,e in pairs:
    a=e['base_yaw_rad'];rot=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
    chassis=np.array([[sx*.0594,sy*.06495] for sx,sy in ((1,1),(-1,1),(-1,-1),(1,-1))])@rot.T+np.array(e['base_xyz'][:2])
    values=[(gap(chassis,o),o['id']) for o in beam]
    if e.get('footprint_xy'):values += [(gap(e['footprint_xy'],o),o['id']) for o in static['obstacles']]
    details.append(min(values))
   active=np.array([x in ('carry_to_zone','destination_acquire') for x in phase[:-1]])
   geometry=intervals(times,active & np.array([x[0]<=0 for x in details[:-1]]),details)
   r['geometry_risk_intervals']=geometry;r['geometry_risk_sim_s']=sum(x['sim_s'] for x in geometry)
   r['geometry_scope']='evaluation SAT against initial authored beam and cargo footprint/static walls; not force/contact proof'
   shadow=np.array([x['map_pose']['reloc18_command_shadow'] for x,e in pairs]);truth=np.array([[*e['base_xyz'][:2],e['base_yaw_rad']] for x,e in pairs])
   a=truth[0,2]-shadow[0,2];rot=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
   aligned=(shadow[:,:2]-shadow[0,:2])@rot.T+truth[0,:2]
   yaw=(shadow[:,2]+a-truth[:,2]+np.pi)%(2*np.pi)-np.pi
   r['aligned_command_errors']=dict(xy=summary.dist(np.linalg.norm(aligned-truth[:,:2],axis=1).tolist()),yaw=summary.dist(abs(np.degrees(yaw)).tolist()))
   r['phase_metrics']={label:{key:summary.dist([float(np.linalg.norm(np.array(x['map_pose'][field])[:2]-np.array(e['base_xyz'])[:2])) if key.endswith('xy') else abs(math.degrees(math.atan2(math.sin(x['map_pose'][field][2]-e['base_yaw_rad']),math.cos(x['map_pose'][field][2]-e['base_yaw_rad'])))) for (x,e),ph in zip(pairs,phase) if ph==label]) for key,field in [('visual_xy','pose_estimate'),('visual_yaw','pose_estimate'),('command_xy','reloc18_command_shadow'),('command_yaw','reloc18_command_shadow')]} for label in ('carry_to_zone','destination_acquire')}
   groups={}
   for x,e in pairs:
    candidates=[x.get('reloc20_motion',{}).get('footprint') or {},x.get('destination_acquisition',{}).get('last') or {}]
    for rec in candidates:
     if rec.get('minimum_gap_m') is None or rec.get('reason') in ('route_clear','swept_enclosure_clear'):continue
     key=(rec.get('reason','unspecified'),rec.get('blocked_object','unspecified'));v=groups.setdefault(key,dict(category='route',reason=key[0],blocked_object=key[1],N=0,minimum_gap_m=math.inf));v['N']+=1;v['minimum_gap_m']=min(v['minimum_gap_m'],rec['minimum_gap_m'])
   r['route_frame_rejections']=sorted(groups.values(),key=lambda x:-x['N'])

   flow=[x.get('reloc20_motion',{}).get('stall') or {} for x,e in pairs]
   r['visual_stall_frame_reasons']=dict(collections.Counter(x.get('reason','off') for x in flow))
   r['visual_stall_intervals']=intervals(times,np.array([bool(x.get('suppressed')) for x in flow[:-1]]),[(0.,'own_camera_stationarity_evidence')]*len(times))
   # Actual issued actuator pulses, invert kinematics. No lateral pulse may
   # hide under a controller function named heading_drive.
   lateral=[]
   for x,e in pairs:
    if x.get('phase_before',x['phase']) not in ('carry_to_zone','destination_acquire'):continue
    w=x['command']['wheels'];dur=x['command']['duration_s'];lat=-w[0]*dur[0]+w[1]*dur[1]+w[2]*dur[2]-w[3]*dur[3]
    if abs(lat)>1e-10:lateral.append(dict(t=x['t'],lateral_wheel_impulse=lat))
   r['lateral_pulse_ticks']=len(lateral);r['lateral_pulse_examples']=lateral[:6]
   drive_path=raw/'drive-eval-only.jsonl'
   if drive_path.exists() or Path(str(drive_path)+'.zst').exists():
    wheel=rows(drive_path);wb={round(x['t'],5):x for x in wheel};measurements=[];contact_names=collections.Counter()
    for (x,e),(nx,ne) in zip(pairs,pairs[1:]):
     wa,ww=wb.get(round(x['t'],5)),wb.get(round(nx['t'],5))
     if wa is None or ww is None:continue
     a,b,cw,dw=np.array(ww['wheel_qpos_rad'])-np.array(wa['wheel_qpos_rad'])
     wd=.0325*np.array([a+b+cw+dw,-a+b+cw-dw,(-a+b-cw+dw)/.12435])/4
     yaw=e['base_yaw_rad'];rot=np.array([[math.cos(yaw),math.sin(yaw)],[-math.sin(yaw),math.cos(yaw)]])
     xy=rot@(np.array(ne['base_xyz'][:2])-np.array(e['base_xyz'][:2]));da=(ne['base_yaw_rad']-yaw+np.pi)%(2*np.pi)-np.pi
     measurements.append(dict(t=x['t'],phase=x.get('phase_before',x['phase']),wheel_xy_m=float(np.linalg.norm(wd[:2])),body_xy_m=float(np.linalg.norm(xy)),wheel_body_residual_m=float(np.linalg.norm(wd[:2]-xy)),wheel_yaw_deg=float(np.degrees(wd[2])),body_yaw_deg=float(np.degrees(da))))
     for contact in wa['contacts']:
      for name in contact['geoms']:
       if name and not name.startswith('r1__'):contact_names[name]+=1
    r['drivetrain_evaluation']=dict(samples=len(measurements),wheel_body_xy_residual_m=summary.dist([x['wheel_body_residual_m'] for x in measurements]),contact_names=dict(contact_names),scope='wheel angle kinematics versus body increments, evaluation only; residual includes roller kinematic/model effects and is not contact-point slip or hardware validation')
   else:r['drivetrain_evaluation']=dict(available=False,reason='not recorded in this source')

  tables.append(dict(run=t['name'],raw=t['raw'],termination=normalized,cumulative=r.get('gate_cumulative',r.get('registration_frame_funnel')),frame_funnel=r.get('acquisition_frame_funnel'),rejections=r.get('acquisition_frame_rejections'),motion=r.get('reloc20_motion'),route_frame_rejections=r.get('route_frame_rejections'),visual_stall_frame_reasons=r.get('visual_stall_frame_reasons'),geometry_risk_intervals=r.get('geometry_risk_intervals'),terminal=r.get('terminal_rejections')))
  mf=raw/'failure-rgb/manifest.json'
  if mf.exists() or Path(str(mf)+'.zst').exists():
   frames=obj(mf)['frames'];out=b/'media'/t['name'];out.mkdir(parents=True,exist_ok=True)
   if frames:
    six=[]
    for i in range(6):
     f=frames[round(i*(len(frames)-1)/5)];p=raw/'failure-rgb'/f['path'];h=hashlib.sha256(p.read_bytes()).hexdigest();assert h==f['sha256'];dest=out/f'failure-{i:02d}.jpg';shutil.copyfile(p,dest);six.append(dict(t=f['t'],path=str(dest),raw=str(p),sha256=h))
    r['failure_six']=six
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','1','-framerate','1','-i',str(out/'failure-%02d.jpg'),'-vf','scale=320:240,tile=3x2:nb_frames=6','-frames:v','1',str(out/'failure-six.jpg')],check=True)
   if media and r.get('errors') and t['kind']=='carry' and ((raw/'playback/manifest.json').exists() or (raw/'playback/manifest.json.zst').exists()) and not (out/'playback').exists():review.make(raw.parent,out/'playback')
 d['integrity']=integrity;d['speed']=obj(b/'speed-gate.json');d['status']='NOT_READY' if any(r.get('place_success') is not True for r in d['runs'] if r['kind']=='carry') else 'PILOT_ONLY'
 (b/'summary.json').write_text(json.dumps(d,indent=2)+'\n')
 (b/'rejection-table.json').write_text(json.dumps(dict(source_queue=str(b/'queue.json'),reproduce=f'PYTHONPATH={ROOT} python {__file__} --round {n}',runs=tables),indent=2)+'\n')
 brief=dict(round=n,status=d['status'],source_sha=q['source_sha'],speed=d['speed'],files_verified=sum(x['integrity']['files'] for x in integrity),runs=[{k:v for k,v in r.items() if k not in ('destination_acquisition','drift_bins','reloc20_motion','source_hashes')} for r in d['runs']])
 (b/'brief.json').write_text(json.dumps(brief,indent=2)+'\n')
 for name in ('summary.json','rejection-table.json','brief.json'):
  p=b/name
  if p.stat().st_size>65536:
   original=hashlib.sha256(p.read_bytes()).hexdigest();subprocess.run(['zstd','-q','-f',str(p)],check=True);assert hashlib.sha256(subprocess.check_output(['zstd','-dc',str(p)+'.zst'])).hexdigest()==original;p.unlink()
 manifest={str(p.relative_to(b)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in b.rglob('*') if p.is_file() and p.name!='retrieval-manifest.json'}
 (b/'retrieval-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('FINAL',json.dumps(dict(round=n,files_verified=brief['files_verified'],runs=[dict(name=r['name'],place=r.get('place_success'),termination=r['termination_normalized'],errors=r.get('errors'),geometry_s=r.get('geometry_risk_sim_s'),lateral_ticks=r.get('lateral_pulse_ticks')) for r in d['runs']])))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--round',type=int,required=True);p.add_argument('--media',action='store_true');a=p.parse_args();main(a.round,a.media)
