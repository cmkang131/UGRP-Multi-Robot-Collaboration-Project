import importlib.util,json,pathlib,subprocess,tempfile,sys,hashlib
import harness
from harness import zone_path_heading_contract as c
from scripts.replay_s2_heading import fixed_inputs
# Read missing modules from the pinned S3 branch into a temporary import root.
# Existing modules (including the common heading implementation) stay from this checkout.
ref='origin/codex/s3-no-prior-smoke'; sha=subprocess.check_output(['git','rev-parse',ref],text=True).strip()
with tempfile.TemporaryDirectory(prefix='s3-heading-source-') as tmp:
 root=pathlib.Path(tmp); files=subprocess.check_output(['git','ls-tree','-r','--name-only',ref,'harness'],text=True).splitlines()
 for name in files:
  if name.endswith('.py') and not pathlib.Path(name).exists():
   dst=root/name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(subprocess.check_output(['git','show',ref+':'+name]))
 harness.__path__.append(str(root/'harness'))
 from harness.zone_s3_no_prior import solo_factory
 from harness import zone_solo_cyan_contract_v106 as legacy
 b=c.bundle('a'*40,1066)
 b['options'].update(localization_certification='posterior_consensus_v1',recorded_camera_mount='off')
 rt=solo_factory(b)(legacy.hp.resolve(legacy.MAP_ID)[0],legacy.ROOT/legacy.CALIBRATION,legacy.CALIBRATION_SHA,**b['task'])
 try:
  rec=rt.record();s3=dict(source_sha=sha,factory='zone_s3_no_prior.solo_factory',heading_mode=rec['heading_mode']['option'],active_rotation_guard=rec['active_rotation_guard']['option'],gt_inputs=False,physics_runs=0)
 finally:rt.close()
rows=[]
base=pathlib.Path('/Users/changmin/projects/ugrp/outputs')
for seed in [1066,1068,1065]:
 p=base/f's2-realism-99d81d8c-s{seed}-v141-graduation/student_record.json';d=json.loads(p.read_text());q=fixed_inputs(d)
 rows.append(dict(seed=seed,count=q['count'],off_matches=q['off_matches'],record_sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
result=dict(s3=s3,off_replay=rows,off_count=sum(x['count'] for x in rows),off_matches=sum(x['off_matches'] for x in rows))
pathlib.Path('experiments/2026-10-09-s2-heading/default-on/integration.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
