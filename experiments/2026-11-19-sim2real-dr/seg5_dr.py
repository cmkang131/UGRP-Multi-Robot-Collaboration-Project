"""Perception DR: how much do seg5 colour classes change when the picture looks like a real camera?

Input: own-camera JPEGs from the sim (640x480). Each frame is perturbed the way a real camera
differs (exposure, white balance, saturation, noise, blur, JPEG), then resized exactly like the
model input (harness.grasp_act_data.image_array: PIL bilinear to 320x240) and segmented by the
evaluated seg5_v1. Reported per class: recall of the clean-frame class pixels (did the class
survive?) and false pixels (pixels newly given that class).
"""
import argparse, io, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import importlib.util as ilu
spec = ilu.spec_from_file_location('seg5', ROOT / 'solo_pipeline' / 'harness' / 'seg_frontend_v1.py'); seg5 = ilu.module_from_spec(spec); spec.loader.exec_module(seg5)
CLASSES = {'target': seg5.TARGET, 'other': seg5.OTHER, 'wall': seg5.WALL, 'body': seg5.BODY, 'dark': seg5.BLACK}


def to_input(img):
    return np.asarray(img.convert('RGB').resize((320, 240), Image.Resampling.BILINEAR), dtype=np.uint8).transpose(2, 0, 1).copy()


def classes(chw, kind):
    out = seg5.segment(chw, kind).transpose(1, 2, 0)
    return {k: np.all(out == np.array(v, np.uint8), axis=-1) for k, v in CLASSES.items()}


def perturb(img, name, x, rng):
    a = np.asarray(img).astype(np.float32)
    if name == 'exposure':
        a = a * x
    elif name == 'white_balance':      # warm (+) / cool (-) cast: R x(1+x), B x(1-x)
        a = a * np.array([1 + x, 1., 1 - x])
    elif name == 'saturation':
        g = a.mean(axis=2, keepdims=True); a = g + (a - g) * x
    elif name == 'gamma':
        a = 255. * (a / 255.) ** x
    elif name == 'noise':
        a = a + rng.normal(0, x, a.shape)
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if name == 'blur':
        out = out.filter(ImageFilter.GaussianBlur(x))
    if name == 'jpeg':
        b = io.BytesIO(); out.save(b, 'JPEG', quality=int(x)); out = Image.open(io.BytesIO(b.getvalue()))
    return out


SWEEP = {'exposure': [0.5, 0.7, 0.85, 1.15, 1.3, 1.5], 'white_balance': [-0.15, -0.08, 0.08, 0.15],
         'saturation': [0.6, 0.8, 1.2], 'gamma': [0.8, 1.25], 'noise': [4, 8], 'blur': [1, 2], 'jpeg': [50, 30]}

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('frames', type=Path); p.add_argument('--kind', default='red'); p.add_argument('--out', type=Path)
    a = p.parse_args(); rng = np.random.default_rng(0)
    frames = sorted(a.frames.glob('*.jpg'))
    clean = [(Image.open(f), classes(to_input(Image.open(f)), a.kind)) for f in frames]
    present = {k: sum(int(c[k].sum()) for _, c in clean) for k in CLASSES}
    rows = []
    for name, values in SWEEP.items():
        for x in values:
            kept = {k: 0 for k in CLASSES}; false = {k: 0 for k in CLASSES}
            for img, ref in clean:
                got = classes(to_input(perturb(img, name, x, rng)), a.kind)
                for k in CLASSES:
                    kept[k] += int((got[k] & ref[k]).sum()); false[k] += int((got[k] & ~ref[k]).sum())
            row = {'perturbation': name, 'value': x}
            for k in ('target', 'other', 'wall'):
                row[f'{k}_recall'] = round(kept[k] / present[k], 3) if present[k] else None
                row[f'{k}_false_px_per_frame'] = round(false[k] / len(clean), 1)
            rows.append(row); print(json.dumps(row))
    summary = {'frames': len(frames), 'kind': a.kind, 'clean_pixels_per_frame': {k: round(v / len(frames), 1) for k, v in present.items()}, 'rows': rows}
    if a.out: a.out.write_text(json.dumps(summary, indent=1))
