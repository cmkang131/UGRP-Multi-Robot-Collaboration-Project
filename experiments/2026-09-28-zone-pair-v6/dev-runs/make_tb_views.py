"""Derived TensorBoard views (result.json + hardlinked overview.mp4), v3-v5g pattern.

Raw run folders are read only. usage: make_tb_views.py <view_root> <version>=<run_dir> ...
"""
import collections, hashlib, json, os, sys
from pathlib import Path

MOTION = ('arm', 'look', 'drive', 'mecanum')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


root = Path(sys.argv[1])
for arg in sys.argv[2:]:
    version, run = arg.split('=', 1)
    run = Path(run)
    m = json.loads((run / 'manifest.json').read_text())
    ev = json.loads((run / 'eval_only/result.json').read_text())
    fails = [json.loads(l) for l in open(run / 'events.jsonl') if '"job_failed"' in l]
    kinds = collections.Counter(json.loads(l)['kind'] for l in open(run / 'commands.jsonl'))
    motion = sum(kinds[k] for k in MOTION)
    first = fails[0] if fails else None
    out = dict(ev)
    out.update({
        'run_id': m['run_id'], 'case': m['run_id'], 'seed': m['seed'], 'pair_policy': m.get('pair_policy', 'v5h'),
        'condition': f"tags_temporary_dev_{m['intervention']}_{m.get('pair_policy', 'v5h')}",
        'source_sha': m['source']['source_sha'], 'labels': m['labels'], 'research_result': False,
        'physical_success': False, 'derived_view': True, 'pipeline_version': version,
        'sim_s': ev.get('sim_s', m['sim_end_s']),
        'sim_s_source': ('eval_only/result.json sim_s' if 'sim_s' in ev else
                         'manifest.json sim_end_s (evaluation EVIDENCE_INCOMPLETE: no pair session)'),
        'wall_s': ev.get('wall_s', m['wall_s']),
        'commands': ev.get('commands', motion),
        'commands_source': 'commands.jsonl rows with kind in arm/look/drive/mecanum',
        'commands_jsonl_by_kind': dict(kinds), 'model_calls': 0,
        'model_calls_scope': 'no model calls in this dev pipeline',
        'model_response_time': 'not_applicable_no_model_calls',
        'job_failed': [{'robot_id': f['robot_id'], 'sim_s': f['sim_s'], 'job_kind': f.get('job_kind'),
                        'reason': f['detail'].get('reason')} for f in fails],
        'failure_reason': None if first is None else f"{first['robot_id']}:{first['detail'].get('reason')}",
        'failure_reason_scope': 'events.jsonl job_failed rows (executor self-report); PARTNER_ABORT is the partner side',
        'stop_reason': ' / '.join(f"{f['robot_id']}:{f['detail'].get('reason')}@{f['sim_s']}s ({f.get('job_kind')})"
                                  for f in fails),
        'video_review_note': 'overview.mp4 registered as original media; manual full-video review not done '
                             '(key frames only checked)',
        'raw_root': str(run),
        'provenance': {p: sha(run / p) for p in ('eval_only/result.json', 'events.jsonl', 'commands.jsonl',
                                                  'manifest.json', 'eval_only/overview.mp4')}})
    view = root / version / m['run_id']
    view.mkdir(parents=True, exist_ok=False)
    (view / 'result.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    os.link(run / 'eval_only/overview.mp4', view / 'overview.mp4')
    print(view)
