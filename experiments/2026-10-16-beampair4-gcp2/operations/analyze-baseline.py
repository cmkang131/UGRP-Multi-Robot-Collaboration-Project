import subprocess,pathlib,os,json,time,hashlib
r=pathlib.Path('/home/ugrp/ugrp-sim');src=r/'src/d72efd13957ce450c5cccc3fd93a555a37dd4705';ops=r/'ops-reviews/beampair4-gcp2'
env={**os.environ,'MUJOCO_GL':'osmesa','PYTHONPATH':str(src),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1'}
py=str(r/'ugrp/.venv-sim/bin/python')
assert (ops/'baseline-EXIT').exists()
cmd=[py,'-m','scripts.analyze_beampair4','--root',str(r/'runs'),'--out',str(ops/'baseline-analysis'),'--pattern','beampair3-gcp2-repro-*-e645b34b/raw','--host','gcp2','--planned-n','3']
subprocess.run(cmd,cwd=src,env=env,check=True)
children=[]
for seed in (8318620,8318626,8318604):
 name=f'beampair3-gcp2-repro-{seed}-e645b34b';out=ops/'playback'/name
 cmd=[py,'-m','scripts.review_beampair3','--raw',str(r/'runs'/name/'raw'),'--out',str(out)]
 log=(ops/f'playback-{seed}.log').open('w');children.append((subprocess.Popen(cmd,cwd=src,env=env,stdout=log,stderr=subprocess.STDOUT),log))
for p,l in children:assert p.wait()==0;l.close()
for f in (ops/'baseline-analysis').glob('*'):
 if f.is_file() and f.stat().st_size>65536:
  digest=hashlib.sha256(f.read_bytes()).hexdigest();subprocess.run(['zstd','-q','--keep',str(f)],check=True)
  assert hashlib.sha256(subprocess.check_output(['zstd','-qdc',str(f)+'.zst'])).hexdigest()==digest
(ops/'baseline-analysis-EXIT').write_text('done\n')
