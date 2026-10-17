"""Finite post-training owner: TRAIN fit, gated VAL, conditional FINAL, packaging.

No cloud credentials, LLM calls, uploads or host lifecycle actions. Publication
and VM stop stay on the Mac. R8 wins a tie only if both independently pass8/8;
this preference is frozen before either new candidate is evaluated.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256,ACT_SHA
from act17_data import read
from act17_v7 import ROOT,B,Q,T,SCENARIOS,KINDS,scenario
from act18_diagnose import write


def live_queue_pid(previous,training):
    """Find the actual act18_queue process for this training directory.

    The lease pid is overwritten by this owner, so a restarted owner cannot
    assume previous['pid'] is the trainer. Only a live cmdline that names both
    act18_queue.py and the exact training directory is accepted.
    """
    candidates=[]
    for entry in Path('/proc').glob('[0-9]*/cmdline'):
        try:value=entry.read_text().replace('\0',' ')
        except OSError:continue
        if 'act18_queue.py' in value and str(training) in value:
            candidates.append(int(entry.parent.name))
    if len(candidates)!=1:
        raise ValueError('exactly one live act18 queue owner required')
    return candidates[0]


def command(argv,log):
    with log.open('x') as stream:
        subprocess.run(argv,check=True,stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT,
            env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'})


def prepare_final(protocol,selection,out):
    """Same authored-start generator and v7 compiled-only adapter as act17."""
    if selection.get('VAL_n')!=8 or selection.get('VAL_N')!=8 or not selection.get('frozen_before_final'):
        raise ValueError('FINAL remains unopened before frozen raw8/8 pass')
    sys.path.insert(0,str(T))
    from scripts import make_solo_teacher_plan as original
    def candidates(kind):
        rows=[]
        for sid in SCENARIOS:
            value,path=scenario(sid)
            rows.extend((sid,path,value,p) for p in value['eval']['setup']['placements'] if p['kind']==kind)
        return rows
    original.candidates=candidates
    counts=Counter();plans=[]
    for index,seed in enumerate(protocol['final_seeds']):
        kind=KINDS[index%4]
        row=original.episode(counts[kind],kind,seed,'heldout_start');counts[kind]+=1
        row.update(episode_id='act18-v7-'+str(seed),batch='act18-v7-final',pr=575,
            gate_eligible=False,training_eligible=False,negative_probe=False,
            end_color_scene='grasp_act_teal_blue_v1',act17_v7=True)
        plans.append(row)
    out.mkdir(parents=True,exist_ok=False);write(out/'plans.json',dict(episodes=plans))
    def one(index):
        folder=out/f'case-{index:03d}'
        argv=[str(B/'runs/simalt3/c-env/bin/python'),str(ROOT/'scripts/act17_v7.py'),
            '--enabled','--action','launch','--','--enabled','--mode','teacher','--',
            '--physics-backend','c_pilot_v1','--teacher-source',str(T),'--plan',str(out/'plans.json'),
            '--episode',str(index),'--scene-v5-v1','--native-sleep-policy-compat-v1',
            '--export-compiled-only','--vm-hourly-usd','1.096','--out',str(folder)]
        command(argv,out/f'case-{index:03d}.log')
        xml=folder/'world-000/scene.xml'
        return dict(index=index,seed=plans[index]['seed'],scene_xml=str(xml),xml_sha256=sha256(xml),
            actuator=str(folder/'compiled-312.json'),geometry=str(folder/'compiled-geometry312.npz'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        inventory=list(pool.map(one,range(40)))
    write(out/'inventory.json',inventory)
    write(out/'per-world-references.json',{r['xml_sha256']:{k:r[k] for k in ('actuator','geometry')} for r in inventory})
    write(out/'summary.json',dict(complete=True,N=40,scope='compiled setup references only; same legacy setup exporter as v7, no ACT task-success claim',selection=selection))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    for key in ('training','training-source','protocol','out','stack-values'):
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if not a.enabled:
        p.error('ACT18 finite post-training owner default OFF')
    host=require_gcp2(training=True);source=frozen_source(ROOT);protocol=read(a.protocol)
    a.out.mkdir(parents=True,exist_ok=False)
    write(a.out/'RUN_META.json',dict(classification='study',**{'class':'study'},pr=575,branch='codex/act18',sha=source,batch='act18-v7-r1'))
    lease=B/'leases/act18.json';previous=read(lease)
    if previous.get('task')!='act18':raise ValueError('owned lease required')
    queue_pid=live_queue_pid(previous,a.training)
    previous.update(pid=os.getpid(),queue_pid=queue_pid,active='post-training owner',expected_end='finite100k→TRAIN4→gatedVAL8→conditionalFINAL40→package',concurrency=0)
    write(lease,previous)
    report=dict(source_sha=source,host=host,status='waiting_training',complete=False,
        started_utc=datetime.now(timezone.utc).isoformat(),candidates={},packages={},
        protocol_sha256=sha256(a.protocol),selection_rule='R8 preferred only if both raw VAL8 pass8/8',
        FINAL40_submitted=False,wall_cap=None)
    try:
        while True:
            training=read(a.training/'summary.json')
            if training.get('status') in ('HOST_ERROR','SUPERVISOR_STOP'):
                raise RuntimeError('training ended without completed comparison')
            if training.get('complete'):
                break
            try:os.kill(queue_pid,0)
            except ProcessLookupError:raise RuntimeError('training owner disappeared before complete receipt')
            write(a.out/'summary.json',report)
            time.sleep(10)
        report.update(status='TRAIN_fit')
        refs=B/'runs/act17-v7/record-references-r1';gate=B/'runs/act17-v7/gate-r1/gate-recount.json'
        prior=B/'runs/act18/diagnosis-r1/audit/rejection_table.json'
        for name in ('R8','R100'):
            checkpoint=a.training/name/'step-100000';row=dict(checkpoint=str(checkpoint),checkpoint_sha256=sha256(checkpoint/'model.safetensors'))
            report['candidates'][name]=row
            command([sys.executable,str(ROOT/'scripts/act18_open_loop.py'),'--enabled','--stage','train',
                '--dataset',str(B/'runs/act17-v7/dataset-r1'),'--checkpoint',str(checkpoint),
                '--protocol',str(a.protocol),'--out',str(a.out/(name+'-TRAIN-open'))],a.out/(name+'-TRAIN-open.log'))
            def stage(stage,selection=None,references=refs):
                output=a.out/(name+'-'+stage)
                argv=[sys.executable,str(ROOT/'scripts/act18_stage.py'),'--enabled','--stage',stage,
                    '--checkpoint',str(checkpoint),'--references',str(references),'--protocol',str(a.protocol),
                    '--native-gate',str(gate),'--out',str(output),'--stack-values',str(a.stack_values),
                    '--prior-rejections',str(prior)]
                if selection:argv+=['--selection',str(selection)]
                command(argv,a.out/(name+'-'+stage+'.log'))
                return read(output/'summary.json')
            fit=stage('train');row['TRAIN']=fit
            if fit['n']==4 and fit['N']==4:
                selection=a.out/(name+'-TRAIN-selection.json')
                value=dict(TRAIN_n=4,TRAIN_N=4,TRAIN_raw_recount_verified=True,TRAIN_recount=fit['raw_recount'],checkpoint_sha256=row['checkpoint_sha256'])
                write(selection,value)
                val=stage('validation',selection);row['VAL']=val
                row['selection']=dict(**value,VAL_n=val['n'],VAL_N=val['N'],VAL_raw_recount_verified=True,VAL_recount=val['raw_recount'])
            else:
                row['VAL']=dict(status='NOT_SUBMITTED_TRAIN_FIT_FAILED',n=None,N=0)
            write(a.out/'summary.json',report)
        passing=[name for name in ('R8','R100') if report['candidates'][name]['VAL'].get('n')==8 and report['candidates'][name]['VAL'].get('N')==8]
        if passing:
            name=passing[0];row=report['candidates'][name];checkpoint=Path(row['checkpoint'])
            selected=dict(**row['selection'],candidate=name,checkpoint=str(checkpoint),frozen_before_final=True,
                frozen_utc=datetime.now(timezone.utc).isoformat(),completed_candidates=['R8','R100'],selection_rule=report['selection_rule'])
            selection=a.out/'FINAL-selection.json';write(selection,selected)
            refs_final=a.out/'FINAL-references';prepare_final(protocol,selected,refs_final)
            report['FINAL40_submitted']=True;report['winner']=name
            report['FINAL']=stage('final',selection,refs_final)
        for name in ('R8','R100'):
            output=a.out/'packages'/name
            command([sys.executable,str(ROOT/'scripts/package_act18_model.py'),'--enabled',
                '--checkpoint',str(a.training/name/'step-100000'),'--training-summary',str(a.training/name/'summary.json'),
                '--dataset-manifest',str(B/'runs/act17-v7/dataset-r1/manifest.json'),
                '--protocol',str(a.protocol),'--training-source',str(a.training_source),'--out',str(output)],a.out/(name+'-package.log'))
            report['packages'][name]=dict(path=str(output/'registry-entry.pending.json'),sha256=sha256(output/'registry-entry.pending.json'))
        report.update(status='COMPARISON_COMPLETE',complete=True,release_state='PENDING_MAC_UPLOAD_AND_ANONYMOUS_READBACK')
    except BaseException as error:
        report.update(status='HOST_ERROR',error=repr(error),complete=False)
        raise
    finally:
        report['ended_utc']=datetime.now(timezone.utc).isoformat();write(a.out/'summary.json',report)


if __name__=='__main__':
    main()
