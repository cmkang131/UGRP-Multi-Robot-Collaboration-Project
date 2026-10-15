"""Actual noisy-teacher evidence is mandatory even for the first RGB recording."""
import json
from pathlib import Path
from harness.grasp_act_data import read_json, sha256
from harness.grasp_act_dart import MODE, PULSE_MODE
from harness.grasp_act_perturb import PERTURB_MODES, verified_recovery_audit


def verify_gate(receipt, *, source, dependency, noise_hash, host, recording_seeds, recovery_mode=None):
    receipt=Path(receipt); proof=json.loads(receipt.read_text())
    if proof.get('approved') is not True or proof.get('gate_promotion_authorized_if_all_conditions_pass') is not False:
        raise ValueError('explicit gate review required; no automatic promotion')
    expected={'source_sha':source,'teacher_dependency_sha':dependency,'noise_sha256':noise_hash}
    if any(proof.get(k)!=v for k,v in expected.items()):raise ValueError('gate source/noise mismatch')
    binding = proof.get('queue', {})
    if not binding.get('path') or not binding.get('sha256'):
        raise ValueError('hash-bound gate queue required')
    queue_path = Path(binding['path'])
    queue_path = queue_path if queue_path.is_absolute() else receipt.parent/queue_path
    if sha256(queue_path) != binding['sha256']:
        raise ValueError('gate queue hash mismatch')
    queue = read_json(queue_path)
    gate_jobs = [j for j in queue.get('jobs', []) if j.get('N') == 40 and j.get('training_rgb') is False]
    if queue.get('source_sha') != source or len(gate_jobs) != 1:
        raise ValueError('gate queue source/stage mismatch')
    queue_seeds = [r['seed'] for r in gate_jobs[0]['runs']]
    if len(queue_seeds) != 40 or len(set(queue_seeds)) != 40:
        raise ValueError('exactly 40 unique queue seeds required')
    rows=proof.get('runs',[]);seeds=set();paths=set();success=0;recovered=0;mode=recovery_mode
    if len(rows)!=40:raise ValueError('exactly 40 fresh noisy teacher gate results required')
    for item in rows:
        p=Path(item['path']);p=p if p.is_absolute() else receipt.parent/p
        if str(p.resolve()) in paths or sha256(p)!=item['sha256']:raise ValueError('duplicate or corrupt gate result')
        paths.add(str(p.resolve()));r=read_json(p);seed=r['recovery']['seed']
        actual_mode=r.get('recovery',{}).get('mode')
        if mode is None:mode=actual_mode
        if actual_mode not in (MODE,PULSE_MODE,*PERTURB_MODES) or actual_mode!=mode:
            raise ValueError('unsupported or mixed recovery gate modes')
        if seed in seeds or seed in recording_seeds:raise ValueError('gate/recording seed overlap')
        seeds.add(seed)
        if (r.get('status')!='complete' or r.get('training_rgb') is not False
                or r.get('recording_mode')!='success_measurement' or r.get('weld')!='off'
                or r.get('student_execution') is not False or r.get('execution_host')!=host
                or r.get('gate_eligible') is not True
                or any(r.get(k)!=v for k,v in expected.items())
                or r.get('input_audit',{}).get('held_world_reads')!=0
                or r.get('input_audit',{}).get('invisible_measurements')!=0
                or r.get('teacher',{}).get('held_object_hidden_v1') is not True
                or r.get('solo_truth_free_lookaround_v1') is not True):
            raise ValueError('unqualified gate result / boundary / host')
        success+=r.get('physical_success') is True
        if mode in PERTURB_MODES:
            audit=verified_recovery_audit(r,p)
            recovered+=bool(r.get('physical_success') is True and audit['recovery_scene_N']>=1)
    if success<38:raise ValueError('noisy teacher did not pass 38/40')
    if mode in PERTURB_MODES and recovered<20:
        raise ValueError('recovery scenes required in at least 20/40 successful runs')
    if (sorted(seeds)!=sorted(proof.get('fresh_seeds',[])) or sorted(seeds)!=sorted(queue_seeds)
            or not proof.get('seed_inventory_sha256')):
        raise ValueError('fresh gate inventory receipt required')
    return {'path':str(receipt),'sha256':sha256(receipt),'n':success,'N':40,'seeds':sorted(seeds),
            'queue_sha256':binding['sha256'],
            **({'recovery_runs':recovered,'mode':mode} if mode in PERTURB_MODES else {})}
