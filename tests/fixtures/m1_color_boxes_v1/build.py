"""Reproduce synthetic RGB inputs. No detector, renderer or physics is used.

Labels are construction labels, fixed before T03 support was added. The polygon
coordinates describe the existing 34x40x32 mm box at SEARCH, x=.32 m, y=0;
they were computed once from static camera FK, then frozen here. These are NOT
final-environment observations or independent physical recognition validation.
"""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent
PAINT = {'cyan': (93, 210, 200), 'red': (1, 210, 200), 'green': (63, 210, 200)}
HULL = np.array([[329, 465], [246, 465], [243, 415], [247, 373], [328, 373], [332, 415]])
TOP = np.array([[332, 415], [243, 415], [247, 373], [328, 373]])
POSE = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


def bgr(hsv):
    return tuple(int(x) for x in cv2.cvtColor(np.uint8([[hsv]]), cv2.COLOR_HSV2BGR)[0, 0])


def build():
    rows = []
    for kind, color in PAINT.items():
        for variant in ('floor', 'shadow', 'occluded', 'desaturated', 'held', 'held_shadow', 'held_occluded', 'clipped'):
            frame = np.full((480, 640, 3), 100, np.uint8)
            h, s, v = color
            if 'shadow' in variant:
                v = 18  # below the common usable-light floor: must refuse
            if variant == 'desaturated':
                s = 25  # grey face: hue alone must never establish kind
            if variant.startswith('held'):
                cv2.rectangle(frame, (110, 240), (530, 479), bgr((h, s, v)), -1)
                if variant == 'held_occluded':
                    frame[250:] = 100  # only a thin strip remains
            else:
                cv2.fillConvexPoly(frame, HULL, bgr((h, s, int(v*.7))))
                cv2.fillConvexPoly(frame, TOP, bgr((h, s, v)))
                if variant == 'occluded':
                    frame[380:] = 100
                if variant == 'clipped':
                    frame[420:474, 243:333] = bgr(color)
                    frame[474:] = 0
            name = f'{kind}_{variant}.png'
            payload = cv2.imencode('.png', frame)[1].tobytes()
            (ROOT / name).write_bytes(payload)
            rows.append({'file': name, 'sha256': hashlib.sha256(payload).hexdigest(),
                         'kind': kind, 'variant': variant, 'own_servo_pwm': POSE,
                         'floor_visible': variant == 'floor', 'attachment_visible': variant == 'held'})
    frame = np.zeros((480, 640, 3), np.uint8)
    payload = cv2.imencode('.png', frame)[1].tobytes()
    (ROOT / 'black.png').write_bytes(payload)
    rows.append({'file': 'black.png', 'sha256': hashlib.sha256(payload).hexdigest(), 'kind': None,
                 'variant': 'black', 'own_servo_pwm': POSE, 'floor_visible': False, 'attachment_visible': False})
    manifest = {'schema': 'ugrp.m1_color_boxes_fixture.v1',
                'label_source': 'construction labels fixed before support enum; no detector outputs used',
                'scope': 'synthetic offline RGB; not final robot/camera/lighting calibration', 'frames': rows}
    (ROOT / 'labels.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    build()
