from pathlib import Path
import sys,json,hashlib,datetime
actor=Path('/home/ugrp/ugrp-sim/src/rl1b-actor-b4db8ba2')
sys.path.insert(0,str(actor))
from harness.grasp_act_rollout import SoloScore
r=Path('/home/ugrp/ugrp-sim/runs/warp3/student-api-r3')
summary=json.loads((r/'summary.json').read_text())
assert summary['passed'] and summary['status']=='complete'
score=SoloScore();count=0
for line in (r/'owner/evaluation-only.jsonl').read_text().splitlines():
 ev=json.loads(line)
 if ev.get('world')!=1 or 'min_z' not in ev or ev['elapsed_sim_s']<=0:continue
 index=max(0,round(ev['elapsed_sim_s']/.1)-1)
 skill=summary['actions'][min(index,len(summary['actions'])-1)]['skills'][1]
 score.add(ev['t'],skill=skill,linear_speed=ev['speed'],clearance=ev['min_z'],tilt=ev['tilt_deg'],forces=ev['finger_forces'],weld=ev['weld_active']);count+=1
result=score.record({},with_release=True)
assert count==2
report=dict(passed=True,scope='original SoloScore posthoc wiring on two actual ACT15 steps, world1 without reset; no completed student task',physical_N=0,physical_n=0,new_physics_steps=0,actor_commands_modified=False,completed_steps_scored=count,source_actor='b4db8ba2fb155ad53b210b48f645fcc759157e7b',score_module_sha256=hashlib.sha256((actor/'harness/grasp_act_rollout.py').read_bytes()).hexdigest(),raw={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [r/'summary.json',r/'owner/evaluation-only.jsonl']},provisional_score=result,recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
Path('/home/ugrp/ugrp-sim/runs/warp3/student-score-prefix-r1.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
