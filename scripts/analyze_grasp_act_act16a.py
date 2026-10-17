"""ACT16a: GCP2 CPU diagnosis only. No optimizer or policy correction.

Legacy runners retain their frozen gcp1 enum. This adapter replaces ONLY their
identity callback after checking the real GCP2 metadata. It never contacts GCP1.
All shadow labels and overview images are evaluation outputs with no return
path to the student. Post-hoc masking is an OOD sensitivity test, not an ablation.
"""
import argparse
import base64
from collections import Counter, defaultdict
from copy import deepcopy
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import urllib.request

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_data import read_json, read_rows, sha256, write_json

ROOT = Path(__file__).resolve().parents[1]
GCP2 = ('ugrp-sim-b-1014', 'ugrp-sim-gcp2', 'n4-highcpu-64')


def validate_cpu_identity(project, instance, machine, zone):
    if (project, instance, machine) != GCP2:
        raise ValueError('ACT16a requires GCP2 CPU; GCP1 and GPUs are forbidden')
    return dict(project=project, instance=instance, machine_type=machine, zone=zone)


def require_cpu():
    if platform.system() != 'Linux':
        raise RuntimeError('Mac analysis execution/physics/render forbidden')
    def meta(key):
        req = urllib.request.Request('http://169.254.169.254/computeMetadata/v1/'+key,
                                     headers={'Metadata-Flavor': 'Google'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=3) as r:
            return r.read().decode().strip().split('/')[-1]
    return validate_cpu_identity(*(meta(k) for k in
        ('project/project-id', 'instance/name', 'instance/machine-type', 'instance/zone')))


def existing(path):
    return path if path.exists() else path.with_suffix(path.suffix+'.zst')


def mask_wheel_pulse_history(state):
    """Zero normalized wheel/pulse slots = checkpoint TRAIN mean, all 16 lags.

    PWM (including latest), history ages, instructions and both clocks stay exact.
    No new acceptance threshold: the 14-slot layout is the frozen input contract.
    """
    changed = state.clone()
    for lag in range(c.HISTORY):
        changed[..., lag*14:lag*14+8] = 0.
    return changed


def student(a):
    host = require_cpu()
    from scripts import run_grasp_act_student as runner
    from scripts.run_grasp_act_recovery import dependency_modules
    from scripts.replay_grasp_act_act15 import ShadowTeacher
    from harness.grasp_act_dart import recovery_hooks
    from harness.grasp_act_search import SEARCH_MODE
    runner.require_gcp = lambda *, training: host if not training else (_ for _ in ()).throw(ValueError('no training'))
    plan = read_json(a.plan)
    protocol = {'closed_loop_seeds': [plan['seed']], 'train_seeds': [], 'validation_seeds': []}
    calibration = read_json(ROOT/'experiments/2026-10-15-act-train/act11-noise.json')
    class NoPerturbation:
        mode = SEARCH_MODE
        active = False
        def apply(self, clean, **kwargs): return deepcopy(clean), None
    def factory(world, port, obj, initial, scene):
        shadow = ShadowTeacher(world, port, obj, initial, scene, plan=plan, output=a.output, original=None)
        top_dir = a.output/'review-top-10hz'
        if a.overview: top_dir.mkdir()
        def observe(obs, jpeg, selected, done):
            shadow(obs, jpeg, selected, done)
            if a.overview:
                camera = scene.config.get('static_map', {}).get('top_cameras', [{'name':'cctv_top'}])[0]['name']
                (top_dir/f'{shadow.n-1:06d}.jpg').write_bytes(world.render_team_jpeg(camera=camera))
        return observe
    with dependency_modules(a.scene_source):
        from sim import grasp_act_solo_teacher as teacher
        from harness import grasp_act_solo_recording as recording
        with (a.output.parent/(a.output.name+'-shadow-hook.jsonl')).open('x') as ledger:
            with recovery_hooks(teacher, recording, NoPerturbation(), ledger,
                                yaw_gain=calibration['rotation_calibration']['yaw_gain']):
                runner.run(plan, protocol, a.model, a.output, actor_python=a.actor_python,
                    cap_s=90., teacher_start_v1=True, n_action_steps=8, actor_threads=1,
                    diagnostic_observer_factory=factory)


def teacher_review(a):
    """Frozen ACT11 success comparison, no training camera/dataset admission.

    Capture wrapper persists the ALREADY captured own JPEG at 10Hz and an
    evaluation-only overview. It never supplies new images/state to the teacher.
    """
    host = require_cpu()
    from scripts.run_grasp_act_recovery import dependency_modules
    from harness.grasp_act_dart import recovery_hooks
    from harness.grasp_act_search import SEARCH_MODE
    calibration = read_json(ROOT/'experiments/2026-10-15-act-train/act11-noise.json')
    plan = read_json(a.plan)
    plan.update(batch='act16a-teacher-review-'+str(plan['seed']), episode_id='review-'+str(plan['seed']))
    class NoPerturbation:
        mode = SEARCH_MODE
        active = False
        def apply(self, clean, **kwargs): return deepcopy(clean), None
    with dependency_modules(a.scene_source):
        from scripts import grasp_act_host, run_solo_grasp_act_teacher as runner
        from sim import grasp_act_solo_teacher as teacher, grasp_act_port
        from harness import grasp_act_solo_recording as recording
        def identity(legacy_enum):
            if legacy_enum != 'gcp1': raise ValueError('unexpected frozen runner enum')
            require_cpu()
            return {**host, 'project_id': host['project'], 'provider': 'gcp',
                    'cpu_count': len(os.sched_getaffinity(0)), 'schema': 'ugrp.grasp_act.host.v1',
                    'adapter': 'act16a_gcp2_cpu_identity_only'}
        grasp_act_host.identity = identity
        capture = grasp_act_port.DutyActPort.capture
        index = []
        def saved_capture(port, *args, **kwargs):
            value = capture(port, *args, **kwargs)
            folder = a.output/'review-own-10hz'; folder.mkdir(exist_ok=True)
            jpeg = base64.b64decode(value['image'])
            path = folder/f'{len(index):06d}.jpg'; path.write_bytes(jpeg)
            top = a.output/'review-top-10hz'; top.mkdir(exist_ok=True)
            (top/path.name).write_bytes(port._world.render_team_jpeg())
            index.append({'path': str(path), 't': float(port._world.data.time), 'sha256': sha256(path)})
            return value
        grasp_act_port.DutyActPort.capture = saved_capture
        with (a.output.parent/(a.output.name+'-recovery-commands.jsonl')).open('x') as ledger:
            with recovery_hooks(teacher, recording, NoPerturbation(), ledger,
                                yaw_gain=calibration['rotation_calibration']['yaw_gain']):
                try:
                    runner.run(plan, a.output, execution_host='gcp1', profile='solo_visible_only_v1',
                        hidden=True, look=True, cap_s=90., teacher_stability='align_relook_v1',
                        reach_mode='pad_window_v2', rgb_lift_mode='solo_lift_lookback_v1',
                        solo_lift_lookback_margin_v1=True, solo_truth_free_lookaround_v1=True,
                        training_rgb=False)
                finally:
                    if a.output.exists(): write_json(a.output/'review-own-index.json', index)


def stats(values):
    v = np.asarray(values, dtype=float)
    return {'n': len(v), 'mean': float(v.mean()), 'p50': float(np.median(v)),
            'p95': float(np.quantile(v,.95)), 'max': float(v.max())} if len(v) else {'n':0}


def errors(command, target):
    return {'wheel_mae': float(np.abs(np.asarray(command['wheels'])-target['wheels']).mean()),
            'wheel_sign_mismatch': float((np.sign(command['wheels'])!=np.sign(target['wheels'])).mean()),
            'pulse_mae_ms': float(np.abs(np.asarray(command['duration_s'])-target['duration_s']).mean()*1000),
            'pwm_mae': float(np.abs(np.asarray(list(command['pwm'].values()))-list(target['pwm'].values())).mean())}


def summarize_errors(rows):
    return {k: stats([r[k] for r in rows]) for k in rows[0]} if rows else {'n':0}


def reversal_events(rows):
    """Direct nonzero +/- flips; next target-sign change censors the response.

    No tolerance/window is tuned. 0.1s timestamps are the frozen control clock.
    Persistence is the one-step predictor on this SAME ACT trajectory; it is
    not an independently rolled-out persistence policy.
    """
    events = []
    for i in range(1,len(rows)):
        before, now = rows[i-1], rows[i]
        if not before['valid'] or not now['valid']: continue
        for wheel in range(4):
            old, new = np.sign(before['target']['wheels'][wheel]), np.sign(now['target']['wheels'][wheel])
            if old*new != -1: continue
            end = i+1
            while end<len(rows) and rows[end]['valid'] and np.sign(rows[end]['target']['wheels'][wheel])==new:
                end += 1
            record = {'t':now['t'], 'wheel':wheel, 'from_sign':int(old), 'to_sign':int(new),
                      'phase':now['phase'], 'target_dwell_s':rows[end-1]['t']-now['t']+c.PERIOD_S,
                      'requires_response':bool(np.sign(now['persistence']['wheels'][wheel])!=new)}
            for policy in ('act','persistence'):
                match = next((r['t'] for r in rows[i:end] if np.sign(r[policy]['wheels'][wheel])==new),None)
                record[policy+'_delay_s'] = None if match is None else match-now['t']
                record[policy+'_censored'] = match is None
            events.append(record)
    return events


def offline(a):
    host = require_cpu()
    import torch
    from harness.grasp_act_policy import GraspActor, observation_batch
    torch.set_num_threads(1)
    actor = GraspActor.load(a.model, device='cpu')
    a.output.mkdir(parents=True, exist_ok=False)
    obs = read_rows(existing(a.run/'student-inputs.jsonl'))
    commands = read_rows(existing(a.run/'commands.jsonl'))
    labels = read_rows(existing(a.run/'shadow-labels.jsonl'))
    assert len(obs)==len(commands)==len(labels)
    by_phase = defaultdict(lambda: defaultdict(list)); rows=[]; mask_rows=[]
    stored = {r['sample_id']:r for r in read_rows(existing(a.run/'chunk-predictions.jsonl'))}
    with (a.output/'mask-rows.jsonl').open('x') as stream:
        for observation, command, label in zip(obs,commands,labels):
            actual = command['command']; previous = observation['issued'][-1]
            target = label['teacher_command']
            row = {'t':observation['t'], 'phase':label['teacher_phase'],
                   'valid':bool(label['label_valid'] and target is not None),
                   'act':actual, 'persistence':previous, 'target':target}
            rows.append(row)
            if row['valid']:
                for name,pred in [('act',actual),('persistence',previous)]:
                    e=errors(pred,target); by_phase[row['phase']][name].append(e); by_phase['ALL'][name].append(e)
                sa,sp,sy = map(np.sign,(actual['wheels'],previous['wheels'],target['wheels']))
                correction = sy!=sp
                row['copy']={'agree_previous':float((sa==sp).mean()), 'corrective_wheels':int(correction.sum()),
                             'kept_previous_on_correction':int(((sa==sp)&correction).sum()),
                             'matched_target_on_correction':int(((sa==sy)&correction).sum())}
            if observation['sample_id'] not in stored: continue
            batch = observation_batch(observation, [(a.run/r['path']).read_bytes() for r in observation['rgb']], actor.stats)
            batch = {k:torch.from_numpy(v.copy()).unsqueeze(0) for k,v in batch.items()}
            masked = {**batch, 'observation.state': mask_wheel_pulse_history(batch['observation.state'])}
            with torch.inference_mode():
                # Same batch-one route as deployment, never action-selecting.
                original = actor.decode_predictions(actor.policy.predict_action_chunk(batch)[0].numpy())
                changed = actor.decode_predictions(actor.policy.predict_action_chunk(masked)[0].numpy())
            decoded0,decoded1 = [c.decode_action(v) for v in original], [c.decode_action(v) for v in changed]
            delta=[errors(v,w) for v,w in zip(decoded1,decoded0)]
            record={'sample_id':observation['sample_id'],'t':observation['t'],'phase':row['phase'],
                    'label_valid':row['valid'],'h0_delta':delta[0], 'chunk_delta':summarize_errors(delta),
                    'done_score_delta':float(changed[0,-1]-original[0,-1]),
                    'done_flip':decoded1[0]['done']!=decoded0[0]['done'],
                    'stored_chunk_max_abs_error':float(np.abs(original-np.asarray(stored[observation['sample_id']]['chunk'])).max()),
                    'h0_original':decoded0[0], 'h0_masked':decoded1[0]}
            if row['valid']:
                record['h0_original_error']=errors(decoded0[0],target)
                record['h0_masked_error']=errors(decoded1[0],target)
            stream.write(json.dumps(record,allow_nan=False)+'\n');stream.flush();mask_rows.append(record)
    events=reversal_events(rows)
    write_json(a.output/'reversal-events.json',events)
    valid=[r for r in rows if r['valid']]; corrections=sum(r['copy']['corrective_wheels'] for r in valid)
    write_json(a.output/'summary.json', {'host':host, 'run':str(a.run), 'complete':True,
        'model_sha256':sha256(a.model/'model.safetensors'), 'optimizer_steps':0,
        'rows':len(rows), 'valid_expert_rows':len(valid), 'invalid_after_hover_rows':len(rows)-len(valid),
        'errors_by_phase':{p:{k:summarize_errors(v) for k,v in policy.items()} for p,policy in by_phase.items()},
        'copycat':{'agreement_with_previous_sign':stats([r['copy']['agree_previous'] for r in valid]),
            'corrective_wheels':corrections,
            'kept_previous_on_correction':sum(r['copy']['kept_previous_on_correction'] for r in valid),
            'matched_target_on_correction':sum(r['copy']['matched_target_on_correction'] for r in valid)},
        'reversals':{'events':len(events), **{p:{'matched':sum(not r[p+'_censored'] for r in events),
            'censored':sum(r[p+'_censored'] for r in events),
            'matched_delay_s':stats([r[p+'_delay_s'] for r in events if r[p+'_delay_s'] is not None])}
            for p in ('act','persistence')}},
        'mask':{'query_count':len(mask_rows),'h0_delta':summarize_errors([r['h0_delta'] for r in mask_rows]),
            'done_flips':sum(r['done_flip'] for r in mask_rows),
            'stored_chunk_max_abs_error':max((r['stored_chunk_max_abs_error'] for r in mask_rows),default=None),
            'h0_original_error':summarize_errors([r['h0_original_error'] for r in mask_rows if r['label_valid']]),
            'h0_masked_error':summarize_errors([r['h0_masked_error'] for r in mask_rows if r['label_valid']]),
            'interpretation':'Inference-only OOD intervention; not causal proof or matched retraining.'},
        'sources':{str(p):sha256(p) for p in [existing(a.run/n) for n in
            ('student-inputs.jsonl','commands.jsonl','shadow-labels.jsonl','chunk-predictions.jsonl')]}})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['student','teacher','offline'])
    p.add_argument('--plan',type=Path);p.add_argument('--model',type=Path)
    p.add_argument('--scene-source',type=Path);p.add_argument('--actor-python')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--run',type=Path)
    p.add_argument('--overview',action='store_true')
    a=p.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    {'student':student,'teacher':teacher_review,'offline':offline}[a.mode](a)


if __name__=='__main__': main()
