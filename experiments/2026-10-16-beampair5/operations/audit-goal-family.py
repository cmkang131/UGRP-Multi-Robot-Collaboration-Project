"""gcp2 evaluation-only census of the entire pinned certified stance family."""
import pathlib,sys,math,json,subprocess,hashlib
import numpy as np,mujoco
r=pathlib.Path('/home/ugrp/ugrp-sim');dep=r/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247';sys.path.insert(0,str(dep))
from sim.grasp_act_search24 import reachability_map
from sim.grasp_act_search18 import HALF_X,HALF_Y,body_clearance
from sim.grasp_act_search21 import FRESH_MARGIN_M
raw=r/'runs/beampair5-r1-1ead2bb9/round/diagnostic/episode-000/raw';p=raw/'eval-only.jsonl.zst';last=json.loads(subprocess.check_output(['zstd','-qdc',str(p)]).splitlines()[-1]);beam=last['beam'];end=beam['ends']['blue'];m=mujoco.MjModel.from_xml_path(str(raw/'scene.xml'));d=mujoco.MjData(m);d.qpos[:]=last['joints'];mujoco.mj_forward(m,d)
gid=m.geom('zone_wall_north').id;wall_y=float(d.geom_xpos[gid,1]-m.geom_size[gid,1]);R=d.geom_xmat[gid].reshape(3,3);rect=(*d.geom_xpos[gid,:2],*m.geom_size[gid,:2],math.atan2(R[1,0],R[0,0]));rows=[]
for a,distance,_,certificate in reachability_map(end[2]):
 heading=beam['pose'][2]+math.pi+a;goal=(end[0]-distance*math.cos(heading),end[1]-distance*math.sin(heading),heading)
 signed=wall_y-(goal[1]+HALF_X*abs(math.sin(heading))+HALF_Y*abs(math.cos(heading)))
 gap=body_clearance(goal,[],[rect]);rows.append(dict(offset_deg=math.degrees(a),distance_m=distance,goal=list(goal),north_inner_edge_y_m=wall_y,signed_north_clearance_m=signed,gap_m=gap,margin_m=FRESH_MARGIN_M,reason_category='blocked_goal' if gap<FRESH_MARGIN_M else 'free_goal',blocked_object='zone_wall_north',min_gap_m=gap,nearest_free_goal_shift_m=max(0.,FRESH_MARGIN_M-signed)))
report=dict(scope='evaluation-only; fixed existing IK/jaw-certified family, not all possible robot grasps; no evaluation value enters control',source_dependency_sha=dep.name,raw=str(raw),source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),target_end=end,beam_yaw_rad=beam['pose'][2],wall_inner_edge_y_m=wall_y,band_to_wall_inner_edge_m=wall_y-end[1],candidate_N=len(rows),free_goal_N=sum(x['reason_category']=='free_goal' for x in rows),best_signed_clearance_m=max(x['signed_north_clearance_m'] for x in rows),nearest_free_shift_min_m=min(x['nearest_free_goal_shift_m'] for x in rows),candidate_funnel=[dict(gate='IK_and_jaw_certified',entered=len(rows),cumulative_passed=len(rows),rejected=0),dict(gate='north_wall_goal_clearance',entered=len(rows),cumulative_passed=sum(x['reason_category']=='free_goal' for x in rows),rejected=sum(x['reason_category']=='blocked_goal' for x in rows)),dict(gate='path',entered=0,cumulative_passed=0,rejected=0)],candidates=rows,reproduce=f'{r}/ugrp/.venv-sim/bin/python {r}/ops-reviews/beampair5/audit-goal-family.py',analysis_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest())
out=r/'ops-reviews/beampair5/goal-family-funnel.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('candidates','candidate_funnel')},indent=2))
