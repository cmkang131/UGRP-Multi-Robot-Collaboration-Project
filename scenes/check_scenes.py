#!/usr/bin/env python3
"""Check the cooperation scenes (scenes_coop.json) against the geometry rules and the analytic time model.

Usage: python3 check_scenes.py [scenes_coop.json]      (standard library only; no simulation, no LLM)
Exit code 0 only if the file has the required scene counts (K2 10, K3 4, L3 3) and every scene passes every check,
including the K2 balance rules across scenes.

Everything is recomputed from the raw fields (boxes, robots, orders, knows, can_grasp); the stored oracle_plan,
baseline_plan, info_flow and estimate must agree with the recomputation.

Baseline rule (T0, no messages), one box per robot (one carry per run):
  U (primary): a robot that knows an order whose colour it can grasp (and a box of that colour exists) takes the
      nearest box of the colour of its lowest-ID such order and sets it down at that order's sign.
      Otherwise it takes the nearest box it can grasp and picks one of the signs 11/12/13 uniformly.
      (Unlike the DESIGN-18 T0, which abstains without an order; a wrong box never costs points, so guessing is
      the more favourable rule for T0.)
  S (stricter test): like U, but a robot without a usable order excludes the signs of the orders it knows
      (one order per sign), and a robot with several usable orders of one colour picks one of them uniformly.
Expected correct boxes are computed by enumerating all joint random choices under the count rule
(sum over orders of min(count, boxes of that colour set down at that sign)), not by adding 1/3 per robot.
"""
import itertools
import json
import math
import os
import sys

# ---- arena and time model (task statement; carry scaling and door slot follow DESIGN-18)
X_MIN, X_MAX, Y_MIN, Y_MAX = -1.05, 5.40, -3.15, 1.45
PART_X = 2.2
DOOR = (2.2, 0.05)
DROP = {11: (5.07, 0.40), 12: (5.07, -2.10), 13: (3.40, -2.82)}
SIGNS = (11, 12, 13)
COLOURS = ('red', 'blue')
CLEAR, BOX_GAP, ROBOT_GAP = 0.40, 0.60, 0.60
NEAR_MIN, NEAR_MAX = 0.60, 1.10
FOV = math.radians(70.0)
LOS_CLEAR = 0.25                               # assumed robot half-width for blocking a line of sight (not measured)
SURVEY_S, PICK_S_AT_08M = 12.0, 58.0           # look-around; approach+grasp proportional to distance (58 s at 0.8 m)
CARRY_S_PER_M, CARRY_MIN, CARRY_MAX = 22.4, 100.0, 120.0   # box -> door -> sign drop point, clamped to 100..120 s
SETDOWN_S, DOOR_SLOT_S = 10.0, 8.0
MSG_S, RANK_WAIT_S, LIMIT_S = 2.0, 4.0, 900.0
GAP_MIN = 0.5                                  # reject when oracle - baseline expected correct boxes < 0.5
EPS = 1e-6

TYPES = {'capability_2': ('K2', 10), 'capability_3': ('K3', 4), 'orders_concentrated_3': ('L3', 3)}


def dist(a, b):
    ax, ay = (a['x'], a['y']) if isinstance(a, dict) else a
    bx, by = (b['x'], b['y']) if isinstance(b, dict) else b
    return math.hypot(ax - bx, ay - by)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def oid_key(oid):
    digits = ''.join(ch for ch in oid if ch.isdigit())
    return (int(digits) if digits else 0, oid)


# ---------------------------------------------------------------- accessors
def robots_of(scene):
    return {r['rid']: r for r in scene['robots']}


def boxes_of(scene):
    return {b['id']: b for b in scene['boxes']}


def orders_of(scene):
    return {o['id']: o for o in scene['orders']}


def caps(scene, rid):
    return tuple((scene.get('can_grasp') or {}).get(rid, COLOURS))


def usable_orders(scene, rid):
    """Orders the robot knows, can grasp the colour of, and sees a box of (lowest ID first)."""
    present = {b['colour'] for b in scene['boxes']}
    known = set(scene['knows'].get(rid, []))
    out = [o for o in scene['orders'] if o['id'] in known and o['colour'] in caps(scene, rid) and o['colour'] in present]
    return sorted(out, key=lambda o: oid_key(o['id']))


def nearest_box(scene, rid, candidates):
    r = robots_of(scene)[rid]
    return min(candidates, key=lambda b: (round(dist(r, b), 9), b['id']))


# ---------------------------------------------------------------- geometry
def seg_point_dist(p, a, b):
    vx, vy = b['x'] - a['x'], b['y'] - a['y']
    t = 0.0 if vx == vy == 0 else max(0.0, min(1.0, ((p['x'] - a['x']) * vx + (p['y'] - a['y']) * vy) / (vx * vx + vy * vy)))
    return math.hypot(p['x'] - (a['x'] + t * vx), p['y'] - (a['y'] + t * vy))


def geometry_report(scene):
    errs, info = [], {}
    xlo, xhi, ylo, yhi = X_MIN + CLEAR, PART_X - CLEAR, Y_MIN + CLEAR, Y_MAX - CLEAR
    for kind, items in (('box', scene['boxes']), ('robot', scene['robots'])):
        for it in items:
            if not (xlo - EPS <= it['x'] <= xhi + EPS and ylo - EPS <= it['y'] <= yhi + EPS):
                errs.append('%s %s (%.2f,%.2f) not >=0.40 m inside the box room x[%.2f,%.2f] y[%.2f,%.2f]'
                            % (kind, it.get('id', it.get('rid')), it['x'], it['y'], xlo, xhi, ylo, yhi))
    for a, b in itertools.combinations(scene['boxes'], 2):
        if dist(a, b) < BOX_GAP - EPS:
            errs.append('boxes %s,%s only %.2f m apart' % (a['id'], b['id'], dist(a, b)))
    for a, b in itertools.combinations(scene['robots'], 2):
        if dist(a, b) < ROBOT_GAP - EPS:
            errs.append('robots %s,%s only %.2f m apart' % (a['rid'], b['rid'], dist(a, b)))
    worst = 0.0
    for r in scene['robots']:
        near = min(dist(r, b) for b in scene['boxes'])
        if not (NEAR_MIN - EPS <= near <= NEAR_MAX + EPS):
            errs.append('%s nearest box %.2f m, outside 0.6..1.1' % (r['rid'], near))
        for b in scene['boxes']:           # every box, whatever the colour or capability (strictest reading)
            dev = abs(wrap(math.atan2(b['y'] - r['y'], b['x'] - r['x']) - r['yaw']))
            worst = max(worst, dev)
            if dev > FOV + EPS:
                errs.append('%s: box %s is %.1f deg off the heading (limit 70)' % (r['rid'], b['id'], math.degrees(dev)))
        for b in scene['boxes']:           # extra rule: no other robot body on the line of sight to a box
            for q in scene['robots']:
                if q is not r and seg_point_dist(q, r, b) < LOS_CLEAR:
                    errs.append('%s blocks the view of %s to box %s' % (q['rid'], r['rid'], b['id']))
    info['max_dev_deg'] = math.degrees(worst)
    return errs, info


# ---------------------------------------------------------------- schedule and score
def simulate(scene, assign, ready=None):
    """assign {rid: (box_id, sign)} -> deliveries with set-down times (s). One door slot of 8 s at a time, FCFS (ties by
    rid); queueing delay shifts the rest of the carry."""
    boxes, robots = boxes_of(scene), robots_of(scene)
    items = []
    for rid, (bid, sign) in sorted(assign.items()):
        r, b = robots[rid], boxes[bid]
        pick_end = SURVEY_S + PICK_S_AT_08M * dist(r, b) / 0.8
        start = max(pick_end, (ready or {}).get(rid, 0.0))
        l1, l2 = dist(b, DOOR), dist(DOOR, DROP[sign])
        carry = min(max(CARRY_S_PER_M * (l1 + l2), CARRY_MIN), CARRY_MAX)
        items.append({'rid': rid, 'box': bid, 'colour': b['colour'], 'sign': sign, 'start': start, 'carry': carry,
                      'arrive': start + carry * l1 / (l1 + l2)})
    free = 0.0
    for it in sorted(items, key=lambda i: (i['arrive'], i['rid'])):
        enter = max(it['arrive'], free)
        free = enter + DOOR_SLOT_S
        it['sd_start'] = it['start'] + it['carry'] + (enter - it['arrive'])
        it['sd_end'] = it['sd_start'] + SETDOWN_S
    return items


def score(scene, deliveries):
    """-> (correct boxes, completion time or None if demand unmet, {delivery index: order id})."""
    used, match = set(), {}
    for o in sorted(scene['orders'], key=lambda o: oid_key(o['id'])):
        met = 0
        for idx in sorted(range(len(deliveries)), key=lambda i: (deliveries[i]['sd_end'], deliveries[i]['rid'])):
            d = deliveries[idx]
            if idx not in used and d['colour'] == o['colour'] and d['sign'] == o['sign'] and met < o['count']:
                used.add(idx)
                match[idx] = o['id']
                met += 1
    demand = sum(o['count'] for o in scene['orders'])
    completion = max((deliveries[i]['sd_end'] for i in match), default=None) if len(match) >= demand else None
    return len(match), completion, match


# ---------------------------------------------------------------- oracle
def oracle_search(scene):
    rids = [r['rid'] for r in scene['robots']]
    options = [[None] + [(b['id'], s) for b in scene['boxes'] if b['colour'] in caps(scene, rid) for s in SIGNS] for rid in rids]
    best = None
    for combo in itertools.product(*options):
        taken = [c[0] for c in combo if c]
        if len(taken) != len(set(taken)):
            continue
        assign = {rid: c for rid, c in zip(rids, combo) if c}
        dels = simulate(scene, assign)
        n, t, match = score(scene, dels)
        key = (-n, t if t is not None else 1e9, len(assign), sorted(assign.items()))
        if best is None or key < best[0]:
            best = (key, assign, dels, match)
    key, assign, dels, match = best
    return {'correct': -key[0], 'completion': None if key[1] >= 1e9 else key[1], 'assign': assign, 'dels': dels, 'match': match}


def plan_to_assign(scene, plan):
    """Stored plan {rid: [[box, order]]} -> ({rid: (box, sign)}, errors)."""
    errs, assign = [], {}
    boxes, orders = boxes_of(scene), orders_of(scene)
    for rid, items in plan.items():
        if rid not in robots_of(scene):
            errs.append('plan names unknown robot %s' % rid)
            continue
        if len(items) > 1:
            errs.append('%s carries %d boxes (one carry per robot)' % (rid, len(items)))
        for bid, oid in items[:1]:
            if bid not in boxes or oid not in orders:
                errs.append('%s plan item %s/%s unknown' % (rid, bid, oid))
                continue
            if boxes[bid]['colour'] != orders[oid]['colour']:
                errs.append('%s: box %s colour differs from order %s' % (rid, bid, oid))
            if boxes[bid]['colour'] not in caps(scene, rid):
                errs.append('%s cannot grasp %s box %s' % (rid, boxes[bid]['colour'], bid))
            assign[rid] = (bid, orders[oid]['sign'])
    used = [b for b, _ in assign.values()]
    if len(used) != len(set(used)):
        errs.append('a box is used twice in the plan')
    return assign, errs


# ---------------------------------------------------------------- baselines
def robot_choices(scene, rid, rule):
    """-> list of (probability, box id or None, sign or None, order id or 'rand')."""
    use = usable_orders(scene, rid)
    if use:
        first = use[0]
        opts = [o for o in use if o['colour'] == first['colour']] if rule == 'S' else [first]
        box = nearest_box(scene, rid, [b for b in scene['boxes'] if b['colour'] == first['colour']])
        return [(1.0 / len(opts), box['id'], o['sign'], o['id']) for o in opts]
    graspable = [b for b in scene['boxes'] if b['colour'] in caps(scene, rid)]
    if not graspable:
        return [(1.0, None, None, None)]
    box = nearest_box(scene, rid, graspable)
    signs = list(SIGNS)
    if rule == 'S':
        known = {o['sign'] for o in scene['orders'] if o['id'] in scene['knows'].get(rid, [])}
        signs = [s for s in SIGNS if s not in known] or list(SIGNS)
    return [(1.0 / len(signs), box['id'], s, 'rand') for s in signs]


def baseline_eval(scene, rule):
    rids = [r['rid'] for r in scene['robots']]
    out = {'E': 0.0, 'p_full': 0.0, 'capped': 0.0, 'active_end': 0.0, 'conflict': False}
    for combo in itertools.product(*[robot_choices(scene, rid, rule) for rid in rids]):
        p, assign = 1.0, {}
        for rid, (pr, bid, sign, _o) in zip(rids, combo):
            p *= pr
            if bid is not None:
                assign[rid] = (bid, sign)
        used = [b for b, _ in assign.values()]
        if len(used) != len(set(used)):
            out['conflict'] = True
            continue
        dels = simulate(scene, assign)
        n, t, _ = score(scene, dels)
        out['E'] += p * n
        out['p_full'] += p * (t is not None)
        out['capped'] += p * (t if t is not None else LIMIT_S)
        out['active_end'] += p * max((d['sd_end'] for d in dels), default=0.0)
    return out


def baseline_plan_from_rule(scene):
    plan = {}
    for r in scene['robots']:
        pr, bid, _sign, oid = robot_choices(scene, r['rid'], 'U')[0]
        plan[r['rid']] = [[bid, oid]] if bid is not None else []
    return plan


def info_flow(scene):
    """Who has to tell whom (derived). A robot with a deterministic baseline cell keeps it; a robot that guesses (no
    usable order) must take a still-uncovered order of its box colour, from a robot that knows that order."""
    orders, plan, boxes = orders_of(scene), scene['oracle_plan'], boxes_of(scene)
    base, rids = baseline_plan_from_rule(scene), [r['rid'] for r in scene['robots']]
    want = {rid: items[0][1] for rid, items in plan.items() if items}
    kept = {}
    for rid in rids:
        item = base[rid][0] if base[rid] else None
        if item and item[1] != 'rand':
            kept.setdefault((orders[item[1]]['colour'], orders[item[1]]['sign']), rid)
    uncovered = [o['id'] for o in sorted(scene['orders'], key=lambda o: oid_key(o['id'])) if (o['colour'], o['sign']) not in kept]
    movers = [rid for rid in rids if rid not in kept.values() and base[rid]]
    given = {}
    for rid in movers:                                  # prefer the oracle's order when it is still uncovered
        if want.get(rid) in uncovered and want[rid] not in given.values():
            given[rid] = want[rid]
    for rid in movers:
        if rid not in given:
            colour = boxes[base[rid][0][0]]['colour']
            pick = [o for o in uncovered if orders[o]['colour'] == colour and o not in given.values()]
            given[rid] = pick[0] if pick else want.get(rid, '?')
    flows = []
    for rid in sorted(given):
        oid = given[rid]
        src = [r for r in rids if r != rid and oid in scene['knows'].get(r, [])]
        flows.append('%s needs %s from %s' % (rid, oid, '/'.join(src) or 'nobody'))
    return flows


# ---------------------------------------------------------------- structure per type
def k2_variant(scene):
    """A: each robot knows exactly the order of the colour it cannot grasp (both blind). B: one holder knows both orders,
    the other knows none (only the other is blind)."""
    sizes = sorted(len(scene['knows'].get(r['rid'], [])) for r in scene['robots'])
    return 'A' if sizes == [1, 1] else 'B' if sizes == [0, 2] else '?'


def type_errors(scene):
    errs, t = [], scene['type']
    rids = [r['rid'] for r in scene['robots']]
    n = len(rids)
    blind = [rid for rid in rids if not usable_orders(scene, rid)]
    sizes = sorted((len(scene['knows'].get(rid, [])) for rid in rids), reverse=True)
    if t == 'capability_2':
        if n != 2 or set(scene.get('can_grasp', {})) != set(rids):
            errs.append('K2 needs 2 robots with can_grasp for both')
        elif any(len(caps(scene, rid)) != 1 for rid in rids) or set(caps(scene, 'r1')) == set(caps(scene, 'r2')):
            errs.append('K2: each robot must grasp exactly one colour, different colours')
        if len(scene['boxes']) != 2 or len(scene['orders']) != 2:
            errs.append('K2 needs 2 boxes and 2 orders')
        v = k2_variant(scene)
        if v == '?':
            errs.append('K2: knows sizes %s are neither variant A (1,1) nor B (2,0)' % sizes)
        if v == 'A' and len(blind) != 2:
            errs.append('K2 variant A: both robots must be blind (blind: %s)' % blind)
        if v == 'B' and len(blind) != 1:
            errs.append('K2 variant B: exactly the non-holder must be blind (blind: %s)' % blind)
    elif t == 'capability_3':
        if n != 3 or 'can_grasp' not in scene:
            errs.append('K3 needs 3 robots and can_grasp')
        if len(blind) != 3:
            errs.append('K3: every robot must be blind to its own sign (blind: %s)' % blind)
        if len({tuple(sorted(caps(scene, rid))) for rid in rids}) < 2:
            errs.append('K3: capabilities are all equal')
        if max(len(scene['knows'].get(rid, [])) for rid in rids) > 2:
            errs.append('K3: a robot knows all three orders')
    elif t == 'orders_concentrated_3':
        if n != 3 or sizes != [3, 0, 0] or 'can_grasp' in scene or len(scene['orders']) != 3:
            errs.append('L3 needs 3 robots, 3 orders, knows sizes {3,0,0}, no capability limit (sizes %s)' % sizes)
    return errs


def k2_balance(scenes, rows_by_id):
    """Position/order-bias balance across the K2 scenes (even counts required)."""
    errs, lines = [], []
    k2 = [s for s in scenes if s['type'] == 'capability_2' and not rows_by_id[s['id']]['errors_basic']]
    n = len(k2)
    if n == 0:
        return errs, lines
    carry_o1_r1 = red_r1 = cross = 0
    holders, holder_first, sign_o1, sign_o2 = [], [], {s: 0 for s in SIGNS}, {s: 0 for s in SIGNS}
    for s in k2:
        orders = orders_of(s)
        want = {rid: items[0][1] for rid, items in s['oracle_plan'].items() if items}
        carry_o1_r1 += want.get('r1') == 'o1'
        red_r1 += caps(s, 'r1') == ('red',)
        cross += all(nearest_box(s, rid, s['boxes'])['colour'] not in caps(s, rid) for rid in ('r1', 'r2'))
        sign_o1[orders['o1']['sign']] += 1
        sign_o2[orders['o2']['sign']] += 1
        if k2_variant(s) == 'B':
            holder = next(r for r in ('r1', 'r2') if len(s['knows'][r]) == 2)
            holders.append(holder)
            holder_first.append(want[holder] == 'o1')
    lines.append('K2 balance over %d scenes: r1 carries o1 in %d (o2 in %d); r1 is the red-capable robot in %d; '
                 'cross-nearest scenes (each robot nearest to a box it cannot grasp; informational) %d' % (n, carry_o1_r1, n - carry_o1_r1, red_r1, cross))
    lines.append('  holder scenes (B) %d: holder r1 %d / r2 %d; holder carries its first-listed order o1 in %d, second-listed o2 in %d'
                 % (len(holders), holders.count('r1'), holders.count('r2'), sum(holder_first), len(holders) - sum(holder_first)))
    lines.append('  sign of o1 per scene: %s; sign of o2: %s' % (dict(sign_o1), dict(sign_o2)))
    if n % 2 == 0 and (2 * carry_o1_r1 != n or 2 * red_r1 != n):
        errs.append('K2 balance: r1 carries o1 in %d/%d, r1 red-capable in %d/%d (must be exactly half)' % (carry_o1_r1, n, red_r1, n))
    if holders and (len(holders) % 2 or holders.count('r1') * 2 != len(holders) or sum(holder_first) * 2 != len(holders)):
        errs.append('K2 balance: holder r1/r2 or first/second order not split evenly over %d holder scenes' % len(holders))
    if max(sign_o1.values()) - min(sign_o1.values()) > 1 or max(sign_o2.values()) - min(sign_o2.values()) > 1:
        errs.append('K2 balance: signs of o1 or o2 differ by more than one scene between signs')
    return errs, lines


# ---------------------------------------------------------------- one scene
def analyse(scene):
    errs = []
    rids = [r['rid'] for r in scene['robots']]
    if len(set(rids)) != len(rids) or not 2 <= len(rids) <= 3 or any(r not in ('r1', 'r2', 'r3') for r in rids):
        errs.append('robots must be 2 or 3 distinct of r1,r2,r3')
    if set(scene['knows']) != set(rids):
        errs.append('knows keys differ from robots')
    if len({b['id'] for b in scene['boxes']}) != len(scene['boxes']) or len({o['id'] for o in scene['orders']}) != len(scene['orders']):
        errs.append('duplicate box or order id')
    if any(b['colour'] not in COLOURS for b in scene['boxes']) or any(o['colour'] not in COLOURS for o in scene['orders']):
        errs.append('colour must be red or blue')
    if len({o['sign'] for o in scene['orders']}) != len(scene['orders']) and not scene.get('shared_sign_ok'):
        errs.append('two orders share a sign (second robot may not see the sign behind the first); not allowed here')
    if any(o['sign'] not in SIGNS for o in scene['orders']):
        errs.append('order sign not in 11/12/13')
    if scene.get('constraints'):
        errs.append('order constraints are not part of this file (S2 dropped)')
    demand = sum(o['count'] for o in scene['orders'])
    if demand > len(rids):
        errs.append('demand %d > %d robots (one carry each)' % (demand, len(rids)))
    known_all = set().union(*[set(v) for v in scene['knows'].values()])
    for o in scene['orders']:
        if o['id'] not in known_all:
            errs.append('order %s is known by nobody' % o['id'])
        if not any(o['colour'] in caps(scene, rid) for rid in rids):
            errs.append('order %s: no robot can grasp %s' % (o['id'], o['colour']))
        if sum(b['colour'] == o['colour'] for b in scene['boxes']) < o['count']:
            errs.append('order %s: not enough %s boxes' % (o['id'], o['colour']))
    geo_errs, geo = geometry_report(scene)
    errs += geo_errs
    basic = list(errs)
    orac = oracle_search(scene)
    if orac['correct'] < demand:
        errs.append('no plan meets all orders (best %d of %d)' % (orac['correct'], demand))
    assign, plan_errs = plan_to_assign(scene, scene['oracle_plan'])
    errs += plan_errs
    if not plan_errs:
        n, t, _ = score(scene, simulate(scene, assign))
        if n != orac['correct'] or (t is None) != (orac['completion'] is None) or (t is not None and t > orac['completion'] + 0.01):
            errs.append('stored oracle_plan scores %s/%s s, best is %s/%s s' % (n, t, orac['correct'], orac['completion']))
    # coordinated completion: rank wait (4 s per rank) + 2 s per message round; hidden behind the pick time
    boxes = boxes_of(scene)
    carried = [boxes[s[0]]['colour'] for s in assign.values() if s[0] in boxes]
    rounds = 2 if len(set(carried)) < len(carried) else 1
    ready = {rid: RANK_WAIT_S * i + MSG_S * rounds for i, rid in enumerate(rids)}
    coop = score(scene, simulate(scene, assign, ready=ready))[1] if assign else None
    bu, bs = baseline_eval(scene, 'U'), baseline_eval(scene, 'S')
    if bu['conflict'] or bs['conflict']:
        errs.append('two robots choose the same box under the baseline (design must avoid)')
    if scene.get('baseline_plan') != baseline_plan_from_rule(scene):
        errs.append('stored baseline_plan differs from rule U: %s' % baseline_plan_from_rule(scene))
    if scene.get('info_flow') != info_flow(scene):
        errs.append('stored info_flow differs from %s' % info_flow(scene))
    errs += type_errors(scene)
    gap_u, gap_s = demand - bu['E'], demand - bs['E']
    if gap_u < GAP_MIN - EPS or gap_s < GAP_MIN - EPS:
        errs.append('gap too small: U %.2f, S %.2f (< %.1f box)' % (gap_u, gap_s, GAP_MIN))
    est = scene.get('estimate', {})
    checks = {'oracle_correct': float(orac['correct']), 'oracle_completion_s': orac['completion'], 'coop_completion_s': coop,
              'baseline_correct': bu['E'], 'baseline_S_correct': bs['E'], 'baseline_p_full': bu['p_full'],
              'baseline_p_full_S': bs['p_full'], 'baseline_capped_completion_s': bu['capped'], 'baseline_active_end_s': bu['active_end']}
    for k, v in checks.items():
        if k not in est or v is None or est[k] is None:
            if est.get(k) is not None or v is not None:
                errs.append('estimate.%s missing or null (computed %s)' % (k, v))
            continue
        if abs(est[k] - v) > (0.6 if k.endswith('_s') else 0.006):
            errs.append('estimate.%s stored %s, computed %.3f' % (k, est[k], v))
    return {'id': scene['id'], 'type': scene['type'], 'n': len(rids), 'demand': demand, 'oracle': orac, 'coop': coop, 'U': bu, 'S': bs,
            'gap_u': gap_u, 'gap_s': gap_s, 'geo': geo, 'errors': errs, 'errors_basic': basic,
            'var': k2_variant(scene) if scene['type'] == 'capability_2' else '-',
            'blind': [rid for rid in rids if not usable_orders(scene, rid)]}


def fmt(v, spec='%.2f'):
    return '   -' if v is None else spec % v


def main(argv):
    path = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes_coop.json')
    with open(path) as fh:
        data = json.load(fh)
    rows = [analyse(s) for s in data['scenes']]
    print('file: %s   scenes: %d   rejected candidates recorded: %d' % (path, len(rows), len(data.get('rejected_candidates', []))))
    print('%-6s %-3s %-3s %-4s %-5s %-6s %-6s %-6s %-5s %-6s %-5s %-6s %-6s %-6s %-4s %-9s %s' % (
        'id', 'n', 'dem', 'var', 'orcE', 'orc_s', 'coop_s', 'U_E', 'dU', 'S_E', 'dS', 'U_full', 'U_cap', 'U_end', 'dev', 'blind', 'status'))
    for r in rows:
        print('%-6s %-3d %-3d %-4s %-5s %-6s %-6s %-6s %-5s %-6s %-5s %-6s %-6s %-6s %-4s %-9s %s' % (
            r['id'], r['n'], r['demand'], r['var'], fmt(r['oracle']['correct'], '%.0f'), fmt(r['oracle']['completion'], '%.0f'),
            fmt(r['coop'], '%.0f'), fmt(r['U']['E']), fmt(r['gap_u']), fmt(r['S']['E']), fmt(r['gap_s']), fmt(r['U']['p_full']),
            fmt(r['U']['capped'], '%.0f'), fmt(r['U']['active_end'], '%.0f'), '%.0f' % r['geo']['max_dev_deg'],
            '/'.join(r['blind']) or '-', 'FAIL' if r['errors'] else 'PASS'))
        for e in r['errors']:
            print('      ! %s' % e)
    print('columns: var = K2 variant (A both blind, B holder + one blind); orcE/orc_s oracle correct boxes / completion s;')
    print('  coop_s coordinated completion (rank wait + message rounds); U_E, S_E expected correct boxes of baseline U / S;')
    print('  dU, dS = oracle - baseline; U_full P(all orders met); U_cap expected completion (900 if unmet); U_end expected end of')
    print('  the last baseline robot; dev max heading offset (deg, all boxes); blind = robots without a usable order.')
    bal_errs, bal_lines = k2_balance(data['scenes'], {r['id']: r for r in rows})
    for line in bal_lines:
        print(line)
    for e in bal_errs:
        print('  ! %s' % e)
    failed = [r['id'] for r in rows if r['errors']] + bal_errs
    by_type, summary = {}, []
    for r in rows:
        by_type.setdefault(r['type'], []).append(r)
    for t, (label, want) in TYPES.items():
        rs = by_type.get(t, [])
        summary.append('%s %d/%d pass (need %d scenes)' % (label, sum(1 for r in rs if not r['errors']), len(rs), want))
        if len(rs) != want:
            failed.append('%s has %d scenes, need %d' % (label, len(rs), want))
    for t in by_type:
        if t not in TYPES:
            failed.append('unknown type ' + t)
    print('pass counts: ' + ', '.join(summary))
    print('RESULT: %s' % ('ALL PASS' if not failed else 'FAILED: ' + '; '.join(failed)))
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
