"""Offline follow-up check (reviewer item 7 of PR #265; no physics, no model call, not used for any judgement).

For every stored own-camera frame on which the b-v6d controller read the beam with the wide hue bound
(``beam_obs`` event with ``hue_lo`` = 25, posture p45/inspect) it re-runs the beam perception on the SAME jpg
with (a) the v1 lime range (hue 36-54, the b-v6c behaviour) and (b) hue 25-54 and compares

* beam pixel count (pixels that project onto the beam-top plane within 2.5 m) and v2 result (visible, points,
  visible length, axis heading, heading error against eval-only GT),
* how many of the pixels that the wide range ADDS project outside the ground-truth beam footprint
  (beam 0.60 x 0.05 m at the eval-only trace pose, margin 0.06 m for side faces seen under the top plane).
  Such pixels would be non-beam yellow objects (a yellow wheel, a yellow box) or background entering the mask.

Ground truth (eval_only/trace.jsonl) is read offline only, for this diagnosis. It never reaches a controller.
Frames are matched to events by sim time and the wide observation is re-run to confirm it reproduces the logged
``points`` / ``axis_heading_rad`` (``repro`` column).
"""
import bisect
import collections
import json
import math
import os
import sys

import cv2
import numpy as np

ROOT = os.environ.get('UGRP_ROOT', os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
sys.path.insert(0, ROOT)
from harness import owncam_pair_beam as v1                      # noqa: E402
from harness import owncam_pair_beam_v2 as v2                   # noqa: E402
from harness import owncam_pair_beam_v6d as v6d                 # noqa: E402
from harness.owncam_view import base_rays                       # noqa: E402

RUNS = ['/Users/changmin/projects/ugrp/outputs/pair-stage-probes-052e3eba-v6d-venv-align-0',
        '/Users/changmin/projects/ugrp/outputs/pair-stage-probes-052e3eba-v6d-venv-align-1']
RAW_OUT = '/Users/changmin/projects/ugrp/outputs/pair-stage-probes-052e3eba-v6d-hue-mask-check.json'
BEAM_HALF_LEN, BEAM_HALF_W, MARGIN = 0.30, 0.025, 0.06
OUTSIDE_MIN_PX = 10                       # a frame "has non-beam pixels" when at least this many added pixels are outside


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def half(a):
    a = wrap(a)
    if a > math.pi / 2:
        a -= math.pi
    if a <= -math.pi / 2:
        a += math.pi
    return a


def plane_points(mask, pose, count_all=False):
    """Beam-plane points of the masked pixels (ray-sampled as v1 does); ``count_all``: also the masked samples
    that do NOT project onto the plane within 2.5 m (above the horizon or farther away)."""
    origin, rays, xs, ys, valid = base_rays(pose, v1.RAY_STEP)
    xi, yi = xs.astype(int), ys.astype(int)
    hit = valid & mask[yi, xi] & (rays[:, 2] < -1e-6)
    s = (v1.BEAM_TOP_Z_M - origin[2]) / rays[hit, 2]
    pts = (origin + s[:, None] * rays[hit])[:, :2]
    ok = (s > 0) & (np.linalg.norm(pts, axis=1) < 2.5)
    if count_all:
        return pts[ok], int((valid & mask[yi, xi]).sum()) - int(ok.sum())
    return pts[ok]


def main():
    rows = []
    for run in RUNS:
        for case in sorted(os.listdir(run + '/cases')):
            base = f'{run}/cases/{case}'
            if not os.path.isdir(base) or not os.path.exists(base + '/result.json'):
                continue
            res = json.load(open(base + '/result.json'))
            rob = json.load(open(base + '/robots.json'))
            tr = [json.loads(line) for line in open(base + '/eval_only/trace.jsonl')]
            ts = [x['t'] for x in tr]
            for rid in ('r1', 'r2'):
                evs = [e for e in res['controller_events'].get(rid, []) if e['event'] == 'beam_obs' and e.get('hue_lo')]
                frames = rob[rid]['frames']
                ft = [f['t'] for f in frames]
                for e in evs:
                    j = min(range(len(ft)), key=lambda k: abs(ft[k] - e['sim_s']))
                    f = frames[j]
                    img = cv2.imread(f"{base}/frames/{rid}/{f['frame']:05d}.jpg")
                    if img is None:
                        continue
                    pose = {int(k): v for k, v in f['commanded_servo'].items()}
                    dark = v6d.dark_band_mask(img)
                    m36, m25 = v6d.lime_mask(img), v6d.lime_mask(img, e['hue_lo'])
                    added = m25 & ~m36 & ~dark
                    p36, p25 = plane_points(m36, pose), plane_points(m25, pose)
                    padd, off_plane = plane_points(added, pose, count_all=True)
                    i = min(bisect.bisect_left(ts, f['t']), len(tr) - 1)
                    x, y, yaw = tr[i]['robots'][rid]
                    bx, by, _ = tr[i]['beam_xyz']
                    gh = half(tr[i]['beam_yaw'] - yaw)
                    c, s = math.cos(-yaw), math.sin(-yaw)
                    centre = np.array([c * (bx - x) - s * (by - y), s * (bx - x) + c * (by - y)])
                    d = padd - centre
                    a = d[:, 0] * math.cos(-gh) - d[:, 1] * math.sin(-gh)
                    lat = d[:, 0] * math.sin(-gh) + d[:, 1] * math.cos(-gh)
                    outside = (np.abs(a) > BEAM_HALF_LEN + MARGIN) | (np.abs(lat) > BEAM_HALF_W + MARGIN)
                    old, new = v2.observe_beam(img, pose), v6d.observe_beam(img, pose, hue_lo=e['hue_lo'])
                    repro = (new.get('points') == e.get('points')
                             and abs((new.get('axis_heading_rad') or 0) - (e.get('axis_heading_rad') or 0)) < 1e-9)

                    def err(o):
                        return None if o.get('axis_heading_rad') is None else half(o['axis_heading_rad'] - gh)
                    rows.append(dict(run=os.path.basename(run), case=case, rid=rid, posture=e['posture'], t=f['t'],
                                     n36=len(p36), n25=len(p25), added=len(padd), off_plane=off_plane, outside=int(outside.sum()),
                                     vis36=bool(old.get('visible')), vis25=bool(new.get('visible')),
                                     pts36=old.get('points'), pts25=new.get('points'),
                                     len36=old.get('visible_length_m'), len25=new.get('visible_length_m'),
                                     err36=err(old), err25=err(new), repro=repro))
    json.dump(rows, open(RAW_OUT, 'w'))         # per-frame rows (0.9 MB): kept out of git, sha256 in the README
    for rid in ('r1', 'r2'):
        for posture in ('p45', 'inspect', None):
            v = [r for r in rows if r['rid'] == rid and (posture is None or r['posture'] == posture)]
            if not v:
                continue
            label = posture or 'p45+inspect'
            e36 = np.array([abs(r['err36']) for r in v if r['err36'] is not None])
            e25 = np.array([abs(r['err25']) for r in v if r['err25'] is not None])
            both = [r for r in v if r['err36'] is not None and r['err25'] is not None]
            print(f'{rid} {label}: frames={len(v)} repro={sum(r["repro"] for r in v)}/{len(v)}')
            print(f'   plane-projected beam pixels  hue36 median={np.median([r["n36"] for r in v]):.0f}  '
                  f'hue25 median={np.median([r["n25"] for r in v]):.0f}  added median={np.median([r["added"] for r in v]):.0f}')
            print(f'   v2 visible hue36={sum(r["vis36"] for r in v)} hue25={sum(r["vis25"] for r in v)}; '
                  f'visible length median hue36={np.median([r["len36"] or 0 for r in v]):.2f} m hue25={np.median([r["len25"] or 0 for r in v]):.2f} m')
            if len(e36) and len(e25):
                print(f'   |heading err| (GT, offline) hue36 median={np.median(e36):.3f} rad, >0.05: {int((e36 > .05).sum())}/{len(e36)}; '
                      f'hue25 median={np.median(e25):.3f} rad, >0.05: {int((e25 > .05).sum())}/{len(e25)}')
            better = sum(abs(r['err25']) < abs(r['err36']) - 0.005 for r in both)
            worse = sum(abs(r['err25']) > abs(r['err36']) + 0.005 for r in both)
            print(f'   per frame (|err| differs by >5 mrad): hue25 better {better}, worse {worse}, same {len(both) - better - worse}')
            fo = [r for r in v if r['outside'] >= OUTSIDE_MIN_PX]
            print(f'   added pixels outside GT beam footprint (+{MARGIN} m): frames with >= {OUTSIDE_MIN_PX} such pixels: {len(fo)}/{len(v)}; '
                  f'max per frame {max(r["outside"] for r in v)}; total {sum(r["outside"] for r in v)} of {sum(r["added"] for r in v)} added')
            print(f'   added samples that do not project onto the beam-top plane within 2.5 m (above horizon / far): '
                  f'frames with any: {sum(r["off_plane"] > 0 for r in v)}/{len(v)}; max per frame {max(r["off_plane"] for r in v)}')
            for r in sorted(fo, key=lambda r: -r['outside'])[:5]:
                print(f'      {r["run"][-7:]} {r["case"]} {r["rid"]} {r["posture"]} t={r["t"]:.1f} outside={r["outside"]} added={r["added"]}')


if __name__ == '__main__':
    main()
