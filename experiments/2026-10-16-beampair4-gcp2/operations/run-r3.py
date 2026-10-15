import pathlib,subprocess,os,json,hashlib,signal
r=pathlib.Path('/home/ugrp/ugrp-sim');sha='d72efd13957ce450c5cccc3fd93a555a37dd4705';src=r/'src'/sha
out=r/'runs/beampair4-r3-gcp2-d72efd13';out.mkdir(exist_ok=False)
ops=r/'ops-reviews/beampair4-gcp2';py=str(r/'ugrp/.venv-sim/bin/python')
assert (ops/'baseline-analysis-EXIT').exists()
assert len(subprocess.run(['pgrep','-f','[p]ython.*scripts.run_'],capture_output=True,text=True).stdout.splitlines())<=34
meta=dict(pr=522,branch='claude/beam-pair-teacher',sha=sha,host='gcp2',batch='beampair4-r3',planned_N=6,**{'class':'dev'})
(out/'RUN_META.json').write_text(json.dumps(meta,indent=2))
env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1','PYTHONPATH':str(src)}
cmd=[py,'-m','scripts.run_beampair1_batch','--plan',str(src/'experiments/2026-10-15-beampair4/r3-plan.json'),'--dependency-root',str(r/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'),'--root',str(out/'round'),'--candidate','baseline','--rendezvous','peer_rendezvous_v2','--approach-repair','beampair_approach_v2','--first-episodes','2']
log=(out/'log.txt').open('w');p=subprocess.Popen(['timeout','--signal=INT','8h',*cmd],cwd=src,env=env,stdout=log,stderr=subprocess.STDOUT)
(out/'PROCESS.json').write_text(json.dumps(dict(pid=p.pid,command=cmd),indent=2))
code=p.wait();log.close();(out/'EXIT').write_text(str(code)+'\n')
subprocess.run([py,'-m','scripts.analyze_beampair1',str(out/'round'),'--out',str(ops/'r3-analysis')],cwd=src,env=env,check=True)
summary=json.loads((ops/'r3-analysis/summary.json').read_text())
for entry in summary['runs']:
 if not entry['strict_success']:
  raw=pathlib.Path(entry['raw']);seed=entry['seed'];pout=ops/'playback'/f'beampair4-r3-gcp2-{seed}'
  subprocess.run([py,'-m','scripts.review_beampair3','--raw',str(raw),'--out',str(pout)],cwd=src,env=env,check=True)
(ops/'r3-analysis-EXIT').write_text('done\n')
