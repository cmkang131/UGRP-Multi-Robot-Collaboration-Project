"""Bit-identical rewrite of the frozen VIS3 ``vision_loc.expected_rows`` for the v98 PF (speedup item, opt-in).

``expected_rows`` calls ``first_blocked`` twice per scan (bottom trace, top trace) over the same particles,
footprints and view-fan corners. Every particle x column element is computed here with the same float32
operations in the same order as ``vision_loc.first_blocked``; only work is removed:

* trace-independent work (float32 casts of origins/directions, ``ddx/ddy``, corner offsets, the corner
  determinant ``det`` and its ``ok`` mask) is done once for both traces;
* the corner-independent ``mu`` numerator ``-rx*dy + ry*dx`` is done once per trace instead of per corner;
* corner offsets ``c - o`` and the footprint gap test are evaluated on the (P, 1) camera origins before
  broadcasting to (P, C) (the same scalar op per particle; ``gap.min()`` is a min over the same values);
* the corner hit time ``t`` is evaluated only on elements with ``ok & mu >= 1`` (elementwise ops on a gathered
  subset give the same values; the original keeps only those elements anyway).

The frozen file is not modified; ``install`` swaps the module attribute ``vision_loc.expected_rows`` only when
the source of the five frozen functions hashes to ``SOURCE_SHA256``. Proof of identity (2026-10-05, DEV):
110 recorded/perturbed P=2000 and small inputs bit-equal; a 400-frame offline replay of recorded r1 frames and
commands gave byte-equal reports, weights and particles (outputs/v98-walltime-profile-20261005/microbench).
A full-run byte comparison is still required before any run enables it.
"""
from __future__ import annotations

import hashlib
import inspect

import numpy as np

FUNCTIONS = ('expected_rows', 'first_blocked', '_segment_hits', '_fan_corners', '_rects')
SOURCE_SHA256 = '9be748c247b33ab5256fdd99be125fb62e6c02178d0cf4060adb0f1f6f1638ea'


def source_sha256(vl):
    return hashlib.sha256(''.join(inspect.getsource(getattr(vl, n)) for n in FUNCTIONS).encode()).hexdigest()


def _blocked0(vl, rects, ox, oy, sx, sy, o1x, o1y):
    reach = float(np.sqrt(np.max((sx - ox)**2 + (sy - oy)**2))) if ox.size else 0.
    blocked0 = np.zeros(ox.shape, bool)
    if reach > 1e-6:
        for r in rects:
            cx, cy, hx, hy = r
            gap = np.hypot(np.maximum(np.abs(o1x - cx) - hx, 0.), np.maximum(np.abs(o1y - cy) - hy, 0.))
            if float(gap.min()) <= reach:
                blocked0 |= vl._segment_hits(ox, oy, sx, sy, r)
    return blocked0


def first_blocked_traces(vl, rects, ox1, oy1, traces, dx, dy, corners):
    """``[vl.first_blocked(rects, ox1, oy1, qx, qy, dx, dy, t_min, corners) for qx, qy, t_min in traces]``.

    ox1, oy1: (P, 1) camera origins; dx, dy: (P, C) directions; qx, qy: (P, C); t_min: scalar or (1, C).
    """
    o32x, o32y = np.asarray(ox1, np.float32), np.asarray(oy1, np.float32)
    dx32, dy32 = np.asarray(dx, np.float32), np.asarray(dy, np.float32)
    shape = np.broadcast_shapes(o32x.shape, dx32.shape)
    dx32, dy32 = np.broadcast_to(dx32, shape), np.broadcast_to(dy32, shape)
    ox, oy = np.broadcast_to(o32x, shape), np.broadcast_to(o32y, shape)
    if o32x.ndim != 2 or o32x.shape[1] != 1:
        raise ValueError('camera origins must be (P, 1)')
    ncol = shape[1]
    st = []
    for qx, qy, t_min in traces:
        qx = np.broadcast_to(np.asarray(qx, np.float32), shape)
        qy = np.broadcast_to(np.asarray(qy, np.float32), shape)
        t_min = np.broadcast_to(np.asarray(t_min, np.float32), shape)
        sx, sy = qx + t_min*dx32, qy + t_min*dy32
        rx, ry = qx - ox, qy - oy
        st.append({'qx': qx, 'qy': qy, 't_min': t_min, 'best': np.full(shape, np.inf, np.float32),
                   'blocked0': _blocked0(vl, rects, ox, oy, sx, sy, o32x, o32y), 'rx': rx, 'ry': ry,
                   'num': -rx*dy32 + ry*dx32})
    ddx = np.where(np.abs(dx32) < 1e-9, 1e-9, dx32)
    ddy = np.where(np.abs(dy32) < 1e-9, 1e-9, dy32)
    for ri, r in enumerate(rects):
        cx, cy, hx, hy = r
        for s in st:
            qx, qy, best = s['qx'], s['qy'], s['best']
            tx1, tx2 = (cx - hx - qx)/ddx, (cx + hx - qx)/ddx
            ty1, ty2 = (cy - hy - qy)/ddy, (cy + hy - qy)/ddy
            tmin = np.maximum(np.minimum(tx1, tx2), np.minimum(ty1, ty2))
            tmax = np.minimum(np.maximum(tx1, tx2), np.maximum(ty1, ty2))
            enter = np.maximum(tmin, s['t_min'])
            s['best'] = np.where((tmax > enter) & (enter < best), enter, best)
        for ki, (kx, ky) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
            if corners is not None and (ri, ki) not in corners:
                continue
            ax, ay = cx + kx*hx - o32x, cy + ky*hy - o32y                          # (P, 1)
            det = -ax*dy32 + ay*dx32
            ok = np.abs(det) > 1e-9
            det = np.where(ok, det, 1.)
            for s in st:
                rx, ry, t_min, best = s['rx'], s['ry'], s['t_min'], s['best']
                mu = s['num']/det
                cand = np.flatnonzero(ok & (mu >= 1.))
                if cand.size == 0:
                    continue
                row = cand // ncol
                tc = (ax[row, 0]*ry.flat[cand] - ay[row, 0]*rx.flat[cand])/det.flat[cand]
                keep = (tc >= t_min.flat[cand]) & (tc < best.flat[cand])
                idx, tk = cand[keep], tc[keep]
                if idx.size == 0:
                    continue
                te = tk + 1e-4
                hit = vl._segment_hits(ox.flat[idx], oy.flat[idx], s['qx'].flat[idx] + te*dx32.flat[idx],
                                       s['qy'].flat[idx] + te*dy32.flat[idx], r)
                best.flat[idx[hit]] = tk[hit]
    return [np.where(s['blocked0'], -np.inf, s['best']) for s in st]


def make_expected_rows(vl):
    """Drop-in for ``vl.expected_rows`` (same signature, same outputs bit for bit)."""
    POS_INF, NEG_INF = vl.POS_INF, vl.NEG_INF

    def expected_rows(geometry, poses, cm, wall_height_m=vl.WALL_HEIGHT_M):
        poses = np.asarray(poses, float).reshape(-1, 3)
        if np.any(geometry.rects[:, 4] < cm.origin[2] - 1e-6):
            raise ValueError('expected_rows assumes walls at least as tall as the camera')
        rects = vl._rects(geometry).astype(np.float32)
        c, s = np.cos(poses[:, 2])[:, None], np.sin(poses[:, 2])[:, None]
        dx = c*cm.d[None, :, 0] - s*cm.d[None, :, 1]
        dy = s*cm.d[None, :, 0] + c*cm.d[None, :, 1]
        o = cm.origin[:2]
        ox = poses[:, :1] + c*o[0] - s*o[1]
        oy = poses[:, 1:2] + s*o[0] + c*o[1]

        def world(q):
            return poses[:, :1] + c*q[None, :, 0] - s*q[None, :, 1], poses[:, 1:2] + s*q[None, :, 0] + c*q[None, :, 1]
        qx, qy = world(cm.q0)
        q0h, _ = cm.trace_at(wall_height_m)
        hx, hy = world(q0h)
        s_cam = np.sum((o[None, :] - q0h)*cm.d, 1)[None, :]
        sight = [(qx - ox, qy - oy), (hx + s_cam*dx - ox, hy + s_cam*dy - oy), (dx, dy)]
        fan = vl._fan_corners(rects, ox, oy, np.concatenate([a for a, _ in sight], 1),
                              np.concatenate([b for _, b in sight], 1))
        t32, st32 = first_blocked_traces(vl, rects, ox, oy, [(qx, qy, 0.), (hx, hy, s_cam)], dx, dy, fan)
        t = t32.astype(float)
        with np.errstate(invalid='ignore'):
            vb = np.where(np.isfinite(t), cm.rows(np.where(np.isfinite(t), t, 0.)), np.nan)
        vb = np.where(t == -np.inf, POS_INF, vb)
        vb = np.where(np.isnan(vb), NEG_INF, vb)
        st = st32.astype(float)
        ok = np.isfinite(st)
        with np.errstate(invalid='ignore'):
            vt = np.where(ok, cm.rows_at(np.where(ok, st, 0.), wall_height_m), np.nan)
        return vb, np.nan_to_num(vt, nan=NEG_INF)
    expected_rows.__wrapped_frozen__ = vl.expected_rows
    return expected_rows


def install(record):
    """Swap ``vision_loc.expected_rows`` (module attribute of the hash-checked frozen VIS3 module); returns undo."""
    from harness import vision_loc_protocol as vp
    vl, _ = vp.load_vis3()
    got = source_sha256(vl)
    if got != SOURCE_SHA256:
        record['pf_geometry_shared'] = {'installed': False, 'refused': f'frozen source sha256 {got} differs'}
        return lambda: None
    original = vl.expected_rows
    vl.expected_rows = make_expected_rows(vl)
    record['pf_geometry_shared'] = {'installed': True, 'source_sha256': got}
    return lambda: setattr(vl, 'expected_rows', original)
