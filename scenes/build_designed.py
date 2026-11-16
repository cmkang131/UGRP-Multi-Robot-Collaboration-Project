#!/usr/bin/env python3
"""Build scenes_designed_v2.json (L 12, C 12, X 3, D 3). Standard library only; deterministic (seeded); no simulation, no LLM.

Each slot has fixed balance attributes (holder, first-listed, sign pair, colours). Geometry is rejection-sampled with a seeded
RNG until the geometry rules, the type structure and the oracle/gap tests all hold. Rejections are counted by reason and written
to the JSON ("dropped"). Usage: python3 build_designed.py [out.json]
"""
import json
import math
import os
import random
import sys
from collections import Counter

import model_v2 as m

SEED_BASE = 20261115
MAX_TRY = 40000
TYPE_NAME = {'L': 'orders_concentrated', 'C': 'same_colour_competition', 'X': 'knowledge_distance_crossed', 'D': 'decoy_boxes'}

# ordered sign pairs (correct sign of the deciding robot, other sign): A (11,12) x2, B (11,13) x4, C (12,11) x3, D (13,11) x1,
# E (13,12) x2. Correct sign 11/12/13 = 6/3/3 (menu read as 11,12,13: 11 first in 6/12); the correct sign is also the lower of the
# holder's two order signs in exactly 6/12 (menu read as the holder's own signs). Other sign 11/12/13 = 4/4/4. 11-correct is 3 per
# holder and 3 per first-listed value. Cells c0..c3 = (holder r1,first), (r2,first), (r1,second), (r2,second), 3 slots each.
CELL_PAIRS = [[(11, 12), (11, 13), (12, 11)],
              [(11, 13), (12, 11), (13, 12)],
              [(11, 13), (12, 11), (13, 12)],
              [(11, 12), (11, 13), (13, 11)]]
CELL_COLOURS = [['red', 'blue', 'red'], ['blue', 'red', 'blue'], ['blue', 'red', 'blue'], ['red', 'blue', 'red']]
CELL_HOLDER = ['r1', 'r2', 'r1', 'r2']
CELL_FIRST = [True, True, False, False]


def snap(v):
    return round(round(v / 0.05) * 0.05, 2)


def pt(rng):
    return (rng.uniform(m.X_MIN + m.CLEAR, m.PART_X - m.CLEAR), rng.uniform(m.Y_MIN + m.CLEAR, m.Y_MAX - m.CLEAR))


def polar(p, d, ang):
    return (p[0] + d * math.cos(ang), p[1] + d * math.sin(ang))


def sp(p):
    return (snap(p[0]), snap(p[1]))


def make_robot(rid, pos, box_points):
    yaw, span = m.bisector_yaw(pos[0], pos[1], box_points)
    return {'rid': rid, 'x': pos[0], 'y': pos[1], 'yaw': round(yaw, 4)}


def two_box_geometry(rng, min_sep, margin):
    """-> (box P pos, box Q pos, robot near P, robot near Q) with distinct nearest boxes and a `margin` m gap to the far box."""
    a, b = sp(pt(rng)), sp(pt(rng))
    if m.dist(a, b) < min_sep:
        return None, 'boxes too close'
    ra = sp(polar(a, rng.uniform(0.65, 1.05), rng.uniform(-math.pi, math.pi)))
    rb = sp(polar(b, rng.uniform(0.65, 1.05), rng.uniform(-math.pi, math.pi)))
    if not (m.dist(ra, a) + margin <= m.dist(ra, b) and m.dist(rb, b) + margin <= m.dist(rb, a)):
        return None, 'nearest-box margin'
    return (a, b, ra, rb), None


MAX_BOX_DIST = 2.6      # designed-scene choice: legacy scenes reach 2.53 m (X05); RGB detection beyond 0.8 m is unverified
MAX_DEV_DEG = 65.0      # designed-scene margin inside the 70 deg rule


def finish(scene, reasons, extra_checks=None):
    errs = m.geometry_errors(scene)
    if errs:
        reasons['geometry'] += 1
        return False
    far = max(m.dist(r, b) for r in scene['robots'] for b in scene['boxes'])
    dev = max(abs(math.degrees(m.wrap(math.atan2(b['y'] - r['y'], b['x'] - r['x']) - r['yaw']))) for r in scene['robots'] for b in scene['boxes'])
    if far > MAX_BOX_DIST or dev > MAX_DEV_DEG:
        reasons['designed distance/heading margin'] += 1
        return False
    m.annotate(scene)
    if extra_checks:
        why = extra_checks(scene)
        if why:
            reasons[why] += 1
            return False
    return True


def knows_dict(**kw):
    return {'r1': kw.get('r1', []), 'r2': kw.get('r2', [])}


def build_L(idx, cell, j, rng, reasons):
    h = CELL_HOLDER[cell]
    o_rid = 'r2' if h == 'r1' else 'r1'
    first = CELL_FIRST[cell]
    sH, sB = CELL_PAIRS[cell][j]
    cH = CELL_COLOURS[cell][j]
    cB = 'blue' if cH == 'red' else 'red'
    swap_ids = rng.random() < 0.5
    for _ in range(MAX_TRY):
        reasons['sampled'] += 1
        g, why = two_box_geometry(rng, 1.2, 0.4)
        if g is None:
            reasons[why] += 1
            continue
        a, b, ra, rb = g                       # a: holder's box, b: blind robot's box
        pos = {h: ra, o_rid: rb}
        pts = [a, b]
        ids = ('a', 'b') if not swap_ids else ('b', 'a')
        boxes = sorted([{'id': ids[0], 'colour': cH, 'x': a[0], 'y': a[1]}, {'id': ids[1], 'colour': cB, 'x': b[0], 'y': b[1]}],
                       key=lambda x: x['id'])
        oH = {'colour': cH, 'count': 1, 'sign': sH}
        oB = {'colour': cB, 'count': 1, 'sign': sB}
        o1, o2 = (oH, oB) if first else (oB, oH)
        orders = [dict(id='o1', **o1), dict(id='o2', **o2)]
        scene = {'id': 'L2-%02d' % idx, 'type': TYPE_NAME['L'], 'type_code': 'L', 'control': False, 'boxes': boxes,
                 'robots': [make_robot(r, pos[r], pts) for r in ('r1', 'r2')], 'orders': orders,
                 'knows': knows_dict(**{h: ['o1', 'o2'], o_rid: []}), 'constraints': []}
        hid = 'o1' if first else 'o2'

        def chk(s):
            if s['oracle_plan'][h] != [[ids[0], hid]] or len(s['oracle_plan'][o_rid]) != 1:
                return 'oracle not holder-nearest'
            e = s['estimate']
            if e['gap'] < m.GAP_MIN - m.EPS or e['gap_guess'] < m.GAP_MIN - m.EPS:
                return 'gap < 0.5'
            if s['balance']['correct_is_first_order'] != first or s['balance']['holder'] != h:
                return 'balance mismatch'
            return None
        if finish(scene, reasons, chk):
            return scene
    raise RuntimeError('L slot %d failed' % idx)


def build_C(idx, cell, j, rng, reasons):
    h = CELL_HOLDER[cell]
    p_rid = 'r2' if h == 'r1' else 'r1'
    first = CELL_FIRST[cell]                       # the holder's correct order (the one the partner does not know) is o1
    sC, sP = CELL_PAIRS[cell][j]
    colour = CELL_COLOURS[cell][j]
    swap_ids = rng.random() < 0.5
    for _ in range(MAX_TRY):
        reasons['sampled'] += 1
        g, why = two_box_geometry(rng, 1.2, 0.4)
        if g is None:
            reasons[why] += 1
            continue
        a, b, ra, rb = g                       # a: holder's nearest box, b: partner's nearest box
        pos = {h: ra, p_rid: rb}
        ids = ('a', 'b') if not swap_ids else ('b', 'a')
        boxes = sorted([{'id': ids[0], 'colour': colour, 'x': a[0], 'y': a[1]}, {'id': ids[1], 'colour': colour, 'x': b[0], 'y': b[1]}],
                       key=lambda x: x['id'])
        oC = {'colour': colour, 'count': 1, 'sign': sC}
        oP = {'colour': colour, 'count': 1, 'sign': sP}
        o1, o2 = (oC, oP) if first else (oP, oC)
        orders = [dict(id='o1', **o1), dict(id='o2', **o2)]
        pid = 'o2' if first else 'o1'
        cid = 'o1' if first else 'o2'
        scene = {'id': 'C2-%02d' % idx, 'type': TYPE_NAME['C'], 'type_code': 'C', 'control': False, 'boxes': boxes,
                 'robots': [make_robot(r, pos[r], [a, b]) for r in ('r1', 'r2')], 'orders': orders,
                 'knows': knows_dict(**{h: ['o1', 'o2'], p_rid: [pid]}), 'constraints': []}

        def chk(s):
            if s['oracle_plan'][h] != [[ids[0], cid]] or s['oracle_plan'][p_rid] != [[ids[1], pid]]:
                return 'oracle not nearest/known split'
            e = s['estimate']
            if e['gap'] < m.GAP_MIN - m.EPS or e['gap_guess'] < m.GAP_MIN - m.EPS:
                return 'gap < 0.5'
            if s['balance']['correct_is_first_order'] != first or s['balance']['holder'] != h:
                return 'balance mismatch'
            return None
        if finish(scene, reasons, chk):
            return scene
    raise RuntimeError('C slot %d failed' % idx)


X_SLOTS = [  # (pattern, colour of the box near r1, sign of the order for the box near r1, sign for the box near r2)
    ('P', 'red', 11, 12), ('Q', 'red', 13, 11), ('P', 'blue', 12, 13)]


def build_X(idx, rng, reasons):
    pattern, cA, sA, sB = X_SLOTS[idx - 1]
    cB = 'blue' if cA == 'red' else 'red'
    swap_ids = rng.random() < 0.5
    for _ in range(MAX_TRY):
        reasons['sampled'] += 1
        g, why = two_box_geometry(rng, 1.8, 0.9)       # each robot's own order is for the far box: 0.9 m further
        if g is None:
            reasons[why] += 1
            continue
        a, b, ra, rb = g                       # a near r1, b near r2
        ids = ('a', 'b') if not swap_ids else ('b', 'a')
        boxes = sorted([{'id': ids[0], 'colour': cA, 'x': a[0], 'y': a[1]}, {'id': ids[1], 'colour': cB, 'x': b[0], 'y': b[1]}],
                       key=lambda x: x['id'])
        oA = {'colour': cA, 'count': 1, 'sign': sA}
        oB = {'colour': cB, 'count': 1, 'sign': sB}
        if pattern == 'P':
            orders, knows = [dict(id='o1', **oA), dict(id='o2', **oB)], knows_dict(r1=['o2'], r2=['o1'])
            plan = {'r1': [[ids[0], 'o1']], 'r2': [[ids[1], 'o2']]}
        else:
            orders, knows = [dict(id='o1', **oB), dict(id='o2', **oA)], knows_dict(r1=['o1'], r2=['o2'])
            plan = {'r1': [[ids[0], 'o2']], 'r2': [[ids[1], 'o1']]}
        scene = {'id': 'X2-%02d' % idx, 'type': TYPE_NAME['X'], 'type_code': 'X', 'control': True, 'boxes': boxes,
                 'robots': [make_robot('r1', ra, [a, b]), make_robot('r2', rb, [a, b])], 'orders': orders, 'knows': knows,
                 'constraints': []}

        def chk(s):
            if s['oracle_plan'] != plan:
                return 'oracle not nearest-box split'
            e = s['estimate']
            if abs(e['gap']) > m.EPS or e['baseline_p_full'] < 1 - m.EPS:
                return 'X must be equal-count control'
            if e['baseline_active_end_s'] - e['oracle_completion_s'] < 60:
                return 'X time gap < 60 s'
            return None
        if finish(scene, reasons, chk):
            return scene
    raise RuntimeError('X slot %d failed' % idx)


D_SLOTS = [('r1', 'red', 12), ('r2', 'blue', 13), ('r1', 'blue', 11)]   # holder, colour of the ordered box, sign


def build_D(idx, rng, reasons):
    h, ct, sign = D_SLOTS[idx - 1]
    u_rid = 'r2' if h == 'r1' else 'r1'
    cd = 'blue' if ct == 'red' else 'red'
    perm = rng.sample(['a', 'b', 'c'], 3) if hasattr(rng, 'sample') else ['a', 'b', 'c']
    for _ in range(MAX_TRY):
        reasons['sampled'] += 1
        u, hp = sp(pt(rng)), sp(pt(rng))
        ang = rng.uniform(-math.pi, math.pi)
        du = sp(polar(u, rng.uniform(0.6, 0.9), ang))
        t = sp(polar(u, rng.uniform(0.9, 1.1), ang + rng.choice((-1, 1)) * rng.uniform(0.7, 1.4)))
        dh = sp(polar(hp, rng.uniform(0.6, 0.9), rng.uniform(-math.pi, math.pi)))
        d_ut, d_hu_t = m.dist(u, t), m.dist(hp, t)
        if not (m.dist(u, du) + 0.05 <= d_ut <= 1.1 and d_hu_t - m.dist(hp, dh) >= 0.4 and d_hu_t - d_ut >= 0.8):
            reasons['D structure'] += 1
            continue
        ids = {'t': perm[0], 'du': perm[1], 'dh': perm[2]}
        boxes = sorted([{'id': ids['t'], 'colour': ct, 'x': t[0], 'y': t[1]}, {'id': ids['du'], 'colour': cd, 'x': du[0], 'y': du[1]},
                        {'id': ids['dh'], 'colour': cd, 'x': dh[0], 'y': dh[1]}], key=lambda x: x['id'])
        pos = {h: hp, u_rid: u}
        pts = [t, du, dh]
        scene = {'id': 'D2-%02d' % idx, 'type': TYPE_NAME['D'], 'type_code': 'D', 'control': True, 'boxes': boxes,
                 'robots': [make_robot(r, pos[r], pts) for r in ('r1', 'r2')], 'orders': [dict(id='o1', colour=ct, count=1, sign=sign)],
                 'knows': knows_dict(**{h: ['o1'], u_rid: []}), 'constraints': []}

        def chk(s):
            if s['oracle_plan'][u_rid] != [[ids['t'], 'o1']] or s['oracle_plan'][h] != []:
                return 'oracle not blind-nearest'
            e = s['estimate']
            if abs(e['gap']) > m.EPS or e['baseline_guess_errors'] < 1 - m.EPS:
                return 'D must be equal-count control with a decoy temptation'
            return None
        if finish(scene, reasons, chk):
            return scene
    raise RuntimeError('D slot %d failed' % idx)


def build(out):
    dropped = {}
    scenes = []
    for code, builder in (('L', build_L), ('C', build_C)):
        rng, reasons = random.Random(SEED_BASE + ord(code)), Counter()
        for s in range(12):
            scenes.append(builder(s + 1, s % 4, s // 4, rng, reasons))
        dropped[code] = dict(reasons)
    for code, builder, n in (('X', build_X, 3), ('D', build_D, 3)):
        rng, reasons = random.Random(SEED_BASE + ord(code)), Counter()
        for s in range(n):
            scenes.append(builder(s + 1, rng, reasons))
        dropped[code] = dict(reasons)
    doc = {
        'schema': 'scenes_v2.designed.v1',
        'status': 'analytical_candidates_not_experimental_results',
        'units': {'position': 'm', 'yaw': 'rad', 'time': 's'},
        'arena': m.ARENA,
        'rules': {'robots': 2, 'one_carry_per_robot': True, 'order_count': 1, 'one_order_per_sign': True,
                  'unordered_move_is_error': True, 'idle_robot_may_finish': True, 'dev_exposed_excluded': list(m.DEV_EXPOSED)},
        'knowledge_contract': {
            'knows_references': 'Order IDs only; absence of an order is not knowledge of its nonexistence. knows lists are in ID order '
                                '(first-listed = lowest ID).',
            'coordinates': 'Evaluator-only. Never give world coordinates, box IDs, all-box lists, oracle or baseline to the LLM.',
            'visibility_verified': False, 'yaw': 'bisector of the bearings to all boxes; every box within 70 deg of it'},
        'model': m.MODEL,
        'baseline_rules': m.BASELINE_RULES,
        'selection_rule': 'L and C keep a scene only if oracle - baseline >= 0.5 correct boxes under BOTH the primary (uniform) and '
                          'the guess baseline; X and D are equal-count controls (control=true).',
        'builder': {'file': 'build_designed.py', 'seed_base': SEED_BASE, 'max_try_per_slot': MAX_TRY},
        'rejections_by_type': dropped,
        'scenes': scenes,
    }
    m.dump(doc, out)
    return doc


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes_designed_v2.json')
    d = build(out)
    print('wrote %s (%d scenes)' % (out, len(d['scenes'])))
    for k, v in d['rejections_by_type'].items():
        print(k, v)
