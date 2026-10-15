"""Prepare paired, entirely disabled ACT11 gates; static plans only."""
import argparse
from collections import Counter
from copy import deepcopy
import json
import math
from pathlib import Path

from harness.grasp_act_data import sha256, write_json
from scripts.grasp_act_training_guard import ROOT, source_sha
from scripts.queue_grasp_act_act10 import build_queue as act10_queue
from scripts.queue_grasp_act_act9 import RECORD, seed_inventory
from scripts.run_grasp_act_recovery import dependency_modules, CALIBRATION_MODE

SEEDS=list(range(8317100,8317140))


def start_bearing(e):
    x,y,_,yaw=e['spawns'][e['robot_id']];cx,cy=e['cargo_pose_m'][:2]
    angle=math.atan2(cy-y,cx-x)-yaw
    return math.degrees(math.atan2(math.sin(angle),math.cos(angle)))


def prepare(dependency_root, queue_dir, evidence):
    inventory=seed_inventory(queue_dir,proposed_seeds=SEEDS,exclude_tag='act11')
    counts=Counter();episodes=[]
    with dependency_modules(dependency_root):
        from scripts.make_solo_teacher_plan import episode
        for i,seed in enumerate(SEEDS):
            kind=('cyan','red','green','yellow')[i%4]
            e=episode(counts[kind],kind,seed,'act11_gate');counts[kind]+=1
            e.update(pr=504,negative_probe=False,gate_eligible=True,training_eligible=False)
            e['start_bearing_deg_setup_only']=start_bearing(e)
            episodes.append(e)
    # Keep the generated poses intact; reorder one large-bearing seed into the
    # first two review runs. Both candidates use this identical order and plan.
    large=next(i for i,e in enumerate(episodes) if abs(start_bearing(e))>20.)
    episodes[1],episodes[large]=episodes[large],episodes[1]
    report=json.loads(Path(evidence).read_text())
    calibration=report['calibration']
    if calibration['fit_cohort']!='act8' or calibration['validation_cohorts']!=['act9','act10']:
        raise ValueError('separate calibration/validation cohorts required')
    write_json(ROOT/RECORD/'act11-gate-plan.json',{'episodes':episodes,'kinds':dict(counts),
        'approved':False,'ready':False,'seed_inventory_verified':False,
        'scope':'static setup only; starting bearing excluded from teacher input; remote non-use unverified'})
    noise=json.loads((ROOT/RECORD/'act10-noise.json').read_text())
    noise.update(rotation_calibration=calibration,
        scope='ACT11 paired search gates; optional frozen ACT8 yaw gain; no online truth')
    write_json(ROOT/RECORD/'act11-noise.json',noise)
    write_json(ROOT/RECORD/'act11-offline.json',report)
    write_json(ROOT/RECORD/'act11-seed-inventory.json',inventory)


def build_queue(source):
    q=deepcopy(act10_queue(source));short=source[:8]
    q.update(schema='ugrp.vm3_queue.act11.v1',record=f'{RECORD}/act11.md',
        scope='paired fresh teacher gates only; rotation calibration off/on; no recording or training')
    for key,name in [('gate_plan','act11-gate-plan.json'),('noise','act11-noise.json'),
                     ('evidence','act11-offline.json'),('seed_inventory','act11-seed-inventory.json')]:
        q[key]={'path':f'{RECORD}/{name}','sha256':sha256(ROOT/RECORD/name)}
    inventory=json.loads((ROOT/RECORD/'act11-seed-inventory.json').read_text())
    if inventory['proposed_seeds']!=SEEDS or inventory['overlap']:raise ValueError('invalid fresh seed inventory')
    plan=json.loads((ROOT/q['gate_plan']['path']).read_text())
    seeds=[e['seed'] for e in plan['episodes']]
    if set(seeds)!=set(SEEDS) or len(seeds)!=40 or not any(abs(start_bearing(e))>20 for e in plan['episodes'][:2]):
        raise ValueError('fresh40 / early large-bearing requirement')
    gain=json.loads((ROOT/q['noise']['path']).read_text())['rotation_calibration']['yaw_gain']
    template=q['jobs'][0];q['jobs']=[]
    for candidate,toggle,factor in [('rotation-off','off',1.),('rotation-on',CALIBRATION_MODE,gain)]:
        job=deepcopy(template)
        job.update(stage=f'act11-{candidate}-gate40',candidate_id=candidate,
            rotation_calibration=toggle,yaw_gain=factor,approved=False,
            first_two_seeds=seeds[:2],first30_review_before_fill=True)
        for i,(run,seed) in enumerate(zip(job['runs'],seeds)):
            old=run['name'];name=f'act11-{candidate}-gate-{seed}-{short}'
            command=[s.replace(old,name) for s in run['command']]
            for flag,value in [('--episode',str(i)),('--plan',q['gate_plan']['path']),('--noise',q['noise']['path'])]:
                command[command.index(flag)+1]=value
            command+=['--rotation-calibration',toggle]
            run.update(name=name,seed=seed,command=command,approved=False,
                rotation_calibration=toggle,yaw_gain=factor,training_rgb=False)
        q['jobs'].append(job)
    q['seed_reuse'].update(seeds=seeds,paired_candidates=True,
        scope='same fresh40 for both candidates; disjoint from act8/9/10; never pool candidates')
    q['prior_queues_untouched']=[e for e in inventory['files'] if 'vm3-queue' in e['path']]
    q['required_before_start']=[s.replace('ACT10','ACT11') for s in q['required_before_start']
        if not s.startswith('Restart all 40')]
    q['required_before_start'] += [
        'Run both candidates on the same ordered fresh40. Each independently needs >=38/40 and >=20 successful recovery-scene runs; no pooling.',
        'Review the first two of EACH candidate, including one abs(start bearing)>20deg. Check initial unseen gaze and repeated SIGINT terminal audit.',
        'Frozen yaw gain fitted on ACT8 only; ACT9/10 are offline validation. Select candidate_id in any gate receipt; calibration must match.',
        'No remote access was made preparing this queue; all approval/execution/promotion flags stay false.']
    return q


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    p.add_argument('--dependency-root',type=Path);p.add_argument('--evidence',type=Path)
    a=p.parse_args()
    if a.prepare:
        if a.dependency_root is None or a.evidence is None:p.error('--prepare requires dependency/evidence')
        prepare(a.dependency_root,a.output_dir,a.evidence);return
    source=source_sha();q=build_queue(source)
    inventory=json.loads((ROOT/RECORD/'act11-seed-inventory.json').read_text())
    for item in inventory['files']:
        if sha256(item['path'])!=item['sha256']:raise ValueError('prior queue/plan changed')
    a.output_dir.mkdir(parents=True,exist_ok=True)
    path=a.output_dir/f'20261015-act11-{source[:8]}.json'
    with path.open('x') as f:f.write(json.dumps(q,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'path':str(path),'sha256':sha256(path),'source_sha':source,'approved':False}))


if __name__=='__main__':main()
