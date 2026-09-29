"""One static frame per camera, default vs noshadow_v1 (mj_forward only; no stepping, no probe, no scene setup).

Run from the repo root:  python experiments/2026-09-29-render-profile/static_frames/render_static_frames.py <out_dir>
Writes <cam>_default_vs_noshadow_v1.jpg (left = default, right = profile) and prints pixel statistics.
"""
import sys
from pathlib import Path

import cv2
import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from sim import render_profile as rp  # noqa: E402
from tests.test_render_profile import _zone_xml  # noqa: E402  (same zone scene the tests compile)


def frame(model, cam):
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    renderer = mujoco.Renderer(model, 480, 640)
    renderer.update_scene(data, camera=cam)
    image = renderer.render().copy()
    renderer.close()
    return image


def variant(xml, **flags):
    model = mujoco.MjModel.from_xml_string(xml)
    if flags.get('shadow_off'):
        model.light_castshadow[:] = 0
    if flags.get('reflect_off'):
        model.mat_reflectance[:] = 0.
    return model


scene, raw = _zone_xml()
xml = scene.transform(raw)
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
for cam in ('r1__robot_cam', 'cctv_warehouse'):
    base = frame(variant(xml), cam)
    arms = {'noshadow_v1': frame(mujoco.MjModel.from_xml_string(rp.apply_xml(xml, 'noshadow_v1')), cam),
            'shadow_off_only': frame(variant(xml, shadow_off=True), cam),
            'reflect_off_only': frame(variant(xml, reflect_off=True), cam)}
    v = base.max(2)
    print(f'{cam}: default meanV {v.mean():.1f} V<8 share {(v < 8).mean():.4f}')
    for name, image in arms.items():
        w = image.max(2)
        print(f'  {name}: px changed {int(np.any(base != image, axis=2).sum())}/{v.size} meanV {w.mean():.1f} V<8 share {(w < 8).mean():.4f}')
    both = np.hstack([base, arms['noshadow_v1']])
    cv2.imwrite(str(out / f'{cam}_default_vs_noshadow_v1.jpg'), cv2.cvtColor(both, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
