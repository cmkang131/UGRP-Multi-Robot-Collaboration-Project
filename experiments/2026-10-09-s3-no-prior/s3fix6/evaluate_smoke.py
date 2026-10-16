"""Read only completed v151 raw; all truth stays in post-run evaluation."""
import collections, hashlib, json, math
from pathlib import Path
import numpy as np
from scripts.evaluate_s3_no_prior import metrics, load_lines

import argparse
p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
B=a.output;B.mkdir(parents=True,exist_ok=False);R=a.raw
V=B/'analysis-view';V.mkdir()
def read(p): return json.loads(p.read_text())
def save(p,d): p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
for entry in R.iterdir():
    if entry.name!='student_record.json': (V/entry.name).symlink_to(entry,target_is_directory=entry.is_dir())
student=read(R/'student_record.json');invalid={}
for rid,loc in student.get('localizers',{}).items():
    bad=[p for p in loc['poses'] if any(not isinstance(p.get(k),(float,int)) or not math.isfinite(p[k]) for k in ['x','y','yaw','std_xy_m','std_yaw_rad'])]
    invalid[rid]=bad
    loc['poses']=[p for p in loc['poses'] if p not in bad]
save(V/'student_record.json',student)
save(B/'invalid-pose-evaluation-exclusions.json',invalid)
result, student, bundle = [read(V/n) for n in ['result.json','student_record.json','bundle.json']]
report = dict(schema='ugrp.s3fix6.eval_only.v1', raw=str(R), source=result['source_sha'],
    gt_use='post-run eval_only; no control feedback', thresholds_changed=False,
    status=result['status'], actual_stop=result.get('failure'), end_reason=result.get('end_reason'),
    evaluation=metrics(V), first_location={}, localization={}, movement={}, stages={},
    would_stop={}, pair_heading={}, camera_contract={}, startup=student['startup'])
pair=student.get('pair',{})
counts=collections.Counter()
for rid in ['r1','r2','r3']:
    loc=student['localizers'][rid]
    truth=list(load_lines(R/f'eval_only/{rid}/trajectory.jsonl'))
    ts=[q['t'] for q in truth];xy=np.array([q['robot_xyz_m'][:2] for q in truth]);yaw=np.unwrap([q['robot_yaw_rad'] for q in truth])
    def score(p):
        at=p['t_est'];dy=p['yaw']-np.interp(at,ts,yaw)
        error=math.dist([p['x'],p['y']],[np.interp(at,ts,xy[:,j]) for j in [0,1]])
        ye=abs(math.degrees(math.atan2(math.sin(dy),math.cos(dy))))
        return dict(t_sim_s=p['t'],estimate_t=at,elapsed_from_first_frame_s=p['t']-loc['poses'][0]['t'],
            xy_error_m=error,yaw_error_deg=ye,sigma_xy_m=p['std_xy_m'],sigma_yaw_deg=math.degrees(p['std_yaw_rad']),
            accurate=error<=.25 and ye<=15,certificate=p.get('convergence_certificate'),
            connected_modes=p.get('convergence_certificate',{}).get('connected_modes'))
    poses=[score(p) for p in loc['poses']]
    handoff=student['startup'].get(rid,{}).get('t')
    report['first_location'][rid]=next((p for p in poses if handoff is not None and p['t_sim_s']>=handoff),None)
    report['localization'][rid]=dict(last=poses[-1],frame_count=len(poses),
        accurate_frames=sum(p['accurate'] for p in poses),
        first_accurate=next((p for p in poses if p['accurate']),None),
        first_sigma=next((p for p in poses if p['sigma_xy_m']<=.05),None),
        first_certificate=next((p for p in poses if (p['certificate'] or {}).get('qualified')),None))
    commands=list(load_lines(R/f'robots/{rid}/commands.jsonl'))
    moving=[c for c in commands if c.get('kind') in ('drive','mecanum') and any(c.get(k,0) for k in ['forward','left','turn'])]
    report['movement'][rid]=dict(nonzero_commands=len(moving),max_displacement_m=max(math.dist(xy[0],p) for p in xy),
        final_displacement_m=math.dist(xy[0],xy[-1]),short_commands=[c for c in moving if c['duration_s']<.10],
        mixed_axis_commands=[c for c in moving if sum(abs(c.get(k,0))>1e-12 for k in ['forward','left','turn'])>1])
    own=pair.get('robots',{}).get(rid,{})
    report['stages'][rid]=dict(localizer_states=[e for e in loc['events'] if e.get('event')=='state'],
        last_state=loc['state'],jobs=own.get('jobs',[]),job_events=own.get('events',[]),
        pair_events=[e for p in pair.get('pair',[]) for e in p['robots'].get(rid,{}).get('events',[])],
        cargo_delivered=report['evaluation']['robots'][rid]['delivery_complete'])
    report['would_stop'][rid]=loc.get('dev_light_would_stop',{})
    counts.update(report['would_stop'][rid])
    renders=list(load_lines(R/f'eval_only/{rid}/render_camera.jsonl'))
    frames=list(load_lines(R/f'robots/{rid}/frames.jsonl'))
    # Independent rendered local mount is compared against the frozen v3/S2 receipt.
    f=read(Path('tests/fixtures/s3_camera/s2-v141-first-camera.json'))['first'];prior=dict(local_position_m=f['camera_local_position_m'],local_quat_wxyz=f['camera_local_quaternion'])
    keys=['local_position_m','local_quat_wxyz']
    report['camera_contract'][rid]=dict(rendered=len(renders),own_frames=len(frames),
        first={k:renders[0][k] for k in ['t','camera_binding']+keys},
        all_mounts_equal_s2=all(all(q[k]==prior[k] for k in keys) for q in renders),
        frame_times_match=len(renders)==len(frames) and all(q['t']==f['sim_time'] for q,f in zip(renders,frames)))
    report['pair_heading'][rid]=dict(localizer_heading=loc.get('heading_mode',{}).get('option'),
        localizer_parameters=loc.get('heading_mode',{}).get('parameters'),
        exact_cache=loc.get('s3_exact_cache'))
report['pair_dev_light']=pair.get('s3_dev_light',{})
for key,n in report['pair_dev_light'].get('counts',{}).items(): counts[key.split(':')[-1]]+=n
legacy=[e for p in pair.get('pair',[]) for rr in p['robots'].values() for e in rr.get('events',[]) if e.get('event')=='dev_light_would_stop']
report['legacy_pair_would_stop']=legacy
counts.update(e.get('code',e.get('would_reason','UNKNOWN')) for e in legacy)
report['would_stop_counts']=dict(counts)
report['would_stop_count_scope']='hook occurrences; includes distinct local/pair/legacy hooks, not physical failures or disk writes'
ph=pair.get('pair_heading',{})
report['pair_heading_audit']=dict(option=ph.get('option'),scope=ph.get('scope'),exceptions=ph.get('exceptions'),
    prediction=ph.get('prediction'),decision_counts={r:len(v) for r,v in ph.get('decisions',{}).items()},
    alignment_counts={r:len(v) for r,v in ph.get('alignment',{}).items()})
report['applied']=dict(bundle_options=bundle['options'],result_heading=result.get('heading_mode'),
    runtime_speedups=result.get('runtime_speedups'),camera_binding=bundle.get('s3_camera_binding'),
    ports=read(R/'eval_only/pair-motion-ports.json'))
report['host_timing']=read(R/'host-timing.json')
report['source_artifacts']={n:digest(V/n) for n in ['result.json','student_record.json','bundle.json','host-timing.json','artifacts.sha256.json']}
report['invalid_pose_exclusions']={r:len(v) for r,v in invalid.items()}
report['pose_validity']={r:l.get('pose_validity',{}) for r,l in student['localizers'].items()}
report['observation_consistency']={r:l.get('observation_consistency',{'option':'off'}) for r,l in student['localizers'].items()}
for r,valid in report['pose_validity'].items():
    counts['UNMEASURED_V3_CAMERA_POSTURE']+=valid.get('count',0)
report['would_stop_counts']=dict(counts)
cargo=list(load_lines(R/'eval_only/referee_truth.jsonl'))
report['cargo']={'scope':'post-run evaluation only','items':{}}
for item in cargo[0]['items']:
    rows=[(q['t'],q['items'][item]) for q in cargo]
    held=[(t,v) for t,v in rows if v['held']]
    report['cargo']['items'][item]=dict(samples=len(rows),held_samples=len(held),first_held_t=held[0][0] if held else None,max_com_z_m=max(v['z'] for _,v in rows),final=rows[-1][1])
report['evaluation']['raw']=str(R)
nonfinite=[]
def clean(v,path=''):
    if isinstance(v,float) and not math.isfinite(v): nonfinite.append(path);return None
    if isinstance(v,dict):return {k:clean(x,path+'/'+str(k)) for k,x in v.items()}
    if isinstance(v,list):return [clean(x,path+'/'+str(i)) for i,x in enumerate(v)]
    return v
report=clean(report)
report['nonfinite_fields']=nonfinite
report['nonfinite_policy']='Nonfinite replay fields become null in derived strict JSON only; original replay preserves NaN'
save(B/'smoke-report.json',report)
print(json.dumps({k:report[k] for k in ['status','actual_stop','first_location','would_stop_counts','pair_heading_audit']},ensure_ascii=False,indent=2))
