#!/usr/bin/env python3
"""Shared analytic model for scenes v2 (standard library only; no simulation, no LLM).

Rules: 2 robots, each carries at most ONE box per run. Every order has count 1 and its own sign (no two boxes for one
sign). Time model = DESIGN-18 (survey 12 s, pick 58*d/0.8 s, carry 110 s with door entry 40 s after the carry starts and
an 8 s door slot, set-down 10 s, FCFS door, ties r1). Only evaluator code uses coordinates.

Baseline T0 (no messages), "rule B": a robot that knows >=1 order picks one of its known orders, takes the nearest box of
that colour and sets it down at that order's sign. A robot that knows no order does nothing.
  * primary  (`baseline_correct`): the choice is uniform over the robot's known orders (position-free expectation, exact
    enumeration of all joint choices).
  * first-listed (`baseline_first_listed_*`, also stored as `baseline_plan`): the choice is knows[rid][0].
  * guess variant (`baseline_guess_*`): like primary, but a robot with no order takes its nearest box (any colour) and a
    uniformly random sign. Because of the same-box conflict rule below it can score LOWER than abstaining (L: 0.83 vs 1.00).
Two robots choosing the same box: the earlier arrival keeps it; the other re-surveys (12 s) at that box and takes the nearest
box nobody chose (same colour if informed, any colour if guessing), or nothing if none is left.
"""
import itertools
import json
import math

# ---- arena (task statement) and geometry rules
X_MIN, X_MAX, Y_MIN, Y_MAX = -1.05, 5.40, -3.15, 1.45
PART_X = 2.2
DOOR = (2.2, 0.05)
SIGNS = (11, 12, 13)
SIGN_POS = {11: (5.37, 0.40), 12: (5.37, -2.10), 13: (3.40, -3.12)}
DROP = {11: (5.07, 0.40), 12: (5.07, -2.10), 13: (3.40, -2.82)}
COLOURS = ('red', 'blue')
CLEAR, BOX_GAP, ROBOT_GAP = 0.40, 0.60, 0.60
NEAR_MIN, NEAR_MAX = 0.60, 1.10
FOV_DEG = 70.0
LOS_CLEAR = 0.25                 # assumed robot half-width blocking a line of sight (not measured)
# ---- DESIGN-18 time model
SURVEY_S, PICK_S_AT_08M = 12.0, 58.0
CARRY_S, DOOR_OFFSET_S, DOOR_SLOT_S, PLACE_S = 110.0, 40.0, 8.0, 10.0
LIMIT_S = 900.0
EPS = 1e-6
GAP_MIN = 0.5
DEV_EXPOSED = ('X01', 'L01', 'C01', 'D01', 'X02')


def dist(a, b):
    ax, ay = (a['x'], a['y']) if isinstance(a, dict) else a
    bx, by = (b['x'], b['y']) if isinstance(b, dict) else b
    return math.hypot(ax - bx, ay - by)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def oid_key(oid):
    digits = ''.join(ch for ch in oid if ch.isdigit())
    return (int(digits) if digits else 0, oid)


def rids_of(scene):
    return [r['rid'] for r in scene['robots']]


def robot_of(scene, rid):
    return next(r for r in scene['robots'] if r['rid'] == rid)


def box_of(scene, bid):
    return next(b for b in scene['boxes'] if b['id'] == bid)


def order_of(scene, oid):
    return next(o for o in scene['orders'] if o['id'] == oid)


def caps(scene, rid):
    return tuple((scene.get('can_grasp') or {}).get(rid, COLOURS))


def demand(scene):
    return sum(o['count'] for o in scene['orders'])


# ---------------------------------------------------------------- geometry
def bisector_yaw(rx, ry, points):
    """Heading that centres the smallest arc containing all bearings to `points`; returns (yaw, span)."""
    angs = sorted(math.atan2(py - ry, px - rx) for px, py in points)
    n = len(angs)
    if n == 1:
        return angs[0], 0.0
    gaps = [(angs[(i + 1) % n] - angs[i]) % (2 * math.pi) for i in range(n)]
    i = max(range(n), key=lambda j: gaps[j])
    start, span = angs[(i + 1) % n], 2 * math.pi - gaps[i]
    return wrap(start + span / 2), span


def seg_point_dist(p, a, b):
    vx, vy = b['x'] - a['x'], b['y'] - a['y']
    t = 0.0 if vx == vy == 0 else max(0.0, min(1.0, ((p['x'] - a['x']) * vx + (p['y'] - a['y']) * vy) / (vx * vx + vy * vy)))
    return math.hypot(p['x'] - (a['x'] + t * vx), p['y'] - (a['y'] + t * vy))


def geometry_errors(scene):
    errs = []
    xlo, xhi, ylo, yhi = X_MIN + CLEAR, PART_X - CLEAR, Y_MIN + CLEAR, Y_MAX - CLEAR
    for kind, items in (('box', scene['boxes']), ('robot', scene['robots'])):
        for it in items:
            if not (xlo - EPS <= it['x'] <= xhi + EPS and ylo - EPS <= it['y'] <= yhi + EPS):
                errs.append('%s %s outside the 0.40 m wall margin' % (kind, it.get('id', it.get('rid'))))
    for a, b in itertools.combinations(scene['boxes'], 2):
        if dist(a, b) < BOX_GAP - EPS:
            errs.append('boxes %s,%s %.2f m apart' % (a['id'], b['id'], dist(a, b)))
    for a, b in itertools.combinations(scene['robots'], 2):
        if dist(a, b) < ROBOT_GAP - EPS:
            errs.append('robots %s,%s %.2f m apart' % (a['rid'], b['rid'], dist(a, b)))
    for r in scene['robots']:
        near = min(dist(r, b) for b in scene['boxes'])
        if not (NEAR_MIN - EPS <= near <= NEAR_MAX + EPS):
            errs.append('%s nearest box %.2f m' % (r['rid'], near))
        for b in scene['boxes']:
            dev = abs(wrap(math.atan2(b['y'] - r['y'], b['x'] - r['x']) - r['yaw']))
            if dev > math.radians(FOV_DEG) + 1e-9:
                errs.append('%s box %s %.1f deg off the heading' % (r['rid'], b['id'], math.degrees(dev)))
            for q in scene['robots']:
                if q is not r and seg_point_dist(q, r, b) < LOS_CLEAR:
                    errs.append('%s blocks %s view of box %s' % (q['rid'], r['rid'], b['id']))
    return errs


# ---------------------------------------------------------------- time model and scoring
def pick_end_s(scene, rid, bid):
    return SURVEY_S + PICK_S_AT_08M * dist(robot_of(scene, rid), box_of(scene, bid)) / 0.8


def simulate(scene, assign):
    """assign {rid: (box id, sign, pick_end override or None)} -> deliveries with set-down end times."""
    items = []
    for rid, (bid, sign, override) in sorted(assign.items()):
        pe = pick_end_s(scene, rid, bid) if override is None else override
        items.append({'rid': rid, 'box': bid, 'colour': box_of(scene, bid)['colour'], 'sign': sign, 'start': pe,
                      'arrive': pe + DOOR_OFFSET_S})
    free = -1e18
    for it in sorted(items, key=lambda i: (i['arrive'], i['rid'])):
        enter = max(it['arrive'], free)
        free = enter + DOOR_SLOT_S
        it['end'] = it['start'] + CARRY_S + (enter - it['arrive']) + PLACE_S
    return items


def score(scene, deliveries):
    """-> (correct boxes, completion s or None when demand is unmet, unmatched deliveries = errors)."""
    used = set()
    for o in sorted(scene['orders'], key=lambda o: oid_key(o['id'])):
        met = 0
        for idx in sorted(range(len(deliveries)), key=lambda i: (deliveries[i]['end'], deliveries[i]['rid'])):
            d = deliveries[idx]
            if idx not in used and d['colour'] == o['colour'] and d['sign'] == o['sign'] and met < o['count']:
                used.add(idx)
                met += 1
    n = len(used)
    completion = max((deliveries[i]['end'] for i in used), default=None) if n >= demand(scene) else None
    return n, completion, len(deliveries) - n


# ---------------------------------------------------------------- oracle
def oracle_search(scene):
    """Omniscient plan: maximise correct boxes, then minimise completion, then prefer plans in which every robot carries an
    order it knows, then fewer carriers, then lexicographic. One carry per robot. -> canonical result dict."""
    rids = rids_of(scene)
    opts = []
    for rid in rids:
        o_ = [None]
        for o in sorted(scene['orders'], key=lambda o: oid_key(o['id'])):
            for b in scene['boxes']:
                if b['colour'] == o['colour'] and b['colour'] in caps(scene, rid):
                    o_.append((b['id'], o['id']))
        opts.append(o_)
    best = None
    for combo in itertools.product(*opts):
        boxes = [c[0] for c in combo if c]
        orders = [c[1] for c in combo if c]
        if len(boxes) != len(set(boxes)):
            continue
        if any(orders.count(o['id']) > o['count'] for o in scene['orders']):
            continue
        assign = {rid: (c[0], order_of(scene, c[1])['sign'], None) for rid, c in zip(rids, combo) if c}
        n, t, err = score(scene, simulate(scene, assign))
        unknown = sum(1 for rid, c in zip(rids, combo) if c and c[1] not in scene['knows'].get(rid, []))
        key = (-n, err, round(t, 6) if t is not None else 1e9, unknown, len(assign), repr(combo))
        if best is None or key < best[0]:
            best = (key, combo, t, n)
    key, combo, t, n = best
    plan = {rid: ([[c[0], c[1]]] if c else []) for rid, c in zip(rids, combo)}
    return {'plan': plan, 'correct': n, 'completion': t, 'errors': key[1]}


# ---------------------------------------------------------------- baseline
def known_usable(scene, rid):
    present = {b['colour'] for b in scene['boxes']}
    by_id = {o['id']: o for o in scene['orders']}
    return [by_id[o] for o in scene['knows'].get(rid, []) if by_id[o]['colour'] in present and by_id[o]['colour'] in caps(scene, rid)]


def nearest(scene, rid, boxes):
    r = robot_of(scene, rid)
    return min(boxes, key=lambda b: (round(dist(r, b), 9), b['id']))


def robot_options(scene, rid, variant):
    """-> [(prob, box id or None, sign or None, restrict colour or None)]; variant primary|first|guess."""
    use = known_usable(scene, rid)
    if use:
        picks = [use[0]] if variant == 'first' else use
        out = []
        for o in picks:
            b = nearest(scene, rid, [b for b in scene['boxes'] if b['colour'] == o['colour']])
            out.append((1.0 / len(picks), b['id'], o['sign'], o['colour']))
        return out
    if variant == 'guess':
        gr = [b for b in scene['boxes'] if b['colour'] in caps(scene, rid)]
        if gr:
            b = nearest(scene, rid, gr)
            return [(1.0 / len(SIGNS), b['id'], s, None) for s in SIGNS]
    return [(1.0, None, None, None)]


def build_assign(scene, picks):
    """picks {rid: (box id, sign, restrict colour)} -> assign for simulate(); resolves same-box conflicts (see module doc)."""
    chosen = {p[0] for p in picks.values()}
    taken, assign = set(), {}
    for rid in sorted(picks, key=lambda r: (pick_end_s(scene, r, picks[r][0]), r)):
        bid, sign, colour = picks[rid]
        if bid not in taken:
            taken.add(bid)
            assign[rid] = (bid, sign, None)
            continue
        cont = box_of(scene, bid)
        cands = [b for b in scene['boxes'] if b['id'] not in chosen and (colour is None or b['colour'] == colour)
                 and b['colour'] in caps(scene, rid)]
        if cands:
            nb = min(cands, key=lambda b: (round(dist(cont, b), 9), b['id']))
            assign[rid] = (nb['id'], sign, pick_end_s(scene, rid, bid) + SURVEY_S + PICK_S_AT_08M * dist(cont, nb) / 0.8)
            taken.add(nb['id'])
    return assign


def baseline_eval(scene, variant):
    rids = rids_of(scene)
    out = {'correct': 0.0, 'errors': 0.0, 'p_full': 0.0, 'capped': 0.0, 'active_end': 0.0, 'conflict': 0.0, 'completion': None}
    for combo in itertools.product(*[robot_options(scene, rid, variant) for rid in rids]):
        p, picks = 1.0, {}
        for rid, (pr, bid, sign, colour) in zip(rids, combo):
            p *= pr
            if bid is not None:
                picks[rid] = (bid, sign, colour)
        if len({v[0] for v in picks.values()}) < len(picks):
            out['conflict'] += p
        dels = simulate(scene, build_assign(scene, picks))
        n, t, err = score(scene, dels)
        out['correct'] += p * n
        out['errors'] += p * err
        out['p_full'] += p * (t is not None)
        out['capped'] += p * (t if t is not None else LIMIT_S)
        out['active_end'] += p * max((d['end'] for d in dels), default=0.0)
        out['completion'] = t
    if variant == 'first':
        out['plan'] = {rid: ([[robot_options(scene, rid, 'first')[0][1], known_usable(scene, rid)[0]['id']]]
                             if known_usable(scene, rid) else []) for rid in rids}
    return out


# ---------------------------------------------------------------- balance attributes and estimate
def balance(scene):
    rids = rids_of(scene)
    k = {rid: len(scene['knows'].get(rid, [])) for rid in rids}
    mx = max(k.values())
    top = [rid for rid in rids if k[rid] == mx]
    holder = 'none' if mx == 0 else top[0] if len(top) == 1 else 'both'
    out = {'holder': holder, 'decision_robot': None, 'correct_is_first_order': None, 'correct_sign': None,
           'correct_is_first_menu': None, 'correct_is_lower_known_sign': None}
    if holder in rids and k[holder] >= 2:
        plan = scene['oracle_plan'].get(holder) or []
        if plan:
            oid = plan[0][1]
            out['decision_robot'] = holder
            out['correct_is_first_order'] = scene['knows'][holder][0] == oid
            out['correct_sign'] = order_of(scene, oid)['sign']
            out['correct_is_first_menu'] = out['correct_sign'] == SIGNS[0]          # menu read as 11,12,13
            out['correct_is_lower_known_sign'] = out['correct_sign'] == min(order_of(scene, o)['sign'] for o in scene['knows'][holder])  # menu read as the holder's own order signs, numeric order
    return out


def r4(x):
    return None if x is None else round(x, 4)


def estimate(scene, oracle=None):
    o = oracle or oracle_search(scene)
    bp, bf, bg = baseline_eval(scene, 'primary'), baseline_eval(scene, 'first'), baseline_eval(scene, 'guess')
    return {
        'oracle_correct': o['correct'], 'oracle_completion_s': r4(o['completion']), 'oracle_errors': o['errors'],
        'baseline_correct': r4(bp['correct']), 'baseline_p_full': r4(bp['p_full']),
        'baseline_capped_completion_s': r4(bp['capped']), 'baseline_active_end_s': r4(bp['active_end']),
        'baseline_errors': r4(bp['errors']), 'baseline_conflict_p': r4(bp['conflict']),
        'baseline_first_listed_correct': r4(bf['correct']), 'baseline_first_listed_completion_s': r4(bf['completion']),
        'baseline_guess_correct': r4(bg['correct']), 'baseline_guess_errors': r4(bg['errors']),
        'baseline_guess_capped_completion_s': r4(bg['capped']),
        'gap': r4(o['correct'] - bp['correct']), 'gap_guess': r4(o['correct'] - bg['correct']),
        'time_gap_capped_s': r4(bp['capped'] - (o['completion'] if o['completion'] is not None else LIMIT_S)),
    }


def annotate(scene):
    """Fill oracle_plan, baseline_plan, estimate, balance from the raw fields (in place)."""
    o = oracle_search(scene)
    scene['oracle_plan'] = o['plan']
    scene['baseline_plan'] = baseline_eval(scene, 'first')['plan']
    scene['estimate'] = estimate(scene, o)
    scene['balance'] = balance(scene)
    return scene


def dump(obj, path):
    with open(path, 'w') as fh:
        fh.write(json.dumps(obj, indent=1, ensure_ascii=False) + '\n')


MODEL = {
    'deadline_s': LIMIT_S, 'survey_s': SURVEY_S, 'pickup_at_0_8m_s': PICK_S_AT_08M,
    'pickup_formula': '58*d/0.8 after the 12 s survey; d = start-to-box distance (analytical proxy only, DESIGN-18)',
    'carry_s': CARRY_S, 'place_s': PLACE_S, 'door_slot_s': DOOR_SLOT_S, 'door_offset_from_carry_start_s': DOOR_OFFSET_S,
    'door_rule': 'The 8 s exclusive slot is inside the 110 s carry; FCFS, ties r1; queue delay shifts the rest of the carry and the set-down.',
    'message_s': 2.0, 'oracle_messages': 0,
    'one_carry_per_robot': True, 'note': 'No second carry in v2 (no return/repeat pickup); DESIGN-18 return_s and repeat_pickup_s do not apply.',
    'count_rule': 'Sum over orders of min(count, boxes of that colour set down at that sign); unmatched deliveries are errors (unordered move).',
    'upper_definition': 'Omniscient plan: maximise correct boxes, then minimise completion, then prefer plans where each robot carries an order it knows. Not a measured minimum.',
    'time_rule': 'Unmet demand counts 900 s in *_capped_completion_s; baseline_active_end_s is the end of the last acting robot.'}

ARENA = {'x': [X_MIN, X_MAX], 'y': [Y_MIN, Y_MAX], 'partition_x': PART_X,
         'door': {'x': DOOR[0], 'y': DOOR[1], 'width': 0.5, 'capacity': 1},
         'box_size': 0.04, 'signs': {str(k): list(v) for k, v in SIGN_POS.items()},
         'drop_centres': {str(k): list(v) for k, v in DROP.items()}}

BASELINE_RULES = {
    'B': 'No messages. A robot that knows >=1 order picks one of its known orders, takes the nearest box of that colour and '
         'sets it down at that order\'s sign (one carry only). A robot that knows no order does nothing.',
    'primary': 'baseline_correct and all baseline_* time fields: the pick among known orders is UNIFORM (position-free expectation, '
               'exact enumeration of all joint choices). This is the gap filter.',
    'first_listed': 'baseline_plan and baseline_first_listed_*: the pick is knows[rid][0] (DESIGN-18 lowest-ID rule; lists are in ID '
                    'order). Diagnostic only: with first-listed balance it equals the oracle in half of the C scenes.',
    'guess': 'baseline_guess_*: like primary, but a robot with no order takes its nearest box (any colour) and a uniformly random '
             'sign. Wrong boxes cost no points under the count rule but count as errors (unordered move).',
    'conflict': 'Two robots choosing the same box: earlier arrival keeps it; the other re-surveys 12 s at that box and takes the '
                'nearest box nobody chose (same colour if informed), or nothing.',
    'time_model': 'DESIGN-18: survey 12 s, pick 58*d/0.8 s, carry 110 s (door entry +40 s, 8 s slot, FCFS, ties r1), set-down 10 s; '
                  'unmet demand counts 900 s in *_capped_completion_s.',
}
