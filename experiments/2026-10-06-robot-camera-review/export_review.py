"""Build read-only comparison records and a new native TensorBoard snapshot.

Run from repo root with the existing simulation venv; no physics or rendering.
Existing output destinations are refused. The six MuJoCo PNGs are read as data.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.tensorboard_tools.offline_audit import convert
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

RAW = Path('/Users/changmin/projects/ugrp/outputs/camera-review-20261006')
RENDER = RAW/'render-v1-r2'
DELIVERY = RAW/'delivery-v1'
SNAPSHOT = RAW.parent/'tensorboard/1006-camera-review-v1'
SOURCE = RAW.parent/'s2-graduation-fae1fc4a-s1026-P2-2-place'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def main():
    DELIVERY.mkdir(exist_ok=False)
    rendered = json.loads((RENDER/'render-summary.json').read_text())
    saved = json.loads((RAW/'frames-audit/summary.json').read_text())
    profiles = {r['profile'] for r in rendered['results']}
    reports = {'saved-1320': {
        'condition': 'recorded_dynamic_baseline', 'frames': saved['frames'],
        'valid_fraction': saved['valid_fraction']['median'],
        'full_fraction': saved['full_fraction']['median'],
        'aggregation': 'median', 'source_sha': saved['source_sha']}}
    for profile in sorted(profiles):
        rows = [r for r in rendered['results'] if r['profile'] == profile]
        reports['static-old' if profile == 'baseline' else 'static-drawing'] = {
            'condition': profile, 'frames': len(rows),
            'valid_fraction': float(np.mean([r['valid_fraction'] for r in rows])),
            'full_fraction': float(np.mean([r['full_fraction'] for r in rows])),
            'aggregation': 'mean', 'source_sha': rendered['source_sha']}
    a = [r for r in rendered['results'] if r['profile'] == 'baseline']
    b = [r for r in rendered['results'] if r['profile'] != 'baseline']
    assert [(r['t'], r['qpos_sha256']) for r in a] == [(r['t'], r['qpos_sha256']) for r in b]
    reports['render-error'] = {'condition': 'first_attempt_joint_name_error', 'frames': 0,
        'source_sha': '965f2f31', 'render_completed': 0,
        'error': 'Invalid shoulder_pitch name; released lock. Corrected from model joint table.'}
    comparison = {'scope': 'saved RGB audit and static command-pose reconstruction; not REAL or mission success',
        'model_calls': 0, 'commands': 0, 'reports': reports, 'paired_qpos_hashes_equal': True,
        'limits': 'Baseline static render does not match dynamic raw. No claim of 99.98 to 26 percent improvement on hardware.',
        'evidence_hashes': {str(p.relative_to(RAW)): sha(p) for p in sorted(RAW.rglob('*')) if p.is_file()}}
    write(DELIVERY/'comparison.json', comparison)
    # A scientific comparison plate; no image content is retouched.
    from PIL import Image, ImageDraw, ImageFont
    figure = Image.new('RGB', (1920, 580), 'white')
    draw = ImageDraw.Draw(figure)
    font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 22)
    paths = [SOURCE/a[0]['recorded_frame'], RENDER/a[0]['image'], RENDER/b[0]['image']]
    labels = ['Recorded dynamic RGB', 'Static HIGH / existing mount', 'Static HIGH / drawing mount']
    fractions = [a[0]['recorded_frame_metrics']['valid_fraction'], a[0]['valid_fraction'], b[0]['valid_fraction']]
    draw.text((20, 8), 't=105 s | Same recorded cargo; static arms use issued HIGH, not measured joints', fill='black', font=font)
    for i, (path, label, fraction) in enumerate(zip(paths, labels, fractions)):
        draw.text((i*640+12, 40), label, fill='black', font=font)
        draw.text((i*640+12, 70), f'cyan / valid pixels = {fraction:.2%}', fill='black', font=font)
        figure.paste(Image.open(path).convert('RGB'), (i*640, 100))
    figure.save(DELIVERY/'comparison.png')
    SNAPSHOT.mkdir(exist_ok=False)
    manifests, readback = [], {}
    for name, report in reports.items():
        src = DELIVERY/'tb-views'/name
        src.mkdir(parents=True, exist_ok=False)
        scalars = {'offline/frames': report['frames']}
        for key in ('valid_fraction', 'full_fraction', 'render_completed'):
            if key in report:
                scalars['offline/'+key] = report[key]
        view = {'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
            'offline_scalar_scope': comparison['scope'], 'offline_scalars': scalars,
            'offline_source': {'path': str(DELIVERY/'comparison.json'), 'sha256': sha(DELIVERY/'comparison.json')},
            'offline_source_pointer': 'reports/'+name, 'family': 'camera-review', 'policy': report['condition'],
            'case': name, 'condition': report['condition'], 'outcome': 'DIAGNOSTIC_ONLY',
            'source_sha': report['source_sha'], 'model_calls': 0, 'commands': 0,
            'texts': {'review/limits': comparison['limits'], 'review/profile': rendered['profile']}}
        write(src/'result.json', view)
        manifest = convert(src, SNAPSHOT/name)
        manifests.append({'source': str(src), 'name': name, 'counts': manifest['counts']})
        acc = EventAccumulator(str(SNAPSHOT/name), size_guidance={'scalars': 0}).Reload()
        expected = {**scalars, 'result/model_calls': 0, 'result/commands': 0}
        readback[name] = {tag: acc.Scalars(tag)[0].value for tag in expected}
        for tag, value in expected.items():
            assert np.isclose(readback[name][tag], value), (name, tag)
        assert '_hparams_/session_start_info' in acc.Tags()['tensors']
    write(SNAPSHOT/'collection.json', {'schema': 'ugrp.tensorboard-collection.v1',
          'exported': manifests, 'failed': []})
    write(DELIVERY/'tensorboard-readback.json', readback)
    here = Path(__file__).parent
    for src, name in [(DELIVERY/'comparison.json', 'comparison.json'),
                      (RAW/'frames-audit/summary.json', 'frames-summary.json'),
                      (RENDER/'render-summary.json', 'render-summary.json'),
                      (DELIVERY/'tensorboard-readback.json', 'tensorboard-readback.json'),
                      (DELIVERY/'comparison.png', 'comparison.png')]:
        if (here/name).exists():
            raise ValueError('refusing overwrite '+str(here/name))
        shutil.copyfile(src, here/name)
    print(json.dumps({'snapshot': str(SNAPSHOT), 'readback': readback}))


if __name__ == '__main__':
    main()
