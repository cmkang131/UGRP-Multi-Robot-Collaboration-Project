"""Prepare metadata only against unchanged crate18; no step/forward/render."""
import base64,hashlib,json,pathlib,re,subprocess,sys,zlib
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).parent
QUEUE=pathlib.Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
SHA='487579ea4b862465b4feb5e64ca55c2fabae9558'
PIN=ROOT.parent/'crate-src-487579ea'
# This external setup-only reservation permits a new gate split without modifying pinned code.
LO,HI=112000,112199
files=list(QUEUE.glob('*.json'))+list((ROOT/'experiments').rglob('*plan*.json'))+list(pathlib.Path('/Users/changmin/projects/ugrp/experiments').rglob('*plan*.json'))
hits=[];inventory=[]
pat=re.compile(r'(?<!\d)112[01]\d\d(?!\d)')
for p in files:
 b=p.read_bytes(); inventory.append((str(p),hashlib.sha256(b).hexdigest()))
 if pat.search(b.decode(errors='ignore')):hits.append(str(p))
assert not hits,hits
assert subprocess.check_output(['git','-C',str(PIN),'rev-parse','HEAD'],text=True).strip()==SHA
assert not subprocess.check_output(['git','-C',str(PIN),'status','--porcelain'])
code='''import sys,json,pathlib,re
sys.path.insert(0,str(pathlib.Path.home()/'ugrp-sim/src/SHA'))
import mujoco
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_inverse','Renderer','mjr_render'):
 setattr(mujoco,name,lambda *a,**k: (_ for _ in ()).throw(AssertionError('static setup only')))
from scripts import make_crate_teacher_plan as m
from harness.grasp_act_seed_splits import registry,check_range
reg=registry();assert not any(a<=112199 and b>=112000 for rr in reg['ranges'].values() for a,b in rr)
reg['ranges']['crate19_noclear_gate']=[[112000,112199]]
m.check_range=lambda split,seed,count:check_range(split,seed,count,reg)
conflicts=[p.name for p in (pathlib.Path.home()/'ugrp-sim/runs').iterdir() if re.search(r'(?<!\\d)112[01]\\d\\d(?!\\d)',p.name)]
assert not conflicts,conflicts
plan=m.prepare(count=40,seed=112000,split='crate19_noclear_gate',scenario_set='v6',assignment='fixed_rgb_lugs_v1',crate_profile='crate14_v1',near_wall_policy='exclude_report_v1')
print(json.dumps(plan,separators=(',',':')))
'''.replace('SHA',SHA)
r=subprocess.run(['ssh','-o','BatchMode=yes','gcp1',"cd ~/ugrp-sim/src/"+SHA+" && .venv-sim/bin/python -"],input=code,text=True,capture_output=True,check=True)
plan=json.loads(r.stdout); blob=(json.dumps(plan,separators=(',',':'))+'\n').encode(); ph=hashlib.sha256(blob).hexdigest()
planpath=QUEUE/'20261015-crate-gate40-noclear-487579ea-plan.json'
planpath.write_bytes(blob)
old=json.loads((QUEUE/'20261015-crate18-diag-487579ea.json').read_text()); template=next(x for x in old['runs'] if x['candidate']=='no_clearance')
remote='/home/ugrp/ugrp-sim/plans/crate19-noclear-gate40-'+ph[:12]+'.json'
q={k:old[k] for k in ['branch','pr','host','machine_type','admission','stop_rule']}
q.update(schema='ugrp.crate_gate40.queue.v1',owner='codex-crate19',sha=SHA,source_sha=SHA,created_utc=datetime.now(timezone.utc).isoformat(),
 pinned_source_worktree=str(PIN),source_worktree=str(PIN),runner_cwd=str(ROOT),status='awaiting_coordinator_approval',
 max_parallel=16,max_combined_concurrency=40,run_count=40,stage_counts={'gate':40},stage_ready={'gate':False},
 coordinator_approval={'approved':False,'sha':SHA,'prior_approval_inherited':False,'pinned_source_worktree':str(PIN)},
 crate_profile='crate17_no_clearance_v1',crate18='crate18_v1',crate19='off',training_rgb=False,
 criteria={'N':40,'required':38,'teacher_target_rate':.95,'grasp_cap_s':90,'release_cap_s':90,'maximum_sim_s_per_episode':180,
 'training_rgb':False,'top_camera_control':False,'top_camera_capture':False,'weld':'off','input_audit':{'invisible_measurements':0,'held_world_reads':0},'timeout_outcome':'cap_end; failure; no replacement'},
 pooling='gate40 n/40 only; never pool crate16/17/18 diagnostics, sources, profiles, hosts, or DEV tuning',
 start_distribution=plan['start_distribution'],near_wall_filter=plan['near_wall_filter'],plan_path=str(planpath),remote_plan_path=remote,plan_sha256=ph,
 plan_zlib_base64=base64.b64encode(zlib.compress(blob,9)).decode(),
 plan_install={'required_before_runs':True,'remote_path':remote,'sha256':ph,'method':'Decode plan_zlib_base64 to remote_plan_path outside source; verify SHA256 before any row; pinned source must remain clean'},
 seed_reservation={'range':[LO,HI],'split':'crate19_noclear_gate','setup_registry_extension_only':True,'registry_on_pinned_source_unchanged':True,
 'inventory_files':len(inventory),'inventory_sha256':hashlib.sha256(json.dumps(inventory).encode()).hexdigest(),'local_conflicts':hits,'remote_conflicts':[],
 'required_before_admission':'recheck live inventory under admission lock'},
 speed_limit={'warn_above':3.5,'median_wall_per_sim_max':6.,'measure':'first30 SIMs of gate, no separate stage'},
 preconditions=['Explicit coordinator approval required; all flags false.','RUNNING existing gcp1, project ugrp-act-train-1014 only; budget-stop and idle guard unchanged.',
 'Shared admission lock: total<=40 and this gate<=16.','Materialize and hash-check embedded plan outside pinned source before invoking rows.',
 'No training recording; success_measurement mode; no top camera.','Keep cap_end/HOST_ERROR/failure denominator; stop confirmed same-defect runs.'],runs=[])
flags=['approved','enabled','ready','runs_enabled','submitted','scheduled','executed','gate_approved','gate_enabled','training_approved','training_enabled','gate_promotion_authorized_if_all_conditions_pass']
q.update({f:False for f in flags})
for i,e in enumerate(plan['episodes']):
 name=f"crate19-noclear-gate-{e['seed']}-487579ea"; payload=template['payload'].copy()
 for flag,v in [('--plan',remote),('--episode',str(i)),('--grasp-cap-s','90'),('--cap-s','90'),('--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw')]:payload[payload.index(flag)+1]=v
 row=dict(row_id=i,candidate='no_clearance',stage='gate',seed=e['seed'],scenario_id=e['scenario_id'],near_wall=e['near_wall'],name=name,
 crate_profile=q['crate_profile'],crate18=q['crate18'],crate19='off',max_parallel=16,max_combined_concurrency=40,maximum_sim_s_per_episode=180,grasp_cap_s=90,release_cap_s=90,
 status=q['status'],payload=payload,command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','500','--per-run-mb','128',str(PIN),name,'--',*payload])
 row.update({f:False for f in flags});q['runs'].append(row)
assert len(q['runs'])==len({r['seed'] for r in q['runs']})==40
assert not any(r['near_wall'] for r in q['runs'])
out=QUEUE/'20261015-crate-gate40-noclear-487579ea.json'
with out.open('x') as f:json.dump(q,f,ensure_ascii=False,separators=(',',':'));f.write('\n')
assert json.loads(out.read_text())==q
alert=QUEUE.parent/'ops-alert.md'
with alert.open('a') as f:f.write(f'crate19: no_clearance gate40 큐 준비 {out}\n')
(HERE/'gate-preparation.json').write_text(json.dumps({'queue':str(out),'queue_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'plan_sha256':ph,'pinned_source_worktree':str(PIN),'seeds':[r['seed'] for r in q['runs']],'drawn':plan['near_wall_filter']['drawn_episode_count'],'excluded':plan['near_wall_filter']['excluded_count'],'accepted':40},indent=2)+'\n')
print((HERE/'gate-preparation.json').read_text())
