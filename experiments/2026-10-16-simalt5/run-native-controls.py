"""Round2 controls: identical C3.16 collision path, old/new compiled damping."""
import json
import os
from pathlib import Path
import subprocess

ROOT=Path('/home/ugrp/ugrp-sim/runs/simalt5')
OLD=ROOT.parent/'simalt3'
SOURCE=Path('/home/ugrp/ugrp-sim/src/51048030')
PY=OLD/'warp-env/bin/python'
SHA='51048030'
jobs=[]
for mode in ('312','316'):
    name='c316-legacy-damping'+mode+'-grip'
    cmd=[str(PY),'-u',str(SOURCE/'scripts/simalt_step_probe.py'),'--enabled',
         '--fixture',str(OLD/'fixture'),'--out',str(ROOT/name),'--engine','cpu','--case','grip',
         '--sha',SHA,'--capacity-reference',str(ROOT.parent/'simalt4/rev5/dense-capacity.json'),
         '--dense-capacity-v1','--backend-mode','legacy-plane-v1','--record-own-rgb',str(OLD/'runtime/source')]
    if mode=='312':cmd+=['--compiled-reference-v1',str(ROOT/'compiled-312.json')]
    jobs.append((name,cmd))
plan={'round':2,'purpose':'native version/backend controls; same Warp candidate, no tuning',
      'rejection_table':str(ROOT/'rejection-before-round2.json'),'jobs':jobs}
assert Path(plan['rejection_table']).is_file()
(ROOT/'round2-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
for name,cmd in jobs:
    with (ROOT/(name+'.log')).open('x') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,
                       env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1'},check=True)
    result=json.loads((ROOT/name/'result.json').read_text())
    print(name,result['status'],result.get('error',''),flush=True)
    if result['status']!='complete':raise RuntimeError(name+' incomplete')
for name,reference,candidate in [
    ('native-matched-vs-c312',ROOT.parent/'simalt4/c312-grip',ROOT/'c316-legacy-damping312-grip'),
    ('native-newdamping-vs-c312',ROOT.parent/'simalt4/c312-grip',ROOT/'c316-legacy-damping316-grip'),
    ('backend-matched',ROOT/'c316-legacy-damping312-grip',ROOT/'warp-compiled312-grip'),
    ('backend-newdamping',ROOT/'c316-legacy-damping316-grip',ROOT.parent/'simalt4/legacy-r3-grip')]:
    out=ROOT/('analysis-'+name)
    with (ROOT/('analysis-'+name+'.log')).open('x') as log:
        subprocess.run([str(PY),str(SOURCE/'scripts/simalt_step_analysis.py'),'--fixture',str(OLD/'fixture'),
            '--reference',str(reference),'--candidate',str(candidate),'--out',str(out)],
            stdout=log,stderr=subprocess.STDOUT,check=True)
print('NATIVE_CONTROLS_COMPLETE',flush=True)
