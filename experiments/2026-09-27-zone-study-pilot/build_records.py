"""Records + TensorBoard snapshot for the real-LLM zone-study adapter pilot (2026-09-27).

Read-only over the raw pilot root; no model/API call, no physics. Writes:

* ``calls.json`` / ``messages.json`` / ``sha256.json`` next to this file (small derived
  records; the raw stays in the primary ``outputs/``);
* with ``--tb``: a NEW TensorBoard snapshot through the existing
  ``scripts.zone_study_report.write_events`` (refuses existing runs), plus
  ``collection.json`` for ``scripts/run_tensorboard.py``;
* with ``--verify``: reloads the events with EventAccumulator and compares every
  scalar with ``calls.json``.

Run from the worktree root with the primary checkout's ``.venv-sim-worker-mac``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = Path('/Users/changmin/projects/ugrp/outputs/zone-study-adapter-pilot-r10')
TB_ROOT = Path('/Users/changmin/projects/ugrp/outputs/tensorboard')
SNAPSHOT = '0927-zone-study-pilot'
RUNS = ('preflight-01', 'preflight-02-v63', 'cohort-01-v63')
CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')
# every raw file whose content backs a number in the record
HASHED = [
    'budget.sqlite', 'preflight-01.driver.log', 'preflight-01.load.txt',
    'preflight-02-v63.load.txt', 'cohort-01-v63.load.txt', 'init-01/budget-created.json',
    'migrate-v63-01/migration-proposal.json', 'migrate-v63-01/source-migration.json',
    'log-evidence-v63-05/manifest.json', 'log-evidence-v63-05/telemetry.jsonl',
    'reconcile-v63-05/reconciliation.json', 'managed-preflight-02-v63/manifest.json',
    'managed-cohort-01-v63/manifest.json',
] + [f'{r}/manifest.json' for r in RUNS] + [f'{r}/reconciliation.json' for r in RUNS]


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def extract():
    """One row per logical call, joined on (run, condition, call_id)."""
    calls, messages, trials = [], [], []
    for run in RUNS:
        manifest = load(RAW / run / 'manifest.json')
        links = {(l['condition'], l['call_id']): l for l in manifest['call_links']}
        for cond in CONDITIONS:
            path = RAW / run / cond / 'trial.json'
            if not path.exists():
                continue
            trial = load(path)
            ledger = {e['call_id']: e for e in trial['send_ledger']['entries']} \
                if trial.get('send_ledger') else {}
            actions = {a['actor']: a for a in trial.get('actions', []) if a.get('accepted')}
            for call in trial['calls']:
                call_id = next((k for (c, k) in links if c == cond and k.endswith('-' + call['actor'])), None)
                link = links[(cond, call_id)]
                led = ledger.get(call_id) or link['ledger']
                comp = link['completion']
                usage = link['provider_usage'] or {}
                start, end = led.get('send_started_at_ns'), led.get('response_received_at_ns')
                action = actions.get(call['actor'])
                calls.append({
                    'run': run, 'stage': manifest['stage'], 'condition': cond,
                    'call_id': call_id, 'actor': call['actor'], 'role': call['role'],
                    'status': call['status'],
                    'provider_total_tokens': usage.get('total_tokens'),
                    'provider_prompt_tokens': usage.get('prompt_tokens'),
                    'provider_completion_tokens': usage.get('completion_tokens'),
                    'model_response_wall_s': round((end - start) / 1e9, 3) if start and end else None,
                    'requested_at_sim_s': call['requested_at_sim_s'],
                    'released_at_sim_s': call['released_at_sim_s'],
                    'sim_cost_s': call['sim_cost_s'],
                    'json_fence_removed': comp.get('json_fence_removed'),
                    'accepted': bool(comp.get('normal_completion')),
                    'rejection_reasons': comp.get('rejection_reasons'),
                    'finish_reason_proxy': comp.get('finish_reason'),
                    'upstream_finish_verified': comp.get('upstream_finish_verified'),
                    'reserved_tokens': link['reserved_tokens'],
                    'reserved_attempts': link['reserved_attempts'],
                    'action': ({'kind': action['kind'], **action['arguments']} if action else None),
                    'code_sha': call['provenance']['code_sha'],
                    'bundle': manifest['source_identity']['rgb_execution_bundle']['id'],
                    'model_requested': manifest['requested_settings']['model'],
                    'model_effective': manifest['effective_settings']['model'],
                })
            for m in trial.get('messages', []):
                messages.append({
                    'run': run, 'condition': cond, 'message_id': m['message_id'],
                    'sender': m['sender'], 'recipients': m['recipients'], 'body': m['body'],
                    'created_at_sim_s': m['created_at_sim_s'],
                    'delivered_at_sim_s': m.get('delivered_at_sim_s'), 'status': m['status']})
            trials.append({'run': run, 'condition': cond, 'trial_id': trial['trial_id'],
                           'leader_id': trial['channel'].get('leader_id'),
                           'think_sim_s': trial['model_evaluation'].get('think_sim_s'),
                           'talk_sim_s': trial['model_evaluation'].get('talk_sim_s')})
    return calls, messages, trials


def scalar_payload(calls, messages, trials):
    """zone_study_report.write_events payload: one run per (pilot run, condition)."""
    runs = []
    for t in trials:
        rows = [c for c in calls if c['run'] == t['run'] and c['condition'] == t['condition']]
        lat = [c['model_response_wall_s'] for c in rows if c['model_response_wall_s'] is not None]
        msgs = [m for m in messages if m['run'] == t['run'] and m['condition'] == t['condition']]
        scalars = {
            'evaluation/accepted_calls': sum(c['accepted'] for c in rows),
            'evaluation/rejected_calls': sum(not c['accepted'] for c in rows),
            'result/release_sim_s': max(c['released_at_sim_s'] for c in rows),
            'result/commands': sum(c['action'] is not None and c['accepted'] for c in rows),
            'result/model_calls': len(rows),
            'result/tokens_total': sum(c['provider_total_tokens'] or 0 for c in rows),
            'result/reserved_tokens': sum(c['reserved_tokens'] for c in rows),
            'result/think_sim_s': t['think_sim_s'] or 0.0,
            'result/talk_sim_s': t['talk_sim_s'] or 0.0,
            'dialogue/messages': len(msgs),
            'result/json_fence_removed_calls': sum(bool(c['json_fence_removed']) for c in rows),
        }
        if lat:   # no latency sample -> no scalar (never 0 as a stand-in)
            scalars['result/model_response_s_mean'] = round(sum(lat) / len(lat), 3)
            scalars['result/model_response_s_max'] = max(lat)
        assert all(math.isfinite(float(v)) for v in scalars.values())
        runs.append({'run': f"{t['run']}/{t['condition']}", 'step': 0, 'scalars': scalars,
                     'hparams': {'condition': t['condition'], 'stage': rows[0]['stage'],
                                 'bundle': rows[0]['bundle'],
                                 'model_effective': rows[0]['model_effective']}})
    return {'runs': runs}


def verify(payload):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    checked, mismatches = 0, []
    for run in payload['runs']:
        acc = EventAccumulator(str(TB_ROOT / SNAPSHOT / run['run']), size_guidance={'scalars': 0})
        acc.Reload()
        tags = set(acc.Tags()['scalars'])
        for tag, value in run['scalars'].items():
            got = acc.Scalars(tag)[-1].value if tag in tags else None
            checked += 1
            if got is None or abs(got - float(value)) > 1e-3 * max(1.0, abs(float(value))):
                mismatches.append((run['run'], tag, value, got))
    return {'runs': len(payload['runs']), 'scalars_checked': checked, 'mismatches': mismatches}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tb', action='store_true', help='write the NEW TensorBoard snapshot')
    parser.add_argument('--verify', action='store_true', help='reload events and compare')
    args = parser.parse_args(argv)
    calls, messages, trials = extract()
    payload = scalar_payload(calls, messages, trials)
    hashes = {p: sha256(RAW / p) for p in HASHED}
    for r in RUNS:
        for c in CONDITIONS:
            if (RAW / r / c / 'trial.json').exists():
                hashes[f'{r}/{c}/trial.json'] = sha256(RAW / r / c / 'trial.json')
    (HERE / 'calls.json').write_text(json.dumps(calls, ensure_ascii=False, indent=1) + '\n')
    (HERE / 'messages.json').write_text(json.dumps(messages, ensure_ascii=False, indent=1) + '\n')
    (HERE / 'scalars.json').write_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n')
    (HERE / 'sha256.json').write_text(json.dumps({'raw_root': str(RAW), 'files': dict(sorted(hashes.items()))},
                                                 indent=1) + '\n')
    if args.tb:
        sys.path.insert(0, str(ROOT))
        from scripts.zone_study_report import write_events
        out = TB_ROOT / SNAPSHOT
        if out.exists():
            raise FileExistsError(f'{out} exists; write a new snapshot ID instead')
        at = time.time()
        events = write_events(payload, out, at)
        collection = {
            'schema': 'ugrp.zone_study_tensorboard_collection.v1', 'snapshot': SNAPSHOT,
            'source_sha': 'c684e6aaef6dc7ee8cd62ce9e18e4034f78146f6 (v63 runs); '
                          '1adfeff01884b308352918a4488c31258adaf478 (preflight-01, v62)',
            'converter': 'experiments/2026-09-27-zone-study-pilot/build_records.py -> '
                         'scripts/zone_study_report.write_events (TensorBoard 2.21.0 protobuf)',
            'raw_root': str(RAW), 'raw_sha256_json': sha256(HERE / 'sha256.json'),
            'scope_ko': '실제 LLM 첫 호출만(물리 실행 0). accepted_calls는 프록시 stop + 연구 응답 '
                        '스키마 통과(상류 finish 미검증)이며 배송 성공이 아니다. run 이름은 '
                        '<파일럿 run>/<condition>.',
            'exported': [{'name': r['run'], 'hparams': r['hparams'],
                          'counts': {'scalars': len(r['scalars'])}} for r in payload['runs']],
            'events': events, 'created_unix': at,
        }
        (out / 'collection.json').write_text(json.dumps(collection, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(events))
    if args.verify:
        print(json.dumps(verify(payload), ensure_ascii=False))
    print(json.dumps({'calls': len(calls), 'messages': len(messages), 'runs': len(payload['runs']),
                      'tokens_total': sum(c['provider_total_tokens'] or 0 for c in calls),
                      'reserved_tokens': sum(c['reserved_tokens'] for c in calls)}))


if __name__ == '__main__':
    main()
