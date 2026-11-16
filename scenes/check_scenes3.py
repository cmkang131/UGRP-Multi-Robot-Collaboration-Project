#!/usr/bin/env python3
"""Validate scenes3_main.json (standard library only; no simulation, no LLM, no network).

Usage: python3 check_scenes3.py [scenes3_main.json]      exit 0 only if every scene passes every check and the file-level checks hold.

Per scene: geometry (literals written here, not imported: wall margin, spacing, nearest box, field of view, line of sight,
designed margins, door corridor, 0.05 m grid), IDs, order / knowledge / capability structure, the type structure of
L3 / C3 / K3 / X3 / D3, FixedPlan feasibility (the runner's nearest-box-of-the-colour rule), the stored oracle_plan /
baseline_plan / estimate / info_flow / balance recomputed from the raw fields with model3.py, and type-level closed-form values
worked out by hand (an independent check of the enumeration code).  File level: counts 9/9/6/3/3, role balance, no duplicate of any
scene in the other scene files or inside this file (boxes or robot starts equal within 1 cm), IDs unique against the other files, the
arena equal to the coop arena, and model3 reproducing the stored estimates of the 7 existing 3-robot scenes of scenes_coop.json.
Every error line starts with a [tag] so a mutation test can grep it.
"""
import itertools
import json
import math
import os
import re
import sys
from collections import Counter

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import model3 as m  # noqa: E402

CLAIM = HERE   # the other scene files sit next to this script
OTHER_FILES = [  # (file next to this script, required)
    ('scenes18b.json', True),             # dev-exposed X01 L01 C01 D01 X02 and the other old scenes
    ('scenes_coop.json', True),           # K2, K301..K304, L301..L303
    ('scenes_designed_v2.json', True),
    ('scenes_random_v2.json', True),
    ('scenes_twotrip.json', False),       # optional files: not shipped in this repository, compared when present
    ('scenes_dynamic.json', False),
    ('test_scenes.json', False)]
COUNTS = {'L3': 9, 'C3': 9, 'K3': 6, 'X3': 3, 'D3': 3}
KEYS = ('id', 'type', 'type_code', 'control', 'boxes', 'robots', 'orders', 'knows', 'constraints', 'oracle_plan', 'baseline_plan',
        'estimate', 'info_flow', 'balance')
TYPE_NAME = {'L3': 'orders_concentrated_3', 'C3': 'same_colour_competition_3', 'K3': 'capability_3', 'X3': 'knowledge_crossed_3',
             'D3': 'decoy_boxes_3'}
# literals, deliberately not imported from model3
WALL_X, WALL_Y = (-1.05 + 0.40, 2.2 - 0.40), (-3.15 + 0.40, 1.45 - 0.40)                       # robot starts: 0.40 m to the walls
BWALL_X, BWALL_Y = (-1.05 + 0.55, 2.2 - 0.55), (-3.15 + 0.55, 1.45 - 0.55)                      # boxes: 0.55 m (held-check back-off 0.40 + half body 0.15)
BOX_DOOR, ROBOT_DOOR = 1.0, 1.5                                                                  # to the door centre (DOOR_BUSY_M = 1.5 in carry_nav_v1.py)
BOX_GAP, ROBOT_GAP = 0.90, 0.80                   # designed (base rule 0.60 / 0.60)
NEAR = (0.60, 1.10)
FOV_RAD, DES_DEV_RAD, MAX_DIST, LOS = math.radians(70.0), math.radians(65.0), 2.6, 0.25
DF, DOOR_C = (1.3, 0.05), (2.2, 0.05)
CORR_BOX, CORR_ROBOT = 0.60, 0.50
NEAREST_MARGIN = 0.15
EPS = 1e-6
DUP_TOL = 0.01                                    # 1 cm
ORACLE_MAX_S = 300.0


def d2(a, b):
    return math.hypot(a['x'] - b['x'], a['y'] - b['y'])


def angdiff(a, b):
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy))) if (vx or vy) else 0.0
    return math.hypot(px - ax - t * vx, py - ay - t * vy)


def on_grid(v):
    return abs(v / 0.05 - round(v / 0.05)) < 1e-6


# ---------------------------------------------------------------- geometry
def geo(s):
    e = []
    for kind, items in (('box', s['boxes']), ('robot', s['robots'])):
        for it in items:
            nm = it.get('id', it.get('rid'))
            wx, wy = (BWALL_X, BWALL_Y) if kind == 'box' else (WALL_X, WALL_Y)
            if not (wx[0] - EPS <= it['x'] <= wx[1] + EPS and wy[0] - EPS <= it['y'] <= wy[1] + EPS):
                e.append('[wall] %s %s (%.2f,%.2f) closer than %.2f m to a wall' % (kind, nm, it['x'], it['y'], 0.55 if kind == 'box' else 0.40))
            if math.hypot(it['x'] - DOOR_C[0], it['y'] - DOOR_C[1]) < (BOX_DOOR if kind == 'box' else ROBOT_DOOR) - EPS:
                e.append('[door] %s %s %.2f m from the door centre (need >= %.1f)' % (kind, nm, math.hypot(it['x'] - DOOR_C[0], it['y'] - DOOR_C[1]),
                                                                                     BOX_DOOR if kind == 'box' else ROBOT_DOOR))
            if not (on_grid(it['x']) and on_grid(it['y'])):
                e.append('[grid] %s %s (%s,%s) not on the 0.05 m grid' % (kind, nm, it['x'], it['y']))
            if seg_dist(it['x'], it['y'], DF[0], DF[1], DOOR_C[0], DOOR_C[1]) < (CORR_BOX if kind == 'box' else CORR_ROBOT) - EPS:
                e.append('[corridor] %s %s inside the door corridor clearance' % (kind, nm))
    for a, b in itertools.combinations(s['boxes'], 2):
        if d2(a, b) < BOX_GAP - EPS:
            e.append('[boxgap] boxes %s,%s %.2f m apart (need >= 0.90)' % (a['id'], b['id'], d2(a, b)))
    for a, b in itertools.combinations(s['robots'], 2):
        if d2(a, b) < ROBOT_GAP - EPS:
            e.append('[robotgap] robots %s,%s %.2f m apart (need >= 0.80)' % (a['rid'], b['rid'], d2(a, b)))
    for r in s['robots']:
        near = min(d2(r, b) for b in s['boxes'])
        if not (NEAR[0] - EPS <= near <= NEAR[1] + EPS):
            e.append('[near] %s nearest box %.2f m (need 0.6..1.1)' % (r['rid'], near))
        sdev = []
        for b in s['boxes']:
            ang = math.atan2(b['y'] - r['y'], b['x'] - r['x'])
            dev = angdiff(ang, r['yaw'])
            sdev.append((ang - r['yaw'] + math.pi) % (2 * math.pi) - math.pi)
            if dev > FOV_RAD + 1e-9:
                e.append('[yaw] %s: box %s is %.1f deg off the heading (limit 70)' % (r['rid'], b['id'], math.degrees(dev)))
            if dev > DES_DEV_RAD + 1e-9:
                e.append('[dev65] %s: box %s is %.1f deg off the heading (designed limit 65)' % (r['rid'], b['id'], math.degrees(dev)))
            if d2(r, b) > MAX_DIST + EPS:
                e.append('[far] %s: box %s %.2f m away (designed limit 2.6)' % (r['rid'], b['id'], d2(r, b)))
            for q in s['robots']:
                if q is not r and seg_dist(q['x'], q['y'], r['x'], r['y'], b['x'], b['y']) < LOS:
                    e.append('[los] %s blocks the view of %s to box %s' % (q['rid'], r['rid'], b['id']))
        if abs(max(sdev) + min(sdev)) > 0.01:
            e.append('[yawcentre] %s heading is not the bisector of the box bearings (%.3f rad off)' % (r['rid'], abs(max(sdev) + min(sdev)) / 2))
    return e


def max_dev_deg(s):
    return max(math.degrees(angdiff(math.atan2(b['y'] - r['y'], b['x'] - r['x']), r['yaw'])) for r in s['robots'] for b in s['boxes'])


def max_dist(s):
    return max(d2(r, b) for r in s['robots'] for b in s['boxes'])


# ---------------------------------------------------------------- one scene
def check_scene(s, other_ids):
    e = []
    sid = s.get('id', '?')
    miss = [k for k in KEYS if k not in s]
    if miss:
        return ['[format] %s missing keys %s' % (sid, miss)]
    t = s['type_code']
    if t not in COUNTS or s['type'] != TYPE_NAME[t]:
        return ['[type] unknown type_code/type %s/%s' % (t, s['type'])]
    if not re.match(r'^%sM\d\d$' % t, sid):
        e.append('[id] %s does not match %sMnn' % (sid, t))
    if sid in other_ids:
        e.append('[id] %s already exists in another scene file' % sid)
    if s['control'] != (t in ('X3', 'D3')):
        e.append('[control] control flag must be true exactly for X3 and D3')
    # structure
    rids = [r['rid'] for r in s['robots']]
    if rids != ['r1', 'r2', 'r3']:
        e.append('[robots] robots must be r1,r2,r3 in order, got %s' % rids)
        return e
    if len(s['boxes']) != 3 or len({b['id'] for b in s['boxes']}) != 3:
        e.append('[boxes] need 3 boxes with distinct ids')
        return e
    if any(b['colour'] not in ('red', 'blue') for b in s['boxes']) or any(o['colour'] not in ('red', 'blue') for o in s['orders']):
        e.append('[colour] colour must be red or blue')
        return e
    bc = Counter(b['colour'] for b in s['boxes'])
    if sorted(bc.values()) != [1, 2]:
        e.append('[boxes] need 2 boxes of one colour and 1 of the other, got %s' % dict(bc))
    dc = max(bc, key=bc.get)
    sc = 'blue' if dc == 'red' else 'red'
    e += geo(s)
    ordr = {o['id']: o for o in s['orders']}
    if len(ordr) != len(s['orders']) or any(not re.fullmatch(r'o\d', i) for i in ordr):
        e.append('[orders] duplicate or malformed order id')
        return e
    if any(o['count'] != 1 for o in s['orders']):
        e.append('[count] every order must have count 1')
    signs = [o['sign'] for o in s['orders']]
    if any(sg not in (11, 12, 13) for sg in signs) or len(set(signs)) != len(signs):
        e.append('[sign] signs must be distinct and in 11/12/13')
    want_n = 1 if t == 'D3' else 3
    if len(s['orders']) != want_n:
        e.append('[orders] %s needs %d orders, has %d' % (t, want_n, len(s['orders'])))
    if t != 'D3' and Counter(o['colour'] for o in s['orders']) != bc:
        e.append('[supply] order colours must equal the box colours (demand 3 = 3 boxes)')
    if t == 'D3' and (s['orders'][0]['colour'] != sc or Counter(b['colour'] for b in s['boxes'])[sc] != 1):
        e.append('[supply] D3: the single order is for the single-colour box (the other two boxes are decoys)')
    if set(s['knows']) != set(rids):
        e.append('[knows] knows keys differ from the robots')
        return e
    for rid, lst in s['knows'].items():
        if len(set(lst)) != len(lst) or any(x not in ordr for x in lst) or lst != sorted(lst):
            e.append('[knows] %s list invalid or not in ID order' % rid)
    if any(not any(o in v for v in s['knows'].values()) for o in ordr):
        e.append('[knows] an order is known by nobody')
    cg = s.get('can_grasp')
    if (t == 'K3') != (cg is not None):
        e.append('[cap] can_grasp must exist exactly for K3')
    if cg is not None:
        if set(cg) != set(rids) or any(len(v) != 1 or v[0] not in ('red', 'blue') for v in cg.values()):
            e.append('[cap] every robot must grasp exactly one colour')
        elif Counter(v[0] for v in cg.values()) != Counter({dc: 2, sc: 1}):
            e.append('[cap] two robots must grasp the doubleton colour, one the single colour')
    if s.get('constraints') != []:
        e.append('[constraints] must be an empty list')
    if e and any(x.startswith(('[knows]', '[cap]', '[supply]', '[orders]', '[sign]', '[count]', '[colour]')) for x in e):
        return e
    # plans and recomputation
    boxes = {b['id']: b for b in s['boxes']}
    assign, perr = m.plan_to_assign(s, s['oracle_plan'])
    e += ['[plan] ' + x for x in perr]
    if perr:
        return e
    res = m.analyse(s)
    orc = res['oracle']
    if s['oracle_plan'] != orc['plan']:
        e.append('[oracle] stored oracle_plan %s != recomputed %s' % (s['oracle_plan'], orc['plan']))
    if orc['correct'] != len(s['orders']):
        e.append('[oracle] best plan meets %d of %d orders' % (orc['correct'], len(s['orders'])))
    if orc['completion'] is None or orc['completion'] > ORACLE_MAX_S:
        e.append('[oracle] completion %s s (limit %.0f)' % (orc['completion'], ORACLE_MAX_S))
    est = m.estimate(s, res)
    for k, v in est.items():
        sv = s['estimate'].get(k, 'MISSING')
        tol = 0.06 if k.endswith('_s') else 0.006
        if (v is None) != (sv is None) or (v is not None and (sv == 'MISSING' or abs(sv - v) > tol)):
            e.append('[estimate] %s stored %s recomputed %s' % (k, sv, v))
    if set(s['estimate']) != set(est):
        e.append('[estimate] key set differs: %s' % sorted(set(s['estimate']) ^ set(est)))
    if s['baseline_plan'] != m.baseline_plan_from_rule(s):
        e.append('[baseline] stored baseline_plan differs from rule U')
    if s['info_flow'] != m.info_flow(s):
        e.append('[info] stored info_flow differs from %s' % m.info_flow(s))
    if s['balance'] != m.roles(s):
        e.append('[balance] stored roles %s != recomputed %s' % (s['balance'], m.roles(s)))
    if res['U']['conflict'] or res['S']['conflict']:
        e.append('[conflict] two robots choose the same box under rule U or S')
    # FixedPlan feasibility, written independently: the robot takes the nearest box (of the plan colour) it can grasp
    for rid, items in s['oracle_plan'].items():
        r = next(x for x in s['robots'] if x['rid'] == rid)
        for bid, _o in items[:1]:
            same = sorted((d2(r, b), b['id']) for b in s['boxes'] if b['colour'] == boxes[bid]['colour'] and b['colour'] in (cg[rid] if cg else ('red', 'blue')))
            if same[0][1] != bid or (len(same) > 1 and same[1][0] - same[0][0] < NEAREST_MARGIN - EPS):
                e.append('[fixed] %s: FixedPlan would not pick plan box %s (nearest %s box %s, lead %.2f m)' % (
                    rid, bid, boxes[bid]['colour'], same[0][1], (same[1][0] - same[0][0]) if len(same) > 1 else 9.9))
    # nearest-box margin and own nearest box
    own = {}
    for r in s['robots']:
        gr = sorted((d2(r, b), b['id']) for b in s['boxes'] if b['colour'] in (cg[r['rid']] if cg else ('red', 'blue')))
        own[r['rid']] = gr[0][1]
        if len(gr) > 1 and gr[1][0] - gr[0][0] < NEAREST_MARGIN - EPS:
            e.append('[margin] %s: nearest graspable box leads by only %.2f m' % (r['rid'], gr[1][0] - gr[0][0]))
    plan = s['oracle_plan']
    if t != 'D3':
        if len(set(own.values())) != 3:
            e.append('[own] the three robots do not have three different nearest boxes')
        if any(not plan[rid] or plan[rid][0][0] != own[rid] for rid in rids):
            e.append('[own] the oracle plan has a robot that does not carry its own nearest box')
    gu, gs = est['gap_U'], est['gap_S']
    # ---- type structure and closed-form values (derived by hand, independent of the enumeration code)
    nk = {rid: len(s['knows'][rid]) for rid in rids}
    sizes = sorted(nk.values(), reverse=True)
    colour_own = {rid: boxes[own[rid]]['colour'] for rid in rids}
    holder = max(rids, key=lambda r: nk[r])
    if t == 'L3':
        if sizes != [3, 0, 0]:
            e.append('[type] L3 needs knows sizes {3,0,0}, got %s' % sizes)
        if colour_own[holder] != ordr[s['knows'][holder][0]]['colour']:
            e.append('[type] L3: the holder\'s lowest-ID order must have the colour of its own box')
        want_e = 19 / 9 if colour_own[holder] == sc else 5 / 3
        if abs(est['baseline_correct'] - want_e) > 0.01 or abs(est['baseline_S_correct'] - want_e) > 0.01:
            e.append('[value] L3 U/S expected %.4f, got %.4f/%.4f' % (want_e, est['baseline_correct'], est['baseline_S_correct']))
        if min(gu, gs) < 0.5 - EPS:
            e.append('[gap] L3 oracle - baseline %.3f / %.3f < 0.5' % (gu, gs))
    elif t == 'C3':
        c_rid = [rid for rid in rids if colour_own[rid] == sc]
        pair = [rid for rid in rids if colour_own[rid] == dc]
        if sizes != [2, 1, 1] or len(c_rid) != 1 or len(pair) != 2:
            e.append('[type] C3 needs knows sizes {2,1,1}, one single-colour robot, two same-colour robots')
        else:
            a = holder
            b = [r for r in pair if r != a]
            same_orders = sorted(o['id'] for o in s['orders'] if o['colour'] == dc)
            if a not in pair or s['knows'][a] != same_orders or len(b) != 1 or s['knows'][b[0]] != [same_orders[0]]:
                e.append('[type] C3: holder of the two same-colour orders must be in the pair, its partner must know the lowest-ID one')
            if [o for o in s['knows'][c_rid[0]]] != [o['id'] for o in s['orders'] if o['colour'] == sc]:
                e.append('[type] C3: the single-colour robot must know exactly the single-colour order')
        if abs(est['baseline_correct'] - 2.0) > 0.01 or abs(est['baseline_S_correct'] - 2.5) > 0.01:
            e.append('[value] C3 U/S expected 2.0000/2.5000, got %.4f/%.4f' % (est['baseline_correct'], est['baseline_S_correct']))
        if min(gu, gs) < 0.5 - EPS:
            e.append('[gap] C3 oracle - baseline %.3f / %.3f < 0.5' % (gu, gs))
    elif t == 'K3':
        odd = [rid for rid in rids if cg and cg[rid] == [sc]]
        if sizes != [2, 1, 0] or len(odd) != 1:
            e.append('[type] K3 needs knows sizes {2,1,0} and one single-colour grasper')
        else:
            if sorted(s['knows'][odd[0]]) != sorted(o['id'] for o in s['orders'] if o['colour'] == dc):
                e.append('[type] K3: the single-colour grasper must know both same-colour orders')
            d1 = [r for r in rids if r != odd[0] and nk[r] == 1]
            if len(d1) != 1 or s['knows'][d1[0]] != [o['id'] for o in s['orders'] if o['colour'] == sc]:
                e.append('[type] K3: one same-colour grasper must know exactly the single-colour order')
        if any(m.usable_orders(s, rid) for rid in rids):
            e.append('[type] K3: every robot must be blind to its own sign (no usable order)')
        if abs(est['baseline_correct'] - 13 / 9) > 0.01 or abs(est['baseline_S_correct'] - 7 / 3) > 0.01:
            e.append('[value] K3 U/S expected 1.4444/2.3333, got %.4f/%.4f' % (est['baseline_correct'], est['baseline_S_correct']))
        if min(gu, gs) < 0.5 - EPS:
            e.append('[gap] K3 oracle - baseline %.3f / %.3f < 0.5' % (gu, gs))
    elif t == 'X3':
        if sizes != [1, 1, 1]:
            e.append('[type] X3 needs knows sizes {1,1,1}')
        else:
            c_rid = [rid for rid in rids if colour_own[rid] == sc]
            a_rid = [rid for rid in rids if ordr[s['knows'][rid][0]]['colour'] == sc]
            b_rid = [rid for rid in rids if rid not in a_rid + c_rid]
            if len(c_rid) != 1 or len(a_rid) != 1 or len(b_rid) != 1 or a_rid[0] == c_rid[0]:
                e.append('[type] X3: one robot knows the single-colour order, another stands at the single-colour box, the third is straight')
            else:
                A, B, C = [next(x for x in s['robots'] if x['rid'] == r) for r in (a_rid[0], b_rid[0], c_rid[0])]
                ba, bc_ = boxes[own[a_rid[0]]], boxes[own[c_rid[0]]]
                if d2(A, bc_) - d2(A, ba) < 0.9 - EPS or d2(C, ba) - d2(C, bc_) < 0.9 - EPS:
                    e.append('[type] X3: crossed boxes must be >= 0.9 m further than the own boxes')
                if boxes[own[b_rid[0]]]['colour'] != dc or ordr[s['knows'][b_rid[0]][0]]['colour'] != dc or ordr[s['knows'][c_rid[0]][0]]['colour'] != dc:
                    e.append('[type] X3: the straight robot and the single-colour robot know same-colour orders')
        if abs(est['baseline_correct'] - 3) > 0.01 or abs(est['baseline_S_correct'] - 3) > 0.01 or est['baseline_p_full'] < 1 - 1e-3:
            e.append('[value] X3 baseline must complete all 3 (equal-count control)')
        if est['time_gap_s'] < 60 - 0.06:
            e.append('[gap] X3 baseline end - oracle completion %.1f s < 60' % est['time_gap_s'])
    elif t == 'D3':
        carr = [rid for rid in rids if plan[rid]]
        if sizes != [1, 0, 0] or len(carr) != 1 or carr[0] == holder:
            e.append('[type] D3 needs one holder of the single order and a different single carrier in the oracle plan')
        else:
            tbox = next(b for b in s['boxes'] if b['colour'] == sc)
            hr = next(x for x in s['robots'] if x['rid'] == holder)
            cr = next(x for x in s['robots'] if x['rid'] == carr[0])
            if d2(hr, tbox) - d2(cr, tbox) < 0.8 - EPS:
                e.append('[type] D3: the holder must be >= 0.8 m further from the target than the carrier')
            if own[carr[0]] == tbox['id']:
                e.append('[type] D3: the carrier\'s nearest box must be a decoy')
            idle = [r for r in rids if r not in (holder, carr[0])][0]
            if boxes[own[idle]]['colour'] == sc or boxes[own[carr[0]]]['colour'] == sc:
                e.append('[type] D3: the carrier and the idle robot must have decoys as their nearest boxes')
        if abs(est['baseline_correct'] - 1) > 0.01 or abs(est['baseline_errors'] - 2) > 0.01 or abs(gu) > 0.01 or abs(gs) > 0.01:
            e.append('[value] D3: baseline must score 1 of 1 with 2 expected wrong-box moves, got E %.3f errors %.3f' % (est['baseline_correct'], est['baseline_errors']))
    return e


# ---------------------------------------------------------------- file level
def load_other():
    out, notes = [], []
    for rel, required in OTHER_FILES:
        path = os.path.join(CLAIM, rel)
        try:
            with open(path) as fh:
                d = json.load(fh)
        except (OSError, ValueError) as ex:
            notes.append(('[file] cannot read %s: %s' % (rel, ex)) if required else 'note: optional file %s not readable (%s)' % (rel, ex))
            continue
        ss = d['scenes'] if isinstance(d, dict) else d
        out.append((rel, ss, d))
    return out, notes


def same_boxes(a, b):
    if len(a['boxes']) != len(b['boxes']):
        return False
    pa = sorted((x['x'], x['y']) for x in a['boxes'])
    pb = sorted((x['x'], x['y']) for x in b['boxes'])
    # exact matching: try all permutations (<= 3 boxes)
    for perm in itertools.permutations(pb):
        if all(abs(p[0] - q[0]) <= DUP_TOL + 1e-9 and abs(p[1] - q[1]) <= DUP_TOL + 1e-9 for p, q in zip(pa, perm)):
            return True
    return False


def same_robots(a, b):
    ra, rb = {r['rid']: r for r in a['robots']}, {r['rid']: r for r in b['robots']}
    common = sorted(set(ra) & set(rb))
    return len(common) >= 2 and all(abs(ra[r]['x'] - rb[r]['x']) <= DUP_TOL + 1e-9 and abs(ra[r]['y'] - rb[r]['y']) <= DUP_TOL + 1e-9 for r in common)


def duplicate_report(scenes, others):
    """-> (errors, lines). A duplicate = box set equal within 1 cm OR the robot starts equal within 1 cm (stricter than 'both')."""
    errs, lines = [], []
    n_cmp = n_both = n_box = n_rob = 0
    for rel, ss, _d in others:
        for o in ss:
            for s in scenes:
                n_cmp += 1
                bx, rb = same_boxes(s, o), same_robots(s, o)
                n_box += bx
                n_rob += rb
                n_both += bx and rb
                if bx or rb:
                    errs.append('[dup] %s equals %s of %s (boxes %s, robot starts %s)' % (s['id'], o['id'], rel, bx, rb))
        lines.append('  vs %-48s %3d scenes' % (rel, len(ss)))
    inner = 0
    for a, b in itertools.combinations(scenes, 2):
        n_cmp += 1
        bx, rb = same_boxes(a, b), same_robots(a, b)
        inner += 1
        if bx or rb:
            errs.append('[dup] %s equals %s inside the file (boxes %s, robot starts %s)' % (a['id'], b['id'], bx, rb))
    lines.append('  inside the file: %d pairs' % inner)
    lines.append('  %d scene pairs compared; boxes equal %d, robot starts equal %d, both %d (tolerance 1 cm per coordinate)' % (n_cmp, n_box, n_rob, n_both))
    return errs, lines


def model_sanity(coop_doc):
    errs, lines = [], []
    n = 0
    for s in coop_doc['scenes']:
        if len(s['robots']) != 3:
            continue
        n += 1
        est = m.estimate(s)
        bad = [k for k in ('oracle_correct', 'oracle_completion_s', 'coop_completion_s', 'baseline_correct', 'baseline_S_correct', 'baseline_p_full',
                           'baseline_p_full_S', 'baseline_capped_completion_s', 'baseline_active_end_s')
               if abs(est[k] - s['estimate'][k]) > (0.06 if k.endswith('_s') else 0.006)]
        same_plan = m.oracle_search(s)['plan'] == s['oracle_plan']
        lines.append('  %-5s estimate %s, oracle plan %s' % (s['id'], 'reproduced' if not bad else 'MISMATCH ' + str(bad), 'same' if same_plan else 'DIFFERENT'))
        if bad or not same_plan:
            errs.append('[model] model3 does not reproduce %s of scenes_coop.json' % s['id'])
    if n != 7:
        errs.append('[model] expected 7 three-robot scenes in scenes_coop.json, found %d' % n)
    return errs, lines


def balance_errors(ds):
    errs, lines = [], []
    by = {t: [s for s in ds if s['type_code'] == t] for t in COUNTS}

    def cnt(ss, f):
        return Counter(f(s) for s in ss)

    def need(label, c, expect, keys, tol=0):
        got = [c.get(k, 0) for k in keys]
        lines.append('  %-44s %s' % (label, '/'.join(str(x) for x in got)))
        if max(abs(g - x) for g, x in zip(got, expect)) > tol:
            errs.append('[balance] %s = %s, expected %s (+-%d)' % (label, got, list(expect), tol))
    R = ('r1', 'r2', 'r3')
    L = by['L3']
    if len(L) == 9:
        need('L3 holder r1/r2/r3', cnt(L, lambda s: s['balance']['holder']), (3, 3, 3), R)
        need('L3 holder in pair T/F', cnt(L, lambda s: s['balance']['holder_in_pair']), (6, 3), (True, False))
        need('L3 doubleton colour red/blue', cnt(L, lambda s: s['balance']['doubleton_colour']), (5, 4), ('red', 'blue'), 1)
        need('L3 o1 sign 11/12/13', cnt(L, lambda s: s['orders'][0]['sign']), (3, 3, 3), (11, 12, 13))
    C = by['C3']
    if len(C) == 9:
        need('C3 single-colour robot r1/r2/r3', cnt(C, lambda s: s['balance']['single_colour_robot']), (3, 3, 3), R)
        need('C3 holder lower of the pair T/F', cnt(C, lambda s: s['balance']['holder_is_lower_of_pair']), (4, 5), (True, False), 1)
        need('C3 doubleton colour red/blue', cnt(C, lambda s: s['balance']['doubleton_colour']), (5, 4), ('red', 'blue'), 1)
        need('C3 single order o1/o2/o3', cnt(C, lambda s: s['balance']['single_order_id']), (3, 3, 3), ('o1', 'o2', 'o3'))
    K = by['K3']
    if len(K) == 6:
        need('K3 single-colour grasper r1/r2/r3', cnt(K, lambda s: s['balance']['odd_robot']), (2, 2, 2), R)
        need('K3 doubleton colour red/blue', cnt(K, lambda s: s['balance']['doubleton_colour']), (3, 3), ('red', 'blue'))
        need('K3 order-knowing d1 is lower T/F', cnt(K, lambda s: s['balance']['d1_is_lower']), (3, 3), (True, False))
        need('K3 single order o1/o2/o3', cnt(K, lambda s: s['balance']['single_order_id']), (2, 2, 2), ('o1', 'o2', 'o3'))
    X = by['X3']
    if len(X) == 3:
        need('X3 straight robot r1/r2/r3', cnt(X, lambda s: s['balance']['straight_b']), (1, 1, 1), R)
        need('X3 crossing knower r1/r2/r3', cnt(X, lambda s: s['balance']['cross_a']), (1, 1, 1), R)
        need('X3 single-colour robot r1/r2/r3', cnt(X, lambda s: s['balance']['single_colour_robot']), (1, 1, 1), R)
    D = by['D3']
    if len(D) == 3:
        need('D3 holder r1/r2/r3', cnt(D, lambda s: s['balance']['holder']), (1, 1, 1), R)
        need('D3 carrier r1/r2/r3', cnt(D, lambda s: s['balance']['carrier']), (1, 1, 1), R)
        need('D3 idle r1/r2/r3', cnt(D, lambda s: s['balance']['idle']), (1, 1, 1), R)
    return errs, lines


def margins(ss):
    """Smallest / largest geometry values over all scenes, so the report can quote them from this output."""
    rd, bd, bw, rw, bg, rgp, nlo, nhi, far, dev, lead_n, lead_c, cr, cb = 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 0.0, 0.0, 0.0, 9.0, 9.0, 9.0, 9.0
    for s in ss:
        cg = s.get('can_grasp')
        for r in s['robots']:
            rd = min(rd, math.hypot(r['x'] - DOOR_C[0], r['y'] - DOOR_C[1]))
            rw = min(rw, r['x'] + 1.05, 2.2 - r['x'], r['y'] + 3.15, 1.45 - r['y'])
            cr = min(cr, seg_dist(r['x'], r['y'], DF[0], DF[1], DOOR_C[0], DOOR_C[1]))
            near = min(d2(r, b) for b in s['boxes'])
            nlo, nhi = min(nlo, near), max(nhi, near)
            gr = sorted(d2(r, b) for b in s['boxes'] if b['colour'] in (cg[r['rid']] if cg else ('red', 'blue')))
            if len(gr) > 1:
                lead_n = min(lead_n, gr[1] - gr[0])
            for b in s['boxes']:
                far = max(far, d2(r, b))
                dev = max(dev, math.degrees(angdiff(math.atan2(b['y'] - r['y'], b['x'] - r['x']), r['yaw'])))
            for bid, _o in (s['oracle_plan'].get(r['rid']) or [])[:1]:
                col = next(b['colour'] for b in s['boxes'] if b['id'] == bid)
                same = sorted(d2(r, b) for b in s['boxes'] if b['colour'] == col and b['colour'] in (cg[r['rid']] if cg else ('red', 'blue')))
                if len(same) > 1:
                    lead_c = min(lead_c, same[1] - same[0])
        for b in s['boxes']:
            bd = min(bd, math.hypot(b['x'] - DOOR_C[0], b['y'] - DOOR_C[1]))
            bw = min(bw, b['x'] + 1.05, 2.2 - b['x'], b['y'] + 3.15, 1.45 - b['y'])
            cb = min(cb, seg_dist(b['x'], b['y'], DF[0], DF[1], DOOR_C[0], DOOR_C[1]))
        bg = min([bg] + [d2(a, b) for a, b in itertools.combinations(s['boxes'], 2)])
        rgp = min([rgp] + [d2(a, b) for a, b in itertools.combinations(s['robots'], 2)])
    return ['robot-door %.2f (need 1.5)  box-door %.2f (1.0)  box-wall %.2f (0.55)  robot-wall %.2f (0.40)' % (rd, bd, bw, rw),
            'corridor robot %.2f (0.5) box %.2f (0.6)  box gap %.2f (0.9)  robot gap %.2f (0.8)' % (cr, cb, bg, rgp),
            'nearest box %.2f..%.2f (0.6..1.1)  max robot-box %.2f (2.6)  max heading dev %.1f deg (65)' % (nlo, nhi, far, dev),
            'smallest lead of the nearest graspable box over the next one %.2f m, of a plan box over the next same-colour box %.2f m (need 0.15)' % (lead_n, lead_c)]


def main(argv):
    path = argv[1] if len(argv) > 1 else os.path.join(HERE, 'scenes3_main.json')
    errors = []
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as ex:
        print('[file] cannot read %s: %s\nFAILED' % (path, ex))
        return 1
    scenes = doc.get('scenes', [])
    others, notes = load_other()
    errors += [n for n in notes if n.startswith('[')]
    print('file: %s  (%d scenes)' % (path, len(scenes)))
    for n in notes:
        print('  ' + n)
    # arena
    coop = next((d for rel, _ss, d in others if rel.endswith('scenes_coop.json')), None)
    if coop is not None:
        if doc.get('arena') != coop['arena']:
            errors.append('[arena] arena differs from scenes_coop.json (must be the same arena)')
        print('arena: %s' % ('same as scenes_coop.json' if doc.get('arena') == coop['arena'] else 'DIFFERENT'))
        print('\nmodel sanity (model3 vs the stored estimates of the 7 existing 3-robot scenes of scenes_coop.json):')
        me, ml = model_sanity(coop)
        errors += me
        print('\n'.join(ml))
    other_ids = {o['id'] for _rel, ss, _d in others for o in ss}
    # counts and ids
    cnt = Counter(s.get('type_code') for s in scenes)
    for t, n in COUNTS.items():
        if cnt[t] != n:
            errors.append('[count] %s has %d scenes, need %d' % (t, cnt[t], n))
    if len(scenes) != sum(COUNTS.values()):
        errors.append('[count] file has %d scenes, need %d' % (len(scenes), sum(COUNTS.values())))
    ids = [s.get('id') for s in scenes]
    if len(set(ids)) != len(ids):
        errors.append('[id] duplicate ids inside the file: %s' % [k for k, v in Counter(ids).items() if v > 1])
    # scenes
    print('\n%-6s %-3s %-5s %-6s %-5s %-6s %-5s %-5s %-6s %-5s %-5s %s' % ('id', 'typ', 'orc_s', 'U_E', 'dU', 'S_E', 'dS', 'err', 'tgap_s', 'dev', 'maxd', 'status'))
    rows, passed = [], 0
    for s in scenes:
        try:
            errs = check_scene(s, other_ids)
        except Exception as ex:  # a malformed scene must fail the check, never crash it
            errs = ['[crash] %s: %s' % (type(ex).__name__, ex)]
        ok = not errs
        passed += ok
        est = s.get('estimate') or {}
        f = lambda k, spec='%.2f': spec % est[k] if isinstance(est.get(k), (int, float)) else '  -'   # noqa: E731
        try:
            dev, far = '%.0f' % max_dev_deg(s), '%.2f' % max_dist(s)
        except Exception:
            dev = far = '-'
        print('%-6s %-3s %-5s %-6s %-5s %-6s %-5s %-5s %-6s %-5s %-5s %s' % (
            s.get('id', '?'), s.get('type_code', '?'), f('oracle_completion_s', '%.0f'), f('baseline_correct'), f('gap_U'), f('baseline_S_correct'),
            f('gap_S'), f('baseline_errors'), f('time_gap_s', '%.0f'), dev, far, 'PASS' if ok else 'FAIL'))
        for x in errs:
            print('      ! ' + x)
            errors.append('%s: %s' % (s.get('id', '?'), x))
        rows.append(s)
    print('columns: orc_s oracle completion s; U_E/S_E expected correct boxes under T0 rule U / S; dU,dS = 3 (or 1) - E;')
    print('  err expected wrong-box moves under U; tgap_s baseline active end - oracle completion; dev max heading offset deg; maxd max robot-box distance m.')
    # balance
    print('\nbalance (enforced; counts in the order of the label):')
    try:
        be, bl = balance_errors(rows)
        errors += be
        print('\n'.join(bl))
        kr = Counter()
        for s in rows:
            b = s['balance']
            kr[{'L3': b.get('holder'), 'C3': b.get('holder'), 'K3': b.get('odd_robot'), 'X3': b.get('cross_a'), 'D3': b.get('carrier')}[s['type_code']]] += 1
        print('  key robot (L3 holder, C3 holder, K3 odd, X3 crossing knower, D3 carrier) r1/r2/r3 over all 30: %d/%d/%d' % (kr['r1'], kr['r2'], kr['r3']))
    except Exception as ex:
        errors.append('[crash] balance %s: %s' % (type(ex).__name__, ex))
    print('\ngeometry margins over all scenes (smallest / largest value, rule in brackets):')
    try:
        print('\n'.join('  ' + x for x in margins(rows)))
    except Exception as ex:
        errors.append('[crash] margins %s: %s' % (type(ex).__name__, ex))
    # duplicates
    print('\nduplicate check (a duplicate = box set equal within 1 cm, or robot starts equal within 1 cm):')
    try:
        de, dl = duplicate_report(rows, others)
        errors += de
        print('\n'.join(dl))
        print('  duplicates found: %d' % len(de))
    except Exception as ex:
        errors.append('[crash] duplicates %s: %s' % (type(ex).__name__, ex))
    print('\nRESULT: %d/%d scenes pass; type counts %s' % (passed, len(scenes), dict(cnt)))
    if errors:
        print('FAILED (%d error lines):' % len(errors))
        for x in errors:
            print('  ' + x)
        return 1
    print('ALL PASS: %d/%d' % (passed, len(scenes)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
