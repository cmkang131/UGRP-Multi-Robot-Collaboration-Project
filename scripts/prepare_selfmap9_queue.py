"""Disabled texture-primary queue only; no execution, network or promotion."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FLAGS=('approved','enabled','ready','stage_ready','execute','submitted')


def make_queue(sha, *, registered, measured_runs, half_rate=True, low_contrast=True, wall_field=False):
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('full source SHA required')
    runs=[]
    for seed in (93571,93590,93591,93592,93593):
        name=f'selfmap9-texture-{seed}-{sha[:8]}'
        args=['.venv-sim/bin/python','-m','scripts.run_self_map_diagnostic','--output',f'/home/ugrp/ugrp-sim/runs/{name}/raw','--expected-source-sha',sha,'--seed',str(seed),'--cap-s','90',
              '--execution-host','gcp1','--project','ugrp-act-train-1014','--self-map-executor','frontier_drive_v1','--bootstrap','command_prior_v1','--initial-sweep','required_360_v1',
              '--recovery-profile','selfmap4_recovery_v1','--revision-gate','selfmap4_revision_gate_v2','--multiframe-registration','selfmap4_multiframe_registration_v1',
              '--render-profile','floor_light_textured_v1','--correction-safety','selfmap6_correction_safety_v1','--active-relocalization','reloc8_active_vision_v1',
              '--reloc10-settle-v1','--reloc10-registration-v1','--reloc11-timing-v1']
        for flag,on in [('--reloc11-half-rate-v1',half_rate),('--reloc11-low-contrast-v1',low_contrast),('--reloc11-wall-field-v1',wall_field)]:
            if on:args.append(flag)
        runs.append(dict(name=name,seed=seed,source_sha=sha,scene_version='floor_light_textured_v1',cap_sim_s=90,depends_on=runs[0]['name'] if runs else None,
                         stage='reproduction' if not runs else 'fresh_four',execution_argument_after_approval='--execute',
                         command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','506','--per-run-mb','256',str(ROOT),name,'--',*args]))
    q=dict(schema='ugrp.selfmap9.queue.reloc11',source_sha=sha,sha=sha,pr=506,branch='claude/map-selfmap',source_worktree=str(ROOT),runner_cwd=str(ROOT),
           host='gcp1',project='ugrp-act-train-1014',machine_type='n4-highcpu-64',max_parallel=16,run_count=len(runs),runs=runs,
           scene_version='floor_light_textured_v1',previous_results_combinable=False,automatic_promotion=False,
           status='BLOCKED' if not registered else 'prepared_not_submitted',blocker='NO_STATIC_REGISTRATION_IN_DIRECT_GCP_CHECK' if not registered else None,
           direct_check=dict(registered_frames=registered,measured_runs=measured_runs,research_success=False),
           coordinator_approval=dict(source_sha=sha),
           execution_stages=[dict(name='reproduction',indices=[0]),dict(name='fresh_four',indices=[1,2,3,4],requires='93571 original review and explicit approval')],
           seed_reservation=dict(reproduction=[93571],fresh=[93590,93591,93592,93593],remote_unused_verified=False),
           smooth_reference=dict(run='reloc11-r1-smooth-93571-4d3335c8',repeat=False,only_one=True),
           storage_budget_mib=dict(per_run=256,total=1280,measured=False),
           preconditions=['All execution/approval flags false; no automatic submission or promotion.',
                          'gcp1 only, project ugrp-act-train-1014, aggregate <=40; preserve budget-stop, 8h STOP and idle20m.',
                          'Check live seed reservations/storage and current budget before any authorized submission.',
                          'Texture is the primary condition; smooth93571 already measured once, never repeat or pool it.',
                          '5Hz and10Hz, model/source/machine/scene conditions remain separate. Retain all sampled own RGB and ledgers.',
                          'Require input audit0/0, TOP capture0, raw/hash verification and >=6 own frames per failure.',
                          'Registration0 is BLOCKED; covariance, ambiguity and independent-view gates cannot be weakened.'])
    for obj in [q,q['coordinator_approval'],*runs,*q['execution_stages']]:obj.update({k:False for k in FLAGS})
    return q


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-sha',required=True);p.add_argument('--registered',type=int,required=True);p.add_argument('--measured-runs',type=int,required=True)
    p.add_argument('--wall-field',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=make_queue(a.source_sha,registered=a.registered,measured_runs=a.measured_runs,wall_field=a.wall_field)
    with a.output.open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False);f.write('\n')
    print(json.dumps(dict(path=str(a.output),sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),status=value['status'])))


if __name__=='__main__':main()
