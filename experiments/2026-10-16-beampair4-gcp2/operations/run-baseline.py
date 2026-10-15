import json,subprocess,pathlib,os,time,hashlib
root=pathlib.Path('/home/ugrp/ugrp-sim');sha='3c073a92cc' # full adapter resolved below
source=next(p for p in (root/'src').iterdir() if p.name.startswith('3c073a92'))
baseline=root/'src/e645b34beb4fa693ab4ddedfe77045ae26b46388';dep=root/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'
ops=root/'ops-reviews/beampair4-gcp2';ops.mkdir(parents=True,exist_ok=True)
lease=root/'leases/beampair4-gcp2';lease.touch()
plan=json.loads((baseline/'experiments/2026-10-15-beampair1/gate-plan.json').read_text())
env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1','PYTHONPATH':str(source)}
children=[]
for seed in (8318620,8318626,8318604):
 i=next(i for i,e in enumerate(plan['episodes']) if e['seed']==seed)
 run=root/f'runs/beampair3-gcp2-repro-{seed}-e645b34b'
 cmd=[str(root/'ugrp/.venv-sim/bin/python'),'-m','scripts.rehost_beampair3','--source',str(baseline),'--dependency-root',str(dep),'--episode',str(i),'--out',str(run/'raw')]
 log=(ops/f'baseline-{seed}.log').open('w')
 process=subprocess.Popen(['timeout','--signal=INT','8h',*cmd],cwd=source,stdout=log,stderr=subprocess.STDOUT,env=env)
 children.append((seed,process,log,run,cmd))
(ops/'baseline-processes.json').write_text(json.dumps([dict(seed=s,pid=p.pid,command=c,raw=str(r/'raw')) for s,p,l,r,c in children],indent=2))
for s,p,l,r,c in children:
 code=p.wait();l.close()
 (r/'EXIT').write_text(str(code)+'\n')
 (r/'RUN_META.json').write_text(json.dumps(dict(pr=522,branch='claude/beam-pair-teacher',sha='e645b34beb4fa693ab4ddedfe77045ae26b46388',host='gcp2',batch='beampair4-baseline-gcp2',**{'class':'dev'}),indent=2))
(ops/'baseline-EXIT').write_text('done\n')
