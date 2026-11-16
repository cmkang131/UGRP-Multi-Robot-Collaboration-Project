#!/usr/bin/env python3
"""Shared analytic model for the 3-robot main scenes (standard library only; no simulation, no LLM, no network).

Time model, oracle search, baselines U / S and the scoring rule are the ones of check_scenes.py (the
file that produced K301..L303); check_scenes3.py proves this by recomputing the stored estimates of those 7 scenes.
New here: type structure for C3 / X3 / D3, the door-corridor clearance, the FixedPlan-feasibility test and `roles`.

Rules (every scene): 3 robots r1,r2,r3, 3 boxes (2 of one colour + 1 of the other: the largest pool the runner has used
for a team scene), orders have count 1 and a sign of their own (11/12/13, no sign twice), every robot carries at most one
box, a robot grasps only the colours in `can_grasp` (default both).  Only evaluator code uses coordinates.

Baseline T0 (no messages), expected correct boxes by exact enumeration of all joint random choices:
  U: a robot that knows an order of a colour it can grasp takes the nearest box of the colour of its lowest-ID such
     order and sets it down at that sign; otherwise it takes the nearest box it can grasp and picks 11/12/13 uniformly.
  S (stricter): like U, but a robot without a usable order excludes the signs of the orders it knows, and a robot with
     several usable orders of one colour picks one of them uniformly.
  Two robots choosing the same box is a design error (the checker rejects the scene).
"""
import itertools
import math

# ---- arena (task statement) and geometry rules
X_MIN, X_MAX, Y_MIN, Y_MAX = -1.05, 5.40, -3.15, 1.45
PART_X = 2.2
DOOR = (2.2, 0.05)
DF = (1.3, 0.05)                     # inner end of the door corridor (DESIGN-TWOTRIP: corridor DF -> door)
DROP = {11: (5.07, 0.40), 12: (5.07, -2.10), 13: (3.40, -2.82)}
SIGNS = (11, 12, 13)
COLOURS = ('red', 'blue')
CLEAR, BOX_GAP, ROBOT_GAP = 0.40, 0.60, 0.60
NEAR_MIN, NEAR_MAX = 0.60, 1.10
FOV_DEG = 70.0
LOS_CLEAR = 0.25
# designed-scene margins (stricter than the base rules)
DES_BOX_GAP, DES_ROBOT_GAP = 0.90, 0.80
DES_MAX_DIST, DES_MAX_DEV_DEG = 2.6, 65.0
# 'strict' placement profile of the map generator (evidence in harness/carry_nav_v1.py): a box needs 0.40 m held-check back-off
# + 0.15 m half body = 0.55 m to the walls (:53,:58); another robot within 1.5 m of the door centre makes a carrier wait 2 s x 20 and
# stop (DOOR_BUSY_M, :46), which an idle or waiting robot at its start would cause; boxes stay 1.0 m from the door centre.
DES_BOX_WALL, DES_BOX_DOOR, DES_ROBOT_DOOR = 0.55, 1.0, 1.5
NEAREST_MARGIN = 0.15                # nearest box of a colour must lead the next one of that colour by this much
CORR_BOX, CORR_ROBOT = 0.60, 0.50    # clearance of box / robot start from the door corridor DF -> door
GRID = 0.05
# ---- time model (coop / DESIGN-18)
SURVEY_S, PICK_S_AT_08M = 12.0, 58.0
CARRY_S_PER_M, CARRY_MIN, CARRY_MAX = 22.4, 100.0, 120.0
SETDOWN_S, DOOR_SLOT_S = 10.0, 8.0
MSG_S, RANK_WAIT_S, LIMIT_S = 2.0, 4.0, 900.0
GAP_MIN = 0.5
EPS = 1e-6


def dist(a, b):
    ax, ay = (a['x'], a['y']) if isinstance(a, dict) else a
    bx, by = (b['x'], b['y']) if isinstance(b, dict) else b
    return math.hypot(ax - bx, ay - by)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def oid_key(oid):
    digits = ''.join(ch for ch in oid if ch.isdigit())
    return (int(digits) if digits else 0, oid)


def other(colour):
    return 'blue' if colour == 'red' else 'red'


# ---------------------------------------------------------------- accessors
def robots_of(scene):
    return {r['rid']: r for r in scene['robots']}


def boxes_of(scene):
    return {b['id']: b for b in scene['boxes']}


def orders_of(scene):
    return {o['id']: o for o in scene['orders']}


def rids_of(scene):
    return [r['rid'] for r in scene['robots']]


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


def targets(scene):
    """{rid: id of the nearest box the robot can grasp}."""
    return {rid: nearest_box(scene, rid, [b for b in scene['boxes'] if b['colour'] in caps(scene, rid)])['id'] for rid in rids_of(scene)}


# ---------------------------------------------------------------- geometry
def seg_point_dist(p, a, b):
    """Distance of point p ({'x','y'} or tuple) to the segment a-b (same kinds)."""
    px, py = (p['x'], p['y']) if isinstance(p, dict) else p
    ax, ay = (a['x'], a['y']) if isinstance(a, dict) else a
    bx, by = (b['x'], b['y']) if isinstance(b, dict) else b
    vx, vy = bx - ax, by - ay
    t = 0.0 if vx == vy == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def bisector_yaw(rx, ry, points):
    """Heading that centres the smallest arc containing all bearings to `points`; returns (yaw, span)."""
    angs = sorted(math.atan2(py - ry, px - rx) for px, py in points)
    n = len(angs)
    gaps = [(angs[(i + 1) % n] - angs[i]) % (2 * math.pi) for i in range(n)]
    i = max(range(n), key=lambda j: gaps[j])
    start, span = angs[(i + 1) % n], 2 * math.pi - gaps[i]
    return wrap(start + span / 2), span


def geometry_errors(scene, designed=True):
    errs = []
    for kind, items in (('box', scene['boxes']), ('robot', scene['robots'])):
        margin = CLEAR if (kind == 'robot' or not designed) else DES_BOX_WALL
        xlo, xhi, ylo, yhi = X_MIN + margin, PART_X - margin, Y_MIN + margin, Y_MAX - margin
        for it in items:
            if not (xlo - EPS <= it['x'] <= xhi + EPS and ylo - EPS <= it['y'] <= yhi + EPS):
                errs.append('[wall] %s %s outside the %.2f m wall margin' % (kind, it.get('id', it.get('rid')), margin))
            if designed and dist(it, DOOR) < (DES_BOX_DOOR if kind == 'box' else DES_ROBOT_DOOR) - EPS:
                errs.append('[door] %s %s %.2f m from the door centre' % (kind, it.get('id', it.get('rid')), dist(it, DOOR)))
    bg, rg = (DES_BOX_GAP, DES_ROBOT_GAP) if designed else (BOX_GAP, ROBOT_GAP)
    for a, b in itertools.combinations(scene['boxes'], 2):
        if dist(a, b) < bg - EPS:
            errs.append('[boxgap] boxes %s,%s %.2f m apart' % (a['id'], b['id'], dist(a, b)))
    for a, b in itertools.combinations(scene['robots'], 2):
        if dist(a, b) < rg - EPS:
            errs.append('[robotgap] robots %s,%s %.2f m apart' % (a['rid'], b['rid'], dist(a, b)))
    for r in scene['robots']:
        near = min(dist(r, b) for b in scene['boxes'])
        if not (NEAR_MIN - EPS <= near <= NEAR_MAX + EPS):
            errs.append('[near] %s nearest box %.2f m' % (r['rid'], near))
        for b in scene['boxes']:
            dev = abs(wrap(math.atan2(b['y'] - r['y'], b['x'] - r['x']) - r['yaw']))
            if dev > math.radians(FOV_DEG) + 1e-9:
                errs.append('[yaw] %s box %s %.1f deg off the heading' % (r['rid'], b['id'], math.degrees(dev)))
            if designed and dev > math.radians(DES_MAX_DEV_DEG) + 1e-9:
                errs.append('[dev65] %s box %s %.1f deg off the heading' % (r['rid'], b['id'], math.degrees(dev)))
            if designed and dist(r, b) > DES_MAX_DIST + EPS:
                errs.append('[far] %s box %s %.2f m away' % (r['rid'], b['id'], dist(r, b)))
            for q in scene['robots']:
                if q is not r and seg_point_dist(q, r, b) < LOS_CLEAR:
                    errs.append('[los] %s blocks %s view of box %s' % (q['rid'], r['rid'], b['id']))
    if designed:
        for b in scene['boxes']:
            if seg_point_dist(b, DF, DOOR) < CORR_BOX - EPS:
                errs.append('[corridor] box %s %.2f m from the door corridor' % (b['id'], seg_point_dist(b, DF, DOOR)))
        for r in scene['robots']:
            if seg_point_dist(r, DF, DOOR) < CORR_ROBOT - EPS:
                errs.append('[corridor] robot %s %.2f m from the door corridor' % (r['rid'], seg_point_dist(r, DF, DOOR)))
    return errs


def fixed_plan_errors(scene):
    """The runner's FixedPlan gets (colour, sign) per robot and the robot takes the nearest listed box of that colour:
    every plan box must be the nearest graspable box of its colour for that robot, with NEAREST_MARGIN to the next one."""
    errs, boxes, robots = [], boxes_of(scene), robots_of(scene)
    for rid, items in scene['oracle_plan'].items():
        for bid, _oid in items[:1]:
            same = sorted((dist(robots[rid], b), b['id']) for b in scene['boxes'] if b['colour'] == boxes[bid]['colour'] and b['colour'] in caps(scene, rid))
            if not same or same[0][1] != bid:
                errs.append('[fixed] %s: plan box %s is not its nearest %s box' % (rid, bid, boxes[bid]['colour']))
            elif len(same) > 1 and same[1][0] - same[0][0] < NEAREST_MARGIN - EPS:
                errs.append('[fixed] %s: nearest %s box leads by only %.2f m' % (rid, boxes[bid]['colour'], same[1][0] - same[0][0]))
    return errs


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


def demand(scene):
    return sum(o['count'] for o in scene['orders'])


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
    completion = max((deliveries[i]['sd_end'] for i in match), default=None) if len(match) >= demand(scene) else None
    return len(match), completion, match


# ---------------------------------------------------------------- oracle
def oracle_search(scene):
    """Omniscient plan: maximise correct boxes, then minimise completion, then fewer carriers, then lexicographic."""
    rids = rids_of(scene)
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
    plan = {rid: [] for rid in rids}
    for idx, oid in match.items():
        plan[dels[idx]['rid']].append([dels[idx]['box'], oid])
    return {'correct': -key[0], 'completion': None if key[1] >= 1e9 else key[1], 'assign': assign, 'dels': dels, 'match': match,
            'plan': plan}


def plan_to_assign(scene, plan):
    """Stored plan {rid: [[box, order]]} -> ({rid: (box, sign)}, errors)."""
    errs, assign = [], {}
    boxes, orders = boxes_of(scene), orders_of(scene)
    if set(plan) != set(rids_of(scene)):
        errs.append('plan keys differ from the robots')
    for rid, items in plan.items():
        if rid not in robots_of(scene):
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
    rids = rids_of(scene)
    out = {'E': 0.0, 'p_full': 0.0, 'capped': 0.0, 'active_end': 0.0, 'errors': 0.0, 'conflict': False}
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
        out['errors'] += p * (len(dels) - n)
    return out


def baseline_plan_from_rule(scene):
    plan = {}
    for r in scene['robots']:
        _pr, bid, _sign, oid = robot_choices(scene, r['rid'], 'U')[0]
        plan[r['rid']] = [[bid, oid]] if bid is not None else []
    return plan


def info_flow(scene):
    """Derived and informational: who has to tell whom for the oracle plan (a carrier that does not know its order needs it
    from a robot that does), and which robots stay idle in the oracle plan."""
    flows = []
    for rid in rids_of(scene):
        items = scene['oracle_plan'].get(rid) or []
        if not items:
            flows.append('%s stays idle' % rid)
            continue
        oid = items[0][1]
        if oid not in scene['knows'].get(rid, []):
            src = [r for r in rids_of(scene) if r != rid and oid in scene['knows'].get(r, [])]
            flows.append('%s needs %s from %s' % (rid, oid, '/'.join(src) or 'nobody'))
    return flows


# ---------------------------------------------------------------- roles (type structure, derived from the raw fields)
def roles(scene):
    """Role robots of the type, recomputed from boxes / colours / knows / can_grasp (never read from the stored copy)."""
    t = scene['type_code']
    rids = rids_of(scene)
    tg, boxes = targets(scene), boxes_of(scene)
    colour_of = {rid: boxes[tg[rid]]['colour'] for rid in rids}
    cnt = {c: sum(1 for b in scene['boxes'] if b['colour'] == c) for c in COLOURS}
    dc = max(COLOURS, key=lambda c: cnt[c])
    sc = other(dc)
    nk = {rid: len(scene['knows'].get(rid, [])) for rid in rids}
    out = {'doubleton_colour': dc}
    singles = [rid for rid in rids if colour_of[rid] == sc]
    pair = [rid for rid in rids if colour_of[rid] == dc]
    if t == 'L3':
        out['holder'] = max(rids, key=lambda r: nk[r])
        out['single_colour_robot'] = singles[0] if len(singles) == 1 else None
        out['holder_in_pair'] = out['holder'] in pair
        out['first_order_colour'] = orders_of(scene)[scene['knows'][out['holder']][0]]['colour']
    elif t == 'C3':
        holder = max(rids, key=lambda r: nk[r])
        out['single_colour_robot'] = singles[0] if len(singles) == 1 else None
        out['holder'] = holder
        out['holder_is_lower_of_pair'] = len(pair) == 2 and holder == min(pair)
        out['single_order_id'] = next((o['id'] for o in scene['orders'] if o['colour'] == sc), None)
    elif t == 'K3':
        odd = [rid for rid in rids if caps(scene, rid) == (sc,)]
        out['odd_robot'] = odd[0] if len(odd) == 1 else None
        d1 = [rid for rid in rids if rid != out['odd_robot'] and nk[rid] == 1]
        d2 = [rid for rid in rids if rid != out['odd_robot'] and nk[rid] == 0]
        out['d1'] = d1[0] if len(d1) == 1 else None
        out['d2'] = d2[0] if len(d2) == 1 else None
        out['d1_is_lower'] = None if None in (out['d1'], out['d2']) else out['d1'] < out['d2']
        out['single_order_id'] = next((o['id'] for o in scene['orders'] if o['colour'] == sc), None)
    elif t == 'X3':
        out['single_colour_robot'] = singles[0] if len(singles) == 1 else None
        a = [rid for rid in rids if scene['knows'].get(rid) and orders_of(scene)[scene['knows'][rid][0]]['colour'] == sc]
        out['cross_a'] = a[0] if len(a) == 1 else None
        rest = [rid for rid in rids if rid not in (out['cross_a'], out['single_colour_robot'])]
        out['straight_b'] = rest[0] if len(rest) == 1 else None
        out['single_order_id'] = next((o['id'] for o in scene['orders'] if o['colour'] == sc), None)
    elif t == 'D3':
        out['holder'] = max(rids, key=lambda r: nk[r])
        plan = scene.get('oracle_plan') or {}
        carr = [rid for rid in rids if plan.get(rid)]
        out['carrier'] = carr[0] if len(carr) == 1 else None
        idle = [rid for rid in rids if rid not in (out['holder'], out['carrier'])]
        out['idle'] = idle[0] if len(idle) == 1 else None
        out['target_colour'] = scene['orders'][0]['colour']
    return out


# ---------------------------------------------------------------- estimate
def r4(x):
    return None if x is None else round(x, 4) + 0.0       # + 0.0 turns -0.0 into 0.0


def analyse(scene, orac=None):
    """-> dict of everything computed from the raw fields."""
    orac = orac or oracle_search(scene)
    rids = rids_of(scene)
    assign, plan_errs = plan_to_assign(scene, orac['plan'])
    boxes = boxes_of(scene)
    carried = [boxes[s[0]]['colour'] for s in assign.values()]
    rounds = 2 if len(set(carried)) < len(carried) else 1
    ready = {rid: RANK_WAIT_S * i + MSG_S * rounds for i, rid in enumerate(rids)}
    coop = score(scene, simulate(scene, assign, ready=ready))[1] if assign else None
    bu, bs = baseline_eval(scene, 'U'), baseline_eval(scene, 'S')
    return {'oracle': orac, 'rounds': rounds, 'coop': coop, 'U': bu, 'S': bs, 'demand': demand(scene)}


def estimate(scene, res=None):
    res = res or analyse(scene)
    o, bu, bs, dem = res['oracle'], res['U'], res['S'], res['demand']
    return {'oracle_correct': o['correct'], 'oracle_completion_s': r4(o['completion']), 'coop_completion_s': r4(res['coop']),
            'message_rounds': res['rounds'],
            'baseline_correct': r4(bu['E']), 'baseline_S_correct': r4(bs['E']),
            'baseline_p_full': r4(bu['p_full']), 'baseline_p_full_S': r4(bs['p_full']),
            'baseline_capped_completion_s': r4(bu['capped']), 'baseline_active_end_s': r4(bu['active_end']),
            'baseline_errors': r4(bu['errors']), 'baseline_errors_S': r4(bs['errors']),
            'gap_U': r4(dem - bu['E']), 'gap_S': r4(dem - bs['E']),
            'time_gap_s': r4(bu['active_end'] - o['completion']) if o['completion'] is not None else None}


def annotate(scene):
    """Fill oracle_plan, baseline_plan, info_flow, estimate and balance (in place) from the raw fields."""
    orac = oracle_search(scene)
    scene['oracle_plan'] = orac['plan']
    scene['baseline_plan'] = baseline_plan_from_rule(scene)
    scene['info_flow'] = info_flow(scene)
    scene['estimate'] = estimate(scene, analyse(scene, orac))
    scene['balance'] = roles(scene)
    return scene
