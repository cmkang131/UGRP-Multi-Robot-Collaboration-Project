"""Post-replay evaluation and provenance. GT is loaded only in this evaluator."""
import json,math,hashlib,pathlib,subprocess,xml.etree.ElementTree as ET
import numpy as np
from harness.zone_solo_cyan_best_cluster import connected_labels
from sim import masterpi_camera_profile as legacy,masterpi_camera_review_v3 as v3
from sim.masterpi_camera_review_v1 import quat_matrix
B=pathlib.Path(__file__).parent;R=B.parent/'s3-no-prior-6c657124-s14201-v142';S=B.parent/'s2-realism-99d81d8c-s1065-v141-graduation'
def read(p):return json.loads(p.read_text())
def lines(p):return [json.loads(x) for x in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
GT={r:lines(R/f'eval_only/{r}/trajectory.jsonl') for r in ['r1','r2','r3']}
def error(p,r):
 q=GT[r];t=[x['t'] for x in q];xy=np.array([x['robot_xyz_m'][:2] for x in q]);yaw=np.unwrap([x['robot_yaw_rad'] for x in q]);truth=np.array([np.interp(p['t_est'],t,xy[:,k]) for k in (0,1)]);e=float(np.linalg.norm(np.array([p['x'],p['y']])-truth));d=p['yaw']-np.interp(p['t_est'],t,yaw);return e,abs(math.degrees(math.atan2(math.sin(d),math.cos(d))))
def score(folder,r,until=14.,cert=False):
 record=read(B/folder/'record.json');p=[q for q in record['poses'] if q['t']<=until];first=good=None
 for q in p:
  if q['std_xy_m']>.05 or (cert and not q.get('convergence_certificate',{}).get('qualified')):continue
  e,y=error(q,r);point=dict(released_t=q['t'],estimate_t=q['t_est'],xy_error_m=e,yaw_error_deg=y,sigma_xy_m=q['std_xy_m'])
  if first is None:first=point
  if e<=.25 and y<=15:good=point;break
 x=p[-1];e,y=error(x,r);m=next(q for q in reversed(record['pose_estimate']['rows']) if q['t']<=x['t_est']+1e-8)
 return dict(first_convergence=first,first_correct_convergence=good,false_convergence=bool(first and (first['xy_error_m']>.25 or first['yaw_error_deg']>15)),last=dict(t=x['t'],x=x['x'],y=x['y'],yaw=x['yaw'],xy_error_m=e,yaw_error_deg=y,sigma_xy_m=x['std_xy_m'],modes=m['cluster_count'],maximum_mass=m['maximum_cluster_weight']),poses=len(p),certificate_required=cert)
base={'r1':'baseline-r1-v3','r2':'baseline-r2','r3':'baseline-r3'};cases={}
for case in ['baseline','peer_mask','s2_order','seed1065','wall_only','certificate','camera_mount','camera_plus_certificate']:
 robots={}
 for r in base:
  folder={'baseline':base[r],'peer_mask':'peer-masked-r2' if r=='r2' else base[r],'s2_order':f's2-order-{r}-v2','seed1065':f'seed1065-{r}-v2','wall_only':f'wall-only-{r}-v2','certificate':f'certified-{r}','camera_mount':f'camera-corrected-{r}','camera_plus_certificate':f'camera-corrected-{r}'}[case]
  robots[r]=score(folder,r,cert=case in ['certificate','camera_plus_certificate'])
 cases[case]=dict(robots=robots,correct_n=sum(x['first_correct_convergence'] is not None for x in robots.values()),false_n=sum(x['false_convergence'] for x in robots.values()),denominator=3,until_abs_sim_s=14.)
full={r:score(f'camera-corrected-full-{r}',r,until=43.55) for r in base} if all((B/f'camera-corrected-full-{r}/record.json').exists() for r in base) else None
matches={}
previous=read(B.parent/'s3-v142-recovery-6c657124-20261009/replayed-student-partial.json')
for r,d in base.items():
 a=read(B/d/'record.json')['poses'];b=previous['localizers'][r]['poses'];delta=max(abs(x[k]-y[k]) for x,y in zip(a,b) for k in ['x','y','yaw','std_xy_m']);assert len(a)==len(b)==846 and delta==0;matches[r]=dict(frames=len(a),maximum_numeric_difference=delta)
matched_s2={}
for r,seed in [('r1',1065),('r2',1066),('r3',1069)]:
 raw=B.parent/f's2-realism-99d81d8c-s{seed}-v141-graduation';record=read(raw/'student_record.json');q=lines(raw/'eval_only/trajectory.jsonl')[0];p=GT[r][0];views=[x for x in record['sensor_landmarks']['rows'] if x['t']<=10.1];matched_s2[r]=dict(seed=seed,start_xy_difference_m=math.dist(q['robot_xyz_m'][:2],p['robot_xyz_m'][:2]),start_yaw_difference_deg=math.degrees(abs(q['robot_yaw_rad']-p['robot_yaw_rad'])),s2_first_sigma_t=next(x['t'] for x in record['poses'] if x['std_xy_m']<=.05),s2_initial_wall_counts=[x['wall_count'] for x in views],s2_initial_feature_counts=[len(x['features']) for x in views])
a,b=read(R/'bundle.json'),read(S/'bundle.json');assert a['map_sha256']==b['map_sha256']
def terrain(path):return {e.get('name'):dict(e.attrib) for e in ET.parse(path).getroot().iter('geom') if e.get('name','').startswith('zone_') or e.get('name')=='floor'}
assert terrain(R/'scene.xml')==terrain(S/'scene.xml')
manifest=read(R/'artifacts.sha256.json');bad=[p for p,h in manifest.items() if sha(R/p)!=h];assert not bad
visibility=read(B/'peer-mask-summary.json');pixelrows=lines(B/'peer-pixel-bounds.jsonl')
for r,q in visibility['robots'].items():q.update(geometry_available_frames=sum(z['camera_geometry_available'] for z in pixelrows if z['robot']==r),geometry_unavailable_frames=sum(not z['camera_geometry_available'] for z in pixelrows if z['robot']==r))
cloud_modes={}
for r,folder in base.items():
 z=np.load(B/folder/'clouds.npz');px=z['final_px'];w=z['final_weights'];labels=connected_labels(px);out=[]
 for i in np.unique(labels):
  keep=labels==i;mass=float(w[keep].sum());weight=w[keep]/mass;v=px[keep];out.append(dict(mass=mass,xy=(weight@v[:,:2]).tolist(),yaw_rad=math.atan2(weight@np.sin(v[:,2]),weight@np.cos(v[:,2])),particles=int(keep.sum())))
 cloud_modes[r]=sorted(out,key=lambda x:-x['mass'])
summary=dict(schema='ugrp.s3diag.offline.v1',code_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),raw=str(R),simulation_runs=0,source_sha=a['source_sha'],raw_manifest_sha256=sha(R/'artifacts.sha256.json'),raw_files_verified=len(manifest),raw_mutated=False,baseline_matches=matches,host_replay=read(B/'host-replay/replay-verification.json'),host_record_errors=read(B/'host-replay/record-errors.json'),causal_cases=cases,camera_corrected_full=full,matched_s2_starts=matched_s2,peer_visibility=visibility,baseline_final_modes=cloud_modes,static_map=dict(sha256=a['map_sha256'],s2_s3_identical=True,terrain_geom_count=len(terrain(R/'scene.xml')),terrain_attributes_identical=True,configuration_only_difference='idle_robot_contacts off vs freeze_v1; model sleep flag also differs'),camera_mismatch=dict(position_delta_mm=float(np.linalg.norm(np.array(v3.POSITION_M)-legacy.CAMERA_LOCAL_POS_M)*1000),rotation_delta_deg=float(np.rad2deg(np.arccos(np.clip((np.trace(quat_matrix(v3.QUAT_WXYZ).T@quat_matrix(legacy.CAMERA_LOCAL_QUAT_WXYZ))-1)/2,-1,1)))),cause='S3 omitted S2 persistent mount binding; controller init and every renderer call restore legacy mount',raw_xml_is_not_runtime_camera_audit=True),limitations=['No original S3 joint/camera-pose or segmentation GT; pixel values are annotation lower bound / exclusion-box upper bound, missing moving-posture geometry explicit.','No counterfactual physical start-pose image can be recovered from existing pixels. Matched S2 starts and unchanged-map replay are controls, not new physics.','Counterfactual sensor replays use fixed original commands; no claim about alternative closed-loop control or deliveries.','COM height regression repaired prospectively; old referee cannot be exactly reconstructed without cargo roll/pitch.','Numerical thresholds unchanged; no claiming that removing false certification restores true localization.'])
(B/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('raw verified',len(manifest));print('cases',[(k,q['correct_n'],q['false_n']) for k,q in cases.items()]);print('camera full',full);print('peer annotation',[(r,q['geometry_available_frames'],q['geometry_unavailable_frames']) for r,q in visibility['robots'].items()])
