#!/usr/bin/env python3
"""Linux read-only scene-tex2 digest and saved-drive-frame ffmpeg montage.

No simulation, image detection, control, acceptance tuning or ready verdict.
All measurements come from source-checked saved probe records.
"""
import argparse
from collections import defaultdict
import importlib.util
from pathlib import Path
import platform
import sys

V2 = 'walls_floor_textured_v2'


def micro(rows):
    counts = {k: sum(r.get('rgb_only_classification', {}).get(k, 0) for r in rows) for k in ('tp', 'fp', 'fn')}
    tp, fp, fn = (counts[k] for k in ('tp', 'fp', 'fn'))
    return {**counts, 'iou': tp / (tp + fp + fn) if tp + fp + fn else None,
            'precision': tp / (tp + fp) if tp + fp else None, 'recall': tp / (tp + fn) if tp + fn else None,
            'classified_frames_n': sum('rgb_only_classification' in r for r in rows)}


def metrics_digest(frames, module):
    surfaces, funnels, positives, colours, bands = [], [], [], [], []
    selected = [f for f in frames if f['profile'] == V2]
    for encoding in ('png', 'jpeg'):
        scopes = [('all', selected), ('drive', [f for f in selected if f['pose'] == 'drive'])]
        scopes += [('drive_map:' + name, [f for f in selected if f['pose'] == 'drive' and f['map'] == name])
                   for name in sorted({f['map'] for f in selected})]
        for scope, group in scopes:
            measurements = [f['metrics'][encoding] for f in group if encoding in f['metrics']]
            for surface in ('wall', 'floor'):
                rows = [m['surfaces'][surface] for m in measurements]
                surfaces.append({'profile': V2, 'encoding': encoding, 'scope': scope, 'surface': surface,
                    'frames_n': len(rows), 'visible_frames_n': sum(r['eval_visible_pixels'] > 0 for r in rows),
                    'visible_pixels': module.distribution(r['eval_visible_pixels'] for r in rows),
                    'orb_count': module.distribution(r['orb_count'] for r in rows),
                    'interior_orb_count': module.distribution(r.get('orb_interior_descriptor_support_count') for r in rows),
                    'classification_micro': micro(rows)})
            wall = [m['surfaces']['wall'] for m in measurements]
            visible = [r for r in wall if r['eval_visible_pixels'] > 0]
            orb = [r for r in visible if r['orb_count'] > 0]
            interior = [r for r in orb if r.get('orb_interior_descriptor_support_count', 0) > 0]
            counts = [len(wall), len(visible), len(orb), len(interior)]
            funnels.append({'encoding': encoding, 'scope': scope,
                'stages': [{'stage': stage, 'cumulative_n': counts[i],
                            'rejected_n': counts[i - 1] - counts[i] if i else 0}
                           for i, stage in enumerate(('saved_frame', 'wall_visible', 'wall_orb_positive', 'wall_interior_orb_positive'))],
                'interpretation': 'zero/nonzero describes observed presence only; no ready criterion'})
            if scope.startswith('drive_map:'):
                continue
            for surface in ('wall', 'floor'):
                grouped = defaultdict(list)
                for m in measurements:
                    for label, row in m.get('colour_ranges', {}).items():
                        grouped[label].append(row['surface_false_pixels'][surface])
                ranked = sorted(grouped, key=lambda label: (-sum(grouped[label]), label))
                colours.append({'encoding': encoding, 'scope': scope, 'surface': surface,
                    'ranges_observed_n': len(grouped), 'range_counts_per_frame': sorted({len(m.get('colour_ranges', {})) for m in measurements}),
                    'all_range_false_pixels_sum': sum(sum(rows) for rows in grouped.values()),
                    'top10': [{'range': label, 'false_pixels': module.distribution(grouped[label]),
                               'frames_with_hits_n': sum(v > 0 for v in grouped[label])} for label in ranked[:10]],
                    'interpretation': 'ranges overlap each other; sums are not unique pixel counts'})
            detectors = defaultdict(list)
            for m in measurements:
                for name, row in m.get('wall_band_detectors', {}).get('detectors', {}).items():
                    detectors[name].append(row)
            bands.append({'encoding': encoding, 'scope': scope, 'detectors': {name: {
                'frames_n': len(rows), 'candidate_total': sum(r['candidate_n'] for r in rows),
                'candidate_column_total': sum(r['candidate_columns_n'] for r in rows)} for name, rows in sorted(detectors.items())}})
        targets = defaultdict(list)
        for frame in selected:
            m = frame['metrics'].get(encoding, {})
            for target, pixels in m.get('positive_fixture_expected_target_visible_pixels', {}).items():
                targets[(frame['pose'], target)].append((frame['robot'], pixels))
        for (pose, target), rows in sorted(targets.items()):
            positives.append({'encoding': encoding, 'pose': pose, 'target': target, 'frames_n': len(rows),
                'visible_frames_n': sum(pixels > 0 for _, pixels in rows), 'visible_pixels': module.distribution(p for _, p in rows),
                'by_robot': {robot: {'frames_n': sum(r == robot for r, _ in rows),
                                    'visible_frames_n': sum(r == robot and p > 0 for r, p in rows)} for robot in sorted({r for r, _ in rows})},
                'zero_visibility_scope': 'unverified, not a positive-detection pass'})
    return {'surface_metrics': surfaces, 'wall_feature_funnel': funnels, 'positive_visibility': positives,
            'colour_overlap_top10': colours, 'wall_band_candidates': bands}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--reader-script', required=True, type=Path)
    args = parser.parse_args(argv)
    if platform.system() != 'Linux':
        parser.error('Linux/GCP only; no Mac digest or review composition')
    root, output = args.input.resolve(), args.output.resolve()
    if output.exists() or output.is_relative_to(root):
        parser.error('output must be new and outside the read-only source run')
    spec = importlib.util.spec_from_file_location('scene_tex2_digest_reader', args.reader_script.resolve())
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    reader, frames, errors, source, index = module.Reader(root), [], [], {}, []
    try:
        source = reader.json('summary.json', kind='probe_summary')
        reader.manifest = reader.json(source.get('sha256_manifest', 'SHA256SUMS.json'), kind='probe_checksum_manifest')
        if not isinstance(reader.manifest, dict):
            raise ValueError('SOURCE_CHECKSUM_MANIFEST_REQUIRED')
        reader.record('summary.json', kind='probe_summary')
        entry = source.get('frame_index', {'path': 'frame-index.json'})
        index = reader.json(entry['path'], expected=entry.get('sha256'), kind='frame_index')
        for entry in index:
            try:
                if not entry.get('frame_analysed'):
                    raise ValueError(entry.get('failure_reason') or 'FRAME_ANALYSIS_NOT_COMPLETE')
                path = reader.locate(entry['metrics_file'])
                if path.relative_to(root).as_posix() not in reader.manifest:
                    raise ValueError('METRICS_NOT_IN_SOURCE_MANIFEST')
                frame = reader.json(entry['metrics_file'], kind='frame_metrics')
                if frame['id'] != entry['id']:
                    raise ValueError('INDEX_METRICS_ID_MISMATCH')
                for suffix, key in (('.png', 'png_sha256'), ('.jpg', 'jpeg_sha256')):
                    reader.record(frame['id'] + suffix, expected=frame[key], kind='source_own_camera')
                frames.append(frame)
            except Exception as exc:
                errors.append({'frame': entry.get('id'), 'reason': f'{type(exc).__name__}: {exc}'})
        errors.extend(source.get('unexecuted', []))
        if source.get('status') == 'RUNNING' or len(frames) != source.get('planned_frames', len(index)):
            errors.append({'reason': 'SOURCE_RUN_UNFINISHED_OR_PLANNED_FRAMES_MISSING'})
    except Exception as exc:
        errors.append({'reason': f'{type(exc).__name__}: {exc}'})
    # Include the evaluation-mask images underlying the saved surface metrics,
    # not just the RGBs selected for the montage. Input files remain untouched.
    if reader.manifest is not None:
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.suffix.lower() in ('.png', '.jpg', '.jpeg'):
                try:
                    if path.relative_to(root).as_posix() not in reader.manifest:
                        raise ValueError('IMAGE_NOT_IN_SOURCE_MANIFEST')
                    reader.record(path, kind='source_camera_or_eval_mask')
                except Exception as exc:
                    errors.append({'source': str(path.relative_to(root)), 'reason': str(exc)})
    output.mkdir(parents=True, exist_ok=False)
    sections = metrics_digest(frames, module)
    artifacts = {name: module.write_parts(output, name, rows) for name, rows in sections.items()}
    montage_frames = [{**f, 'map': f'{f["map"]}__view{f["view"]}'} for f in frames if f['pose'] == 'drive']
    maps = sorted({f['map'] for f in montage_frames})
    try:
        if not maps:
            raise ValueError('NO_VERIFIED_DRIVE_FRAMES')
        montage = module.make_montage(reader, output, montage_frames, maps, source.get('profiles', []),
                                      poses=('drive',), filename='drive-all-views.jpg')
        if any('reason' in tile for tile in montage['tiles']):
            errors.append({'reason': 'DRIVE_MONTAGE_HAS_UNMEASURED_TILES'})
        artifacts['drive_montage'] = module.write_json(output / 'drive-montage.json', montage)
    except Exception as exc:
        errors.append({'reason': 'DRIVE_MONTAGE_ERROR:' + str(exc)})
    reader.check_unchanged()
    errors.extend(reader.errors)
    errors = [{'category': row.get('category', 'DIGEST_SOURCE_ERROR'), 'blocking_object': row.get('blocking_object', 'saved_probe_source'),
               'minimum_gap_m': row.get('minimum_gap_m'), **row} for row in errors]
    artifacts['source_errors'] = module.write_parts(output, 'source-errors', errors)
    artifacts['source_checksums'] = module.write_parts(output, 'source-checksums', [reader.sources[k] for k in sorted(reader.sources)])
    summary = {'schema': 'ugrp.scene_tex2_camera_digest.v1', 'status': 'SOURCE_ERROR' if errors else 'MEASURED_ONLY',
        'ready_decision': 'not made; presence counts are not acceptance thresholds', 'input': str(root),
        'source_sha': source.get('source_sha'), 'input_status': source.get('status'),
        'analysis_script_sha256': module.digest(Path(__file__)), 'reader_script_sha256': module.digest(args.reader_script),
        'planned_frames_n': source.get('planned_frames'), 'verified_frames_n': len(frames),
        'v2_all_frames_n': sum(f['profile'] == V2 for f in frames),
        'v2_drive_frames_n': sum(f['profile'] == V2 and f['pose'] == 'drive' for f in frames),
        'source_error_n': len(errors), 'artifacts': artifacts,
        'limits': ['Source evaluation masks never enter control.', 'No extra render, detector run, threshold fitting or ready claim.',
                   'Static view metrics do not establish localization or task success; zero-visible positives remain unverified.'],
        'reproduction_command': [sys.executable, str(Path(__file__).resolve()), '--input', str(root), '--output', str(output),
                                 '--reader-script', str(args.reader_script.resolve())]}
    module.write_json(output / 'summary.json', summary)
    module.write_json(output / 'SHA256SUMS.json', {p.name: module.digest(p) for p in sorted(output.iterdir()) if p.is_file()})
    print(f'{summary["status"]} v2_all={summary["v2_all_frames_n"]} v2_drive={summary["v2_drive_frames_n"]} errors={len(errors)}')
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
