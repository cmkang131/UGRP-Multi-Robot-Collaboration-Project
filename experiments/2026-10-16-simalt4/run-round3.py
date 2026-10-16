"""Last allowed physics round: dense buffers + C3.12 plane collision selection."""
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path('/home/ugrp/ugrp-sim/runs/simalt4')
OLD=ROOT.parent/'simalt3'
REV=ROOT/'rev5'
PY=OLD/'warp-env/bin/python'
SOURCE_SHA=(REV/'SOURCE_SHA').read_text().strip()

while True:
    p=ROOT/'capacity-r2-grip/result.json'
    if p.exists():
        info=json.loads(p.read_text())
        if info['status']!='running':break
    time.sleep(5)
if info['status']!='complete':raise RuntimeError('round2 incomplete; round3 not admitted')

summary=[]
for case in ('forward','side','turn','grip'):
    out=ROOT/f'capacity-r2-analysis-{case}'
    cmd=[str(PY),str(ROOT/'scripts/simalt_step_analysis.py'),'--fixture',str(OLD/'fixture'),
         '--reference',str(ROOT/f'c316-{case}'),'--candidate',str(ROOT/f'capacity-r2-{case}'),
         '--out',str(out)]
    with (ROOT/f'capacity-r2-analysis-{case}.log').open('w') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    summary.append(json.loads((out/'summary.json').read_text()))

rejections=json.loads((REV/'rejection-before-round2.json').read_text())
rejections['round2_same_version']=summary
rejections['next_action']='round3 final: legacy plane collision only; no gain/damping/physics parameter mutation'
(ROOT/'rejection-before-round3.json').write_text(json.dumps(rejections,indent=2)+'\n')
commands=[]
for case in ('forward','side','turn','grip'):
    commands.append([str(PY),'-u',str(REV/'scripts/simalt_step_probe.py'),'--enabled',
       '--fixture',str(OLD/'fixture'),'--out',str(ROOT/f'legacy-r3-{case}'),'--engine','warp',
       '--case',case,'--sha',SOURCE_SHA,'--capacity-reference',str(REV/'dense-capacity.json'),
       '--dense-capacity-v1','--backend-mode','legacy-plane-v1','--record-own-rgb',str(OLD/'runtime/source')])
plan={'round':3,'rejection_table':str(ROOT/'rejection-before-round3.json'),'commands':commands,
      'source_sha':SOURCE_SHA,'physics_overrides':{},'stop_after_this_round':True}
(ROOT/'round3-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
assert Path(plan['rejection_table']).is_file()
for cmd in commands:
    out=Path(cmd[cmd.index('--out')+1])
    with (ROOT/(out.name+'.log')).open('w') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,
                       env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1'},check=True)
    info=json.loads((out/'result.json').read_text())
    print(out.name,info['status'],info.get('error',''),flush=True)
    if info['status']!='complete':break
