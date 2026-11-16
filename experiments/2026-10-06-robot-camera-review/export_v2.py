"""Derive immutable v2 records, comparison plate/video and native TensorBoard."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from collections import defaultdict
import urllib.parse

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from scripts.tensorboard_tools.offline_audit import convert
from scripts.tensorboard_tools.export import convert as convert_video
from scripts.tensorboard_tools.media import media_registry
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
RAW = Path('/Users/changmin/projects/ugrp/outputs/camera-review-20261006')
RENDER = RAW/'render-v2'; OUT = RAW/'delivery-v2'
SNAPSHOT = RAW.parent/'tensorboard/1006-camera-review-v2'
HERE = Path(__file__).parent


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, value):
    with p.open('x') as f: json.dump(value, f, ensure_ascii=False, indent=2); f.write('\n')


def main():
    OUT.mkdir(exist_ok=False); SNAPSHOT.mkdir(exist_ok=False)
    s = json.loads((RENDER/'summary.json').read_text())
    groups = defaultdict(list)
    for r in s['results']:
        assert sha(RENDER/r['image']) == r['sha256']
        groups[(r['phase'], r['variant'])].append(r)
    # Every contemporaneous camera pair uses identical *actual* qpos.
    for rs in groups.values():
        for r in rs:
            label = r['image'].rsplit('-'+r['variant'], 1)[0]
            peers = [x for x in s['results'] if x['image'].rsplit('-'+x['variant'], 1)[0] == label]
            assert len(peers) == 4 and len({x['qpos_sha256'] for x in peers}) == 1
    stats = {}
    for (phase, variant), rs in groups.items():
        stats[phase+'/'+variant] = {'frames': len(rs), 'phase': phase, 'variant': variant,
            **{k: {'min': min(r[k] for r in rs), 'mean': float(np.mean([r[k] for r in rs])),
                    'max': max(r[k] for r in rs)} for k in ('full_fraction', 'valid_fraction')},
            'last': {k: v for k, v in rs[-1].items() if k != 'cargo_corners_optical_m'}}
    comparison = {k: v for k, v in s.items() if k != 'results'}
    comparison.update(stats=stats, matched_qpos_verified=True,
        images_verified=len(s['results']), unique_dynamic_frames=102,
        evidence_hashes={p.name: sha(p) for p in RENDER.iterdir() if p.is_file()},
        verdict='Does not match user observation: sample SDK still ~31.47% cyan while lifted',
        scope='Single arm-only contact fixture. No chassis transport, S2, or real hardware validation.')
    write(OUT/'comparison-v2.json', comparison)
    variants = ('baseline', 'position_only', 'drawing_v1', 'sdk_sample_v2')
    phases = ('static_HIGH', 'HIGH', 'official_lift')
    img = Image.new('RGB', (1280, 912), 'white'); d = ImageDraw.Draw(img)
    font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 17)
    for j, phase in enumerate(phases):
        for i, variant in enumerate(variants):
            r = groups[(phase, variant)][-1]
            d.text((i*320+6,j*304+3), phase+' / '+variant, fill='black', font=font)
            d.text((i*320+6,j*304+27), f"cyan/valid {r['valid_fraction']:.2%}", fill='black', font=font)
            frame = Image.open(RENDER/r['image']).convert('RGB').resize((320, 240))
            img.paste(frame, (i*320, j*304+64))
    img.save(OUT/'comparison-v2.png')
    # Derived 5 fps contact sheet video. Overlay is SIM time: endpoints add
    # extra samples, so playback duration is not a performance measurement.
    video_dir = OUT/'tb-views'/'lift-sequence'; video_dir.mkdir(parents=True)
    vp = video_dir/'overview.mp4'
    writer = cv2.VideoWriter(str(vp), cv2.VideoWriter_fourcc(*'mp4v'), 5., (1280, 264))
    assert writer.isOpened()
    dynamic = [r for r in s['results'] if not r['phase'].startswith('static') and r['variant']=='baseline']
    for r in dynamic:
        canvas = np.full((264, 1280, 3), 255, np.uint8)
        prefix = r['image'].rsplit('-baseline',1)[0]
        for i, v in enumerate(variants):
            frame = cv2.imread(str(RENDER/(prefix+'-'+v+'.png')))
            canvas[24:,i*320:(i+1)*320] = cv2.resize(frame, (320,240))
            cv2.putText(canvas, f'{v} t={r["t"]:.2f} {r["phase"]}', (i*320+4,17),
                        cv2.FONT_HERSHEY_SIMPLEX, .39, (0,0,0), 1)
        writer.write(canvas)
    writer.release()
    cap = cv2.VideoCapture(str(vp)); count = 0
    while cap.read()[0]: count += 1
    cap.release(); assert count == len(dynamic) == 102
    reports = {}
    for phase in ('static_HIGH','HIGH','official_lift'):
        for variant in variants:
            if phase == 'static_HIGH' and variant in ('baseline','drawing_v1'): continue
            key = phase.replace('static_HIGH','static').replace('official_lift','SDK')+'-'+variant
            st = stats[phase+'/'+variant]
            reports[key] = {'offline/valid_fraction': st['valid_fraction']['mean'],
                            'offline/full_fraction': st['full_fraction']['mean'],
                            'offline/frames': st['frames']}
    reports['lift-sequence'] = {'offline/captured_frames': count, 'offline/arm_stages': s['arm_stages'],
                                'offline/target_updates': s['mj_step_calls']}
    readback, manifests = {}, []
    for name, scalars in reports.items():
        src = OUT/'tb-views'/name; src.mkdir(parents=True, exist_ok=True)
        view = {'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
            'offline_scalar_scope': comparison['scope'], 'offline_scalars': scalars,
            'offline_source': {'path': str(OUT/'comparison-v2.json'), 'sha256': sha(OUT/'comparison-v2.json')},
            'family': 'camera-review-v2', 'case': name, 'policy': name, 'condition': name,
            'outcome': 'DIAGNOSTIC_MISMATCH', 'source_sha': s['source_sha'], 'model_calls': 0,
            'hparam_metrics': list(scalars),
            'texts': {'review/scope': comparison['scope'], 'review/verdict': comparison['verdict']}}
        if name == 'lift-sequence':
            view.update(wall_s=s['wall_s'], sim_s=s['sim_s'], commands=s['arm_stages'],
                        command_unit='fixed arm stages; target updates recorded separately')
        write(src/'result.json', view)
        manifest = (convert_video(src, SNAPSHOT/name, max_images=0) if name == 'lift-sequence'
                    else convert(src, SNAPSHOT/name))
        manifests.append({'name': name, 'source': str(src), 'counts': manifest['counts']})
        ea = EventAccumulator(str(SNAPSHOT/name), size_guidance={'scalars':0}).Reload()
        readback[name] = {tag: ea.Scalars(tag)[0].value for tag in scalars}
        for tag, value in scalars.items(): assert np.isclose(readback[name][tag],value)
        assert '_hparams_/session_start_info' in ea.Tags()['tensors']
    registry = media_registry(SNAPSHOT)
    assert len(registry) == 1
    video_id = next(iter(registry))
    write(SNAPSHOT/'collection.json', {'schema':'ugrp.tensorboard-collection.v1','exported':manifests,'failed':[]})
    write(OUT/'tensorboard-v2-readback.json', {'runs':readback, 'video_id':video_id,
        'video_sha256':sha(vp), 'decoded_video_frames':count, 'video_registered':True})
    pins = ['offline/valid_fraction','offline/full_fraction','result/wall_s','result/commands','result/model_calls']
    url = 'http://127.0.0.1:6006/?'+urllib.parse.urlencode({
        'pinnedCards':json.dumps([{'plugin':'scalars','tag':t} for t in pins],separators=(',',':')),
        'smoothing':'0','runFilter':'^1006-camera-review-v2/'})+'#timeseries'
    (OUT/'dashboard-url.txt').write_text(url+'\n')
    for name in ('comparison-v2.json','comparison-v2.png','tensorboard-v2-readback.json'):
        assert not (HERE/name).exists(); shutil.copyfile(OUT/name,HERE/name)
    print(json.dumps({'snapshot':str(SNAPSHOT),'video_id':video_id,'images':len(s['results']),'runs':len(reports)}))


if __name__ == '__main__': main()
