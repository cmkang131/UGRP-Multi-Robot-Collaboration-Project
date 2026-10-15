#!/usr/bin/env python3
"""Read-only scene-tex2 camera measurements and a finite GCP-only montage.

Reads finished or partial probe outputs, including verified zstd JSON. No
simulator, controller, estimator or renderer is imported or executed. Results
are measured-only: this tool introduces no feature, colour or accuracy gate.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys

MAX_JSON_BYTES = 65536  # existing project JSON storage limit
MAX_MONTAGE_BYTES = 8_000_000  # user-requested <=8 MB per review image
V2 = 'walls_floor_textured_v2'
BASELINES = ('floor_light_v1', 'floor_light_textured_v1')
OCCLUDED = 'high_beam_peer_occluded'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode()


def distribution(values):
    values = list(values)
    finite = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return {'n': len(finite), 'missing_or_nonfinite_n': len(values) - len(finite),
            'min': min(finite) if finite else None,
            'median': statistics.median(finite) if finite else None,
            'max': max(finite) if finite else None,
            'sum': math.fsum(finite), 'zero_n': sum(v == 0 for v in finite)}


def write_json(path, value):
    raw = canonical(value)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError('JSON_EXCEEDS_PROJECT_CAP:' + str(path))
    path.write_bytes(raw)
    return {'path': path.name, 'sha256': digest(path), 'bytes': len(raw)}


def write_parts(output, stem, rows):
    """Split by encoded bytes, without rounding away measurements."""
    parts, pending = [], []
    for row in rows:
        candidate = pending + [row]
        if len(canonical(candidate)) > MAX_JSON_BYTES:
            if not pending:
                raise ValueError('ONE_DETAIL_ROW_EXCEEDS_JSON_CAP:' + stem)
            parts.append(write_json(output / f'{stem}-{len(parts):03d}.json', pending))
            pending = [row]
        else:
            pending = candidate
    if pending or not parts:
        parts.append(write_json(output / f'{stem}-{len(parts):03d}.json', pending))
    return {'rows_n': len(rows), 'parts': parts}


def write_csv(path, rows, fields):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, separators=(',', ':'))
                             if isinstance(value, (dict, list, tuple)) else value for key, value in row.items()})
    return {'path': path.name, 'sha256': digest(path), 'bytes': path.stat().st_size}


class Reader:
    """Record both stored and decompressed hashes; never modify input files."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.sources = {}
        self.manifest = None
        self.errors = []

    def locate(self, relative):
        path = Path(relative)
        # Probe summary has historical absolute run paths. Rebase those names
        # only; a supplied metrics path may never escape the input directory.
        if path.is_absolute():
            path = path.resolve()
            path = path.relative_to(self.root) if path.is_relative_to(self.root) else Path(path.name)
        path = (self.root / path).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('SOURCE_PATH_ESCAPES_INPUT:' + str(relative))
        if not path.is_file() and path.suffix != '.zst':
            compressed = path.with_name(path.name + '.zst')
            if compressed.is_file():
                path = compressed
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def record(self, path, *, expected=None, kind='source'):
        path = self.locate(path)
        relative = path.relative_to(self.root).as_posix()
        before = path.stat()
        actual = digest(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('SOURCE_CHANGED_DURING_READ:' + relative)
        manifest_sha = self.manifest.get(relative) if self.manifest is not None else None
        for label, wanted in (('frame', expected), ('run_manifest', manifest_sha)):
            if wanted is not None and wanted != actual:
                raise ValueError(f'SOURCE_SHA256_MISMATCH:{label}:{relative}')
        record = {'path': relative, 'kind': kind, 'stored_sha256': actual,
                  'bytes': before.st_size, 'manifest_sha256': manifest_sha,
                  'declared_sha256': expected, 'mtime_ns_at_read': before.st_mtime_ns}
        self.sources[relative] = {**self.sources.get(relative, {}), **record}
        return path

    def json(self, relative, *, expected=None, kind='json'):
        path = self.record(relative, expected=expected, kind=kind)
        stored = path.read_bytes()
        if hashlib.sha256(stored).hexdigest() != self.sources[path.relative_to(self.root).as_posix()]['stored_sha256']:
            raise ValueError('SOURCE_CHANGED_DURING_JSON_READ:' + str(path))
        raw = subprocess.check_output(['zstd', '-q', '-d', '-c', '--', str(path)]) if path.suffix == '.zst' else stored
        raw_sha = hashlib.sha256(raw).hexdigest()
        self.sources[path.relative_to(self.root).as_posix()]['decompressed_sha256'] = raw_sha
        if path.suffix == '.zst':
            meta_path = path.with_name(path.name[:-4] + '.compression.json')
            if meta_path.is_file():
                meta = self.json(meta_path, kind='compression_proof')
                if meta.get('original_sha256') != raw_sha or meta.get('compressed_sha256') != digest(path):
                    raise ValueError('ZSTD_COMPRESSION_PROOF_MISMATCH:' + str(path))
        return json.loads(raw)

    def check_unchanged(self):
        for relative, row in self.sources.items():
            path = self.root / relative
            current = path.stat()
            if (current.st_size, current.st_mtime_ns) != (row['bytes'], row['mtime_ns_at_read']):
                self.errors.append({'category': 'SOURCE_CHANGED_DURING_ANALYSIS', 'source': relative,
                                    'reason': 'size/mtime changed after the checksum read'})


def grouping(frame, encoding):
    return (frame['profile'], encoding, frame['pose'], frame['robot'])


def summarize_frames(frames, baselines=BASELINES):
    surfaces, segmentation, occlusion, boundaries = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    colour_samples, colour_raw, frame_raw = defaultdict(list), [], []
    by_case = {(f['case'], f['profile']): f for f in frames}
    for frame in frames:
        for encoding, measurements in frame['metrics'].items():
            key = grouping(frame, encoding)
            flat = {k: frame[k] for k in ('id', 'case', 'map', 'view', 'pose', 'robot', 'profile')}
            flat.update(encoding=encoding, beam_pixels=measurements.get('eval_beam_pixels'),
                        peer_pixels=measurements.get('eval_partner_pixels'))
            for surface in ('wall', 'floor'):
                row = measurements['surfaces'][surface]
                surfaces[(*key, surface)].append(row)
                segmentation[(*key, surface)].append(row.get('rgb_only_classification', {}))
                for field in ('orb_count', 'orb_interior_descriptor_support_count', 'eval_visible_pixels'):
                    flat[surface + '_' + field] = row.get(field)
            frame_raw.append(flat)
            if frame['pose'] == OCCLUDED:
                occlusion[key].append({'beam_pixels': measurements.get('eval_beam_pixels'),
                                       'peer_pixels': measurements.get('eval_partner_pixels'),
                                       'wall': measurements['surfaces']['wall']})
            for label, colour in measurements.get('colour_ranges', {}).items():
                for surface in ('wall', 'floor'):
                    colour_samples[(frame['profile'], encoding, label, surface)].append(
                        colour['surface_false_pixels'][surface])
                colour_raw.append({**flat, 'range': label, 'pixels': colour['pixels'],
                    'wall_false_pixels': colour['surface_false_pixels']['wall'],
                    'floor_false_pixels': colour['surface_false_pixels']['floor'],
                    'target_support_pixels': colour.get('target_support_pixels', {}), 'mask_sha256': colour.get('mask_sha256')})
            for detector, row in measurements.get('wall_band_detectors', {}).get('detectors', {}).items():
                boundaries[(*key, detector)].append(row)
    fields = ('profile', 'encoding', 'pose', 'robot')
    surface_stats = [{**dict(zip(fields, key[:4])), 'surface': key[4],
        **{field: distribution(r.get(field) for r in rows) for field in
           ('orb_count', 'orb_interior_descriptor_support_count', 'eval_visible_pixels')}}
        for key, rows in sorted(surfaces.items())]
    segmentation_stats = [{**dict(zip(fields, key[:4])), 'surface': key[4],
        **{field: distribution(r.get(field) for r in rows) for field in ('iou', 'recall', 'precision')},
        'tp_sum': sum(r.get('tp', 0) for r in rows), 'fp_sum': sum(r.get('fp', 0) for r in rows),
        'fn_sum': sum(r.get('fn', 0) for r in rows)} for key, rows in sorted(segmentation.items())]
    occlusion_stats = [{**dict(zip(fields, key)), 'frames_n': len(rows),
        'beam_pixels': distribution(r['beam_pixels'] for r in rows),
        'peer_pixels': distribution(r['peer_pixels'] for r in rows),
        'both_occluders_visible_n': sum((r['beam_pixels'] or 0) > 0 and (r['peer_pixels'] or 0) > 0 for r in rows),
        'wall_visible_n': sum(r['wall']['eval_visible_pixels'] > 0 for r in rows),
        'wall_orb_remaining_n': sum(r['wall']['orb_count'] > 0 for r in rows),
        'wall_interior_orb_remaining_n': sum(r['wall'].get('orb_interior_descriptor_support_count', 0) > 0 for r in rows),
        'both_occluders_visible_and_wall_interior_orb_remaining_n': sum(
            (r['beam_pixels'] or 0) > 0 and (r['peer_pixels'] or 0) > 0 and
            r['wall'].get('orb_interior_descriptor_support_count', 0) > 0 for r in rows),
        'wall_orb': distribution(r['wall']['orb_count'] for r in rows),
        'wall_interior_orb': distribution(r['wall'].get('orb_interior_descriptor_support_count') for r in rows)}
        for key, rows in sorted(occlusion.items())]
    colour_stats = [{'profile': key[0], 'encoding': key[1], 'range': key[2], 'surface': key[3],
                     'surface_false_pixels': distribution(rows), 'frames_with_false_pixels_n': sum(v > 0 for v in rows)}
                    for key, rows in sorted(colour_samples.items())]
    boundary_stats = [{**dict(zip(fields, key[:4])), 'detector': key[4],
        **{field: distribution(r.get(field) for r in rows) for field in
           ('candidate_n', 'candidate_columns_n', 'eval_visible_boundary_columns_n', 'eval_candidates_without_visible_boundary_n')},
        'nearest_boundary_residual_px': distribution(v for r in rows for v in r.get('eval_nearest_boundary_residual_px', [])),
        'accuracy_threshold_added': False} for key, rows in sorted(boundaries.items())]

    colour_pairs, detector_pairs, pair_raw = defaultdict(list), defaultdict(list), []
    missing_pairs = []
    for frame in frames:
        for baseline in baselines:
            if baseline == frame['profile']:
                continue
            reference = by_case.get((frame['case'], baseline))
            if reference is None:
                missing_pairs.append({'frame': frame['id'], 'baseline': baseline, 'reason': 'MATCHING_BASELINE_FRAME_ABSENT'})
                continue
            for encoding, current in frame['metrics'].items():
                old = reference['metrics'].get(encoding)
                if old is None:
                    missing_pairs.append({'frame': frame['id'], 'baseline': baseline, 'encoding': encoding,
                                          'reason': 'MATCHING_BASELINE_ENCODING_ABSENT'})
                    continue
                key = (frame['profile'], baseline, encoding, frame['pose'], frame['robot'])
                detectors = set(current.get('detectors', {})) | set(old.get('detectors', {}))
                for detector in ['ALL_ACTUAL_DETECTORS', *sorted(detectors)]:
                    a = current.get('detectors', {}) if detector == 'ALL_ACTUAL_DETECTORS' else current.get('detectors', {}).get(detector)
                    b = old.get('detectors', {}) if detector == 'ALL_ACTUAL_DETECTORS' else old.get('detectors', {}).get(detector)
                    detector_pairs[(*key, detector)].append(a == b)
                for label, colour in current.get('colour_ranges', {}).items():
                    previous = old.get('colour_ranges', {}).get(label)
                    if previous is None:
                        missing_pairs.append({'frame': frame['id'], 'baseline': baseline, 'encoding': encoding,
                                              'range': label, 'reason': 'BASELINE_RANGE_ABSENT'})
                        continue
                    targets = set(colour.get('target_support_pixels', {})) | set(previous.get('target_support_pixels', {}))
                    pair = {'frame': frame['id'], 'case': frame['case'], 'profile': frame['profile'],
                            'baseline': baseline, 'encoding': encoding, 'range': label,
                            'target_support_pixel_delta': {k: colour.get('target_support_pixels', {}).get(k, 0) -
                                previous.get('target_support_pixels', {}).get(k, 0) for k in sorted(targets)}}
                    for surface in ('wall', 'floor'):
                        a, b = colour['surface_false_pixels'][surface], previous['surface_false_pixels'][surface]
                        pair[surface + '_false_delta'] = a - b
                        pair[surface + '_new_false_frame'] = a > 0 and b == 0
                        pair[surface + '_excess_count'] = max(0, a - b)
                    pair_raw.append(pair)
                    colour_pairs[(frame['profile'], baseline, encoding, label)].append(pair)
    pair_stats = []
    for key, rows in sorted(colour_pairs.items()):
        targets = sorted(set(t for r in rows for t in r['target_support_pixel_delta']))
        pair_stats.append({'profile': key[0], 'baseline': key[1], 'encoding': key[2], 'range': key[3],
            'paired_frames_n': len(rows), **{surface: {
                'false_pixel_count_delta': distribution(r[surface + '_false_delta'] for r in rows),
                'new_false_frame_n': sum(r[surface + '_new_false_frame'] for r in rows),
                'excess_false_pixel_count_sum': sum(r[surface + '_excess_count'] for r in rows)} for surface in ('wall', 'floor')},
            'target_support_pixel_delta': {t: distribution(r['target_support_pixel_delta'].get(t, 0) for r in rows) for t in targets}})
    parity_stats = [{**dict(zip(('profile', 'baseline', 'encoding', 'pose', 'robot', 'detector'), key)),
                     'paired_frames_n': len(rows), 'identical_n': sum(rows), 'changed_n': len(rows) - sum(rows)}
                    for key, rows in sorted(detector_pairs.items())]
    return {'surfaces': surface_stats, 'segmentation': segmentation_stats, 'occlusion': occlusion_stats,
            'colour_ranges': colour_stats, 'colour_baseline_comparisons': pair_stats,
            'actual_detector_parity': parity_stats, 'wall_bands': boundary_stats,
            'frame_rows': frame_raw, 'colour_frame_rows': colour_raw, 'colour_pair_rows': pair_raw,
            'missing_pairs': missing_pairs}


def histogram_percentiles(counts, percentiles=(0, 1, 5, 50, 95, 99, 100)):
    """Exact empirical linear percentiles from integer-value frequencies.

    This matches NumPy's default rank=(N-1)*p/100 definition without retaining
    every camera pixel in RAM. Values/percentiles are descriptive, not gates.
    """
    total = sum(int(n) for n in counts)
    if not total:
        return {str(p): None for p in percentiles}
    cumulative, running = [], 0
    for count in counts:
        running += int(count)
        cumulative.append(running)
    from bisect import bisect_right
    result = {}
    for p in percentiles:
        rank = (total - 1) * p / 100
        lower, upper = math.floor(rank), math.ceil(rank)
        lo, hi = bisect_right(cumulative, lower), bisect_right(cumulative, upper)
        result[str(p)] = lo + (rank - lower) * (hi - lo)
    return result


def surface_hsv_statistics(reader, frames):
    """Truth masks score saved images only; no fitting or control feedback.

    A 3x3 erosion discards the one-pixel neighborhood that can intersect the
    four samples of a bilinear 2x2 interpolation footprint. It does not claim
    to eliminate JPEG block/ringing contamination or all texture boundaries.
    Both all-visible and eroded masks are retained, not selectively dropped.
    """
    import cv2
    import numpy as np
    histograms = defaultdict(lambda: np.zeros((3, 256), dtype=np.int64))
    details, errors = [], []
    for frame in frames:
        try:
            masks = {}
            for surface in ('wall', 'floor'):
                path = reader.record(Path('eval_only') / (frame['id'] + '--' + surface + '.png'), kind='hsv_eval_mask')
                mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                if mask is None:
                    raise ValueError('CANNOT_DECODE_EVAL_SURFACE_MASK:' + str(path))
                mask = (mask > 0).astype(np.uint8)
                masks[(surface, 'visible')] = mask > 0
                masks[(surface, 'interior_3x3')] = cv2.erode(mask, np.ones((3, 3), np.uint8),
                    borderType=cv2.BORDER_CONSTANT, borderValue=0) > 0
            for encoding, suffix in (('png', '.png'), ('jpeg', '.jpg')):
                path = reader.record(frame['id'] + suffix, expected=frame[encoding + '_sha256'], kind='hsv_original_frame')
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is None:
                    raise ValueError('CANNOT_DECODE_HSV_SOURCE:' + str(path))
                hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
                for (surface, scope), mask in masks.items():
                    if mask.shape != hsv.shape[:2]:
                        raise ValueError('SURFACE_HSV_MASK_SHAPE_MISMATCH')
                    pixels = hsv[mask]
                    counts = np.stack([np.bincount(pixels[:, c], minlength=256) for c in range(3)])
                    histograms[(frame['profile'], encoding, surface, scope)] += counts
                    details.append({'frame': frame['id'], 'map': frame['map'], 'pose': frame['pose'],
                        'robot': frame['robot'], 'profile': frame['profile'], 'encoding': encoding,
                        'surface': surface, 'scope': scope, 'pixels_n': int(mask.sum()),
                        **{channel: histogram_percentiles(counts[c]) for c, channel in enumerate(('H', 'S', 'V'))}})
        except (OSError, ValueError, KeyError) as exc:
            errors.append({'frame': frame['id'], 'category': 'SURFACE_HSV_HOST_ERROR', 'reason': str(exc),
                           'blocking_object': 'saved_rgb_or_eval_mask', 'minimum_gap_m': None})
    rows = [{'profile': key[0], 'encoding': key[1], 'surface': key[2], 'scope': key[3],
             'pixels_n': int(counts[0].sum()),
             **{channel: histogram_percentiles(counts[c]) for c, channel in enumerate(('H', 'S', 'V'))}}
            for key, counts in sorted(histograms.items())]
    return rows, details, errors


def make_montage(reader, output, frames, map_names, profiles):
    if platform.system() != 'Linux':
        raise RuntimeError('MONTAGE_GCP_LINUX_ONLY')
    from PIL import Image, ImageDraw, ImageFont
    # Half-native thumbnails (640x480 -> 320x240); layout/codec choices do not
    # affect measurements, which always come from the original saved frames.
    width, height, banner = 320, 240, 76
    poses = ('drive', OCCLUDED)
    image = Image.new('RGB', (width * len(profiles), (height + banner) * len(map_names) * len(poses)), 'white')
    draw, font = ImageDraw.Draw(image), ImageFont.load_default()
    chosen = []
    for mi, map_name in enumerate(map_names):
        for pi, pose in enumerate(poses):
            y = (mi * len(poses) + pi) * (height + banner)
            for column, profile in enumerate(profiles):
                x = column * width
                candidates = [f for f in frames if f['map'] == map_name and f['pose'] == pose and
                              f['robot'] == 'r1' and f['profile'] == profile]
                candidates.sort(key=lambda f: (f['view'], f['id']))
                if not candidates:
                    draw.text((x + 5, y + 5), f'{map_name}\n{profile}\n{pose}\nMISSING FRAME', fill='red', font=font)
                    chosen.append({'map': map_name, 'profile': profile, 'pose': pose, 'reason': 'NO_MATCHING_FRAME'})
                    continue
                frame = candidates[0]
                path = reader.record(frame['id'] + '.png', expected=frame['png_sha256'], kind='montage_original_png')
                with Image.open(path) as original:
                    thumbnail = original.convert('RGB')
                    thumbnail.thumbnail((width, height), Image.Resampling.LANCZOS)
                image.paste(thumbnail, (x, y))
                metrics = frame['metrics']['png']
                wall, floor = metrics['surfaces']['wall'], metrics['surfaces']['floor']
                label = (f'{map_name} view{frame["view"]} r1\n{profile}\n{pose}\n'
                         f'ORB wall={wall["orb_count"]} interior={wall.get("orb_interior_descriptor_support_count")} floor={floor["orb_count"]}\n'
                         f'wallpx={wall["eval_visible_pixels"]} beam={metrics.get("eval_beam_pixels")} peer={metrics.get("eval_partner_pixels")}')
                draw.multiline_text((x + 5, y + height + 3), label, fill='black', font=font, spacing=2)
                chosen.append({'frame': frame['id'], 'source_png': path.relative_to(reader.root).as_posix(),
                               'source_png_sha256': digest(path), 'metrics_png': label})
    path = output / 'camera-montage.jpg'
    # Only display compression changes if needed; no metric image is modified.
    for quality in (85, 75, 65, 55):
        stream = io.BytesIO()
        image.save(stream, format='JPEG', quality=quality, optimize=True)
        if stream.tell() <= MAX_MONTAGE_BYTES:
            path.write_bytes(stream.getvalue())
            return {'path': path.name, 'sha256': digest(path), 'bytes': path.stat().st_size,
                    'jpeg_quality': quality, 'size_px': list(image.size), 'tiles': chosen,
                    'selection': 'first measured view per map/profile/pose, r1; PNG metrics; not selected for quality'}
    raise ValueError('MONTAGE_EXCEEDS_USER_8MB_LIMIT')


def run(input_dir, output):
    input_dir, output = Path(input_dir).resolve(), Path(output).resolve()
    if output.is_relative_to(input_dir):
        raise ValueError('OUTPUT_MUST_NOT_MODIFY_SOURCE_RUN_DIRECTORY')
    if output.exists():
        raise FileExistsError(output)
    reader = Reader(input_dir)
    source_summary = reader.json('summary.json', kind='probe_summary')
    manifest_available = False
    try:
        manifest_name = source_summary.get('sha256_manifest', 'SHA256SUMS.json')
        manifest = reader.json(manifest_name, kind='probe_checksum_manifest')
        if not isinstance(manifest, dict):
            raise ValueError('EXPECTED_SOURCE_CHECKSUM_OBJECT')
        reader.manifest = manifest
        manifest_available = True
        # Source summary was read before its manifest; now verify it too.
        reader.record('summary.json', kind='probe_summary')
    except FileNotFoundError:
        reader.errors.append({'category': 'SOURCE_MANIFEST_UNAVAILABLE', 'reason': 'Run may be unfinished; do not report complete verification'})
    index_spec = source_summary.get('frame_index', {'path': 'frame-index.json'})
    index = reader.json(index_spec['path'], expected=index_spec.get('sha256'), kind='frame_index')
    frames, host_errors = [], []
    for entry in index:
        if not entry.get('frame_analysed'):
            host_errors.append({'frame': entry.get('id'), 'category': 'FRAME_ANALYSIS_HOST_ERROR',
                                'reason': entry.get('failure_reason') or 'FRAME_ANALYSIS_NOT_COMPLETED',
                                'blocking_object': 'static_camera_analysis', 'minimum_gap_m': None})
            continue
        try:
            frame = reader.json(entry['metrics_file'], kind='frame_metrics')
            if frame['id'] != entry['id']:
                raise ValueError('FRAME_INDEX_METRICS_ID_MISMATCH')
            for suffix, field in (('.png', 'png_sha256'), ('.jpg', 'jpeg_sha256')):
                reader.record(frame['id'] + suffix, expected=frame[field], kind='original_own_camera')
            frames.append(frame)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            host_errors.append({'frame': entry.get('id'), 'category': 'FRAME_SOURCE_HOST_ERROR',
                                'reason': f'{type(exc).__name__}: {exc}', 'blocking_object': 'saved_frame_or_metrics',
                                'minimum_gap_m': None})
    for row in source_summary.get('unexecuted', []):
        host_errors.append({'frame': row.get('map'), 'category': row.get('category', 'UNEXECUTED'),
                            'reason': row.get('reason') or 'EXPLICITLY_UNEXECUTED',
                            'blocking_object': row.get('blocking_object', 'probe_setup'),
                            'minimum_gap_m': row.get('minimum_gap_m')})
    # Hash every original PNG/JPEG, including evaluation masks that supported
    # the source metrics. They remain on GCP; none is copied or fed to control.
    for path in sorted(input_dir.rglob('*')):
        if path.is_file() and path.suffix.lower() in ('.png', '.jpg', '.jpeg'):
            try:
                reader.record(path, kind='original_camera_or_eval_mask')
            except (OSError, ValueError) as exc:
                reader.errors.append({'category': 'SOURCE_INTEGRITY_ERROR', 'source': str(path.relative_to(input_dir)), 'reason': str(exc)})
    output.mkdir(parents=True, exist_ok=False)
    result = summarize_frames(frames)
    hsv_stats, hsv_details, hsv_errors = surface_hsv_statistics(reader, frames)
    host_errors.extend(hsv_errors)
    artifacts = {}
    for section in ('surfaces', 'segmentation', 'occlusion', 'colour_ranges', 'colour_baseline_comparisons',
                    'actual_detector_parity', 'wall_bands', 'missing_pairs'):
        artifacts[section] = write_parts(output, section, result[section])
    artifacts['surface_hsv_percentiles'] = write_parts(output, 'surface-hsv-percentiles', hsv_stats)
    artifacts['surface_hsv_frames_csv'] = write_csv(output / 'surface-hsv-frames.csv', hsv_details,
        ['frame', 'map', 'pose', 'robot', 'profile', 'encoding', 'surface', 'scope', 'pixels_n', 'H', 'S', 'V'])
    artifacts['frames_csv'] = write_csv(output / 'frames.csv', result['frame_rows'],
        ['id', 'case', 'map', 'view', 'pose', 'robot', 'profile', 'encoding', 'beam_pixels', 'peer_pixels',
         'wall_orb_count', 'wall_orb_interior_descriptor_support_count', 'wall_eval_visible_pixels',
         'floor_orb_count', 'floor_orb_interior_descriptor_support_count', 'floor_eval_visible_pixels'])
    artifacts['colour_frames_csv'] = write_csv(output / 'colour-frames.csv', result['colour_frame_rows'],
        ['id', 'map', 'view', 'pose', 'robot', 'profile', 'encoding', 'range', 'pixels', 'wall_false_pixels',
         'floor_false_pixels', 'target_support_pixels', 'mask_sha256'])
    artifacts['colour_pairs_csv'] = write_csv(output / 'colour-baseline-pairs.csv', result['colour_pair_rows'],
        ['frame', 'case', 'profile', 'baseline', 'encoding', 'range', 'wall_false_delta', 'floor_false_delta',
         'wall_new_false_frame', 'floor_new_false_frame', 'wall_excess_count', 'floor_excess_count', 'target_support_pixel_delta'])
    artifacts['host_errors_csv'] = write_csv(output / 'host-errors.csv', host_errors,
        ['frame', 'category', 'reason', 'blocking_object', 'minimum_gap_m'])
    maps = sorted({Path(p).stem for p in source_summary.get('source_paths', [])} or {f['map'] for f in frames})
    profiles = [p for p in (*BASELINES, V2) if p in source_summary.get('profiles', (*BASELINES, V2))]
    try:
        montage = make_montage(reader, output, frames, maps, profiles)
        artifacts['montage'] = write_json(output / 'montage.json', montage)
    except (OSError, ValueError, RuntimeError) as exc:
        host_errors.append({'frame': None, 'category': 'MONTAGE_HOST_ERROR', 'reason': str(exc),
                            'blocking_object': 'saved_image_composition', 'minimum_gap_m': None})
        artifacts['host_errors_csv'] = write_csv(output / 'host-errors.csv', host_errors,
            ['frame', 'category', 'reason', 'blocking_object', 'minimum_gap_m'])
    reader.check_unchanged()
    artifacts['source_integrity_csv'] = write_csv(output / 'source-integrity-issues.csv', reader.errors,
        ['category', 'source', 'reason'])
    artifacts['source_checksums_csv'] = write_csv(output / 'source-checksums.csv',
        [reader.sources[k] for k in sorted(reader.sources)], ['path', 'kind', 'bytes', 'stored_sha256',
            'decompressed_sha256', 'declared_sha256', 'manifest_sha256', 'mtime_ns_at_read'])
    brief = []
    for profile in profiles:
        for encoding in ('png', 'jpeg'):
            rows = [m for f in frames if f['profile'] == profile for e, m in f['metrics'].items() if e == encoding]
            brief.append({'profile': profile, 'encoding': encoding, 'frames_n': len(rows),
                'wall_orb': distribution(r['surfaces']['wall']['orb_count'] for r in rows),
                'wall_interior_orb': distribution(r['surfaces']['wall'].get('orb_interior_descriptor_support_count') for r in rows),
                'floor_orb': distribution(r['surfaces']['floor']['orb_count'] for r in rows),
                'colour_surface_false_pixels_sum': {surface: sum(c['surface_false_pixels'][surface]
                    for r in rows for c in r.get('colour_ranges', {}).values()) for surface in ('wall', 'floor')}})
    summary = {'schema': 'ugrp.scene_tex2_probe_summary.v1', 'status': 'MEASURED_ONLY',
               'acceptance_or_ready_decision': 'not made; no thresholds introduced', 'input': str(input_dir),
               'input_status': source_summary.get('status'), 'source_sha': source_summary.get('source_sha'),
               'analysis_script_sha256': digest(Path(__file__).resolve()), 'host': platform.node(),
               'frame_index_n': len(index), 'measured_frames_n': len(frames), 'host_error_n': len(host_errors),
               'source_files_hashed_n': len(reader.sources),
               'source_integrity_issue_n': len(reader.errors), 'source_manifest_available': manifest_available,
               'input_run_complete': source_summary.get('status') != 'RUNNING' and manifest_available,
               'incomplete_analysis': bool(host_errors or reader.errors or result['missing_pairs'] or source_summary.get('status') == 'RUNNING'),
               'brief': brief, 'artifacts': artifacts,
               'colour_count_interpretation': 'new_false_frame: candidate count>0 and paired baseline count=0; excess is positive count delta, not pixel-set difference',
               'actual_detector_parity_interpretation': 'exact full-output dictionary equality includes numeric estimates/debug values; changed output does not by itself imply semantic class/count or detection failure',
               'surface_hsv_method': 'OpenCV integer H0..179/S,V0..255; pooled original saved pixels; empirical linear p0/1/5/50/95/99/100; all-visible and 3x3-eroded truth masks separately',
               'limits': ['evaluation-only source masks never enter control',
                          'static fixtures do not establish localization, manipulation, task or physical success',
                          'wall-band component uses legacy analytic command FK; no v3 calibration accuracy claim',
                          'colour surface totals sum detector classes, so one pixel may contribute to several ranges'],
               'reproduction_command': [sys.executable, '-m', 'scripts.summarize_scene_tex2_probe',
                                        '--input', str(input_dir), '--output', str(output)]}
    write_json(output / 'summary.json', summary)
    hashes = {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}
    write_json(output / 'SHA256SUMS.json', hashes)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if platform.system() != 'Linux':
        parser.error('GCP/Linux only; Mac does not compose or open review images')
    result = run(args.input, args.output)
    print(json.dumps({key: result[key] for key in ('status', 'measured_frames_n', 'host_error_n',
                      'source_integrity_issue_n', 'incomplete_analysis')}))
    return 1 if result['incomplete_analysis'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
