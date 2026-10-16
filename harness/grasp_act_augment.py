"""Training-only image augmentation for the grasp ACT student (explicit toggle).

Photometric: brightness, contrast, saturation, hue jitter, Gaussian blur,
additive noise. Geometric: only a small translation by crop-and-pad (<= 4 %
of width/height). No rotation, flip, zoom or FOV change: camera geometry is
unchanged. One parameter draw per training sample, applied identically to
every frame of that sample's own RGB history (one physical camera).
Inference/evaluation never augment. Ranges are recorded in the training report.
"""
from __future__ import annotations
import io
import numpy as np

RANGES = {'brightness': .25, 'contrast': .25, 'saturation': .25, 'hue': .03,
          'blur_p': .3, 'blur_sigma_px': (.3, 1.2), 'noise_p': .5, 'noise_sigma': (.0, .03),
          'shift_frac': .04}
MEAN = (.485, .456, .406)
STD = (.229, .224, .225)


def draw(rng):
    r = RANGES
    return {'brightness': float(rng.uniform(1-r['brightness'], 1+r['brightness'])),
            'contrast': float(rng.uniform(1-r['contrast'], 1+r['contrast'])),
            'saturation': float(rng.uniform(1-r['saturation'], 1+r['saturation'])),
            'hue': float(rng.uniform(-r['hue'], r['hue'])),
            'blur_sigma_px': float(rng.uniform(*r['blur_sigma_px'])) if rng.random() < r['blur_p'] else 0.,
            'noise_sigma': float(rng.uniform(*r['noise_sigma'])) if rng.random() < r['noise_p'] else 0.,
            'shift': [float(rng.uniform(-r['shift_frac'], r['shift_frac'])) for _ in range(2)],
            'noise_seed': int(rng.integers(0, 2**31-1))}


IDENTITY = {'brightness': 1., 'contrast': 1., 'saturation': 1., 'hue': 0., 'blur_sigma_px': 0.,
            'noise_sigma': 0., 'shift': [0., 0.], 'noise_seed': 0}


def _photometric(a, p):
    a = a*p['brightness']
    mean = a.mean()
    a = (a-mean)*p['contrast']+mean
    gray = (a@np.array([.299, .587, .114], dtype=np.float32))[..., None]
    a = (a-gray)*p['saturation']+gray
    if p['hue']:
        # YIQ rotation: small hue shift without leaving the RGB gamut much.
        t = 2*np.pi*p['hue']; c, s = np.cos(t), np.sin(t)
        to = np.array([[.299, .587, .114], [.596, -.274, -.322], [.211, -.523, .312]], dtype=np.float32)
        rot = np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float32)
        a = a@(np.linalg.inv(to)@rot@to).T
    return np.clip(a, 0., 1.)


def augmented_tensor(jpeg, size, params):
    """Same resize + ImageNet normalization as harness.grasp_act.tensor."""
    import torch
    from PIL import Image, ImageFilter
    with Image.open(io.BytesIO(jpeg)) as image:
        image = image.convert('RGB').resize((size, size), Image.Resampling.BILINEAR)
        if params['blur_sigma_px']:
            image = image.filter(ImageFilter.GaussianBlur(params['blur_sigma_px']))
        a = np.array(image, dtype=np.float32)/255.
    if params is not IDENTITY and params != IDENTITY:
        a = _photometric(a, params)
        dx, dy = (int(round(v*size)) for v in params['shift'])
        if dx or dy:
            a = np.roll(a, (dy, dx), axis=(0, 1))
            # Pad uncovered border with edge values (no wrap-around content).
            if dy > 0: a[:dy] = a[dy:dy+1]
            elif dy < 0: a[dy:] = a[dy-1:dy]
            if dx > 0: a[:, :dx] = a[:, dx:dx+1]
            elif dx < 0: a[:, dx:] = a[:, dx-1:dx]
        if params['noise_sigma']:
            noise = np.random.default_rng(params['noise_seed']).normal(0., params['noise_sigma'], a.shape).astype(np.float32)
            a = np.clip(a+noise, 0., 1.)
    value = torch.from_numpy(np.ascontiguousarray(a)).permute(2, 0, 1)
    return (value-torch.tensor(MEAN)[:, None, None])/torch.tensor(STD)[:, None, None]
