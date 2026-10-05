"""Read-only integration-run evidence adapter. No simulator or model calls.

Every raw file is verified, including unsampled request images. An event import
is not a robot success, a provider reconciliation or a video playback check.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from harness import zone_study_eval as ev
from harness.zone_study_contract import digest
from scripts.zone_study_evidence_contract import verify_identity_join, read_auxiliary, verify_referee_derivations
from scripts import zone_study_evidence_join as join

RUN_SCHEMA = 'ugrp.zone_study_integration_run.v1'
MEDIA_SCHEMA = 'ugrp.zone_study_media.v1'
# Off by default: a missing request image fails the conversion. Set by `export.py --allow-removed-request-images`
# when the images were removed under the AGENTS.md retention rule (hashes stay in the request rows).
ALLOW_REMOVED_REQUEST_IMAGES = False
REQUIRED = {'result.json', 'study/trial_record.json', 'eval_only/evaluation.json',
            'study/frozen_plan.json', 'study/record_index.json'}


def file_digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify_raw(src, result):
    from scripts.tensorboard_tools.export import inside
    manifest = src.read('manifest.json', required=True)
    files = manifest.get('files')
    if manifest.get('schema') != RUN_SCHEMA or not isinstance(files, dict) or not REQUIRED <= files.keys():
        raise ValueError('Incomplete zone-study raw manifest: terminal record/evaluation required')
    if (manifest.get('run_id') != result.get('run_id')
            or manifest.get('bundle_sha256') != result.get('bundle_sha256')
            or digest(manifest.get('bundle')) != manifest.get('bundle_sha256')):
        raise ValueError('Zone-study run/bundle identity mismatch')
    # The writer excludes manifest.json itself; no other evidence may disappear
    # from the inventory (including wire files and every original request image).
    actual = {str(p.relative_to(src.root)) for p in src.root.rglob('*')
              if p.is_file() and p != src.root / 'manifest.json'}
    if actual != set(files):
        raise ValueError('Zone-study raw file inventory mismatch')
    for relative, expected in files.items():
        path = inside(src.root, relative)
        if path is None or file_digest(path) != expected:
            raise ValueError(f'Zone-study raw file missing/hash mismatch: {relative}')
        if path.suffix == '.json':
            join.strict_json(path.read_bytes())
        elif path.suffix == '.jsonl':
            with path.open() as stream:
                for line in stream:
                    if line.strip():
                        join.strict_json(line)
        st = path.stat()
        old = src.files.get(relative)
        if old and old['sha256'] != expected:
            raise ValueError(f'Zone-study source changed while reading: {relative}')
        src.files[relative] = {'sha256': expected, 'size': st.st_size, 'mtime_s': st.st_mtime}
    join.strict_json((src.root / 'manifest.json').read_bytes())
    return manifest


def request_images(src, record, w, max_images):
    from scripts.tensorboard_tools.export import sample_indices
    archive = record.get('request_archive', [])
    if record.get('record_complete', True) and record.get('calls'):
        if {c['request_id'] for c in record['calls']} != {r['request_id'] for r in archive}:
            raise ValueError('Complete trial is missing original model request archives')
    selected = set(sample_indices(len(archive), max_images))
    hash_only = 0
    for i, request in enumerate(archive):
        w.text('decisions/request', request, i)
        for ref in request.get('image_refs', []):
            sha = ref.get('bytes_sha256')
            relative = f'study/request_images/{sha}.jpg'
            if sha is None:
                raise ValueError('Model request image reference has no bytes_sha256')
            if relative not in src.files:
                if not ALLOW_REMOVED_REQUEST_IMAGES:
                    raise ValueError(f'Missing/hash-mismatched original model request image: {relative}')
                # The image was removed under the AGENTS.md retention rule and the caller said so explicitly. The
                # request row and the image hash stay (the hash identifies the image); only the preview is absent.
                hash_only += 1
                continue
            if src.files[relative].get('sha256') != sha:
                raise ValueError(f'Hash-mismatched model request image: {relative}')
            if i in selected:
                data = src.image({'path': relative, 'sha256': sha})
                if data is None:
                    raise ValueError(f'Cannot read original model request image: {relative}')
                w.image('observations/own/' + str(ref.get('label', 'image')), data, i)
    return len(archive), hash_only


def media_evidence(src):
    """Camera JSON is configuration only; TOP RGB requires an explicit typed file."""
    if 'eval_only/media.json' not in src.files:
        return []
    media = src.read('eval_only/media.json', required=True)
    if media.get('schema') != MEDIA_SCHEMA or not isinstance(media.get('videos'), list):
        raise ValueError('Invalid zone-study media declaration')
    result, seen = [], set()
    for row in media['videos']:
        path, kind = row.get('path'), row.get('kind')
        if (not isinstance(path, str) or not path.startswith('eval_only/')
                or Path(path).name not in ('overview.mp4', 'execution.mp4', 'motion.mp4')
                or kind not in ('top_rgb', 'gt_visualization') or path in seen
                or row.get('sha256') != src.files.get(path, {}).get('sha256')
                or not src.files.get(path, {}).get('size')):
            raise ValueError('Invalid/missing/hash-mismatched zone-study video')
        if kind == 'top_rgb' and 'eval_only/top_camera.json' not in src.files:
            raise ValueError('TOP RGB video needs its camera configuration')
        seen.add(path)
        result.append({'path': path, 'kind': kind, 'sha256': row['sha256']})
    return result


def export_study(src, w, result, max_images):
    raw = verify_raw(src, result)
    verified = {name: row['sha256'] for name, row in src.files.items()}
    record = src.read('study/trial_record.json', required=True)
    trial = ev.parse_trial(record)
    metrics = ev.efficiency_metrics(trial)
    evaluation = src.read('eval_only/evaluation.json', required=True)
    identity = verify_identity_join(raw, result, record, evaluation)
    plan = src.read('study/frozen_plan.json', required=True)
    pin = raw.get('plan_sha256')
    join.admitted_trial(plan, pin, identity, record['orders'])
    if any(envelope.get('plan_sha256') != pin for envelope in (result, record, evaluation)):
        raise ValueError('INVALID: conflicting frozen plan pins')
    auxiliary = read_auxiliary(lambda p: src.read(p, required=True), src.read_jsonl, src.files)
    index = join.record_index(record, identity, auxiliary)
    if digest(index) != digest(src.read('study/record_index.json', required=True)):
        raise ValueError('INVALID: exact input record index mismatch')
    inputs = {'study/trial_record.json': verified['study/trial_record.json']}
    if 'eval_only/referee.json' in verified:
        inputs['eval_only/referee.json'] = verified['eval_only/referee.json']
    expected_derived = join.derivations({k: v for k, v in evaluation.items() if k != 'derived'}, inputs,
                                        [record['evidence_key'], *record['order_keys']])
    if digest(evaluation.get('derived')) != digest(expected_derived):
        raise ValueError('INVALID: derived evaluation numbers/input hashes disagree')
    for key in evaluation.keys() & metrics.keys():
        if digest(evaluation[key]) != digest(metrics[key]):
            raise ValueError(f'INVALID: re-derived evaluation differs: {key}')
    referee = src.read('eval_only/referee.json', required=True) if 'eval_only/referee.json' in src.files else None
    nested = result.get('eval_only', {}).get('referee')
    if nested is not None and digest(nested) != digest(referee):
        raise ValueError('INVALID: embedded referee history conflicts with its source')
    source_key = None
    if referee is not None:
        sources = raw.get('event_sources')
        if (not isinstance(sources, dict) or set(sources) != {'eval_only/referee.json'}
                or not isinstance(sources['eval_only/referee.json'], dict)
                or set(sources['eval_only/referee.json']) != {'evidence_key'}):
            raise ValueError('INVALID: missing/conflicting raw event manifest entry')
        source_key = sources['eval_only/referee.json']['evidence_key']
        if join.key_tuple(source_key) != join.key_tuple(join.key_for(identity)):
            raise ValueError('INVALID: raw event manifest entry/trial key conflict')
    raw_metrics = verify_referee_derivations(record, evaluation, referee, identity,
                                              source_key=source_key,
                                              pinned_policy=plan['referee_policy'], bundle=raw['bundle'])
    if digest(raw_metrics) != digest(metrics):
        raise ValueError('INVALID: raw referee outcome conflicts with trial metrics')
    metrics = raw_metrics
    if 'study/study_config.json' in src.files:
        config = src.read('study/study_config.json', required=True)
        for key in ('seed', 'condition', 'order_sheet_sha256'):
            if digest(config.get(key)) != digest(identity[key]):
                raise ValueError(f'Zone-study study config identity mismatch: {key}')
    if result.get('terminal') is not True:
        raise ValueError('Zone-study terminal=true is required; running/legacy evidence refused')
    for key in ('success', 'end_reason', 'par_makespan_sim_s', 'delivered_items', 'sim_horizon_s'):
        if key in evaluation and evaluation[key] != metrics[key]:
            raise ValueError(f'Zone-study evaluation disagrees with trial record: {key}')
    if evaluation.get('success') is not metrics['success']:
        raise ValueError('Zone-study evaluation lacks a matching bool success')
    study = result.get('study', {})
    for key in ('end_reason', 'end_sim_s'):
        if study.get(key) != record.get(key):
            raise ValueError(f'Zone-study result/trial mismatch: {key}')
    if result.get('condition') != record['condition'] or result.get('failure_class') != record.get('failure_class'):
        raise ValueError('Zone-study condition/failure class mismatch')
    terminal = raw.get('terminal')
    required_terminal = {'end_reason', 'end_sim_s', 'failure_class', 'sim_horizon_s', 'record_complete'}
    if not isinstance(terminal, dict) or not required_terminal <= terminal.keys():
        raise ValueError('Zone-study complete terminal manifest is required')
    for key in ('end_reason', 'end_sim_s', 'failure_class'):
        if terminal[key] != record.get(key):
            raise ValueError(f'Zone-study terminal manifest mismatch: {key}')
    if (terminal['sim_horizon_s'] != metrics['sim_horizon_s']
            or result.get('sim_horizon_s') != metrics['sim_horizon_s']):
        raise ValueError('Zone-study manifest SIM cap mismatch')
    for envelope in (record, terminal, study):
        if (type(envelope.get('record_complete')) is not bool
                or envelope['record_complete'] != record['record_complete']):
            raise ValueError('Zone-study record completeness mismatch')
    values = {tag: metrics[key] for tag, key in ev.SCALAR_TAGS.items()}
    values.update({'evaluation/reported_success': metrics['success'], 'cohort/trials': 1,
                   'result/sim_horizon_s': metrics['sim_horizon_s'],
                   'result/wall_s': raw.get('wall_s'),
                   'result/think_sim_cost_s': metrics['think_sim_cost_s'],
                   'result/call_sim_cost_s': metrics['call_sim_cost_s'],
                   'result/http_attempts': metrics['http_attempts']})
    # Partial snapshots keep known log aggregates, explicitly labelled incomplete.
    usage = record.get('model_usage')
    if usage != result.get('model_usage'):
        raise ValueError('Zone-study provider usage summary mismatch')
    if usage is not None:
        for key in ('requests', 'tokens_total_known', 'usage_unknown_requests'):
            values['provider/' + key] = usage.get(key)
        values['provider/tokens_total'] = usage.get('tokens_total_known') if usage.get('tokens_complete') else None
        w.text('result/provider_usage', usage)
    command_files = [f'robots/{r}/inputs/commands.jsonl' for r in record['robots']]
    if command_files and all(p in src.files for p in command_files):
        values['result/commands'] = sum(len(src.read_jsonl(p)) for p in command_files)
    for tag, value in values.items():
        w.scalar(tag, float(value) if isinstance(value, bool) else value)
    count, hash_only_images = request_images(src, record, w, max_images)
    videos = media_evidence(src)
    camera = src.read('eval_only/top_camera.json', required='eval_only/top_camera.json' in src.files)
    w.text('evaluation/referee', evaluation)
    w.text('evaluation/top_camera_configuration', camera if camera is not None else {'status': 'missing'})
    w.text('result/trial_record', record)
    meta = {'family': 'zone-study', 'run_id': result['run_id'], 'condition': record['condition'],
            'evidence_identity': identity,
            **join.envelope_keys(identity, record['orders']),
            'plan_sha256': pin,
            'case': record['scenario'], 'seed': record['seed'], 'source_sha': raw.get('code', {}).get('sha'),
            'outcome': record['end_reason'], 'failure_class': record.get('failure_class'),
            'clock': 'SIM', 'sim_horizon_s': metrics['sim_horizon_s'],
            'tokens_complete': metrics['tokens_complete'],
            'record_complete': record.get('record_complete', True), 'missing': record.get('missing', []),
            'referee_status': metrics['referee_status'], 'plumbing_only': result.get('plumbing_only'),
            'success_source_field': 'study/trial_record.json + evaluation-only referee',
            'denominator_trials': 1, 'source_metrics': values,
            'request_archive_rows': count, 'request_images_hash_only': hash_only_images,
            'request_images_verified': sum(p.startswith('study/request_images/') for p in src.files),
            'top_camera_config_present': camera is not None,
            'top_rgb_video_registered': any(v['kind'] == 'top_rgb' for v in videos),
            'video_declarations': videos,
            'scope': 'terminal attempt; includes failures/interruptions; missing metrics remain absent'}
    hashes = {name: row['sha256'] for name, row in src.files.items()}
    meta['derived'] = join.derivations(values, hashes, [record['evidence_key'], *record['order_keys']])
    meta['relations'] = join.relation_rows(identity, record['orders'], metrics['success'], hashes, pin)
    w.text('provenance/derived_numbers', meta['derived'])
    w.text('provenance/composite_keys', join.envelope_keys(identity, record['orders']))
    if any(row['sha256'] != verified.get(name) for name, row in src.files.items()):
        raise ValueError('Zone-study source changed after manifest verification')
    return meta, values


class _ReadOnlySink:
    def scalar(self, *args, **kwargs):
        pass

    def text(self, *args, **kwargs):
        pass

    def image(self, *args, **kwargs):
        pass


def inspect_study(source):
    """Re-read the originals; never use an exported success as input evidence."""
    from scripts.tensorboard_tools.export import Source
    src = Source(Path(source))
    result = src.read('result.json', required=True)
    meta, values = export_study(src, _ReadOnlySink(), result, 0)
    for name, row in src.files.items():
        if file_digest(src.root / name) != row['sha256']:
            raise ValueError('Source changed during evidence inspection')
    return meta, values, src.files


def verify_publication(source, metadata):
    derived, _, _ = inspect_study(source)
    for field in ('evidence_key', 'order_keys', 'plan_sha256', 'source_metrics', 'derived', 'relations'):
        if digest(derived[field]) != digest(metadata.get(field)):
            raise ValueError(f'Published evidence differs from re-derived originals: {field}')
