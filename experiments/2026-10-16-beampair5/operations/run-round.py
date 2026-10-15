"""gcp2 bounded round; persists lease, exact source, commands and complete analysis."""
import pathlib,sys,subprocess,os,json,datetime,shutil
r=pathlib.Path('/home/ugrp/ugrp-sim');sha=sys.argv[1];round_id=sys.argv[2];src=r/'src'/sha;ops=r/'ops-reviews/beampair5';py=str(r/'ugrp/.venv-sim/bin/python')
assert len(sha)==40 and (src/'.git').exists(), 'exact existing source SHA required'
out=r/'runs'/f'beampair5-{round_id}-{sha[:8]}';out.mkdir(exist_ok=False)
lease=r/'leases/beampair5.json';lease.write_text(json.dumps(dict(task='beampair5',pid=os.getpid(),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='bounded short6; 8h process cap',source=sha,round=round_id)))
cmd=[py,'-m','scripts.run_beampair1_batch','--plan',str(src/'experiments/2026-10-16-beampair5/short6-plan.json'),'--dependency-root',str(r/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'),'--root',str(out/'round'),'--candidate','baseline','--rendezvous','peer_rendezvous_v2','--approach-repair','beampair_approach_v2','--wall-layer','beampair_wall_clear_v1','--first-episodes','2']
env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1','PYTHONPATH':str(src)}
processes=[dict(pid=int(p.parent.name),command=p.read_bytes().replace(b'\0',b' ').decode(errors='replace')) for p in pathlib.Path('/proc').glob('[0-9]*/cmdline') if p.exists() and any(v in p.read_bytes().split(b'\0')[0] for v in (b'python',b'mujoco',b'ffmpeg'))]
assert len(processes)+6<=40
assert shutil.disk_usage(r).free>8*1024**3+6*256*1024**2
mem=next(int(l.split()[1])*1024 for l in pathlib.Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:'));assert mem>6*1024**3
(out/'host-admission.json').write_text(json.dumps(dict(processes=processes,leases={p.name:p.read_text() for p in (r/'leases').iterdir()},free_bytes=shutil.disk_usage(r).free,memory_available_bytes=mem,loadavg=os.getloadavg(),planned_max=6,global_limit=40,disk_budget_bytes=6*256*1024**2),indent=2))
(out/'RUN_META.json').write_text(json.dumps(dict(pr=522,branch='claude/beam-pair-teacher',sha=sha,host='gcp2',batch='beampair5-'+round_id,planned_N=6,**{'class':'dev'}),indent=2))
(out/'PROCESS.json').write_text(json.dumps(dict(pid=os.getpid(),command=cmd),indent=2))
with (out/'log.txt').open('w') as log:
 p=subprocess.Popen(['timeout','--signal=INT','8h',*cmd],cwd=src,env=env,stdout=log,stderr=subprocess.STDOUT);code=p.wait()
(out/'EXIT').write_text(str(code)+'\n')
analysis=ops/(round_id+'-analysis')
with (ops/(round_id+'-analysis.log')).open('w') as log:
 a=subprocess.run([py,'-m','scripts.analyze_beampair1',str(out/'round'),'--out',str(analysis)],cwd=src,env=env,stdout=log,stderr=subprocess.STDOUT)
if a.returncode==0:
 summary=json.loads((analysis/'summary.json').read_text())
 for entry in summary['runs']:
  if not entry['strict_success']:
   raw=pathlib.Path(entry['raw']);pout=ops/'playback'/f'beampair5-{round_id}-{entry["seed"]}'
   with (ops/(round_id+'-playback.log')).open('w') as log:
    subprocess.run([py,'-m','scripts.review_beampair3','--raw',str(raw),'--out',str(pout)],cwd=src,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
(ops/(round_id+'-DONE')).write_text(json.dumps(dict(exit=code,analysis_exit=a.returncode,raw=str(out),source=sha))+'\n')
