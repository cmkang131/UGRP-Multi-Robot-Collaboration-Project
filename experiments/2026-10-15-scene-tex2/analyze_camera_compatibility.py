#!/usr/bin/env python3
"""Linux-only read-only compatibility tables; no simulator or acceptance gate."""
import argparse
from collections import Counter, defaultdict
import importlib.util
from pathlib import Path
import platform
import sys

BASELINES = ('floor_light_v1', 'floor_light_textured_v1')


def semantic(outputs):
    boxes = outputs.get('boxes_own_zone_v2', {})
    detections = boxes.get('detections', [])
    beam = outputs.get('beam_legacy_dark_band_v2', {})
    return {'box_kind_counts': dict(sorted(Counter(d['kind'] for d in detections).items())),
            'box_kind_range_class_counts': dict(sorted(Counter(d['kind'] + ':' + d['range_class'] for d in detections).items())),
            'box_clipped_kinds': sorted(boxes.get('clipped_kinds', [])),
            **{'beam_' + k: beam.get(k) for k in ('visible', 'end_visible', 'reason', 'grip_source')}}


def target_ranges(pose):
    if pose == 'box_palette':
        return [('box_' + c, 'own_zone:cyan' if c == 'cyan' else 'OWN_HSV:' + c)
                for c in ('cyan', 'red', 'green', 'yellow')]
    if pose == 'beam_end_bands':
        return [('beam_neg', 'beam_band:teal'), ('beam_pos', 'beam_band:blue')]
    if pose.startswith('paint_'):
        zone = pose[-1]
        labels = ['AMCL_all_paint_hues', 'legacy_goal:' + zone]
        labels += ['solo_zone'] if zone == 'C' else ['floor_goal_B'] if zone == 'B' else []
        return [('paint_zone_' + zone, label) for label in labels]
    return []


def support(measurements, target, label):
    visible = measurements.get('eval_target_visible_pixels', {}).get(target)
    if visible is None:
        visible = measurements.get('positive_fixture_expected_target_visible_pixels', {}).get(target)
    colour = measurements.get('colour_ranges', {}).get(label)
    pixels = colour.get('target_support_pixels', {}).get(target) if colour else None
    ratio = pixels / visible if visible is not None and visible > 0 and pixels is not None else None
    scope = 'UNVERIFIED_ZERO_VISIBILITY' if visible == 0 else 'MISSING_SOURCE' if ratio is None else 'MEASURED_ONLY'
    return {'visible_pixels': visible, 'support_pixels': pixels, 'ratio': ratio, 'scope': scope}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reader-script', type=Path, required=True)
    a = p.parse_args(argv)
    if platform.system() != 'Linux':
        p.error('Linux analysis host required; no Mac analysis execution')
    root, output = a.input.resolve(), a.output.resolve()
    if output.exists() or output.is_relative_to(root):
        p.error('output must be a new directory outside the read-only source run')
    spec = importlib.util.spec_from_file_location('scene_tex2_saved_reader', a.reader_script.resolve())
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    reader = module.Reader(root)
    source = reader.json('summary.json', kind='probe_summary')
    reader.manifest = reader.json(source.get('sha256_manifest', 'SHA256SUMS.json'), kind='probe_checksum_manifest')
    if not isinstance(reader.manifest, dict):
        raise ValueError('RUN_CHECKSUM_MANIFEST_REQUIRED')
    reader.record('summary.json', kind='probe_summary')
    index_spec = source.get('frame_index', {'path': 'frame-index.json'})
    index = reader.json(index_spec['path'], expected=index_spec.get('sha256'), kind='frame_index')
    frames, errors = [], list(source.get('unexecuted', []))
    for entry in index:
        if not entry.get('frame_analysed'):
            errors.append({'frame': entry.get('id'), 'reason': entry.get('failure_reason') or 'FRAME_NOT_ANALYSED'})
            continue
        try:
            metrics_path = reader.locate(entry['metrics_file'])
            if metrics_path.relative_to(root).as_posix() not in reader.manifest:
                raise ValueError('METRICS_ABSENT_FROM_RUN_MANIFEST')
            frame = reader.json(entry['metrics_file'], kind='frame_metrics')
            if frame['id'] != entry['id']:
                raise ValueError('FRAME_INDEX_ID_MISMATCH')
            for suffix, key in (('.png', 'png_sha256'), ('.jpg', 'jpeg_sha256')):
                reader.record(frame['id'] + suffix, expected=frame[key], kind='original_camera')
            for target, _ in target_ranges(frame['pose']):
                reader.record(Path('eval_only') / (frame['id'] + '--' + target + '.png'), kind='positive_eval_mask')
            frames.append(frame)
        except Exception as exc:
            errors.append({'frame': entry.get('id'), 'reason': f'{type(exc).__name__}: {exc}'})
    lookup = {(f['case'], f['profile']): f for f in frames}
    pairs, positive, equal_groups, support_groups = [], [], defaultdict(list), defaultdict(list)
    for frame in frames:
        for baseline in BASELINES:
            if baseline == frame['profile']:
                continue
            reference = lookup.get((frame['case'], baseline))
            if reference is None:
                errors.append({'frame': frame['id'], 'baseline': baseline, 'reason': 'BASELINE_CASE_ABSENT'})
                continue
            for encoding, current in frame['metrics'].items():
                previous = reference['metrics'].get(encoding)
                if previous is None:
                    errors.append({'frame': frame['id'], 'baseline': baseline, 'encoding': encoding, 'reason': 'BASELINE_ENCODING_ABSENT'})
                    continue
                identity = {'frame': frame['id'], 'case': frame['case'], 'profile': frame['profile'],
                            'baseline': baseline, 'encoding': encoding, 'pose': frame['pose'], 'robot': frame['robot']}
                current_semantic, old_semantic = semantic(current['detectors']), semantic(previous['detectors'])
                equal = {k: current_semantic[k] == old_semantic[k] for k in current_semantic}
                equal['full_output_dictionary'] = current['detectors'] == previous['detectors']
                pairs.append({**identity, 'current_semantic': current_semantic, 'baseline_semantic': old_semantic, 'equal': equal})
                group = (frame['profile'], baseline, encoding, frame['pose'])
                for field, same in equal.items():
                    equal_groups[(*group, field)].append(same)
                for target, label in target_ranges(frame['pose']):
                    now, old = support(current, target, label), support(previous, target, label)
                    row = {**identity, 'target': target, 'range': label, 'current': now, 'baseline_value': old}
                    row['support_delta'] = now['support_pixels'] - old['support_pixels'] if None not in (now['support_pixels'], old['support_pixels']) else None
                    row['ratio_delta'] = now['ratio'] - old['ratio'] if None not in (now['ratio'], old['ratio']) else None
                    positive.append(row)
                    support_groups[(*group, target, label)].append(row)
    equality = [{**dict(zip(('profile', 'baseline', 'encoding', 'pose', 'field'), key)),
                 'paired_frames_n': len(rows), 'identical_n': sum(rows), 'changed_n': len(rows) - sum(rows)}
                for key, rows in sorted(equal_groups.items())]
    support_summary = [{**dict(zip(('profile', 'baseline', 'encoding', 'pose', 'target', 'range'), key)),
        'paired_frames_n': len(rows),
        'current_visible_n': sum((r['current']['visible_pixels'] or 0) > 0 for r in rows),
        'baseline_visible_n': sum((r['baseline_value']['visible_pixels'] or 0) > 0 for r in rows),
        **{side: {field: module.distribution(r[side][field] for r in rows) for field in ('visible_pixels', 'support_pixels', 'ratio')}
           for side in ('current', 'baseline_value')},
        'support_delta': module.distribution(r['support_delta'] for r in rows),
        'ratio_delta': module.distribution(r['ratio_delta'] for r in rows)} for key, rows in sorted(support_groups.items())]
    reader.check_unchanged()
    errors.extend(reader.errors)
    errors = [{'category': row.get('category', 'ANALYSIS_SOURCE_ERROR'),
               'blocking_object': row.get('blocking_object', 'saved_probe_source'),
               'minimum_gap_m': row.get('minimum_gap_m'), **row} for row in errors]
    output.mkdir(parents=True, exist_ok=False)
    artifacts = {name: module.write_parts(output, name, rows) for name, rows in
                 (('semantic-pairs', pairs), ('semantic-counts', equality), ('positive-support-pairs', positive),
                  ('positive-support-distributions', support_summary), ('source-errors', errors),
                  ('source-checksums', [reader.sources[k] for k in sorted(reader.sources)]))}
    summary = {'schema': 'ugrp.scene_tex2_compatibility.v1', 'status': 'MEASURED_ONLY', 'ready_decision': 'not made',
        'input': str(root), 'source_sha': source.get('source_sha'), 'input_status': source.get('status'),
        'analysis_script_sha256': module.digest(Path(__file__)), 'reader_script_sha256': module.digest(a.reader_script),
        'indexed_frames_n': len(index), 'analysed_frames_n': len(frames), 'paired_encodings_n': len(pairs),
        'source_errors_n': len(errors), 'incomplete': bool(errors or source.get('status') == 'RUNNING'), 'artifacts': artifacts,
        'limits': ['No new acceptance threshold or ready verdict.', 'Zero visible pixels are unverified; both-negative equality is not positive detection evidence.',
                   'Full dictionary differences include numeric estimates/debug values; semantic fields are reported separately.',
                   'Black-band detector does not validate teal/blue band identity. Paint ranges are pixel support, not complete zone-boundary detector verification.',
                   'Segmentation masks and positions remain evaluation-only.'],
        'reproduction_command': [sys.executable, str(Path(__file__).resolve()), '--input', str(root), '--output', str(output),
                                 '--reader-script', str(a.reader_script.resolve())]}
    module.write_json(output / 'summary.json', summary)
    module.write_json(output / 'SHA256SUMS.json', {p.name: module.digest(p) for p in sorted(output.iterdir()) if p.is_file()})
    print(f'MEASURED_ONLY frames={len(frames)} pairs={len(pairs)} source_errors={len(errors)}')
    return int(summary['incomplete'])


if __name__ == '__main__':
    raise SystemExit(main())
