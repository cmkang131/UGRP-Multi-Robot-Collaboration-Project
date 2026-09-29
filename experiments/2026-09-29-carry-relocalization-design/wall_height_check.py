"""Does the wall height (0.10 m dev tag map vs 0.40 m final walls_v3) change what a wrist camera can see?

Map-only geometry (geom_min.py): ray-cast the recorded wrist pose + issued servo pulses against the door map's walls, once with
the walls at 0.10 m and once at 0.40 m (same footprints, same map file zone_wide_door_geometry_v2, tag free). Occlusion by the beam
and arm is NOT modelled, so every share is an upper bound (the audit's `G`).

(a) carry: recorded carry frames of the nominal s911 leg cases (GT robot pose from eval_only/trace.jsonl, issued servo from robots.json)
(b) unloaded look poses at every chain checkpoint (the audit's cand_points geometry)

usage: python wall_height_check.py <cases_root> <out.json>
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geom_min as gm  # noqa: E402

MAP = 'zone_wide_door_geometry_v2'
ROUTE = [[1.0, 0.05], [1.55, 0.05], [2.4, 0.05], [3.2, 0.05], [3.2, -0.6667], [3.2, -1.3833], [3.2, -2.1], [3.9, -2.1], [4.6, -2.1]]
HALF = 0.425
SEARCH_POSE = {1: 2000, 3: 740, 4: 2320, 5: 1320}
PANS = (1500, 1230, 1770, 970, 2030, 700, 2300)
CARRY_HOVER = {1: 1500, 3: 611, 4: 1711, 5: 2200, 6: 1500}
CARRY_CASES = {0: 'carry_b-v6e_teacher_nominal_s911_pE2E_Vcal', **{k: f'carry_b-v6e_teacher_nominal_s911_pE2E_L{k}_Vcal' for k in range(1, 7)}}


def pct(a, p):
    return float(np.percentile(a, p)) if len(a) else None


def main(root, out):
    base = gm.load_map(MAP)
    maps = {'wall_0.10m': gm.with_wall_height(base, 0.10), 'wall_0.40m': gm.with_wall_height(base, 0.40)}
    res = {'map': MAP, 'note': 'G = map-predicted wall/post pixel share of the valid image; beam/arm occlusion ignored (upper bound)',
           'carry': {}, 'look': {}}
    # (a) recorded carry frames
    for leg, name in CARRY_CASES.items():
        cdir = Path(root) / name
        try:
            rb = json.load(open(cdir / 'robots.json'))
            tr = [json.loads(l) for l in open(cdir / 'eval_only' / 'trace.jsonl')]
        except OSError:
            continue
        tt = np.array([t['t'] for t in tr])
        shares = {k: [] for k in maps}
        n = 0
        for rid in ('r1', 'r2'):
            frames = (rb.get(rid) or {}).get('frames') or []
            for i, f in enumerate(frames):
                if i % 8:
                    continue
                row = tr[int(np.abs(tt - f['t']).argmin())]
                if row['states'].get(rid) not in ('wait_carry', 'carry') or row['lift_m'] < 0.03:
                    continue
                pose = row['robots'][rid]
                for k, m in maps.items():
                    shares[k].append(gm.structure_share(m, f['commanded_servo'], pose))
                n += 1
        res['carry'][f'L{leg}'] = {'frames': n, **{k: {'max': max(v) if v else None, 'p95': pct(v, 95), 'median': pct(v, 50),
                                                         'share_frames_ge_3pct': (float(np.mean(np.array(v) >= 0.03)) if v else None)}
                                                   for k, v in shares.items()}}
    # (b) unloaded look poses at checkpoints
    for k, (bx, by) in enumerate(ROUTE):
        for rid, dx, yaw in (('r1', -HALF, 0.), ('r2', HALF, math.pi)):
            pose = (bx + dx, by, yaw)
            row = {}
            for mk, m in maps.items():
                looks = {str(p): gm.structure_share(m, {**SEARCH_POSE, 6: p}, pose) for p in PANS}
                row[mk] = {'best_pan_G': max(looks.values()), 'centre_pan_G': looks['1500'],
                           'carry_hover_G': gm.structure_share(m, CARRY_HOVER, pose)}
            res['look'][f'cp{k}_{rid}'] = {'robot_xyyaw': [round(v, 3) for v in pose], **row}
    json.dump(res, open(out, 'w'), indent=1)
    print(json.dumps({k: v for k, v in res['carry'].items()}, indent=None)[:1500])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
