"""Fine-tuning / evaluation of the VIS3 wall-floor segmentation network for other floor colours (torch env).

Re-uses `experiments/2026-09-26-vision-loc/seg_model.py` (LR-ASPP MobileNetV3-Large, 5 classes) unchanged for the
architecture, undistortion, label loading, confusion and metrics.  New here:
  * an image cache (undistorted, 320 x 240 uint8 RGB + labels) so several fine-tunes can share one decode pass,
  * photometric augmentation with per-channel colour cast, gamma and a LABEL-GUIDED FLOOR RECOLOUR (training only: the
    teacher label chooses which pixels get a new colour; the trained network sees only the image),
  * optional colour-invariant input modes (``perimg``: per-image per-channel standardisation, ``gray_perimg``: luminance
    only, standardised) used identically in training and at run time,
  * ``Seg``: run-time wrapper (own RGB frame -> 5-class probabilities) with the same interface as `seg_model.Segmenter`.

Run-time input of the network = the own RGB frame only.  Labels are training targets / scoring only.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VL = ROOT / 'experiments' / '2026-09-26-vision-loc'
sys.path[:0] = [str(VL), str(HERE)]

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn.functional as F  # noqa: E402

import seg_model as sm  # noqa: E402
import vision_loc as vl  # noqa: E402

IN_W, IN_H = sm.IN_W, sm.IN_H
MEAN, STD = sm.MEAN, sm.STD
SEG_V2 = Path('/Users/changmin/projects/ugrp/outputs/vision-loc-20260926/model/seg-v2/seg_lraspp_mbv3.pt')
SEG_V2_SHA256 = '348539030fda962cc5ba64e21c956619bc4db9321a99cd3ae6746611a9939fd9'
PREPROCS = ('rgb', 'perimg', 'gray_perimg')


# Inference-only image transforms (dev diagnostics on the frozen seg-v2; applied to the undistorted RGB in [0,1] before normalisation)
XFS = {
    'none': None,
    'gain0.6': lambda x: x * .6, 'gain0.4': lambda x: x * .4, 'gain0.3': lambda x: x * .3,
    'gamma2': lambda x: np.clip(x, 0, 1) ** 2.0, 'gamma3': lambda x: np.clip(x, 0, 1) ** 3.0,
    'gray': lambda x: np.repeat((x @ np.array([.299, .587, .114], np.float32))[..., None], 3, 2),
    'stretch': lambda x: (x - np.percentile(x, 2)) / max(np.percentile(x, 98) - np.percentile(x, 2), 1e-3) * .35,   # per-image contrast stretch to a dark range
}


# ----------------------------------------------------------------------------------------------- input normalisation
def normalise(rgb01: np.ndarray, mode: str) -> np.ndarray:
    """(H, W, 3) float32 RGB in [0, 1] -> (3, H, W) float32 network input."""
    if mode == 'rgb':
        return ((rgb01 - MEAN) / STD).transpose(2, 0, 1)
    if mode == 'perimg':
        m = rgb01.reshape(-1, 3).mean(0)
        s = rgb01.reshape(-1, 3).std(0) + 1e-3
        return ((rgb01 - m) / s).transpose(2, 0, 1)
    if mode == 'gray_perimg':
        g = rgb01 @ np.array([.299, .587, .114], np.float32)
        g = (g - g.mean()) / (g.std() + 1e-3)
        return np.repeat(g[None], 3, 0).astype(np.float32)
    raise ValueError(mode)


def undistort_resize(bgr_raw: np.ndarray, size) -> np.ndarray:
    """Raw fisheye BGR -> undistorted pinhole, resized (INTER_AREA), RGB float32 [0, 1] (H, W, 3)."""
    und = vl.mp.undistort(bgr_raw)
    small = cv2.resize(und, tuple(size), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.


# ----------------------------------------------------------------------------------------------------- run-time wrapper
class Seg:
    """Own RGB frame -> (480, 640, 5) class probabilities.  ``pre`` = input mode, ``xf`` = optional inference-only image transform."""

    def __init__(self, ckpt: Path, pre: str = 'rgb', infer_size=(480, 360), dev=None, xf=None):
        blob = torch.load(str(ckpt), map_location='cpu', weights_only=False)
        if tuple(blob['classes']) != vl.CLASSES:
            raise ValueError('classes differ')
        self.sha256 = hashlib.sha256(Path(ckpt).read_bytes()).hexdigest()
        self.dev = torch.device(dev) if dev else sm.device()
        self.model = sm.build(False)
        self.model.load_state_dict(blob['state_dict'])
        self.model.eval().to(self.dev)
        self.pre = blob.get('input', {}).get('preproc', pre) if pre is None else pre
        self.infer_size = (int(infer_size[0]), int(infer_size[1]))
        self.xf = xf

    @torch.no_grad()
    def probs(self, bgr_raw: np.ndarray) -> np.ndarray:
        rgb = undistort_resize(bgr_raw, self.infer_size)
        if self.xf is not None:
            rgb = np.clip(self.xf(rgb), 0., 1.).astype(np.float32)
        x = torch.from_numpy(normalise(rgb, self.pre))[None].to(self.dev)
        logits = self.model(x)['out']
        up = F.interpolate(logits, size=(vl.HEIGHT, vl.WIDTH), mode='bilinear', align_corners=False)
        return torch.softmax(up, 1)[0].permute(1, 2, 0).float().cpu().numpy()


# -------------------------------------------------------------------------------------------------------- evaluation
def eval_sets(seg: Seg, sets: dict, max_frames: int | None = None) -> dict:
    """Per look: wall/floor IoU (valid pixels, 640 x 480, label = teacher render) and per-frame wall IoU quantiles.

    sets: {name: dir with manifest.json (rows: file, label)}.
    """
    out = {}
    for name, d in sets.items():
        d = Path(d)
        man = json.loads((d / 'manifest.json').read_text())
        k = len(vl.CLASSES)
        cm = np.zeros((k, k), np.int64)
        wall_iou = []
        for row in man['rows'][:max_frames]:
            bgr = cv2.imread(str(d / row['file']), cv2.IMREAD_COLOR)
            lab = cv2.imread(str(d / row['label']), cv2.IMREAD_UNCHANGED)
            pred = seg.probs(bgr).argmax(2)
            ok = vl.VALID & (lab != vl.IGNORE)
            cm += np.bincount(lab[ok].astype(np.int64) * k + pred[ok], minlength=k * k).reshape(k, k)
            inter = float(((pred == vl.WALL) & (lab == vl.WALL) & ok).sum())
            union = float((((pred == vl.WALL) | (lab == vl.WALL)) & ok).sum())
            if union > 0:
                wall_iou.append(inter / union)
        m = sm.metrics_from_confusion(cm)
        w = np.array(wall_iou) if wall_iou else np.array([np.nan])
        out[name] = {'frames': len(man['rows'][:max_frames]), 'iou_floor': m['iou']['floor'], 'iou_wall': m['iou']['wall'], 'miou': m['miou'],
                     'pixel_acc': m['pixel_acc'], 'wall_iou_frame_p10': round(float(np.percentile(w, 10)), 3),
                     'wall_iou_frame_median': round(float(np.median(w)), 3)}
    return out


# ------------------------------------------------------------------------------------------------------------- caching
def build_cache(items, out_prefix: Path, workers: int = 4):
    """items: list of (frame_path, label_path, kind).  Writes <prefix>_x.npy (N, 240, 320, 3) uint8, <prefix>_y.npy (N, 240, 320) uint8."""
    out_prefix = Path(out_prefix)
    n = len(items)
    X = np.lib.format.open_memmap(str(out_prefix) + '_x.npy', mode='w+', dtype=np.uint8, shape=(n, IN_H, IN_W, 3))
    Y = np.lib.format.open_memmap(str(out_prefix) + '_y.npy', mode='w+', dtype=np.uint8, shape=(n, IN_H, IN_W))
    from concurrent.futures import ThreadPoolExecutor

    def one(i):
        fr, lb, _ = items[i]
        bgr = cv2.imread(str(fr), cv2.IMREAD_COLOR)
        X[i] = (undistort_resize(bgr, (IN_W, IN_H)) * 255. + .5).astype(np.uint8)
        Y[i] = cv2.resize(sm.load_label(Path(lb)), (IN_W, IN_H), interpolation=cv2.INTER_NEAREST)
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, range(n)))
    X.flush(); Y.flush()
    (Path(str(out_prefix) + '_meta.json')).write_text(json.dumps([{'frame': str(a), 'label': str(b), 'kind': c} for a, b, c in items]))


# ------------------------------------------------------------------------------------------------------------- dataset
class CacheDataset(torch.utils.data.Dataset):
    """Cached (undistorted 320 x 240) frames; augment=True applies flip + photometric jitter + optional floor recolour."""

    def __init__(self, prefix: Path, idx, pre: str, augment: bool, recolour_p: float = 0.0, cast: float = .0, gamma: float = 0.0):
        self.X = np.load(str(prefix) + '_x.npy', mmap_mode='r')
        self.Y = np.load(str(prefix) + '_y.npy', mmap_mode='r')
        self.meta = json.loads(Path(str(prefix) + '_meta.json').read_text())
        self.idx = np.asarray(idx)
        self.pre, self.augment, self.recolour_p, self.cast, self.gamma = pre, augment, recolour_p, cast, gamma

    def __len__(self):
        return len(self.idx)

    def __getitem__(self, i):
        j = int(self.idx[i])
        rgb = self.X[j].astype(np.float32) / 255.
        y = np.array(self.Y[j]).astype(np.int64)
        if self.augment:
            rng = np.random.default_rng((torch.initial_seed() + i * 7919 + j * 104729) % (2 ** 32))
            if rng.random() < .5:
                rgb, y = rgb[:, ::-1].copy(), y[:, ::-1].copy()
            if self.recolour_p and self.meta[j]['kind'] == 'replay' and rng.random() < self.recolour_p:
                # label-guided floor recolour (training only): new mean tone + hue for the FLOOR pixels, keeps the checker structure
                fl = (y == vl.FLOOR)
                if fl.any():
                    gain = rng.uniform(.8, 3.2) * np.exp(rng.normal(0, .12, 3))
                    off = rng.uniform(-.03, .08, 3)
                    rgb = rgb.copy()
                    rgb[fl] = rgb[fl] * gain + off
            if self.cast:
                rgb = rgb * np.exp(rng.normal(0, self.cast, 3)).astype(np.float32)
            if self.gamma:
                rgb = np.clip(rgb, 1e-4, 1.) ** float(np.exp(rng.uniform(-self.gamma, self.gamma)))
            gain = rng.uniform(.75, 1.3)
            bias = rng.uniform(-.06, .06)
            rgb = rgb * gain + bias + rng.normal(0, .01, size=rgb.shape).astype(np.float32)
            rgb = np.clip(rgb, 0., 1.).astype(np.float32)
        x = normalise(rgb.astype(np.float32), self.pre)
        return torch.from_numpy(np.ascontiguousarray(x, np.float32)), torch.from_numpy(np.ascontiguousarray(y))


def train(prefix: Path, train_idx, val_idx, out: Path, *, pre: str = 'rgb', init: Path = SEG_V2, epochs: int = 4, batch: int = 16,
          lr: float = 3e-4, seed: int = 0, workers: int = 1, recolour_p: float = 0.0, cast: float = .05, gamma: float = .25,
          bn_idx=None, log=print, tag: str = '') -> dict:
    torch.manual_seed(seed); np.random.seed(seed)
    dev = sm.device()
    dl = torch.utils.data.DataLoader(CacheDataset(prefix, train_idx, pre, True, recolour_p, cast, gamma), batch_size=batch, shuffle=True, num_workers=workers,
                                     drop_last=True, persistent_workers=workers > 0, generator=torch.Generator().manual_seed(seed))
    vdl = torch.utils.data.DataLoader(CacheDataset(prefix, val_idx, pre, False), batch_size=batch, num_workers=workers)
    model = sm.build(False)
    if init is not None:
        blob = torch.load(str(init), map_location='cpu', weights_only=False)
        model.load_state_dict(blob['state_dict'])
    else:
        model = sm.build(True)
    model.to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    steps = epochs * len(dl)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=steps, pct_start=.1)
    history, step, t0 = [], 0, time.time()
    for epoch in range(epochs):
        model.train()
        for x, y in dl:
            x, y = x.to(dev), y.to(dev)
            loss = F.cross_entropy(model(x)['out'], y, ignore_index=vl.IGNORE)
            opt.zero_grad(set_to_none=True); loss.backward(); opt.step(); sched.step(); step += 1
            if step % 50 == 0:
                history.append({'step': step, 'epoch': epoch, 'loss': round(float(loss), 5), 'wall_s': round(time.time() - t0, 1)})
                log(json.dumps(history[-1]))
        val = sm.evaluate(model, vdl, dev)
        history.append({'step': step, 'epoch': epoch, 'val': val, 'wall_s': round(time.time() - t0, 1)})
        log(json.dumps(history[-1]))
    # precise BN on clean (un-augmented) frames of the SAME training mixture, as for seg-v2
    bn_idx = train_idx if bn_idx is None else bn_idx
    bdl = torch.utils.data.DataLoader(CacheDataset(prefix, bn_idx, pre, False), batch_size=32, num_workers=workers)
    bns = [m for m in model.modules() if isinstance(m, torch.nn.modules.batchnorm._BatchNorm)]
    saved = [m.momentum for m in bns]
    for m in bns:
        m.reset_running_stats(); m.momentum = None
    model.train()
    with torch.no_grad():
        for x, _ in bdl:
            model(x.to(dev))
    for m, mom in zip(bns, saved):
        m.momentum = mom
    model.eval()
    val = sm.evaluate(model, vdl, dev)
    history.append({'step': step, 'val': val, 'bn': f'precise BN on {len(bn_idx)} clean mixture frames', 'wall_s': round(time.time() - t0, 1)})
    log(json.dumps(history[-1]))
    out.mkdir(parents=True, exist_ok=True)
    ckpt = out / 'seg_lraspp_mbv3.pt'
    torch.save({'schema': 'ugrp.seg_lightfloor.seg_model.v1', 'state_dict': {k: v.cpu() for k, v in model.state_dict().items()}, 'classes': vl.CLASSES,
                'input': {'width': IN_W, 'height': IN_H, 'preproc': pre, 'mean': MEAN.tolist(), 'std': STD.tolist(), 'view': 'undistorted pinhole (K)'},
                'arch': 'torchvision.models.segmentation.lraspp_mobilenet_v3_large(num_classes=5)', 'init': str(init), 'init_sha256': SEG_V2_SHA256 if init == SEG_V2 else None},
               ckpt)
    info = {'tag': tag, 'checkpoint': str(ckpt), 'sha256': hashlib.sha256(ckpt.read_bytes()).hexdigest(), 'bytes': ckpt.stat().st_size, 'preproc': pre,
            'init': str(init), 'epochs': epochs, 'batch': batch, 'lr': lr, 'seed': seed, 'recolour_p': recolour_p, 'cast': cast, 'gamma': gamma,
            'train_frames': int(len(train_idx)), 'val_frames': int(len(val_idx)), 'device': str(dev), 'torch': torch.__version__, 'wall_s': round(time.time() - t0, 1),
            'history': history}
    (out / 'train_info.json').write_text(json.dumps(info, indent=1))
    return info
