
from pathlib import Path
import json,os,subprocess,time,hashlib,shutil,sys
base=Path('/home/ugrp/ugrp-sim');sha='cc8fc1a2e62d7f331b732e1261be55c70c016355';source=base/'src'/sha
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==sha
assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain']).strip()
subprocess.run(['python3','/usr/local/lib/ugrp-storage/scripts/azure_shutdown.py','admit'],check=True)
assert shutil.disk_usage(base).free - 6*4*2**30 >=8*2**30
assert float(Path('/proc/uptime').read_text().split()[0])+25200+600<28800
assert os.getpriority(os.PRIO_PROCESS,0)==0
from urllib.request import urlopen
with urlopen('http://127.0.0.1:18393/identity',timeout=15) as r:identity=json.load(r)
assert identity['single_model'] and identity['upstream']=='openrouter_v1'
assert identity['checked_unix']+identity['valid_for_s']-time.time()>25400
os.chdir(source)
sys.path.insert(0,str(source))
from harness.s4_live_transport import validate_receipt
from scripts.run_e2e_ownmap_live import relay_url
assert relay_url('study_gemma4_31b_v1')==identity['remote_url']=='http://127.0.0.1:18393/v1/chat/completions'
validate_receipt(identity,now=time.time()+25200,remote_url='http://127.0.0.1:18393/v1/chat/completions')
env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','LP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
subprocess.run(['.venv-sim/bin/python','-c','from scripts.run_e2e_azure_batch import prepare_native; import json; print(json.dumps(prepare_native()))'],env=env,check=True)
submissions=[]
for seed in range(61001,61004):
 for group in ('a','b'):
  mem=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
  assert mem>=6*2**30 and os.getloadavg()[0]<51
  assert shutil.disk_usage(base).free>=8*2**30
  name=f'e2e15r2-{group}-s{seed}';root=base/'runs'/name
  assert not root.exists();root.mkdir();(base/'leases'/name).touch()
  command=['.venv-sim/bin/python','-m','scripts.sim_cli','workflow','run','e2e-combo14-vo2-v205' if group=='a' else 'e2e-stall-budget-v199','--timeout','25200','--','--expected-source-sha',sha,'--output',str(root/f'e2e15-{group}-s{seed}'/'raw'),'--seed',str(seed),'--driver-profile','study_gemma4_31b_v1','--relay-receipt',str(base/'relays/e2e15r2/a.json'),'--e2e-live','--event-driven-llm','--compact-prompt','--setdown-only-when-relook','on_v1','--decider','off','--exploration-progress','frontier_progress_v1','--pose-fix','innovation','--path-follow','rpp_v1','--dev-light','--stall-bundle','--mapping-budget','case_cap_v1','--wall-cap-s','25200','--execute']
  command+=['--stall-odometry','rgb_vo_v2' if group=='a' else 'rgb_pulse_gate_v1','--stall-recovery','off' if group=='a' else 'backup_replan_v1','--stall-noise','off' if group=='a' else 'amcl_alpha_v1']
  if group=='a':command+=['--boundary-views','candidate_views_v1','--b-marker-detect','contrast_v1']
  meta=dict(raw_relative=f'e2e15-{group}-s{seed}/raw', execution_config_revision='vm3-relay-r2', host='azure3', class_='dev',pr=446,branch='claude/e2e14-combo',sha=sha,batch='e2e14-rerun-vm3',group=group,seed=seed,started_unix=time.time(),wall_cap_s=25200,workflow_timeout_s=25200,storage_budget_bytes=4*2**30,memory_available_bytes=mem,loadavg=os.getloadavg(),runner_assets={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('/usr/local/lib/ugrp-storage/scripts')/x for x in ('remote_run_finish.py','azure_shutdown.py','azure_archive_native.py')]});meta['class']=meta.pop('class_')
  (root/'RUN_META.json').write_text(json.dumps(meta,indent=2)+'\n');(root/'SOURCE_SHA').write_text(sha+'\n');(root/'COMMAND').write_text(json.dumps(command)+'\n');(root/'LOADAVG').write_text(str(os.getloadavg())+'\n')
  proc=subprocess.Popen(['python3','/usr/local/lib/ugrp-storage/scripts/remote_run_finish.py','--source',str(source),'--run',str(root),'--',*command],cwd=source,env=env,start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  submissions.append(dict(run=name,pid=proc.pid,submitted_unix=time.time(),meta=meta))
  print(json.dumps(submissions[-1]),flush=True)
(base/'e2e15r2-submissions.json').write_text(json.dumps(submissions,indent=2)+'\n')
with (base/'e2e15r2-observer.log').open('x') as log:
 proc=subprocess.Popen(['python3',str(base/'e2e15r2-observe.py')],cwd=base,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(base/'e2e15r2-observer-process.json').write_text(json.dumps(dict(pid=proc.pid,started_unix=time.time())))
