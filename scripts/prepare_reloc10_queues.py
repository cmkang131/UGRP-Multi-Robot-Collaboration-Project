"""Prepare disabled reloc10 queues; never connect, submit or promote."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.make_solo_carry_plan import ROOT, queue
from scripts.prepare_reloc8_carry_queue import FLAGS
from scripts.run_reloc10_rotation_check import TARGETS_DEG

PLAN = 'experiments/2026-10-15-reloc10/diagnostic-plan.json'
SELF = Path('/Users/changmin/projects/ugrp-wt/map-selfmap')


def disable(q):
    for obj in [q, q['coordinator_approval'], *q['runs'], *q['execution_stages']]:
        obj.update({key: False for key in FLAGS})
    return q


def carry_queue(sha):
    plan = json.loads((ROOT/PLAN).read_bytes())
    q = queue({**plan, 'schema':'ugrp.solo_carry_plan.v5'}, sha, 505, plan_path=PLAN)
    name = f'solo-carry-rotation-check-{sha[:8]}'
    check = dict(name=name, source_sha=sha, stage='rotation_check', targets_deg=list(TARGETS_DEG),
        command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','505',
            '--per-run-mb','256',str(ROOT),name,'--','.venv-sim/bin/python','-m',
            'scripts.run_reloc10_rotation_check','--plan',PLAN,'--expected-source-sha',sha,
            '--execution-host','gcp1','--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw'],
        depends_on=None, execution_argument_after_approval='--execute')
    for i,(run,e) in enumerate(zip(q['runs'],plan['episodes'])):
        old=run['name']; new=f'solo-carry-{e["seed"]}-{e["reloc10_candidate"]}-{sha[:8]}'
        run.update(name=new,candidate=e['reloc10_candidate'],depends_on=name,
                   stage='reproductions' if i<6 else 'fresh_eight')
        run['command']=[a.replace(old,new) for a in run['command']]
    q['runs'].insert(0,check)
    q.update(schema='ugrp.solo_carry_queue.reloc10',source_sha=sha,max_parallel=16,
        run_count=23,previous_results_combinable=False,automatic_promotion=False,
        runner_cwd=str(ROOT), supersedes_blocked_queue='20261015-solo-carry-05e3e61f.json',
        execution_stages=[dict(name='rotation_check',indices=[0],requires='all four ratios 0.9-1.1 + ledger review'),
            dict(name='reproductions',indices=list(range(1,7)),requires='rotation_check passed + explicit coordinator approval'),
            dict(name='fresh_eight',indices=list(range(7,23)),requires='all reproduction reviews + explicit coordinator approval')],
        seed_reservation=dict(reproduction=[93261,93262,93266],fresh=list(range(93310,93318)),
                              remote_unused_verified=False),
        candidates=plan['candidates'],storage_budget_mib=dict(per_run=256,total=23*256,measured=False))
    q['preconditions']=[
        'Coordinator authorizes exact source SHA and plan hash; all flags false; this script never submits.',
        'gcp1 only, project ugrp-act-train-1014, aggregate active <=40, max_parallel16 is a ceiling, preserve budget-stop/8h STOP/idle20m.',
        'Same layouts/seeds for both candidates. No pooling with reloc9 or other scene/host versions.',
        'Rotation checker is the same module used by reloc10 DEV rounds, 90L/90R/180L/180R independently pass.',
        'Do not infer mission success from a capped DEV run. Review result, command/evaluation ledger, input audit and >=6 own frames.',
        'No TOP capture; own-only review toggle is true in every episode. Truth is evaluator/offline-calibration only.',
        'New seeds must be checked live before submission; reserve all output plus other admitted writes.',
        'New runs remain blocked if the recorded reloc10 registration defect is unresolved; no automatic promotion.']
    return disable(q)


def selfmap_queue(sha, *, texture=False):
    scene='floor_light_textured_v1' if texture else 'floor_light_v1'
    runs=[]
    for i,seed in enumerate([93571,93580,93581,93582,93583]):
        name=f'selfmap8-{seed}-{sha[:8]}'
        args=['.venv-sim/bin/python','-m','scripts.run_self_map_diagnostic',
            '--output',f'/home/ugrp/ugrp-sim/runs/{name}/raw','--expected-source-sha',sha,
            '--seed',str(seed),'--cap-s','60','--execution-host','gcp1','--project','ugrp-act-train-1014',
            '--self-map-executor','frontier_drive_v1','--bootstrap','command_prior_v1',
            '--initial-sweep','required_360_v1','--recovery-profile','selfmap4_recovery_v1',
            '--revision-gate','selfmap4_revision_gate_v2','--multiframe-registration','selfmap4_multiframe_registration_v1',
            '--render-profile',scene,'--correction-safety','selfmap6_correction_safety_v1',
            '--active-relocalization','reloc8_active_vision_v1','--reloc10-settle-v1','--reloc10-registration-v1']
        runs.append(dict(name=name,seed=seed,source_sha=sha,scene_version=scene,cap_sim_s=60,
            depends_on=None if i==0 else runs[0]['name'],stage='reproduction' if i==0 else 'fresh_four',
            execution_argument_after_approval='--execute',
            command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','506',
                '--per-run-mb','256',str(SELF),name,'--',*args]))
    q=dict(schema='ugrp.selfmap8.queue.reloc10',source_sha=sha,sha=sha,pr=506,branch='claude/map-selfmap',
        source_worktree=str(SELF),runner_cwd=str(SELF),host='gcp1',project='ugrp-act-train-1014',
        machine_type='n4-highcpu-64',run_count=5,max_parallel=16,runs=runs,scene_version=scene,
        previous_results_combinable=False,automatic_promotion=False,status='prepared_not_submitted',
        coordinator_approval=dict(source_sha=sha),
        seed_reservation=dict(reproduction=[93571],fresh=[93580,93581,93582,93583],remote_unused_verified=False),
        execution_stages=[dict(name='reproduction',indices=[0],requires='coordinator approval + raw/registration review'),
            dict(name='fresh_four',indices=[1,2,3,4],requires='93571 reviewed + explicit approval')],
        storage_budget_mib=dict(per_run=256,total=1280,measured=False),
        preconditions=[
            'Every approval/execution flag false; no automatic submission or promotion.',
            'gcp1 only; aggregate<=40, max_parallel16 ceiling, no budget-stop/idle20m/8h STOP bypass.',
            'Keep smooth and texture and all older cohorts separate; verify raw/result and native own RGB hashes.',
            'Registration0 is a blocker, not successful localization; do not weaken confidence/ambiguity guards to pass.',
            'Check live unused seeds and storage admission before submission; no TOP or truth control inputs.'])
    return disable(q)


def main():
    p=argparse.ArgumentParser();p.add_argument('--carry-sha',required=True);p.add_argument('--selfmap-sha',required=True)
    p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--texture',action='store_true');a=p.parse_args()
    a.out_dir.mkdir(parents=True,exist_ok=True)
    for name,value in [(f'20261015-solo-carry-{a.carry_sha[:8]}.json',carry_queue(a.carry_sha)),
                       (f'20261015-selfmap8-{a.selfmap_sha[:8]}.json',selfmap_queue(a.selfmap_sha,texture=a.texture))]:
        path=a.out_dir/name
        with path.open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False);f.write('\n')
        print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())))


if __name__=='__main__':main()
