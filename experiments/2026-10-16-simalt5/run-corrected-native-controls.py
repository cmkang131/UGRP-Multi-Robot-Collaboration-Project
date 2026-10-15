"""R3 instrumentation repair only; Warp candidate and physics remain frozen."""
import json
import os
from pathlib import Path
import signal
import subprocess

R=Path('/home/ugrp/ugrp-sim/runs/simalt5');OLD=R.parent/'simalt3'
S=Path('/home/ugrp/ugrp-sim/src/09d585b7')
SHA=subprocess.check_output(['git','-C',str(S),'rev-parse','HEAD'],text=True).strip()
jobs=[]
for name,python,extra in [('c312-native-corrected',OLD/'c-env/bin/python',[]),
    ('c316-native-corrected',OLD/'warp-env/bin/python',[
        '--compiled-reference-v1',R/'compiled-312.json','--compiled-geometry-312-v1',R/'compiled-geometry312.npz'])]:
    cmd=list(map(str,[python,'-u',S/'scripts/simalt_step_probe.py','--enabled','--fixture',OLD/'fixture',
        '--out',R/name,'--engine','cpu','--case','grip','--sha',SHA,
        '--capacity-reference',R.parent/'simalt4/rev5/dense-capacity.json','--dense-capacity-v1',
        '--backend-mode','legacy-plane-v1','--record-own-rgb',OLD/'runtime/source',*extra]))
    jobs.append((name,cmd))
reject={'stage':'R3 comparator repair','reason':'native port self-control differs13.317663mm; preserve original MuJoCo math call order',
        'blocking_object':'Plane–Mesh point transform arithmetic','minimum_gap_m':None,'gap_note':'not a planning clearance',
        'funnel':[{'gate':'old native port C312 fidelity','entered':1,'passed':0,'rejected':1}],
        'raw':str(R/'c312-native-port-selfcontrol/steps.npz')}
(R/'rejection-native-port-repair.json').write_text(json.dumps(reject,indent=2)+'\n')
plan={'round':3,'instrumentation_repair':True,'additional_Warp_candidates':0,'source_sha':SHA,
      'rejection_table':str(R/'rejection-native-port-repair.json'),'jobs':jobs}
assert Path(plan['rejection_table']).is_file()
(R/'round3-corrected-native-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
children=[]
try:
    for name,cmd in jobs:
        log=(R/(name+'.log')).open('x')
        child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,
                               env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1'})
        children.append((child,log,name))
    for child,log,name in children:
        if child.wait()!=0:raise RuntimeError(name+' process failed')
        info=json.loads((R/name/'result.json').read_text());print(name,info['status'],flush=True)
        if info['status']!='complete':raise RuntimeError(name+' incomplete')
finally:
    for child,log,name in children:
        if child.poll() is None:os.killpg(child.pid,signal.SIGINT);child.wait()
        log.close()
