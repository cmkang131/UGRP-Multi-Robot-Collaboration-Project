"""Bit-identical wall-time cuts of the v98 OpenCV wall observation (speedup item, opt-in).

``markerless_probe.detect_boundaries`` (frozen VIS3 file, not modified) spends a frame mostly in work that depends
only on the camera model, not on the image: per-row floor traces, ranges, implied top rows, the acceptance mask
of the geometry, the band/below/above window rows and their 2-D fancy indices. The camera model changes only
with the own servo posture / load state, so consecutive frames repeat it.

``detect_boundaries`` below is a copy of the frozen function in which
* the image-independent block is computed once per camera model (key: exact bytes of every array/scalar
  attribute of the model, the detector parameters and ``self_top``) and reused;
* ``SL[r, ci]`` gathers use ``SL.ravel().take(r*n_c + ci)`` (same elements, same order).
Every arithmetic expression keeps its operands and order, so the outputs are bit-identical.

``observations`` memo: when a frame's BGR bytes, the camera model key and the gate values equal those of the
previous call, the previous ``ColumnObs`` is returned (deep copy). ``observations`` is a deterministic function of
exactly these inputs (``harness.opencv_wall_observation``). About 12 % of recorded v98 frames repeat the previous
frame byte for byte.

``install`` refuses unless the source of the frozen functions hashes to the recorded values.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import math
from collections import OrderedDict

import numpy as np

# sha256 of inspect.getsource of the functions this module copies or wraps (a3415342)
PINNED = {'markerless_probe.detect_boundaries': '59459639ec2b7576ef97ff06e0724b2056e6174ef135b8240cd7bb0c85aca4e6',
          'opencv_wall_observation.observations': 'b37ceeec6dbee32d10bc8e071655ddd813e8ac1cd1fabb5732ca3bfe34e458cb'}


def _sha(fn):
    return hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()


def model_key(cm):
    parts = [type(cm).__qualname__]
    for name in sorted(vars(cm)):
        v = vars(cm)[name]
        if isinstance(v, np.ndarray):
            parts.append((name, v.dtype.str, v.shape, v.tobytes()))
        elif isinstance(v, (int, float, str, bool, tuple)) or v is None:
            parts.append((name, repr(v)))
        # dict caches (``_traces``) are derived from the attributes above
    return hashlib.sha256(repr(parts).encode()).hexdigest()


class GeometryCache:
    def __init__(self, size=16):
        self.size, self.data, self.hits, self.misses = size, OrderedDict(), 0, 0

    def get(self, key, build):
        if key in self.data:
            self.hits += 1
            self.data.move_to_end(key)
            return self.data[key]
        self.misses += 1
        value = build()
        self.data[key] = value
        if len(self.data) > self.size:
            self.data.popitem(last=False)
        return value


def make_detect_boundaries(mp, cache):
    WIDTH, HEIGHT, CY = mp.WIDTH, mp.HEIGHT, mp.CY
    DEFAULT_DETECTOR, Scan = mp.DEFAULT_DETECTOR, mp.Scan

    def geometry(cm, p, cols, n_c, self_top):
        vb = np.arange(HEIGHT - 2, 2, -1, dtype=float)[:, None]*np.ones((1, n_c))    # bottom -> top
        t = cm.t_of_row(vb)
        rng, _ = cm.range_bearing(np.where(np.isfinite(t), t, 0.))
        vt = cm.rows(np.where(np.isfinite(t), t, 0.), float(p['wall_height_m']))
        ok = (np.isfinite(t) & (rng >= p['min_range_m']) & (rng <= p['max_range_m']) & np.isfinite(vt)
              & (vb <= (self_top - int(p['self_margin_px']) - int(p['window_px']) - 1)[None, :])
              & (vb - vt >= p['min_band_px']))
        m = float(p['edge_margin_px'])
        w = int(p['window_px'])
        vb_i = np.round(vb).astype(int)
        tol = np.where(ok, float(p['top_tol_px']) + float(p['top_tol_frac'])*(vb - vt), 0.)
        band_top = np.floor(np.where(ok, np.maximum(vt + tol, 0.), 0.) + m).astype(int)
        band_bot = (vb_i - int(math.ceil(m)) + 1)
        vt_i = np.floor(np.where(ok, vt - tol, 0.)).astype(int)
        top_visible = vt_i - 1 - w >= 0

        def idx(r0, r1):
            r0 = np.clip(r0, 0, HEIGHT)
            r1 = np.clip(r1, 0, HEIGHT)
            n = np.maximum(r1 - r0, 1)
            ci = np.broadcast_to(np.arange(n_c), r0.shape)
            return r0*n_c + ci, r1*n_c + ci, n, r1 - r0
        lo, hi = np.clip(cols - (half := int(p['strip_half_px'])), 0, WIDTH), np.clip(cols + half + 1, 0, WIDTH)
        return {'vb': vb, 'vt': vt, 'ok': ok, 'vb_i': vb_i, 'tol': tol, 'top_visible': top_visible,
                'band': idx(band_top, band_bot), 'below': idx(vb_i + 1, vb_i + 1 + w),
                'above': idx(vt_i - w - 1, vt_i - 1), 'lo': lo, 'hi': hi}

    def detect_boundaries(und_bgr, cm, params=None, self_top=None):
        p = {**DEFAULT_DETECTOR, **(params or {})}
        cols = cm.columns
        n_c = len(cols)
        n_k = int(p['candidates'])
        img = und_bgr.astype(np.float32)
        lum = .114*img[..., 0] + .587*img[..., 1] + .299*img[..., 2]
        chroma = (img[..., 0] - img[..., 2])*float(p['chroma_weight'])
        if self_top is None:
            self_top = np.full(n_c, HEIGHT, int)
        key = (model_key(cm), repr(sorted(p.items())), np.asarray(self_top).tobytes())
        G = cache.get(key, lambda: geometry(cm, p, cols, n_c, self_top))
        csum = lambda a: np.concatenate([np.zeros((a.shape[0], 1), np.float64), np.cumsum(a, 1, dtype=np.float64)], 1)
        lo, hi = G['lo'], G['hi']
        strips = []
        for a in (lum, chroma):
            cs = csum(a)
            strips.append((cs[:, hi] - cs[:, lo])/(hi - lo)[None, :])
        L, Cr = strips
        pre = lambda a: np.vstack([np.zeros((1, n_c)), np.cumsum(a, 0)])
        SL, SL2, SC, SC2 = pre(L).ravel(), pre(L*L).ravel(), pre(Cr).ravel(), pre(Cr*Cr).ravel()

        def window(ix):
            f0, f1, n, rows = ix
            mL = (SL.take(f1) - SL.take(f0))/n
            mC = (SC.take(f1) - SC.take(f0))/n
            vL = np.maximum((SL2.take(f1) - SL2.take(f0))/n - mL*mL, 0.)
            vC = np.maximum((SC2.take(f1) - SC2.take(f0))/n - mC*mC, 0.)
            return mL, mC, vL + vC, rows

        vb, vt, ok, vb_i, tol, top_visible = G['vb'], G['vt'], G['ok'], G['vb_i'], G['tol'], G['top_visible']
        band = window(G['band'])
        below = window(G['below'])
        above = window(G['above'])
        contrast = lambda x, y: np.hypot(x[0] - y[0], x[1] - y[1])
        c_below = contrast(band, below)
        c_above = np.where(top_visible, contrast(band, above), 0.)
        std = np.sqrt(band[2])
        band_rows = band[3]
        accept = ok & (band_rows >= 2) & (c_below >= p['min_contrast_below']) & (std <= p['max_band_std']) & (
            np.where(top_visible, c_above >= p['min_contrast_above'], band_rows >= p['min_open_band_px']))

        def step(j, v):
            v = int(np.clip(v, 1, HEIGHT - 2))
            return math.hypot(L[v + 1, j] - L[v - 1, j], Cr[v + 1, j] - Cr[v - 1, j])

        def refine(j, v0, half_win):
            vs = np.arange(int(round(v0)) - half_win, int(round(v0)) + half_win + 1)
            vs = vs[(vs >= 1) & (vs <= HEIGHT - 2)]
            if vs.size < 3:
                return float(v0)
            g = np.array([step(j, v) for v in vs])
            k = int(np.argmax(g))
            off = 0.
            if 0 < k < len(g) - 1:
                den = g[k - 1] - 2*g[k] + g[k + 1]
                off = .5*(g[k - 1] - g[k + 1])/den if abs(den) > 1e-9 else 0.
            return float(vs[k] + np.clip(off, -.5, .5))

        out = {k: np.full((n_c, n_k), np.nan) for k in ('vb', 'vt', 'c', 's', 'r', 'b')}
        out_top = np.zeros((n_c, n_k), bool)
        for j in range(n_c):
            rows_ok = np.flatnonzero(accept[:, j])
            k = 0
            ceiling = np.inf
            for i in rows_ok:
                if k >= n_k:
                    break
                if vb[i, j] > ceiling:
                    continue
                v_b = refine(j, vb_i[i, j], 2)
                out['vb'][j, k] = v_b
                out['c'][j, k] = c_below[i, j]
                out['s'][j, k] = std[i, j]
                if top_visible[i, j]:
                    span = int(math.ceil(tol[i, j])) + 2
                    out['vt'][j, k] = refine(j, vt[i, j], span)
                    out_top[j, k] = True
                ceiling = max(float(vt[i, j]), 0.) + 2.
                k += 1
        det = np.isfinite(out['vb'])
        t_obs = cm.t_of_row(np.where(det, out['vb'], CY + 1.).T).T
        r_obs, b_obs = cm.range_bearing(np.where(np.isfinite(t_obs), t_obs, 0.).T)
        return Scan(cols.copy(), out['vb'], np.where(det & out_top, out['vt'], np.nan), out_top & det,
                    out['c'], out['s'], np.where(det, r_obs.T, np.nan), np.where(det, b_obs.T, np.nan),
                    np.asarray(self_top, int))
    return detect_boundaries


class ObservationMemo:
    """Previous-frame memo of ``observations(vl, bgr, camera, gates)`` (exact input equality)."""

    def __init__(self, original):
        self.original, self.key, self.bgr, self.value, self.hits, self.misses = original, None, None, None, 0, 0

    def __call__(self, vl, bgr, camera, gates=None):
        key = (id(vl), model_key(camera), repr(gates))
        bgr = np.asarray(bgr)
        if (self.value is not None and key == self.key and self.bgr.shape == bgr.shape
                and self.bgr.dtype == bgr.dtype and np.array_equal(self.bgr, bgr)):
            self.hits += 1
            return copy.deepcopy(self.value)
        self.misses += 1
        self.key = self.value = None
        value = self.original(vl, bgr, camera, gates)
        self.key, self.bgr, self.value = key, bgr.copy(), copy.deepcopy(value)
        return value


def install(record):
    """Swap ``markerless_probe.detect_boundaries`` (frozen VIS3 module attribute) and memoise observations."""
    from harness import vision_loc_protocol as vp
    from harness import opencv_wall_observation as ow
    vl, _ = vp.load_vis3()
    mp = vl.mp
    got = {'markerless_probe.detect_boundaries': _sha(mp.detect_boundaries),
           'opencv_wall_observation.observations': _sha(ow.observations)}
    if got != PINNED:
        record['opencv_exact'] = {'installed': False, 'refused': f'source sha256 differs: {got}'}
        return lambda: None
    cache = GeometryCache()
    original_detect, original_obs = mp.detect_boundaries, ow.observations
    mp.detect_boundaries = make_detect_boundaries(mp, cache)
    memo = ObservationMemo(original_obs)
    ow.observations = memo
    record['opencv_exact'] = {'installed': True, 'source_sha256': got, 'cache': cache, 'memo': memo}

    def undo():
        mp.detect_boundaries, ow.observations = original_detect, original_obs
    return undo
