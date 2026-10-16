"""Finite native A/B -> h4 -> h5 -> frozen final40 orchestration on owned L4.

Existing A/B jobs are observed, never resubmitted. Actual playback review is
required at each validation boundary. No automatic retry, VM lifecycle command,
credentials, manual grasp controller or wall deadline is provided here.
"""
import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from act16w_runtime import require_gcp2, frozen_source, sha256

ROOT = Path(__file__).resolve().parents[1]
B = Path('/home/ugrp/ugrp-sim')
CODE = B/'src/c27a9d537eaae873c7e7bc2ceaeeada69696cc48'
Q = B/'src/f0db6b1abb842ea65b71c433738210254f300a7c'
ACT = B/'src/3f99d58c5ada0862e669ef4065c0ba957f1b4547'
PY = B.parent/'ugrp-rl1b-act-env/bin/python'
WARP = B/'runs/simalt3/warp-env/bin/python'
GATE = B/'runs/act16w-native-gate-r2/independent-gate-recount.json'
REFS = B/'runs/act16w-native-record-references-r1'
RECORDS = B/'runs/act16w-native-record-r1'
DATA = B/'runs/act16w-native-dataset-r1/records'
TRAIN = B/'runs/act16w-native-training-r1'
PROTOCOL = CODE/'experiments/2026-10-16-act16w/resume3/protocol.json'
CAPACITY = B/'runs/act16w-native-capacity.json'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2)+'\n'); tmp.replace(path)


def select_arm(metrics, arms):
    """Registered validation success, alignment rejection, then A-first tie."""
    for arm in arms:
        row = metrics[arm]
        if row['N'] != 8 or not row['complete'] or not 0 <= row['n'] <= 8:
            raise ValueError('completed registered validation8 required for selection')
        if not 0 <= row['alignment_rejections'] <= 8:
            raise ValueError('complete alignment denominator required')
    return max(arms, key=lambda a: (metrics[a]['n'], -metrics[a]['alignment_rejections'],
                                   -('A','B','C','D1').index(a)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if not a.enabled:
        p.error('explicit finite native experiment required')
    host, source = require_gcp2(training=True), frozen_source(ROOT)
    frozen_source(CODE, 'c27a9d537eaae873c7e7bc2ceaeeada69696cc48')
    if not read(GATE)['passed'] or not read(DATA/'dataset-audit.json')['passed']:
        raise ValueError('native gate and complete recording audit required')
    a.out.mkdir(parents=True, exist_ok=False)
    lease = B/'leases/act16w-native-experiment.json'
    report = dict(status='WAIT_EXISTING_A_B', complete=False, source_sha=source,
        execution_source_sha=CODE.name, host=host, wall_cap=None,
        started_utc=datetime.now(timezone.utc).isoformat(), final40_accessed=False,
        model_tag='models-20261016-act16w-native-v1', metrics={}, packages={})
    with lease.open('x') as f:
        json.dump(dict(task='act16w-native-experiment',pid=os.getpid(),start=report['started_utc'],
            expected_end='fixed A/B,C,D1 and final40; review boundaries; no wall cap',concurrency=0),f)
    stop, children = {'requested': False}, []
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.update(requested=True))
    def publish(status=None):
        if status:
            report['status'] = status
        report['updated_utc'] = datetime.now(timezone.utc).isoformat()
        write(a.out/'summary.json', report)
    def tick():
        if stop['requested']:
            raise InterruptedError('supervisor stop')
        write(CAPACITY, dict(project_id='ugrp-sim-b-1014', foreign_cpu_worlds=0,
            scope='owned L4 only; CPU VM is neither inspected nor started',
            valid_until_utc=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat()))
        publish(); time.sleep(5)
    def launch(name, arguments, *, python=PY, env=None):
        if stop['requested']:
            raise InterruptedError('supervisor stop before '+name)
        argv = [str(python), '-u', *map(str,arguments)]
        log = (a.out/(name+'.log')).open('x')
        proc = subprocess.Popen(argv,cwd=Q,stdout=log,stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,start_new_session=True,env={**os.environ,
                'PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1',
                'LP_NUM_THREADS':'1','MUJOCO_GL':'osmesa',**(env or {})})
        job = dict(name=name,proc=proc,log=log);children.append(job)
        write(a.out/(name+'-launch.json'),dict(pid=proc.pid,argv=argv,source_sha=source))
        return job
    def wait(jobs):
        while any(j['proc'].poll() is None for j in jobs):
            report['children']=[dict(name=j['name'],pid=j['proc'].pid) for j in jobs if j['proc'].poll() is None]
            tick()
        for j in jobs:
            j['log'].close()
            if j['proc'].returncode:
                raise RuntimeError(j['name']+' failed; inspect preserved log before any retry')
    def train(arm, history, dataset, curriculum):
        publish('TRAIN_'+arm)
        wait([launch('train-'+arm,[CODE/'scripts/act16w_native_learning.py','--enabled','--stage','train',
            '--native-gate',GATE,'--out',TRAIN/arm,'--references',REFS,'--dataset-root',dataset,
            '--arm',arm,'--history',history,'--curriculum-starts',curriculum])])
    def checkpoint(arm):
        value=read(TRAIN/arm/'main/summary.json')
        if not value['complete'] or not value['readback_verified'] or value['steps_completed']!=10000:
            raise ValueError('completed fixed10000 model required '+arm)
        return Path(value['last_checkpoint'])/'actor'
    def validate(arms, datasets):
        publish('VALIDATE_'+'_'.join(arms));jobs=[]
        native={'UGRP_ACT16W_NATIVE_GATE':str(GATE)}
        for arm in arms:
            jobs.append(launch('validate-'+arm,[CODE/'scripts/act16w_native_learning.py','--enabled',
                '--stage','validate','--native-gate',GATE,'--out',a.out/('validation-'+arm),
                '--references',REFS,'--records',RECORDS,'--dataset-root',datasets[arm],
                '--checkpoint',checkpoint(arm),'--capacity',CAPACITY,'--arm',arm],env=native))
        wait(jobs)
        for arm in arms:
            folder=a.out/('validation-'+arm)/'validation';value=read(folder/'summary.json')
            rejects=0;receipts=[]
            for group in sorted(folder.glob('group-*')):
                evaluation=group/'evaluation';plans=read(group/'plans.json')['episodes']
                for i,plan in enumerate(plans):
                    out=a.out/f'alignment-{arm}-{plan["seed"]}.json'
                    wait([launch(f'alignment-{arm}-{plan["seed"]}',[
                        CODE/'scripts/audit_act16w_alignment.py','--enabled',
                        '--world-root',evaluation/'owner'/f'world-{i:03d}',
                        '--actions',evaluation/'actor-actions.jsonl','--action-format','student',
                        '--world-index',str(i),'--out',out],python=WARP)])
                    diagnostic=read(out);rejects+=diagnostic['alignment_rejection']
                    receipts.append(dict(path=str(out),sha256=sha256(out)))
            if len(receipts)!=8:
                raise ValueError('all8 saved-state alignment audits required')
            report['metrics'][arm]=dict(n=value['n'],N=value['N'],complete=value['complete'],
                alignment_rejections=rejects,alignment_receipts=receipts,
                checkpoint=str(checkpoint(arm)),validation=dict(path=str(folder/'summary.json'),
                sha256=sha256(folder/'summary.json')))
        publish()
    def review(label, arms):
        receipts={arm:report['metrics'][arm]['validation']['sha256'] for arm in arms}
        write(a.out/('review-'+label+'-request.json'),dict(arms=arms,validation_sha256=receipts,
            rule='inspect full2Hz + final10SIMs10Hz playback before acknowledging; no final outcomes available'))
        publish('WAIT_REVIEW_'+label);path=a.out/('review-'+label+'.json')
        while not path.exists():
            tick()
        ack=read(path)
        if ack.get('approved') is not True or ack.get('validation_sha256')!=receipts or not ack.get('playback_receipts'):
            raise ValueError('actual playback review must match validation evidence '+label)
        if any(not row.get('path') or sha256(row['path'])!=row.get('sha256') for row in ack['playback_receipts']):
            raise ValueError('playback review evidence changed '+label)
        report.setdefault('reviews',{})[label]=dict(path=str(path),sha256=sha256(path))
    def package(arm,dataset):
        out=a.out/('model-'+arm)
        wait([launch('package-'+arm,[CODE/'scripts/package_act16w.py','--enabled','--arm',arm,
            '--checkpoint',checkpoint(arm),'--training-summary',TRAIN/arm/'main/summary.json',
            '--dataset-manifest',dataset/'dataset/manifest.json','--protocol',PROTOCOL,
            '--tag',report['model_tag'],'--out',out])])
        report['packages'][arm]=dict(path=str(out/'package-summary.json'),sha256=sha256(out/'package-summary.json'),
            state='staged_not_uploaded');publish()
    try:
        original=read(TRAIN/'launch-A-B.json')
        while not all(read(TRAIN/arm/'summary.json')['complete'] for arm in ('A','B')):
            for arm in ('A','B'):
                s=read(TRAIN/arm/'summary.json')
                if s['status']!='running' and not s['complete']:
                    raise ValueError('existing A/B failed; never resubmit '+arm)
                pid=next(row['pid'] for row in original if row['arm']==arm)
                cmd=Path(f'/proc/{pid}/cmdline')
                if s['status']=='running' and (not cmd.exists() or str(TRAIN/arm).encode() not in cmd.read_bytes()):
                    raise ValueError('existing A/B disappeared; inspect original before retry '+arm)
            tick()
        for arm in ('A','B'):
            checkpoint(arm);package(arm,DATA)
        validate(['A','B'],{'A':DATA,'B':DATA});review('A_B',['A','B'])
        selected=select_arm(report['metrics'],['A','B'])
        history=read(TRAIN/selected/'main/summary.json')['history_causal_split_v1']
        report['history_selected_from']=selected
        curriculum=TRAIN/selected/'admission/curriculum-starts.json'
        train('C',history,DATA,curriculum);package('C',DATA)
        validate(['C'],{'C':DATA});review('C',['C'])
        starts=TRAIN/'C/admission/dagger-starts.json'
        if set(read(starts)['seeds'])!=set(read(PROTOCOL)['dagger_train_seeds']):
            raise ValueError('registered20 native TRAIN DAgger starts changed')
        collection=a.out/'dagger-collection';publish('DAGGER_TRAIN_PREFIXES')
        wait([launch('dagger-collect',[CODE/'scripts/act16w_dagger_batch.py','--enabled',
            '--checkpoint',checkpoint('C'),'--starts',starts,'--references-root',REFS,
            '--groups',RECORDS/'exact-groups/model-groups.json','--capacity-receipt',CAPACITY,
            '--out',collection,'--max-worlds','20','--native-protocol',PROTOCOL],
            env={'UGRP_ACT16W_NATIVE_GATE':str(GATE)})])
        derived=a.out/'dagger-dataset';publish('DAGGER_DATA_AUDIT')
        wait([launch('dagger-dataset',[CODE/'scripts/act16w_dagger_dataset.py','--enabled',
            '--base-root',DATA,'--starts',starts,'--act-source',ACT,'--out',derived,
            '--collections',*read(collection/'summary.json')['collections']])])
        train('D1',history,derived,curriculum);package('D1',derived)
        validate(['D1'],{'D1':derived});review('D1',['D1'])
        selected=select_arm(report['metrics'],['A','B','C','D1']);model=checkpoint(selected)
        selection=dict(approved=True,frozen_before_final=True,validation_complete=True,
            contact_profile='warp_native_contact_v1',checkpoint_sha256=sha256(model/'model.safetensors'),
            arm=selected,completed_comparisons=dict(A_B=True,h4=True,h5=True),metrics=report['metrics'],
            frozen_utc=datetime.now(timezone.utc).isoformat(),rule=read(PROTOCOL)['selection_rule'],
            final_outcomes_seen=False,reviews=report['reviews'])
        frozen=a.out/'final-selection.json';write(frozen,selection)
        report['selected_arm']=selected;report['final40_accessed']=True;publish('FINAL40_REFERENCE_SETUP')
        refs=a.out/'final40-references';groups=a.out/'final40-groups'
        wait([launch('prepare-final',[CODE/'scripts/act16w_native_prepare.py','--enabled','--split','final',
            '--selection',frozen,'--out',refs],python=WARP)])
        wait([launch('group-final',[CODE/'scripts/act16w_native_groups.py','--enabled','--references',refs,
            '--out',groups],python=WARP)])
        publish('FINAL40')
        wait([launch('final40',[CODE/'scripts/act16w_eval_batch.py','--enabled','--checkpoint',model,
            '--references-root',refs,'--groups',groups/'model-groups.json','--protocol',PROTOCOL,
            '--capacity-receipt',CAPACITY,'--out',a.out/'final40','--split','final','--selection',frozen,
            '--name','native-final40','--max-worlds','40','--speed-gate-override',
            'User-required native MJWarp cohort; actual per-world latency recorded; no wall cap or speed-pass claim.'],
            env={'UGRP_ACT16W_NATIVE_GATE':str(GATE)})])
        result=read(a.out/'final40/summary.json')
        report.update(status='FINAL40_COMPLETE_REQUIRES_DELIVERY' if result['complete'] else 'FINAL40_INCOMPLETE',
            complete=result['complete'],n=result['n'],N=result['N'],model_upload_verified=False,
            remaining='final raw recount/playback, model public upload/hash/loading verification, curves/report and safe owned-VM stop')
    except BaseException as error:
        report.update(status='SUPERVISOR_STOP' if isinstance(error,InterruptedError) else 'HOST_ERROR',
                      complete=False,error=repr(error))
        raise
    finally:
        for job in children:
            if job['proc'].poll() is None:
                os.killpg(job['proc'].pid,signal.SIGINT)
                try:job['proc'].wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(job['proc'].pid,signal.SIGTERM);job['proc'].wait()
            if not job['log'].closed:job['log'].close()
        report['ended_utc']=datetime.now(timezone.utc).isoformat();publish()
        if read(lease).get('pid')==os.getpid():lease.unlink()


if __name__=='__main__':
    main()
