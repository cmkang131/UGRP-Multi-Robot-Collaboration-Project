"""Per-frame structure-pixel audit of recorded stage-probe wrist frames (offline; no simulator, no models).

usage: python audit_run.py <inventory.json> <out.jsonl.gz> [--workers N] [--limit N]

Per (case, robot, frame) row: stage phase from the eval-only trace, load state from the robot's own report, and
three structure fractions over the valid (non-rim) pixels:
  G  map-predicted structure in the field of view (GT pose + issued servo + static map; occlusion ignored)
  V  visible structure = G minus pixels the colour rules call beam / dark occluder / orange gripper
  R  rule-only column-scan structure from the image alone (no GT; counts the wall's mirror image on the glossy floor)
Wall-tag plates are excluded from every numerator and reported apart.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import geom  # noqa: E402
import rule  # noqa: E402

DOOR_X, DOOR_Y = 2.2, 0.05
STRIDE = 4
STRIDE_CARRY = 8
OCC_V = 18


def phase_of(stage, state, lift, jaws_closed, rid_state_t, load):
    """Audit phase from the controller state name (eval trace), beam lift and own load state."""
    if stage == 'align':
        if state is None or state in ('approach',):
            return 'align_start'
        if state.startswith('align_relook'):
            return 'align_relook' if rid_state_t['seen_align'] else 'align_start'
        if state == 'align':
            rid_state_t['seen_align'] = True
            return 'align_body'
        return 'align_other'
    if stage == 'grasp_lift':
        if state is None:
            return 'grasp_staged_start'
        if state in ('approach', 'pregrasp_standoff', 'pregrasp_descend'):
            return 'pregrasp'
        if state in ('wait_close', 'grasp'):
            return 'grasp_close'
        if state in ('wait_lift', 'lift') and lift < 0.03:
            return 'lifting'
        if lift >= 0.03:
            return 'lift_done'
        return 'grasp_other'
    if stage == 'carry':
        if state in ('wait_carry', 'carry') and lift >= 0.03:
            return 'carry'
        if state in ('wait_lower', 'probe_exit_carry') and lift >= 0.03:
            return 'carry_leg_end'
        return None                     # teacher staging / pre-controller frames
    if stage == 'setdown':
        if state in ('wait_lower', 'lower'):
            return 'setdown_lowering' if lift >= 0.01 else 'setdown_after_lower'
        if state == 'wait_open':
            return 'setdown_after_lower'
        if state in ('released', 'done'):
            if state == 'released' and rid_state_t.get('t_rel') is None:
                rid_state_t['t_rel'] = rid_state_t['t']
            t_rel = rid_state_t.get('t_rel')
            return 'open_0_2s' if (t_rel is not None and rid_state_t['t'] - t_rel <= 2.0) else 'open_2s_plus'
        return None
    return None


def process_case(item):
    case, stride_scale = item
    cdir = case['dir']
    out = []
    try:
        rb = json.load(open(f'{cdir}/robots.json'))
        tr = [json.loads(l) for l in open(f'{cdir}/eval_only/trace.jsonl')]
    except (OSError, ValueError):
        return out
    tt = np.array([t['t'] for t in tr])
    valid = geom.full_valid()
    nvalid = int(valid.sum())
    for rid in ('r1', 'r2'):
        frames = (rb.get(rid) or {}).get('frames') or []
        ctx = {'seen_align': False, 't_rel': None, 't': 0.}
        for n, f in enumerate(frames):
            i = int(np.abs(tt - f['t']).argmin())
            row_tr = tr[i]
            state = row_tr['states'].get(rid)
            lift = float(row_tr['lift_m'])
            ctx['t'] = float(f['t'])
            ph = phase_of(case['stage'], state, lift, row_tr['jaws'][rid][0], ctx, f['report']['load_state'])
            if ph is None:
                continue
            stride = (STRIDE_CARRY if ph.startswith('carry') else STRIDE)
            if n % stride:
                continue
            g = row_tr['robots'][rid]
            servo = f['commanded_servo']
            im = cv2.imread(f"{cdir}/frames/{rid}/{f['frame']:05d}.jpg")
            if im is None:
                continue
            lab4, _ = geom.predict_labels(servo, g, 4)
            lab = cv2.resize(lab4.astype(np.uint8), (640, 480), interpolation=cv2.INTER_NEAREST)
            tagp = geom.tag_mask(servo, g) & valid
            wall_g = ((lab == geom.WALL) | (lab == geom.POST)) & valid & ~tagp
            post_g = (lab == geom.POST) & valid & ~tagp
            stt, tagr, beam, m = rule.structure(im, valid)
            orange = (m['h'] >= 5) & (m['h'] <= 25) & (m['s'] > 120) & (m['v'] > 60)
            occ = beam | orange | (m['v'] < OCC_V)
            vis = wall_g & ~occ
            vis_post = post_g & ~occ
            door = (abs(g[0] - DOOR_X) < 0.6) and (-0.45 < g[1] - 0. < 0.55)
            out.append({
                'run': case['run'], 'case': os.path.basename(cdir), 'stage': case['stage'], 'leg': case['leg'],
                'policy': case['policy'], 'cell': case['cell'], 'seed': case['seed'], 'variant': case['setup_variant'],
                'source': case['source'], 'profile': case['render_profile'], 'robot': rid, 't': round(float(f['t']), 3),
                'frame': f['frame'], 'phase': ph, 'load': f['report']['load_state'], 'state': state,
                'lift_m': round(lift, 4), 'gt': [round(float(v), 4) for v in g], 'door_zone': bool(door),
                'servo': {k: int(v) for k, v in servo.items() if k in ('3', '4', '5', '6')},
                'G': float(wall_g.sum() / nvalid), 'V': float(vis.sum() / nvalid), 'R': float(stt.sum() / nvalid),
                'G_post': float(post_g.sum() / nvalid), 'V_post': float(vis_post.sum() / nvalid),
                'cols_V': int((vis.sum(axis=0) >= 4).sum()), 'cols_R': int((stt.sum(axis=0) >= 4).sum()),
                'tag_geom': float(tagp.sum() / nvalid), 'tag_rule': float(tagr.sum() / nvalid),
                'beam': float(beam.sum() / nvalid), 'dark': float(((m['v'] < OCC_V) & valid).sum() / nvalid),
            })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inventory')
    ap.add_argument('out')
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    inv = json.load(open(a.inventory))
    if a.limit:
        inv = inv[::max(1, len(inv) // a.limit)][:a.limit]
    items = [(c, 1) for c in inv]
    n = 0
    with gzip.open(a.out, 'wt') as fh, Pool(a.workers) as pool:
        for k, rows in enumerate(pool.imap(process_case, items, chunksize=2)):
            for r in rows:
                fh.write(json.dumps(r) + '\n')
            n += len(rows)
            if k % 50 == 0:
                print(k, len(items), n, flush=True)
    print('rows', n)


if __name__ == '__main__':
    main()
