#!/usr/bin/env python3
"""Build scenes3_main.json: 30 three-robot main scenes (L3 9, C3 9, K3 6, X3 3, D3 3). Standard library only; deterministic
(fixed seed); no simulation, no LLM, no network.

Every slot fixes its structure first (who knows what, colours, signs, order IDs, which robot plays which role); coordinates are
then rejection-sampled with a seeded RNG on a 0.05 m grid until the geometry rules, the structure tests and the oracle /
baseline tests all hold.  Rejections are counted by reason and written to the JSON.   Usage: python3 build_scenes3.py [out.json]
"""
import json
import math
import os
import random
import sys
from collections import Counter

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model3 as m  # noqa: E402

SEED = 20261116
MAX_TRY = 400000
RIDS = ('r1', 'r2', 'r3')
XLO, XHI, YLO, YHI = m.X_MIN + m.CLEAR, m.PART_X - m.CLEAR, m.Y_MIN + m.CLEAR, m.Y_MAX - m.CLEAR          # robots: 0.40 m to the walls
BXLO, BYLO, BYHI = m.X_MIN + m.DES_BOX_WALL, m.Y_MIN + m.DES_BOX_WALL, m.Y_MAX - m.DES_BOX_WALL            # boxes: 0.55 m to the walls
BOX_XHI = 1.3                      # as the coop generator: boxes stay west of x = 1.3 (robots may stand further east)
SIGN_PERMS = [(11, 12, 13), (12, 13, 11), (13, 11, 12), (11, 13, 12), (13, 12, 11), (12, 11, 13)]
SIGN_ROUND9 = [0, 1, 2, 3, 4, 5, 0, 1, 2]          # 9 slots: all 6 permutations, then the 3 cyclic shifts (each sign 3x per position)
TYPE_NAME = {'L3': 'orders_concentrated_3', 'C3': 'same_colour_competition_3', 'K3': 'capability_3',
             'X3': 'knowledge_crossed_3', 'D3': 'decoy_boxes_3'}
COUNTS = {'L3': 9, 'C3': 9, 'K3': 6, 'X3': 3, 'D3': 3}
CONTROL = {'L3': False, 'C3': False, 'K3': False, 'X3': True, 'D3': True}
X_CROSS_MIN, X_TIME_GAP_MIN = 0.9, 60.0           # X3: extra distance of the crossed box; baseline end - oracle completion (s)
D_HOLDER_FAR = 0.8                                # D3: holder's distance to the target exceeds the carrier's by this much (m)
ORACLE_MAX_S = 300.0


def snap(v):
    return round(round(v / m.GRID) * m.GRID, 2)


def order(i, colour, sign):
    return {'id': 'o%d' % i, 'colour': colour, 'count': 1, 'sign': sign}


def knows_of(**kw):
    return {rid: sorted(kw.get(rid, []), key=m.oid_key) for rid in RIDS}


# ---------------------------------------------------------------------------------------------------- slot structures
def spec_L(i):
    h, spos, dc = i // 3, i % 3, ('red' if i % 2 == 0 else 'blue')
    sc = m.other(dc)
    vec = [sc if k == spos else dc for k in range(3)]
    first = vec[h]
    rest = ([sc, dc] if i % 2 == 1 else [dc, sc]) if first == dc else [dc, dc]
    cols = [first] + rest
    signs = SIGN_PERMS[SIGN_ROUND9[i]]
    orders = [order(k + 1, cols[k], signs[k]) for k in range(3)]
    return dict(colours=vec, anchor={RIDS[k]: k for k in range(3)}, orders=orders,
                knows=knows_of(**{RIDS[h]: ['o1', 'o2', 'o3']}), can_grasp=None)


C_CELLS = {0: [('lo', 'blue'), ('hi', 'red'), ('hi', 'blue')],      # per position of the single-colour robot: 3 of the 4 (holder, colour) cells
           1: [('lo', 'red'), ('lo', 'blue'), ('hi', 'red')],
           2: [('lo', 'red'), ('hi', 'red'), ('hi', 'blue')]}


def spec_C(i):
    cpos, j = i // 3, i % 3
    which, dc = C_CELLS[cpos][j]
    sc = m.other(dc)
    pair = [k for k in range(3) if k != cpos]
    a, b = (pair[0], pair[1]) if which == 'lo' else (pair[1], pair[0])      # a holds both same-colour orders, b knows the lowest-ID one
    sid = j + 1
    p, q = [x for x in (1, 2, 3) if x != sid]
    signs = SIGN_PERMS[SIGN_ROUND9[i]]
    cols = {sid: sc, p: dc, q: dc}
    orders = [order(k, cols[k], signs[k - 1]) for k in (1, 2, 3)]
    vec = [sc if k == cpos else dc for k in range(3)]
    return dict(colours=vec, anchor={RIDS[k]: k for k in range(3)}, orders=orders,
                knows=knows_of(**{RIDS[a]: ['o%d' % p, 'o%d' % q], RIDS[b]: ['o%d' % p], RIDS[cpos]: ['o%d' % sid]}), can_grasp=None)


def spec_K(i):
    opos, dc = i // 2, ('red' if i % 2 == 0 else 'blue')
    sc = m.other(dc)
    others = [k for k in range(3) if k != opos]
    d1, d2 = (others[0], others[1]) if (opos + i % 2) % 2 == 0 else (others[1], others[0])
    sid = i % 3 + 1
    dcs = [x for x in (1, 2, 3) if x != sid]
    signs = SIGN_PERMS[i]
    cols = {sid: sc, dcs[0]: dc, dcs[1]: dc}
    orders = [order(k, cols[k], signs[k - 1]) for k in (1, 2, 3)]
    vec = [sc if k == opos else dc for k in range(3)]
    can = {RIDS[k]: ([sc] if k == opos else [dc]) for k in range(3)}
    return dict(colours=vec, anchor={RIDS[k]: k for k in range(3)}, orders=orders,
                knows=knows_of(**{RIDS[opos]: ['o%d' % x for x in dcs], RIDS[d1]: ['o%d' % sid]}), can_grasp=can)


def spec_X(j):
    b, a, c = j, (j + 1) % 3, (j + 2) % 3
    dc = ('red', 'blue', 'red')[j]
    sc = m.other(dc)
    sid = j + 1
    p, q = [x for x in (1, 2, 3) if x != sid]
    signs = SIGN_PERMS[3 + j]
    cols = {sid: sc, p: dc, q: dc}
    orders = [order(k, cols[k], signs[k - 1]) for k in (1, 2, 3)]
    vec = [sc if k == c else dc for k in range(3)]
    return dict(colours=vec, anchor={RIDS[k]: k for k in range(3)}, orders=orders,
                knows=knows_of(**{RIDS[a]: ['o%d' % sid], RIDS[b]: ['o%d' % p], RIDS[c]: ['o%d' % q]}), can_grasp=None,
                roles=dict(a=RIDS[a], b=RIDS[b], c=RIDS[c]))


def spec_D(j):
    h, u, w = j, (j + 1) % 3, (j + 2) % 3
    tc = ('red', 'blue', 'red')[j]
    sign = (12, 13, 11)[j]
    return dict(colours=[tc, m.other(tc), m.other(tc)], anchor=None, orders=[order(1, tc, sign)],
                knows=knows_of(**{RIDS[h]: ['o1']}), can_grasp=None, roles=dict(h=RIDS[h], u=RIDS[u], w=RIDS[w], h_anchor=1 + j % 2))


# ---------------------------------------------------------------------------------------------------- geometry sampling
def pt(rng, xhi=BOX_XHI):
    return (snap(rng.uniform(BXLO, xhi)), snap(rng.uniform(BYLO, BYHI)))


def around(rng, p, dmin, dmax):
    ang, d = rng.uniform(0, 2 * math.pi), rng.uniform(dmin, dmax)
    return (snap(p[0] + d * math.cos(ang)), snap(p[1] + d * math.sin(ang)))


def inside(p):
    return XLO - 1e-9 <= p[0] <= XHI + 1e-9 and YLO - 1e-9 <= p[1] <= YHI + 1e-9


def layout_std(rng, spec, reasons):
    """Boxes at indices 0..2 (robot r_k's own box is box k); robots 0.65..1.05 m from their own box."""
    pts = [pt(rng) for _ in range(3)]
    if any(m.dist(a, b) < m.DES_BOX_GAP for i, a in enumerate(pts) for b in pts[i + 1:]):
        reasons['boxes too close'] += 1
        return None
    rob = []
    for k in range(3):
        p = around(rng, pts[k], 0.65, 1.05)
        if not inside(p):
            reasons['robot outside room'] += 1
            return None
        rob.append(p)
    return pts, rob, {RIDS[k]: k for k in range(3)}


def layout_D(rng, spec, reasons):
    """Boxes: 0 = target t, 1 = decoy near the carrier u, 2 = decoy near the idle robot w. Holder h stands near decoy `h_anchor`."""
    roles = spec['roles']
    du, dw = pt(rng), pt(rng)
    ru, rw = around(rng, du, 0.65, 0.9), around(rng, dw, 0.65, 0.9)
    d_ud = m.dist(ru, du)
    t = around(rng, ru, d_ud + 0.15, 1.1)
    pts = [t, du, dw]
    if any(m.dist(a, b) < m.DES_BOX_GAP for i, a in enumerate(pts) for b in pts[i + 1:]):
        reasons['boxes too close'] += 1
        return None
    anchor_pt = pts[roles['h_anchor']]
    rh = around(rng, anchor_pt, 0.65, 1.05)
    if not (inside(ru) and inside(rw) and inside(rh) and inside(t)):
        reasons['outside room'] += 1
        return None
    if m.dist(rh, t) - m.dist(ru, t) < D_HOLDER_FAR:
        reasons['holder not far from target'] += 1
        return None
    rob = {roles['h']: rh, roles['u']: ru, roles['w']: rw}
    return pts, [rob[r] for r in RIDS], None


def build_scene(sid, tcode, spec, rng, reasons):
    ids = ['a', 'b', 'c']
    rng.shuffle(ids)                                    # box id of box index k
    for attempt in range(1, MAX_TRY + 1):
        reasons['sampled'] += 1
        res = layout_D(rng, spec, reasons) if tcode == 'D3' else layout_std(rng, spec, reasons)
        if res is None:
            continue
        pts, rob, _anchor = res
        boxes = sorted([{'id': ids[k], 'colour': spec['colours'][k], 'x': pts[k][0], 'y': pts[k][1]} for k in range(3)], key=lambda b: b['id'])
        robots = []
        for k, rid in enumerate(RIDS):
            yaw, _span = m.bisector_yaw(rob[k][0], rob[k][1], pts)
            robots.append({'rid': rid, 'x': rob[k][0], 'y': rob[k][1], 'yaw': round(yaw, 4)})
        scene = {'id': sid, 'type': TYPE_NAME[tcode], 'type_code': tcode, 'control': CONTROL[tcode], 'boxes': boxes, 'robots': robots,
                 'orders': spec['orders'], 'knows': spec['knows']}
        if spec['can_grasp']:
            scene['can_grasp'] = spec['can_grasp']
        scene['constraints'] = []
        errs = m.geometry_errors(scene)
        if errs:
            reasons['geometry ' + errs[0].split(']')[0][1:]] += 1
            continue
        tg = m.targets(scene)
        box_idx = {ids[k]: k for k in range(3)}
        bad = False
        for rid in RIDS:
            near = sorted(m.dist(m.robots_of(scene)[rid], b) for b in scene['boxes'] if b['colour'] in m.caps(scene, rid))
            if len(near) > 1 and near[1] - near[0] < m.NEAREST_MARGIN - m.EPS:
                bad = True
        if bad:
            reasons['nearest-box margin'] += 1
            continue
        if tcode != 'D3' and any(box_idx[tg[rid]] != k for k, rid in enumerate(RIDS)):
            reasons['nearest box is not own box'] += 1
            continue
        if tcode == 'D3':
            if any(box_idx[tg[spec['roles'][r]]] != 1 + (r == 'w') for r in ('u', 'w')):
                reasons['D3 nearest box is not the own decoy'] += 1
                continue
        extra = type_filter(scene, tcode, spec, box_idx, reasons)
        if not extra:
            continue
        m.annotate(scene)
        why = estimate_filter(scene, tcode, spec)
        if why:
            reasons[why] += 1
            continue
        return scene, attempt
    raise RuntimeError('slot %s failed after %d samples' % (sid, MAX_TRY))


def type_filter(scene, tcode, spec, box_idx, reasons):
    """Cheap geometric conditions of a type that need no oracle."""
    if tcode != 'X3':
        return True
    r = spec['roles']
    rb = m.robots_of(scene)
    boxes = m.boxes_of(scene)
    own = {rid: next(b for b in scene['boxes'] if box_idx[b['id']] == k) for k, rid in enumerate(RIDS)}
    A, B, C = rb[r['a']], rb[r['b']], rb[r['c']]
    if m.dist(A, own[r['c']]) - m.dist(A, own[r['a']]) < X_CROSS_MIN or m.dist(C, own[r['a']]) - m.dist(C, own[r['c']]) < X_CROSS_MIN:
        reasons['X3 crossed box not far enough'] += 1
        return False
    if m.dist(C, own[r['b']]) - m.dist(C, own[r['a']]) < m.NEAREST_MARGIN:
        reasons['X3 C nearest red is not A box'] += 1
        return False
    del boxes, B
    return True


def estimate_filter(scene, tcode, spec):
    """Oracle / baseline conditions of a type; returns a rejection reason or None."""
    e = scene['estimate']
    dem = m.demand(scene)
    res = m.analyse(scene)
    if res['U']['conflict'] or res['S']['conflict']:
        return 'baseline conflict (same box)'
    if e['oracle_correct'] != dem:
        return 'oracle misses an order'
    if e['oracle_completion_s'] is None or e['oracle_completion_s'] > ORACLE_MAX_S:
        return 'oracle too slow'
    if m.fixed_plan_errors(scene):
        return 'FixedPlan not feasible'
    plan = scene['oracle_plan']
    tg = m.targets(scene)
    if tcode == 'D3':
        r = spec['roles']
        if [rid for rid in RIDS if plan[rid]] != [r['u']]:
            return 'D3 oracle carrier is not u'
        if e['baseline_errors'] < 1 - m.EPS or abs(e['gap_U']) > m.EPS or abs(e['gap_S']) > m.EPS:
            return 'D3 needs equal count and >=1 expected error'
        return None
    if any(plan[rid] and plan[rid][0][0] != tg[rid] for rid in RIDS) or not all(plan[rid] for rid in RIDS):
        return 'oracle box is not own nearest box'
    if tcode == 'X3':
        if abs(e['gap_U']) > m.EPS or abs(e['gap_S']) > m.EPS or e['baseline_p_full'] < 1 - m.EPS:
            return 'X3 must be an equal-count control'
        if e['time_gap_s'] < X_TIME_GAP_MIN:
            return 'X3 time gap < 60 s'
        return None
    if e['gap_U'] < m.GAP_MIN - m.EPS or e['gap_S'] < m.GAP_MIN - m.EPS:
        return 'gap < 0.5'
    return None


def build(out):
    scenes, dropped, tries = [], {}, {}
    plan = [('L3', spec_L, 9), ('C3', spec_C, 9), ('K3', spec_K, 6), ('X3', spec_X, 3), ('D3', spec_D, 3)]
    for tcode, fn, n in plan:
        reasons = Counter()
        for i in range(n):
            sid = '%sM%02d' % (tcode, i + 1)
            rng = random.Random('%s/%d' % (sid, SEED))
            scene, attempt = build_scene(sid, tcode, fn(i), rng, reasons)
            tries[sid] = attempt
            scenes.append(scene)
        dropped[tcode] = dict(reasons)
    with open(os.path.join(HERE, 'scenes_coop.json')) as fh:
        coop = json.load(fh)
    doc = {
        'schema': 'scenes3.main.v1',
        'status': 'analytical_candidates_not_experimental_results',
        'scope': 'Three-robot main scenes: L3 9, C3 9, K3 6, X3 3 (control), D3 3 (control). Analytic only: no simulation, LLM or paid call was run.',
        'units': coop['units'],
        'arena': coop['arena'],
        'knowledge_contract': {
            'knows_references': 'Order IDs only (complete order: colour, count, sign). A robot does not learn that an order it lacks does not exist.',
            'can_grasp': 'Optional {rid: [colours]}: the robot can only grasp those colours. A robot knows its own capability, not the others.',
            'coordinates': 'Evaluator-only. Never give world coordinates, box IDs or oracle plans to the LLM.',
            'one_carry': 'Each robot carries at most one box per run. Demand never exceeds the number of robots.',
            'one_order_per_sign': 'Distinct signs per order.',
            'boxes': 'Always 3 boxes, 2 of one colour and 1 of the other (the largest pool the runner has used for a team scene).',
            'constraints': 'Always empty.',
            'visibility_verified': False},
        'model': 'model3.py = the time model, oracle and baselines U / S of scenes/check_scenes.py (reproduces its 3-robot estimates)',
        'selection_rule': 'L3, C3, K3: oracle - baseline >= 0.5 correct boxes under BOTH U and S. X3, D3: equal-count controls (control=true): '
                          'X3 baseline end - oracle completion >= 60 s, D3 >= 1 expected wrong-box move.',
        'builder': {'file': 'build_scenes3.py', 'seed': SEED, 'max_try_per_slot': MAX_TRY, 'attempts_per_scene': tries},
        'rejections_by_type': dropped,
        'scenes': scenes,
    }
    with open(out, 'w') as fh:
        fh.write(json.dumps(doc, indent=1, ensure_ascii=False) + '\n')
    return doc


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'scenes3_main.json')
    d = build(out)
    print('wrote %s (%d scenes)' % (out, len(d['scenes'])))
    for k, v in d['rejections_by_type'].items():
        print(k, dict(v))
    print('attempts', d['builder']['attempts_per_scene'])
