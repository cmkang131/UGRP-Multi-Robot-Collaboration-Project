#!/usr/bin/env python3
"""Measure the recorded nav-gate frame and predict the neutral-paint values.

No simulator, no GPU: the before side is the recorded frame
``experiments/2026-10-18-nav-gate-1/raw/r1-tick5.jpg``; the after side is a
first-order prediction from that frame plus the light-scale change.  The GPU
gate frame is still the only evidence for the real after appearance.

    python3 experiments/2026-10-18-nav-scene-neutral/measure.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sim import neutral_pickup_floor as neutral  # noqa: E402

FRAME = ROOT / 'experiments/2026-10-18-nav-gate-1/raw/r1-tick5.jpg'
OUT = Path(__file__).resolve().parent
PICKUP_LINEAR = np.array([.12, .36, .70])      # map rgba (sim/zone_arena.py:251)
OLD_LIGHT_SCALE, NEW_LIGHT_SCALE = .30, .70


def srgb8(linear):
    linear = np.clip(np.asarray(linear, dtype=float), 0., 1.)
    srgb = np.where(linear <= .0031308, 12.92*linear, 1.055*linear**(1/2.4)-.055)
    return np.clip(np.rint(srgb*255), 0, 255).astype(int)


def srgb_to_linear(value8):
    value = np.asarray(value8, dtype=float)/255.
    return np.where(value <= .04045, value/12.92, ((value+.055)/1.055)**2.4)


def main():
    rgb = cv2.cvtColor(cv2.imread(str(FRAME)), cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    indigo = (h >= 100) & (h <= 120) & (s >= 100)
    detector = (h >= 110) & (h <= 114) & (s >= 100) & (v >= 30) & (v <= 110)
    median_rgb = np.median(rgb[indigo], axis=0)
    # Per-channel irradiance = rendered linear / authored linear paint.  The red
    # channel is crushed by the dark painting + JPEG, so G/B set the estimate.
    irradiance = srgb_to_linear(median_rgb)/PICKUP_LINEAR
    gamma = float(np.median(irradiance[1:]))
    scaled = gamma*NEW_LIGHT_SCALE/OLD_LIGHT_SCALE
    palette = neutral.PALETTE_LINEAR
    predicted = [dict(linear=level, rendered_linear=level*scaled, srgb8=int(srgb8(level*scaled)))
                 for level in palette]
    record = {
        'schema': 'ugrp.nav_scene_neutral.measure.v1',
        'frame': str(FRAME.relative_to(ROOT)), 'frame_sha256': hashlib.sha256(FRAME.read_bytes()).hexdigest(),
        'frame_shape': list(rgb.shape),
        'before': {
            'pickup_paint_rgba_linear': PICKUP_LINEAR.tolist(),
            'indigo_mask': 'H 100-120 and S>=100 (OpenCV units)',
            'indigo_fraction': round(float(indigo.mean()), 4),
            'median_hsv': [float(np.median(h[indigo])), float(np.median(s[indigo])), float(np.median(v[indigo]))],
            'median_rgb8': [float(x) for x in median_rgb],
            'detector_band_pixels': int(detector.sum()),
            'detector_band_fraction': round(float(detector.mean()), 6),
        },
        'prediction': {
            'method': 'irradiance from the recorded frame (median of G/B channels) x 0.70/0.30; first-order, not a render',
            'irradiance_v1_gb_median': round(gamma, 4),
            'irradiance_v2': round(scaled, 4),
            'neutral_palette_srgb8': [int(srgb8(level)) for level in palette],
            'predicted_pickup_v_srgb8': [row['srgb8'] for row in predicted],
            'predicted_pickup_saturation': 0,
            'predicted_pickup_opencv_hue': None,
        },
        'notes': ['after frame is NOT rendered: no local MuJoCo/GPU; run the nav gate on gcp6',
                  'zone B paint is unchanged in the map; its rendered V rises with the light scale, '
                  'so the gpu_calib_v1 V<=110 band must be recalibrated on the new scene'],
    }
    (OUT/'before-after.json').write_text(json.dumps(record, indent=2)+'\n')

    # Swatch: actual before crop + predicted neutral swatches, explicitly labelled.
    crop = rgb[200:400, 260:520]
    panel = np.full((200, 720, 3), 32, np.uint8)
    panel[:200, :260] = cv2.resize(crop, (260, 200))
    x = 300
    for row in predicted:
        panel[40:160, x:x+110] = [row['srgb8']]*3
        x += 130
    cv2.putText(panel, 'BEFORE: recorded frame (H108 S212 V90)', (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(panel, f'AFTER: predicted paint V {'/'.join(str(r["srgb8"]) for r in predicted)} (not rendered)', (300, 20),
                cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1, cv2.LINE_AA)
    for i, row in enumerate(predicted):
        cv2.putText(panel, f'V{row["srgb8"]}', (300+130*i, 185),
                    cv2.FONT_HERSHEY_SIMPLEX, .45, (220, 220, 220), 1, cv2.LINE_AA)
    cv2.imwrite(str(OUT/'before-after-swatch.png'), cv2.cvtColor(panel, cv2.COLOR_RGB2BGR))
    print(json.dumps(record['prediction'], indent=1))
    print(json.dumps(record['before'], indent=1))


if __name__ == '__main__':
    main()
