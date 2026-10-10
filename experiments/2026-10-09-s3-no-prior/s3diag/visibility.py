"""EVAL ONLY conservative peer sphere projection. Static model compile; no data/step/render.
The camera uses command-calibrated extrinsics, not unavailable measured S3 joint poses.
"""
import json,math,pathlib,hashlib
import numpy as np,mujoco
from harness.zone_s3_no_prior import solo_factory
from harness import zone_s3_no_prior_contract as c
from harness import vision_loc_protocol as vp
B=pathlib.Path(__file__).parent;RAW=B.parent/'s3-no-prior-6c657124-s14201-v142'
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
m=mujoco.MjModel.from_xml_path(str(RAW/'scene.xml'));radius={}
for r in ['r1','r2','r3']:
 root=m.body(r+'__robot').id;values=[]
 for g in range(m.ngeom):
  k=int(m.geom_bodyid[g]);v=np.linalg.norm(m.geom_pos[g])+m.geom_rbound[g]
  while k not in (0,root):v+=np.linalg.norm(m.body_pos[k]);k=int(m.body_parentid[k])
  if k==root:values.append(float(v))
 radius[r]=max(values)
b=json.loads((RAW/'bundle.json').read_text());static=c.hp.resolve(b['map_id'])[0]
own=solo_factory(b['controller_config'])(static,c.ROOT/b['calibration'],b['calibration_sha256'],seed=14201,robot_id='r1',pickup_slot='P1-1',destination='B');from harness.zone_s3_recorded_camera import attach
own=attach(own,recorded_camera_mount='legacy_centered_replay_v1');pf=own.pose.provider.loc._pf
Kinv=vp.load_vis3()[0].mp.K_INV;K=np.linalg.inv(Kinv);rays=np.array([[0,0,1],[639,0,1],[0,479,1],[639,479,1]])@Kinv.T
truth={r:rows(RAW/f'eval_only/{r}/trajectory.jsonl') for r in radius};frames={r:rows(RAW/f'robots/{r}/frames.jsonl') for r in radius};cache={};result=[];summary={}
try:
 for r in radius:
  for f in frames[r]:
   t=f['sim_time'];p={int(k):v for k,v in f['commanded_servo'].items()};key=tuple(sorted(p.items()))
   if key not in cache:
    try:
     cm=pf.column_model_for(p);cache[key]=(cm.origin.copy(),cm._rot.copy())
    except Exception as error:
     from harness.vision_pose_source_final import CalibrationError
     if not isinstance(error,CalibrationError):raise
     cache[key]=None
   if cache[key] is None:
    result.append(dict(robot=r,t=t,peer_geometry=[],visible_fraction_upper_bound=None,camera='uncalibrated moving posture; not an accepted filter measurement'));continue
   origin,rot=cache[key];g=min(truth[r],key=lambda z:abs(z['t']-t));xy=np.array(g['robot_xyz_m'][:2]);yaw=g['robot_yaw_rad'];co,si=math.cos(yaw),math.sin(yaw);R=np.array([[co,-si,0],[si,co,0],[0,0,1]])
   # Calibration origin is ground-relative, so add measured XY but not root height.
   camera=np.r_[xy,0.]+R@origin;worldrays=rays@rot.T@R.T;rayangles=np.arctan2(worldrays[:,1],worldrays[:,0]);axis=rot[:,2]@R.T;az=math.atan2(axis[1],axis[0]);relative=np.arctan2(np.sin(rayangles-az),np.cos(rayangles-az));lo,hi=relative.min(),relative.max();peers=[]
   for peer in radius:
    if peer==r:continue
    q=min(truth[peer],key=lambda z:abs(z['t']-t));center=np.array(q['robot_xyz_m']);delta=center-camera;distance=np.linalg.norm(delta[:2]);angle=math.atan2(delta[1],delta[0]);a=math.atan2(math.sin(angle-az),math.cos(angle-az));half=math.asin(min(1.,radius[peer]/distance));gap=max(lo-(a+half),(a-half)-hi)
    # Horizontal cone suffices to prove a zero projected footprint.
    rectangle=None
    if gap<=0:
     cam=delta@R@rot;z=cam[2];rad=radius[peer]
     if z>rad:
      bounds=[]
      for axis_idx in (0,1):
       x=cam[axis_idx];root=rad*math.sqrt(max(0.,x*x+z*z-rad*rad));bounds.append(((x*z-root)/(z*z-rad*rad),(x*z+root)/(z*z-rad*rad)))
      x0,x1=[max(0.,min(640.,K[0,0]*v+K[0,2])) for v in bounds[0]];y0,y1=[max(0.,min(480.,K[1,1]*v+K[1,2])) for v in bounds[1]]
      rectangle=[x0,y0,x1,y1]
     elif z+rad>0:rectangle=[0.,0.,640.,480.]
    peers.append(dict(robot=peer,rectangle=rectangle,angular_gap_deg=math.degrees(gap),potentially_visible=bool(gap<=0)))
   result.append(dict(robot=r,t=t,peer_geometry=peers,visible_fraction_upper_bound=0. if all(not p['potentially_visible'] for p in peers) else None,camera='own issued-command calibrated model; measured camera pose unavailable'))
  ownrows=[x for x in result if x['robot']==r];summary[r]=dict(frames=len(ownrows),zero_bound_frames=sum(x['visible_fraction_upper_bound']==0 for x in ownrows),ambiguous_frames=sum(x['visible_fraction_upper_bound'] is None for x in ownrows),minimum_horizontal_clearance_deg=min(p['angular_gap_deg'] for x in ownrows for p in x['peer_geometry']))
finally:own.close()
(B/'peer-visibility.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in result));(B/'peer-visibility-summary.json').write_text(json.dumps(dict(method='whole articulated body sphere from static model triangle bound; own calibrated camera composed to recorded legacy mount horizontal frustum',radius_m=radius,gt_use='eval_only projection, never production controller',limitation='joint/camera ground truth absent; fractions are nominal geometric upper bounds, not exact pixel segmentation',robots=summary),indent=2)+'\n');print(summary)
