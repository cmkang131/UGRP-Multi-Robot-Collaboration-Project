"""Finite replacement batch using the standard managed workflows and speed gate."""
import json,os,subprocess,sys,time
from pathlib import Path
from scripts.azure_speed_gate import replace_option,main as gate_main
from scripts.run_e2e_ownmap_live import relay_url
from harness.s4_live_transport import validate_receipt

b=Path.home()/'ugrp-sim';sha=sys.argv[1];host=os.uname().nodename
selected={'ugrp-sim-azure3':[(61003,245,'range_v1'),(61006,248,'off')],
          'ugrp-sim-azure4':[(61007,246,'range_wall_v1'),(61009,247,'range_wall_slots_v1')]}[host]
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==sha
assert not subprocess.check_output(['git','status','--porcelain'])
assert os.getpriority(os.PRIO_PROCESS,0)==0 and os.getloadavg()[0]<51
assert int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))>6*1024**2
assert float(Path('/proc/uptime').read_text().split()[0])+2400+1200<28800,'FINITE_VM_LIFETIME_REQUIRED'
for h,minimum in [('x86',6*2560*2**20),('arm',12*2560*2**20),('mac',12*80*2**20)]:
 p=b/f'e2e18-r36-budget-{h}.json';x=json.loads(p.read_text());assert time.time()-p.stat().st_mtime<300 and x['ok']
 assert x['checks'][0]['expected_bytes']>=minimum
active=[r for r in (b/'runs').glob('e2e18-v*-s*-r*') if r.is_dir() and not (r/'EXIT').exists()]
assert len(active)==4,[(r.name) for r in active]
receipt=json.loads((b/'relays/e2e18/a.json').read_text())
validate_receipt(receipt,now=time.time()+3300,remote_url=relay_url('study_gemma4_31b_v1'))
old_plan=json.loads(next((b/'runs').glob('speed-gate-e2e18-*-r33-*-plan.json')).read_text())
specs=[]
for seed,version,mode in selected:
 name=f'e2e18-v{version}-s{seed}-r36';target=b/'runs'/name;target.mkdir(exist_ok=False)
 (b/'leases'/name).touch()
 meta={'class':'dev','pr':461,'branch':'codex/e2e18','sha':sha,'batch':'e2e18-r36','seed':seed,
       'execution_bundle_id':f'e2e18-v{version}','variant':mode,'sonar_frame':'site_z_v1',
       'wall_cap_s':2400,'storage_budget_bytes':2048*2**20,'submitted_unix':time.time(),
       'gate_new_samples':2,'continuing':4,'planned_concurrency':6,'research_result':False}
 (target/'RUN_META.json').write_text(json.dumps(meta)+'\n');(target/'SOURCE_SHA').write_text(sha+'\n')
 (target/'resource-admission.json').write_text(json.dumps({'loadavg':os.getloadavg(),'continuing':[r.name for r in active]})+'\n')
 command=next(x['command'] for x in old_plan if f'-s{seed}-' in x['name'])
 command=[f'e2e18-v{version}' if x=='e2e18-v241' else x for x in command]
 for flag,value in [('--timeout',3000),('--wall-cap-s',2400),('--expected-source-sha',sha),('--output',str(target/'raw')),('--arm-clearance',mode),('--sonar-frame','site_z_v1')]:
  command=replace_option(command,flag,value)
 specs.append(dict(name=name,target=str(target),command=command))
plan=b/'runs'/f'speed-gate-e2e18-{host}-r36-plan.json';assert not plan.exists();plan.write_text(json.dumps(specs,indent=2)+'\n')
print('NEW 2 + CONTINUING 4 = 6; 30 SIM gate; limit3.0',flush=True)
raise SystemExit(gate_main(['start','--plan',str(plan),'--gate-root',str(b/'runs'/f'speed-gate-e2e18-{host}-r36-{sha[:12]}'),'--speed-gate-limit','3.0']))
