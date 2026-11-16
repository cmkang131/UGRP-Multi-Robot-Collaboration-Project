"""Read-only archive audit; no robot, model, simulation or render call.

Hashes every archived member against the 2026-09-07 preservation manifest.
Post-lift is defined by the recorded close command, not by a grasp-success claim.
Whole-image color area is an image statistic, not proof of holding the object.
"""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from datetime import datetime, timezone

import cv2
import numpy as np

PRIMARY = Path('/Users/changmin/projects/ugrp')
RAW = PRIMARY/'outputs/camera-review-20261006/search-v3/real-analysis-v1'
ARCHIVE = PRIMARY/'outputs/experiment-archives-20260907/real_traces-20260907.zip'
MANIFEST = ARCHIVE.with_suffix('.manifest.jsonl')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def color_area(bgr, color):
    h, s, v = cv2.split(cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV))
    hue = ((h <= 10) | (h >= 170)) if color == 'red' else ((h >= 100) & (h <= 130))
    mask = (hue & (s >= 80) & (v >= 40)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    # Largest target-color component touching the bottom two pixel rows.
    ids = [i for i in range(1, count) if np.any(labels[-2:] == i)]
    best = max(ids, key=lambda i: stats[i, cv2.CC_STAT_AREA]) if ids else 0
    pixels = int(stats[best, cv2.CC_STAT_AREA]) if best else 0
    return {'whole_color_pixels': int(mask.sum()), 'full_pixels': int(mask.size),
            'whole_color_fraction': float(mask.mean()),
            'bottom_component_pixels': pixels, 'bottom_component_fraction': pixels/mask.size,
            'bottom_component_box_xywh': stats[best, :4].tolist() if best else None}


def main():
    RAW.mkdir(exist_ok=False)
    expected = {r['path']: r for r in map(json.loads, MANIFEST.read_text().splitlines()[1:])
                if r['kind'] == 'file'}
    frames, members, picks = [], [], []
    with ZipFile(ARCHIVE) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            data = z.read(info.filename)
            relative = info.filename.removeprefix('real_traces/')
            digest = sha(data)
            assert expected[relative]['sha256'] == digest, info.filename
            members.append({'path': str(ARCHIVE)+'!/'+info.filename, 'sha256': digest,
                            'bytes': len(data), 'zip_date_local_unspecified': info.date_time})
        for name in z.namelist():
            if '-pick-' not in name or not name.endswith('/events.jsonl'):
                continue
            prefix = name.rsplit('/', 1)[0]
            result = json.loads(z.read(prefix+'/result.json'))
            color = result['argv'][-1]
            events = [json.loads(line) for line in z.read(name).decode().splitlines()]
            close = next(e['event_seq'] for e in events if e['kind'] == 'servo_command'
                         and e['servo'] == 1 and e['to_pulse'] == 1500)
            rows = []
            for e in events:
                if e['kind'] != 'camera_frame' or not e.get('sampled_jpeg'):
                    continue
                n = prefix+'/'+e['sampled_jpeg']; data = z.read(n)
                bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                # Debug frames duplicate an observation; keep them in the inventory,
                # but exclude them from statistical denominators.
                row = {'archive_member': n, 'sha256': sha(data), 'color': color,
                    'wall_time_utc': datetime.fromtimestamp(e['wall_time_s'], timezone.utc).isoformat(),
                    'frame_seq': e['frame_seq'], 'commanded_pose': e['commanded_pose'],
                    'after_close': e['event_seq'] > close, 'debug_duplicate': e.get('source') == 'debug',
                    **color_area(bgr, color)}
                rows.append(row); frames.append(row)
            post = [r for r in rows if r['after_close'] and not r['debug_duplicate']]
            picks.append({'span': prefix, 'source': result['source'],
                'status': result['execution_status'], 'exit_code': result['exit_code'],
                'positive_grasp_confirmation': False,
                'post_lift_frames': len(post), 'color': color,
                **{key: {'min': min(r[key] for r in post),
                         'mean': float(np.mean([r[key] for r in post])),
                         'max': max(r[key] for r in post)}
                   for key in ('whole_color_fraction', 'bottom_component_fraction')},
                'first': post[0], 'last': post[-1]})
        assert len(members) == len(expected)
        jpgs = sum(n.endswith('.jpg') for n in z.namelist())
    for filename, rows in [('archive-members-verified.jsonl', members), ('real-pick-frames.jsonl', frames)]:
        with (RAW/filename).open('x') as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False)+'\n')
    report = {'archive': str(ARCHIVE), 'archive_sha256': sha(ARCHIVE.read_bytes()),
        'manifest': str(MANIFEST), 'manifest_sha256': sha(MANIFEST.read_bytes()),
        'verified_file_members': len(members), 'jpeg_members': jpgs, 'pick_frames': len(frames),
        'method': 'OpenCV HSV red H<=10 or H>=170; blue H100..130; S>=80,V>=40; no morphology; full 640x480 denominator',
        'scope': 'Historical real post-lift observations, commanded joints only; not independent grasp or hand-eye calibration.',
        'picks': picks,
        'unknown': ['camera serial/label and calibration frame linkage', 'independent joint angles',
                    'known 3D target/camera correspondences', 'actual object dimensions',
                    'external proof of held state; no post-carry frame in the pick spans']}
    (RAW/'real-archive-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
