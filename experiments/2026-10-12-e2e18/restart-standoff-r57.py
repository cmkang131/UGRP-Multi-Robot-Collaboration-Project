"""Finite replacement batch using the standard managed workflows and speed gate."""
import json,os,subprocess,sys,time
from pathlib import Path
from scripts.azure_speed_gate import replace_option,main as gate_main
from scripts.run_e2e_ownmap_live import relay_url
from harness.s4_live_transport import validate_receipt

# Explicit render/CPU environment, shared with the r45 retry.
for key,value in {'MUJOCO_GL':'osmesa','PYOPENGL_PLATFORM':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1'}.items():os.environ[key]=value
b=Path.home()/'ugrp-sim';sha=sys.argv[1];host=os.uname().nodename
assert host=='ugrp-sim-azure3'
seeds=[61006]
VERS=[int(x) for x in sys.argv[2].split(',')]
BATCH=sys.argv[3]
EXTRA={295:[('--beam-lost-standoff','v1')],296:[('--beam-lost-standoff','v1'),('--arm-clearance-align-skip','v1'),('--acquire-scan-fast','v1')]}
S3=[('--beam-lost-standoff','v1'),('--arm-clearance-align-skip','v1'),('--acquire-scan-fast','v1')]
EXTRA[297]=S3;EXTRA[298]=S3
MODE={295:None,296:None,297:'view5_pan_v1',298:'view5_pan_v1'}
selected=[(seed,version,MODE.get(version)) for seed in seeds for version in VERS]
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==sha
assert not subprocess.check_output(['git','status','--porcelain'])
assert os.getpriority(os.PRIO_PROCESS,0)==0 and os.getloadavg()[0]<51
assert int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))>6*1024**2
for h,minimum in [('x86',1*1024*2**20),('arm',1*1024*2**20),('mac',1*80*2**20)]:
 p=b/f'e2e18-{BATCH}-budget-{h}.json';x=json.loads(p.read_text());assert time.time()-p.stat().st_mtime<300 and x['ok']
 assert x['checks'][0]['expected_bytes']>=minimum
active=[r for r in (b/'runs').glob('e2e18-v*-s*-r*') if r.is_dir() and not (r/'EXIT').exists()]
assert len(active)<=6-len(selected),[(r.name) for r in active]
receipt=json.loads((b/'relays/e2e18/a-r4.json').read_text())
from datetime import datetime
deadline=datetime.fromisoformat('2026-10-13T07:00:00+00:00').timestamp()
cap=int(min(7200,receipt['checked_unix']+receipt['valid_for_s']-time.time()-660,deadline-time.time()-900))
assert cap>=900,'INSUFFICIENT_RELAY_LIFETIME_FOR_BATCH'
assert float(Path('/proc/uptime').read_text().split()[0])+cap+1200<28800,'FINITE_VM_LIFETIME_REQUIRED'
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:18393/identity',timeout=5) as response:live=json.load(response)
assert live==receipt,'LIVE_MAC_RELAY_IDENTITY_REQUIRED'
validate_receipt(receipt,now=time.time()+cap+600,remote_url=relay_url('study_gemma4_31b_v1'))
old_plan=json.loads(next((b/'runs').glob('speed-gate-e2e18-*-r33-*-plan.json')).read_text())
from harness.public_navigation.native import PublicCore
from harness.public_navigation_unknown import UnknownCore
from harness.public_navigation_monitor import MonitorCore
for cls in (PublicCore,UnknownCore,MonitorCore):cls()
print('NATIVE_BUILD_AND_LOAD_READY',flush=True)
specs=[]
for seed,version,mode in selected:
 name=f'e2e18-v{version}-s{seed}-{BATCH}';target=b/'runs'/name;target.mkdir(exist_ok=False)
 (b/'leases'/name).touch()
 meta={'class':'dev','pr':461,'branch':'codex/e2e18','sha':sha,'batch':f'e2e18-{BATCH}','seed':seed,
       'execution_bundle_id':f'e2e18-v{version}','variant':mode,'sonar_frame':'site_z_v1',
       'wall_cap_s':cap,'storage_budget_bytes':1024*2**20,'submitted_unix':time.time(),
       'gate_new_samples':len(selected),'continuing':len(active),'planned_concurrency':len(active)+len(selected),'research_result':False}
 (target/'RUN_META.json').write_text(json.dumps(meta)+'\n');(target/'SOURCE_SHA').write_text(sha+'\n')
 (target/'resource-admission.json').write_text(json.dumps({'loadavg':os.getloadavg(),'continuing':[r.name for r in active]})+'\n')
 command=list(old_plan[0]['command'])
 command=[f'e2e18-v{version}' if x=='e2e18-v241' else x for x in command]
 for flag,value in [('--timeout',cap+300),('--wall-cap-s',cap),('--expected-source-sha',sha),('--output',str(target/'raw')),('--arm-clearance','range_wall_v1'),('--acquisition-mobility','resume_v1'),('--approach-commit','memory60_view_v1'),('--scan-guard','map_v1'),('--fine-view','inspect60_v1'),('--approach-heading','path20_v1'),('--fine-entry','capture60_mpc_v1'),('--station-heading','station20_v1'),('--clip-recovery','back3_v1'),('--station-handoff','pan_v1'),('--capture-pose','pose08_track_v1'),*([('--relook-search',mode)] if mode else []),*EXTRA[version],('--stage-physics','release_dt1_v1' if version==298 else 'pregrasp_dt1_v1'),('--sonar-frame','site_z_v1'),('--relay-receipt',str(b/'relays/e2e18/a-r4.json')),('--seed',seed)]:
  command=replace_option(command,flag,value)
 specs.append(dict(name=name,target=str(target),command=command))
plan=b/'runs'/f'speed-gate-e2e18-{host}-{BATCH}-plan.json';assert not plan.exists();plan.write_text(json.dumps(specs,indent=2)+'\n')
print(f'NEW {len(selected)} + CONTINUING {len(active)} = {len(selected)+len(active)}; 30 SIM gate; limit3.0',flush=True)
raise SystemExit(gate_main(['start','--plan',str(plan),'--gate-root',str(b/'runs'/f'speed-gate-e2e18-{host}-{BATCH}-{sha[:12]}'),'--speed-gate-limit','3.0']))
