"""Prepare v7 authored starts and exact C3.12 compilation references on gcp2.

Reference export retains the existing folded setup settling. No scored C teacher
rollout is used as evidence; all scored gate/record execution is MJWarp native0.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_v7 import ROOT,B,Q,T


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plans',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(ROOT)
    plans=json.loads(a.plans.read_text())['episodes']
    if not plans or len({x['seed'] for x in plans})!=len(plans) or any(not x.get('act17_v7') for x in plans):
        raise ValueError('unique registered v7 starts required')
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/'plans.json').write_bytes(a.plans.read_bytes())
    python=B/'runs/simalt3/c-env/bin/python'
    def one(i):
        output=a.out/f'case-{i:03d}'
        command=[str(python),'-u',str(ROOT/'scripts/act17_v7.py'),'--enabled','--action','launch','--',
            '--enabled','--mode','teacher','--','--physics-backend','c_pilot_v1',
            '--teacher-source',str(T),'--plan',str(a.out/'plans.json'),'--episode',str(i),
            '--scene-v5-v1','--native-sleep-policy-compat-v1','--export-compiled-only',
            '--vm-hourly-usd','1.096','--out',str(output)]
        (a.out/f'case-{i:03d}-argv.json').write_text(json.dumps(command,indent=2))
        with (a.out/f'case-{i:03d}.log').open('x') as log:
            subprocess.run(command,cwd=Q,check=True,stdout=log,stderr=subprocess.STDOUT,
                env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','MUJOCO_GL':'osmesa',
                     'LP_NUM_THREADS':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
        xml=output/'world-000/scene.xml'
        return dict(index=i,seed=plans[i]['seed'],xml_sha256=sha256(xml),scene_xml=str(xml),
            actuator=str(output/'compiled-312.json'),geometry=str(output/'compiled-geometry312.npz'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(one,range(len(plans))))
    (a.out/'inventory.json').write_text(json.dumps(rows,indent=2)+'\n')
    (a.out/'per-world-references.json').write_text(json.dumps({x['xml_sha256']:{k:x[k] for k in ['actuator','geometry']} for x in rows},indent=2)+'\n')
    (a.out/'summary.json').write_text(json.dumps(dict(status='complete',complete=True,N=len(rows),host=host,
        source_sha=source,reference_only=True,scored_C_teacher_rollouts=0,training_rgb=False),indent=2)+'\n')


if __name__=='__main__':main()
