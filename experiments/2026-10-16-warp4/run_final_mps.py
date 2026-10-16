"""Finite private-MPS run-first; gcp2 L4 only; no controller/physics edits."""
import json,pathlib,subprocess,os,datetime,time,signal
r=pathlib.Path('/home/ugrp/ugrp-sim');src=r/'src/a2216618a';py=str(r/'runs/simalt3/warp-env/bin/python')
end=datetime.datetime.fromisoformat('2026-10-16T05:57:25+00:00');jobs=[]
for name,flow,indices,refs in [('beampair','beampair','0,1,2,3','beampair'),('release-s1','release','0,1,3,4,5,7','release-s1'),('release-s3','release','2,6','release-s3')]:
 out=r/'runs/warp4'/(name+'-short-r3-mps');assert not out.exists()
 cmd=[py,str(src/'scripts/run_warp_flow_teacher.py'),'--flow',flow,'--adapter-source',str(r/'src'/('835ccef26aa84b08cc8f7e256fd0f43aa1583ef9' if flow=='beampair' else '8e81b7d96c0c73171635348c90631462adfe1eb0')),'--cases',str(r/'ops-reviews/warp4'/(flow+'-short-cases.json')),'--indices',indices,'--cap-s','60' if flow=='beampair' else '180','--vm-hourly-usd','1.096','--mps-shared-v1','--placement-graspable-filter-v1','--world-model-parameters-v1','--native-sleep-policy-compat-v1','--per-world-model-references-v1',str(r/'runs/warp4'/(refs+'-references-d236')/'per-world-references.json'),'--out',str(out)]
 if flow=='beampair':cmd+=['--teacher-source',str(r/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247')]
 log=(out.parent/(out.name+'.log')).open('w')
 p=subprocess.Popen(cmd,cwd=src,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True,env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MUJOCO_GL':'osmesa','CUDA_MPS_PIPE_DIRECTORY':str(r/'runs/warp4/mps/pipe'),'CUDA_MPS_LOG_DIRECTORY':str(r/'runs/warp4/mps/log')})
 jobs.append(dict(name=name,p=p,out=out,cmd=cmd,log=log))
lease=r/'leases/warp4.json'
lease.write_text(json.dumps(dict(task='warp4',pid=os.getpid(),pids=[j['p'].pid for j in jobs],started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end=end.isoformat(),source_sha='a2216618a',stage='final run-first R3, private MPS shared-load, beam4 release A/B each4; existing-host deadline',concurrency=12,gpu_shared=True),indent=2))
while any(j['p'].poll() is None for j in jobs):
 now=datetime.datetime.now(datetime.timezone.utc)
 if now>=end:
  for j in jobs:
   if j['p'].poll() is None:
    j['out'].mkdir(parents=True,exist_ok=True)
    (j['out']/'SUPERVISOR_STOP.json').write_text(json.dumps(dict(category='HOST_ERROR',reason='existing L4 8h host resource deadline, not task SIM cap',utc=now.isoformat())))
    # Verify exact owned process identity before signalling one Python child.
    args=pathlib.Path('/proc/'+str(j['p'].pid)+'/cmdline').read_bytes().split(b'\0')
    assert str(j['out']).encode() in args
    j['p'].send_signal(signal.SIGINT)
  break
 state=[]
 for j in jobs:
  progress=j['out']/'progress.json'
  try:d=json.loads(progress.read_text())
  except (FileNotFoundError,json.JSONDecodeError):d={}
  state.append(dict(name=j['name'],pid=j['p'].pid,exit=j['p'].poll(),progress=d))
 (r/'runs/warp4/r3-mps-state.json').write_text(json.dumps(dict(utc=now.isoformat(),jobs=state),indent=2))
 time.sleep(20)
for j in jobs:
 code=j['p'].wait();j['log'].close();print(j['name'],code,flush=True)

# Only the private task pipe is addressed; never quit a default/global daemon.
mps_env={**os.environ,'CUDA_MPS_PIPE_DIRECTORY':str(r/'runs/warp4/mps/pipe'),'CUDA_MPS_LOG_DIRECTORY':str(r/'runs/warp4/mps/log')}
check=subprocess.run(['nvidia-cuda-mps-control'],input='ps\n',text=True,capture_output=True,env=mps_env)
clients=[int(line.split()[0]) for line in check.stdout.splitlines() if line.split() and line.split()[0].isdigit()]
unknown=set(clients)-{j['p'].pid for j in jobs}
cleanup=dict(client_check=check.stdout,unowned_clients=sorted(unknown),quit_sent=False)
if not unknown:
 result=subprocess.run(['nvidia-cuda-mps-control'],input='quit\n',text=True,capture_output=True,env=mps_env)
 cleanup.update(quit_sent=True,exit=result.returncode,stdout=result.stdout,stderr=result.stderr)
(r/'runs/warp4/mps/cleanup.json').write_text(json.dumps(cleanup,indent=2))
if lease.exists() and json.loads(lease.read_text()).get('pid')==os.getpid():lease.unlink()
