from pathlib import Path
import json,subprocess,hashlib,math
root=Path.home()/'ugrp-sim';source=root/'src/e654ae01dc07014b960acf0b9c5de292f9f0436f';out=root/'runs/route1-stage-replay-b1';out.mkdir(exist_ok=False)
recipe=json.loads(subprocess.check_output(['zstd','-dc',str(source/'experiments/2026-10-13-e2e18-grasp1/checkpoints/e2e18-v375-s61008-r80-mapping30.json.zst')]))
# Label-only rigid registration fixed at the staged cutoff, never planner input.
world=recipe['setup_only']['robots']['r1'];own=recipe['own_inputs']['r1']['frames'][-1]['expected_pose'];yaw=world['robot_yaw_rad']-own[2];c=math.cos(yaw);s=math.sin(yaw);tf=[world['robot_xyz_m'][0]-c*own[0]+s*own[1],world['robot_xyz_m'][1]-s*own[0]-c*own[1],yaw]
map_path=source/'maps/zones_e2e/zone_wide_door_e2e_b80_v1.json';m=json.loads(map_path.read_text());assert hashlib.sha256(map_path.read_bytes()).hexdigest()==recipe['setup_only']['scene_fingerprint']['scenario_setup']['map_file_sha256'] if 'scenario_setup' in recipe['setup_only']['scene_fingerprint'] else True
bounds=m['bounds_m'];obstacles=[]
for o in m['obstacles']:
 x,y=o['center_m'];a,b=o['half_extents_m'];assert not o.get('yaw_rad',0);obstacles.append([x-a,y-b,x+a,y+b])
labels=out/'eval_only';labels.mkdir();roots=[];N=0
import sys;sys.path.insert(0,str(source));from harness.pair_stage_probe import digest
for run in sorted((root/'runs').glob('stage-b-cohort2-*-route-*')):
 assert (run/'EXIT').exists();recordings=run/'raw/route-inputs';roots.append(str(recordings))
 index=recordings/'index.jsonl'
 if not index.exists():continue
 for line in index.read_text().splitlines():
  row=json.loads(line)
  if row['status']!='SAVED':continue
  p=recordings/row['file'];data=p.read_bytes();assert hashlib.sha256(data).hexdigest()==row['sha256'];record=json.loads(subprocess.check_output(['zstd','-dc',str(p)]));sha=digest(record['snapshot'])
  label=dict(schema='ugrp.route_eval_rectangles.v1',input_sha256=sha,own_to_world=tf,bounds_xyxy=[bounds[0],bounds[2],bounds[1],bounds[3]],obstacles_xyxy=obstacles)
  (labels/(sha+'.json')).write_text(json.dumps(label)+'\n');N+=1
(out/'RUN_META.json').write_text(json.dumps(dict(**{'class':'dev'},pr=476,branch='codex/e2e18',sha=source.name,batch='route1-stage-replay-b1')))
(out/'EVAL_PROVENANCE.json').write_text(json.dumps(dict(scope='initial cutoff rigid transform, excludes later odometry drift and dynamic robot obstacles; geometric only, no physical passage',checkpoint_sha256=recipe['checkpoint_sha256'],map_file_sha256=hashlib.sha256(map_path.read_bytes()).hexdigest(),own_to_world=tf,recordings=roots,snapshots_N=N)))
(out/'SOURCE_SHA').write_text(source.name+'\n');(out/'RECORDINGS.json').write_text(json.dumps(roots));print(json.dumps(dict(N=N,own_to_world=tf,map_sha256=hashlib.sha256(map_path.read_bytes()).hexdigest())))
