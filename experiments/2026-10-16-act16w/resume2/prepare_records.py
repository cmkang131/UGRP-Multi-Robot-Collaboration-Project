"""Frozen sampler50 fresh training starts + exact C312 compile references only.
No teacher rollout, no training camera or dataset admission. Run on gcp2 L4.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

B=Path('/home/ugrp/ugrp-sim');Q=B/'src/f0db6b1abb842ea65b71c433738210254f300a7c'
T=B/'src/warp1-teacher-snapshot-6f057f7e';C=B/'runs/simalt3/c-env/bin/python'

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--seed-start',type=int,default=86820);p.add_argument('--count',type=int,default=50)
    p.add_argument('--split',choices=['train','heldout_start'],default='train');a=p.parse_args()
    if not 1<=a.count<=50:p.error('finite at most50 setup exports')
    sys.path.insert(0,str(Q/'scripts'));from simalt_host import gcp2_identity
    if gcp2_identity()['instance']!='ugrp-act-l4-gcp2':raise RuntimeError('qualified L4 metadata required')
    a.root.mkdir(parents=True,exist_ok=False)
    code="""import sys,json,math
from collections import Counter
sys.path.insert(0,sys.argv[1])
from scripts.make_solo_teacher_plan import episode
from harness.grasp_act_seed_splits import check_range
from sim.grasp_act_solo_teacher import BOX_KINDS
split,start,count=sys.argv[3],int(sys.argv[4]),int(sys.argv[5])
check_range(split,start,count)
counts=Counter();rows=[]
for i in range(count):
 kind=BOX_KINDS[i%4];p=episode(counts[kind],kind,start+i,split);counts[kind]+=1
 p.update(episode_id='act16w-'+split+'-'+str(p['seed']),batch='act16w-resume2',pr=539,negative_probe=False,gate_eligible=False,training_eligible=split=='train')
 rows.append(p)
open(sys.argv[2],'x').write(json.dumps({'episodes':rows,'seed_scope':split+'; registered before training; no rollout or checkpoint selection','distribution':dict(counts)},indent=2)+'\\n')
"""
    subprocess.run([str(C),'-c',code,str(T),str(a.root/'plans.json'),a.split,str(a.seed_start),str(a.count)],check=True)
    plans=json.loads((a.root/'plans.json').read_text())['episodes']
    def one(i):
        out=a.root/f'case-{i:02d}'
        cmd=[str(C),str(Q/'scripts/run_warp_act_teacher.py'),'--physics-backend','c_pilot_v1',
             '--teacher-source',str(T),'--plan',str(a.root/'plans.json'),'--episode',str(i),
             '--scene-v5-v1','--native-sleep-policy-compat-v1','--export-compiled-only',
             '--vm-hourly-usd','1.096','--out',str(out)]
        with (a.root/f'case-{i:02d}.log').open('x') as log:
            result=subprocess.run(cmd,cwd=Q,stdout=log,stderr=subprocess.STDOUT,
                env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
        if result.returncode:raise RuntimeError('reference export failed index'+str(i))
        return dict(index=i,seed=plans[i]['seed'],xml_sha256=hashlib.sha256((out/'world-000/scene.xml').read_bytes()).hexdigest(),
                    actuator=str(out/'compiled-312.json'),geometry=str(out/'compiled-geometry312.npz'))
    with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,range(a.count)))
    (a.root/'inventory.json').write_text(json.dumps(rows,indent=2)+'\n')
    (a.root/'per-world-references.json').write_text(json.dumps({r['xml_sha256']:{k:r[k] for k in ('actuator','geometry')} for r in rows},indent=2)+'\n')
    print(json.dumps(dict(status='complete',cases=len(rows),teacher_rollouts=0,training_rgb=False,data_admitted=False)))

if __name__=='__main__':main()
