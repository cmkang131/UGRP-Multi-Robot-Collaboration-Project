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
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    sys.path.insert(0,str(Q/'scripts'));from simalt_host import gcp2_identity
    if gcp2_identity()['instance']!='ugrp-act-l4-gcp2':raise RuntimeError('qualified L4 metadata required')
    a.root.mkdir(parents=True,exist_ok=False)
    code="""import sys,json,math
from collections import Counter
sys.path.insert(0,sys.argv[1])
from scripts.make_solo_teacher_plan import episode
from harness.grasp_act_seed_splits import check_range
from sim.grasp_act_solo_teacher import BOX_KINDS
check_range('train',86820,50)
counts=Counter();rows=[]
for i in range(50):
 kind=BOX_KINDS[i%4];p=episode(counts[kind],kind,86820+i,'train');counts[kind]+=1
 p.update(episode_id='act16w-record-'+str(p['seed']),batch='act16w-resume2',pr=539,negative_probe=False,gate_eligible=False,training_eligible=True)
 rows.append(p)
open(sys.argv[2],'x').write(json.dumps({'episodes':rows,'seed_scope':'independent of warp1 debugging8317100-139 and heldout91620-659;86820 warm3SIM repeated only as full training record later','distribution':dict(counts)},indent=2)+'\\n')
"""
    subprocess.run([str(C),'-c',code,str(T),str(a.root/'plans.json')],check=True)
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
    with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,range(50)))
    (a.root/'inventory.json').write_text(json.dumps(rows,indent=2)+'\n')
    (a.root/'per-world-references.json').write_text(json.dumps({r['xml_sha256']:{k:r[k] for k in ('actuator','geometry')} for r in rows},indent=2)+'\n')
    print(json.dumps(dict(status='complete',cases=len(rows),teacher_rollouts=0,training_rgb=False,data_admitted=False)))

if __name__=='__main__':main()
