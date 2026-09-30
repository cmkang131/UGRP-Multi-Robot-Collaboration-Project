"""Candidate P06 terminal writer, separate from the byte-pinned v6e runner.

This module does not install hooks or start an episode. A future registered
runner must call it with the actual scenario, cap and attempt after termination,
including exceptions/interruptions. The legacy runner remains byte-for-byte
unchanged and does not automatically produce this evidence contract.
"""
from __future__ import annotations

import collections
import copy
import json
import os
import platform
import time
from pathlib import Path

from harness import zone_study_integration as zi
from harness import zone_study_offline as zo
from harness import zone_study_llm_driver as llm
from harness import zone_study_referee as zr
from harness.zone_study_contract import ROBOTS, digest
from scripts.run_zone_study_integration import jsonl, robot_eval, SCHEMA
from scripts.zone_study_evidence_contract import (identity_for, per_order_evaluation,
                                                 validate_record_identity, seal_new_evidence)
from scripts.zone_study_evidence_join import admitted_trial

ROOT = Path(__file__).resolve().parents[1]


def write_outputs(out, prereg, episode, condition, bundle, bundle_sha, host, trial, result, stop, failure, code,
                  started, load0, dev, *, horizon_s, scenario_id, attempt, frozen_plan, plan_sha256, referee=None):
    """Everything that exists, also after an exception; returns the result summary."""
    identity = identity_for(run_id=out.name,
                            trial_id=trial.run_id if trial else f'{condition}-{scenario_id}-s{episode["trial_seed"]}',
                            episode_id=episode['episode_id'], attempt=attempt, condition=condition,
                            scenario=scenario_id, seed=episode['trial_seed'], bundle=bundle)
    if bundle_sha != identity['bundle_sha256']:
        raise ValueError('Zone-study writer bundle digest mismatch')
    admitted_trial(frozen_plan, plan_sha256, identity, bundle['host_spec']['order_sheet']['orders'])
    ledger = getattr(trial, 'send_ledger', None) if trial is not None else None
    summary = {'schema': SCHEMA, 'run_id': out.name, 'condition': condition, 'episode': episode['episode_id'],
               'dev': dev, 'stop': stop, 'failure': failure, 'bundle_sha256': bundle_sha,
               'failure_class': (failure or {}).get('failure_class') or (
                   llm.trial_failure_class(None, ledger, transport=trial.transport)
                   if isinstance(ledger, llm.MainStudySendLedger) else None),
               'pose_provider': bundle['pose_provider']['label'],
               'actor': trial.actor if trial else prereg.get('actor', zi.FIXTURE_ACTOR),
               'plumbing_only': trial is None or trial.actor == zi.FIXTURE_ACTOR,
               'note_ko': '통합 dev 경로. 통신 효과·연구 결과가 아니다. ' + zi.TEMPORARY_NOTE_KO}
    summary['terminal'] = True
    summary['scenario'] = scenario_id
    summary['seed'] = episode['trial_seed']
    summary['sim_horizon_s'] = horizon_s
    summary['evidence_identity'] = identity
    if host is not None:
        summary['sim_s'] = round(float(host.world.data.time), 3)
        ev = host.eval_only
        boxes = {b: [float(v) for v in host.world.data.body(o['body_name']).xpos] for b, o in host.objects.items()
                 if o['kind'] in ('cyan', 'long_beam')}
        ref_row = referee.record() if referee is not None else None
        summary['robots'] = {rid: robot_eval(host, rid, boxes) for rid in ROBOTS}
        hidden = list(getattr(host, 'hidden_log', []))    # the full rows go to eval_only/hidden_events.jsonl only
        summary['eval_only'] = {'referee': ref_row, 'hidden_events': {'file': 'eval_only/hidden_events.jsonl',
                                                                       'rows': len(hidden)},
                                'box_final_xyz': {b: [round(v, 4) for v in p] for b, p in boxes.items()},
                                'weld_max_eq_active': ev['max_eq_active'], 'contact_profile': host.contact_record}
        for rid, slot in host.robots.items():
            base = out / 'robots' / rid
            jsonl(base / 'inputs' / 'commands.jsonl', slot.commands)
            jsonl(base / 'inputs' / 'pose_timing.jsonl', getattr(slot.executor.pose, 'timing', []))
            jsonl(base / 'inputs' / 'frames.jsonl', slot.frames)
            jsonl(base / 'executor' / 'events.jsonl', slot.executor.events)
            jsonl(base / 'executor' / 'api.jsonl', slot.executor.api_log)
            jsonl(base / 'executor' / 'judgments.jsonl', slot.executor.judgment_log)
            jsonl(base / 'executor' / 'macros.jsonl', slot.decisions)
            (base / 'executor' / 'job_summaries.json').write_text(
                json.dumps(slot.executor._summaries, indent=1, default=str) + '\n')
        jsonl(out / 'eval_only' / 'gt.jsonl', ev['gt'])
        jsonl(out / 'eval_only' / 'frames_eval.jsonl', ev['frames_eval'])
        jsonl(out / 'eval_only' / 'contacts.jsonl', ev['contacts'])
        (out / 'eval_only' / 'referee.json').write_text(json.dumps(ref_row, indent=1) + '\n')
        jsonl(out / 'eval_only' / 'hidden_events.jsonl', hidden)
        (out / 'eval_only' / 'top_camera.json').write_text(json.dumps(ev['top_camera'], indent=1) + '\n')
        (out / 'eval_only' / 'static_map.json').write_text(json.dumps(host.eval_static, indent=1) + '\n')
        (out / 'scene.xml').write_text(host.world.scene_xml)
        summary['provider_sources'] = dict(host.provider_sources)
    if trial is not None:
        write_study(out, trial, result, summary, referee)
    else:
        record = incomplete_record(summary, orders=bundle['host_spec']['order_sheet']['orders'],
                                   seed=episode['trial_seed'])
        save_evaluation(out, record, summary)
    manifest = {'schema': SCHEMA, 'run_id': out.name, 'bundle': bundle, 'bundle_sha256': bundle_sha, 'code': code,
                'applied_contact_profile': copy.deepcopy(host.contact_record) if host else None,
                'perception_delay_s': zi.PERCEPTION_DELAY_S,
                'actor': summary['actor'],
                'prereg_sha256': zi.file_sha256(ROOT / prereg['_path']) if prereg.get('_path') else None,
                'env': {'python': platform.python_version(), 'platform': platform.platform(),
                        'threads': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                                                                   'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS')}},
                'load_average': {'start': [round(v, 2) for v in load0], 'end': [round(v, 2) for v in os.getloadavg()]},
                'wall_s': round(time.time() - started, 1), 'pose_provider': bundle['pose_provider']['label']}
    manifest['terminal'] = {'end_reason': summary['study']['end_reason'],
                            'end_sim_s': summary['study']['end_sim_s'],
                            'failure_class': summary['failure_class'],
                            'sim_horizon_s': summary['sim_horizon_s'],
                            'record_complete': summary['study']['record_complete']}
    manifest['evidence_identity'] = copy.deepcopy(identity)
    (out / 'result.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + '\n')
    manifest['files'] = {str(q.relative_to(out)): zi.file_sha256(q) for q in sorted(out.rglob('*'))
                         if q.is_file() and q != out / 'manifest.json'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + '\n')
    return seal_new_evidence(out, frozen_plan, plan_sha256)


def incomplete_record(summary, *, orders, seed, trial=None):
    """Snapshot available logs without finishing the scheduler or inventing missing usage."""
    record = {'schema': zr.ev.TRIAL_SCHEMA, 'trial_id': summary['evidence_identity']['trial_id'],
              'condition': summary['condition'], 'scenario': summary['scenario'], 'seed': seed,
              'robots': list(ROBOTS), 't0_sim_s': 0., 'end_sim_s': summary.get('sim_s', 0.),
              'budget': {'sim_horizon_s': summary['sim_horizon_s']}, 'orders': copy.deepcopy(orders),
              'end_reason': terminal_reason(summary, 'not_evaluated'),
              'failure_class': summary.get('failure_class'), 'record_complete': False,
              'missing': ['terminal_result'], 'end_state': {}}
    if trial is not None:
        record.update(calls=copy.deepcopy(trial.calls), messages=copy.deepcopy(trial.messages),
                      actions=copy.deepcopy(trial.actions), request_archive=copy.deepcopy(trial.requests),
                      provenance=copy.deepcopy(trial.provenance))
    if summary['condition'] == 'leader_ko':
        record['leader_id'] = ROBOTS[int(seed) % len(ROBOTS)]
    return zr.not_evaluated(record)


def terminal_reason(summary, default):
    failure = summary.get('failure') or {}
    if failure.get('type') in ('KeyboardInterrupt', 'InterruptedError') or summary.get('stop') == 'interrupted':
        return 'interrupted'
    return {llm.HOST_ERROR: 'host_error', llm.API_ERROR: 'api_failure',
            llm.OTHER: 'policy_failure'}.get(summary.get('failure_class'),
                                           'aborted' if failure else default)


def save_evaluation(out, record, summary, referee=None):
    """Persist the terminal envelope and recomputed verdict, including early failures."""
    identity = summary['evidence_identity']
    validate_record_identity(record, identity)
    if record['budget']['sim_horizon_s'] != summary['sim_horizon_s']:
        raise ValueError('Zone-study writer trial SIM cap mismatch')
    record['record_complete'] = record.get('record_complete', True)
    record['evidence_identity'] = copy.deepcopy(identity)
    study = out / 'study'
    study.mkdir(parents=True, exist_ok=True)
    (study / 'trial_record.json').write_text(json.dumps(record, indent=1, ensure_ascii=False) + '\n')
    evaluation = (zr.evaluation_block(record, referee) if referee is not None else
                  {'schema': 'ugrp.zone_study_referee_evaluation.v2', 'status': 'not_evaluated',
                   **zr.ev.efficiency_metrics(record), 'orders': per_order_evaluation(record),
                   'note': 'no terminal referee evaluation'})
    evaluation['evidence_identity'] = copy.deepcopy(identity)
    summary.setdefault('eval_only', {})['evaluation'] = evaluation
    (out / 'eval_only').mkdir(parents=True, exist_ok=True)
    if referee is not None:
        (out / 'eval_only' / 'referee.json').write_text(json.dumps(referee.record(), indent=1) + '\n')
    (out / 'eval_only' / 'evaluation.json').write_text(json.dumps(evaluation, indent=1, ensure_ascii=False) + '\n')
    summary['study'] = {'end_reason': record['end_reason'], 'end_sim_s': record['end_sim_s'],
                        'record_complete': record.get('record_complete', True),
                        'end_state': record.get('end_state', {}),
                        'reopen': zo.reopen_trial_record(study / 'trial_record.json')}


def write_study(out, trial, result, summary, referee=None):
    """Study-side logs: requests (text + image bytes), calls, messages, actions, dispatch, checks."""
    study = out / 'study'
    images = study / 'request_images'
    images.mkdir(parents=True, exist_ok=True)
    for sha, jpeg in trial.request_images.items():
        (images / f'{sha}.jpg').write_bytes(jpeg)
    if isinstance(trial.send_ledger, llm.MainStudySendLedger):
        # Raw request/response bytes are already in study/wire/ (written before/after each POST).
        rows = llm.call_rows(trial.send_ledger)
        jsonl(study / 'model_calls.jsonl', rows)
        summary['model_usage'] = llm.usage_summary(rows)
        summary['model_ledger'] = {'run_key': trial.send_ledger.run_key, 'live': trial.send_ledger.live,
                                   'host_errors': list(trial.send_ledger.host_errors),
                                   'proxy_identity': getattr(trial.send_ledger, 'proxy_identity', None)}
    jsonl(study / 'dispatch.jsonl', trial.dispatch_log)
    jsonl(study / 'inputs.jsonl', trial.input_log)
    jsonl(study / 'executor_events.jsonl', trial.executor_events)
    jsonl(study / 'scheduler_events.jsonl', trial.scheduler.events)
    jsonl(study / 'decision_events.jsonl', trial.scheduler.decision_events)
    (study / 'pair_status.json').write_text(json.dumps(trial.pair_status.record(), indent=1) + '\n')
    (study / 'study_config.json').write_text(json.dumps(trial.study_config(), indent=1, ensure_ascii=False) + '\n')
    (study / 'send_ledger.json').write_text(json.dumps(trial.send_ledger.to_dict(), indent=1) + '\n')
    if result is None:
        record = incomplete_record(summary, orders=trial.sheet['orders'], seed=trial.seed, trial=trial)
    else:
        record = trial.trial_record(result)
    # Always write the trial record (PR #257 review P1-G b). Without a referee
    # (the run failed before it existed) the block says not_evaluated and the
    # record is never a success.
    record['failure_class'] = summary.get('failure_class')
    record['end_reason'] = terminal_reason(summary, record['end_reason'])
    record = (zr.apply_to_record(record, referee) if referee is not None and result is not None
              else zr.not_evaluated(record))
    if isinstance(trial.send_ledger, llm.MainStudySendLedger):
        record['model_usage'] = summary['model_usage']
    record['pose_provider'] = dict(summary['pose_provider'])   # A's provenance keys are closed: top level
    record['plumbing_only'] = trial.actor == zi.FIXTURE_ACTOR
    save_evaluation(out, record, summary, referee if result is not None else None)
    if result is None:
        return
    summary['study'].update({'calls': len(result.calls), 'messages': len(result.messages), 'actions': len(result.actions),
                        'end_reason': record['end_reason'], 'end_sim_s': record['end_sim_s'],
                        'end_state': record['end_state'],
                        'channel': zo.channel_checks(trial, result), 'cost': zo.cost_checks(trial, result),
                        'requests': zo.request_checks(result),
                        'reopen': zo.reopen_trial_record(study / 'trial_record.json'),
                        'clock_drift_s': trial.clock_drift_s, 'wakeups': {r: trial.wakeups(r) for r in ROBOTS},
                        'dispatch': collections.Counter(f'{d["api"]}:{(d["ack"] or {}).get("accepted")}'
                                                        for d in trial.dispatch_log),
                        'pair_status_sha256': trial.pair_status.config_sha256(),
                        'study_config_sha256': digest(trial.study_config())})
