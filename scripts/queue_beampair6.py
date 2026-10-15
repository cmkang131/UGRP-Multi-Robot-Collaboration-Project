"""Prepare a disjoint, unapproved v2 gate40 after exact-source short6 success."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.queue_beampair2 import build as previous,ROOT
from scripts.queue_beampair1 import sha

PLAN='experiments/2026-10-16-beampair6/gate-plan.json'
SHORT='experiments/2026-10-16-beampair6/short6-plan.json'


def frozen(source,path):
    return subprocess.check_output(['git','show',source+':'+path],cwd=ROOT)


def build(source,evidence,table):
    report=json.loads(evidence.read_text());short=json.loads(frozen(source,SHORT))['episodes']
    wanted=[e['seed'] for e in short]
    if (report.get('N')!=6 or report.get('n')!=6 or report.get('cap_end_N')
            or [r['seed'] for r in report['runs']]!=wanted
            or any(r.get('adapter_sha')!=source or not r.get('strict_success') for r in report['runs'])):
        raise ValueError('all six exact-source v2 sentinel and regression successes required')
    q=previous(source,evidence,table,expected_bursts=[e['burst_ticks'] for e in short])
    data=frozen(source,PLAN);plan=json.loads(data);episodes=plan['episodes']
    if (len(episodes)!=40 or len({e['seed'] for e in episodes})!=40
            or plan['setup_validity']!='beampair_gate_valid_v2'
            or any(not e['placement_validity']['accepted'] for e in episodes)):
        raise ValueError('complete distinct certified v2 gate required')
    template=deepcopy(q['runs'][0]);runs=[]
    for i,e in enumerate(episodes):
        name=f'beampair6-gate-{e["seed"]}-{source[:8]}'
        command=deepcopy(template['command'])
        old=template['name'];command=[v.replace(old,name) for v in command]
        command[1]='/Users/changmin/projects/ugrp-wt/gcp-sim-host/scripts/remote_run.py'
        for flag,value in [('--host','gcp2'),('--per-run-mb','256'),('--plan',PLAN),('--episode',str(i)),('--rendezvous','peer_rendezvous_v2')]:
            command[command.index(flag)+1]=value
        command+=['--approach-repair','beampair_approach_v2','--wall-layer','beampair_wall_clear_v1','--failure-tail']
        runs.append(dict(name=name,seed=e['seed'],episode=i,source_sha=source,command=command,
                         training_rgb=False,approved=False,submitted=False,burst_ticks=e['burst_ticks'],roles=e['roles']))
    runs.sort(key=lambda r:(r['seed']!=wanted[0],r['episode']))
    for path in (PLAN,SHORT,'scripts/prepare_beampair6.py','scripts/prepare_beampair1.py',
                 'harness/beampair_approach.py','harness/beampair_host.py','harness/failure_rgb_tail.py',
                 'harness/beampair_wall_layer.py','harness/beampair_visible_rays.py',
                 'experiments/2026-10-16-beampair6/placement-validity.json'):
        q['source_hashes'][path]=hashlib.sha256(frozen(source,path)).hexdigest()
    setup=table.parent/'setup-funnel.json'
    if not setup.is_file() or setup.read_bytes()!=frozen(source,'experiments/2026-10-16-beampair6/setup-funnel.json'):
        raise ValueError('exact-source setup funnel required')
    q.update(schema='ugrp.beampair6.gate40_queue.v1',owner='beampair6',runs=runs,
        status='HOLD_SCENE',ready=False,approved=False,submitted=False,scene_approved=False,
        host='gcp2',project_id='ugrp-sim-b-1014',account='changmin5781@gmail.com',max_parallel=16,
        setup_validity='beampair_gate_valid_v2',k=plan['k'],setup_plan=PLAN,setup_plan_sha256=hashlib.sha256(data).hexdigest(),
        setup_funnel=str(setup),setup_funnel_sha256=sha(setup),first_two_seeds=[r['seed'] for r in runs[:2]],
        peer_rendezvous='peer_rendezvous_v2',approach_repair='beampair_approach_v2',wall_layer='beampair_wall_clear_v1',
        failure_tail_recording=True,held_object_hidden_v1=True,training_rgb=False,
        scene_profile='beampair3 cargo_v7 / grasp_act_teal_blue_v1 / floor_light_v1; setup generator v2',
        queue_builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        cohort_scope='Fresh v2 setups40; no v1 gate, short6, earlier teachers or gcp1 pooled',
        required_before_start=[
            'HOLD_SCENE: scene approval by coordinator required; ready/approved/submitted remain false.',
            'Clean exact-source coordinator pin, absolute rejection_table and all input/source hashes required.',
            'Measure all40 from zero. Training off, held hidden on, weld off, recording-only failure tail on.',
            'Max16 here and global40; retain leases, credit-stop, idle20min, VM/command runtime bounds.',
            'VM had24h scheduling at short6 admission; coordinator must resolve/check required8h VM cap before gate.',
            'At planned16 load inspect first30 timing, own RGB, issued commands and GO/ACK before filling.',
            'Stop owned same-defect siblings; preserve failures/HOST_ERROR and classify cap_end separately.'])
    return q


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True)
    p.add_argument('--evidence',type=Path,required=True);p.add_argument('--rejection-table',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    q=build(a.source,a.evidence.resolve(),a.rejection_table.resolve())
    with a.output.open('x') as f:f.write(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:q[k] for k in ('status','ready','approved','submitted','first_two_seeds','rejection_table')}))
