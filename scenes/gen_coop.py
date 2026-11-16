#!/usr/bin/env python3
"""Scratch generator for scenes_coop.json (not a deliverable). Samples valid geometry per scene spec with a fixed
seed, then fills oracle_plan / baseline_plan / info_flow / estimate from the checker's own model."""
import json
import math
import os
import random
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_scenes as cs  # noqa: E402

OUT = os.path.join(HERE, 'scenes_coop.json')
RED, BLUE = 'red', 'blue'
BOTH = ['red', 'blue']
OTHER = {RED: BLUE, BLUE: RED}


def O(i, colour, sign):
    return {'id': 'o%d' % i, 'colour': colour, 'count': 1, 'sign': sign}


SPECS, REJECT_SPECS = [], []


def add(**kw):
    SPECS.append(kw)


def addr(**kw):
    REJECT_SPECS.append(kw)


def k2(idx, o1c, r1c, s1, s2, variant, holder=None, cross=False):
    """K2 scene. o1c colour of order o1 (o2 has the other colour); r1c capability colour of r1 (r2 the other).
    variant A: each robot knows only the order of the colour it cannot grasp. B: `holder` knows both orders, other none."""
    o2c = OTHER[o1c]
    orders = [O(1, o1c, s1), O(2, o2c, s2)]
    cap = {'r1': [r1c], 'r2': [OTHER[r1c]]}
    colours = [o1c, o2c] if idx % 2 else [o2c, o1c]        # box ids a,b: colour order alternates
    oid_of = {o1c: 'o1', o2c: 'o2'}
    if variant == 'A':
        knows = {'r1': [oid_of[OTHER[r1c]]], 'r2': [oid_of[r1c]]}
    else:
        knows = {r: (['o1', 'o2'] if r == holder else []) for r in ('r1', 'r2')}
    targets = {rid: colours.index(cap[rid][0]) for rid in ('r1', 'r2')}
    add(id='K2%02d' % idx, seed_id='K2-%02d' % idx, type='capability_2', colours=colours, orders=orders, knows=knows, can_grasp=cap,
        targets=targets, extra='cross' if cross else None)


# ---- K2: capability, 2 robots (10 scenes). A = cross knowledge (both blind), B = one holder knows both orders.
k2(1, RED, RED, 11, 12, 'A')
k2(2, BLUE, BLUE, 13, 11, 'A')
k2(3, RED, BLUE, 12, 13, 'A', cross=True)
k2(4, BLUE, RED, 11, 13, 'A')
k2(5, RED, RED, 13, 12, 'A')
k2(6, RED, BLUE, 12, 11, 'A', cross=True)
k2(7, RED, RED, 12, 13, 'B', holder='r1')                   # holder r1 carries its first-listed order o1
k2(8, RED, BLUE, 11, 12, 'B', holder='r1', cross=True)      # holder r1 (blue) carries its second-listed order o2
k2(9, BLUE, RED, 13, 12, 'B', holder='r2')                  # holder r2 (blue) carries o1
k2(10, BLUE, BLUE, 13, 11, 'B', holder='r2')                # holder r2 (red) carries o2

# ---- K3: capability, 3 robots, every robot blind to its own sign under rule U
add(id='K301', seed_id='K3-01', type='capability_3', colours=[RED, BLUE, RED],
    orders=[O(1, RED, 11), O(2, RED, 13), O(3, BLUE, 12)],
    knows={'r1': ['o3'], 'r2': [], 'r3': ['o1', 'o2']}, can_grasp={'r1': [RED], 'r2': [RED], 'r3': [BLUE]},
    targets={'r1': 0, 'r3': 1, 'r2': 2})
add(id='K302', seed_id='K3-02', type='capability_3', colours=[BLUE, RED, BLUE],
    orders=[O(1, BLUE, 12), O(2, BLUE, 11), O(3, RED, 13)],
    knows={'r1': [], 'r2': ['o1', 'o2'], 'r3': ['o3']}, can_grasp={'r1': [BLUE], 'r2': [RED], 'r3': [BLUE]},
    targets={'r1': 0, 'r2': 1, 'r3': 2})
add(id='K303', seed_id='K3-03', type='capability_3', colours=[BLUE, RED, RED],
    orders=[O(1, RED, 13), O(2, RED, 12), O(3, BLUE, 11)],
    knows={'r1': ['o1', 'o2'], 'r2': ['o3'], 'r3': []}, can_grasp={'r1': [BLUE], 'r2': [RED], 'r3': [RED]},
    targets={'r1': 0, 'r2': 1, 'r3': 2})
add(id='K304', seed_id='K3-04', type='capability_3', colours=[RED, RED, BLUE],
    orders=[O(1, RED, 12), O(2, RED, 11), O(3, BLUE, 13)],
    knows={'r1': [], 'r2': ['o3'], 'r3': ['o1', 'o2']}, can_grasp={'r1': BOTH, 'r2': [RED], 'r3': [BLUE]},
    targets={'r1': 0, 'r2': 1, 'r3': 2})

# ---- L3: orders concentrated in one robot (r1, r2, r3 in turn); its lowest-ID order has the colour of its nearest box
add(id='L301', seed_id='L3-01', type='orders_concentrated_3', colours=[RED, BLUE, RED], orders=[O(1, RED, 11), O(2, BLUE, 12), O(3, RED, 13)],
    knows={'r1': ['o1', 'o2', 'o3'], 'r2': [], 'r3': []}, targets={'r1': 0, 'r2': 1, 'r3': 2})
add(id='L302', seed_id='L3-02', type='orders_concentrated_3', colours=[RED, BLUE, BLUE], orders=[O(1, BLUE, 12), O(2, RED, 13), O(3, BLUE, 11)],
    knows={'r1': [], 'r2': ['o1', 'o2', 'o3'], 'r3': []}, targets={'r1': 0, 'r2': 1, 'r3': 2})
add(id='L303', seed_id='L3-03', type='orders_concentrated_3', colours=[RED, RED, BLUE], orders=[O(1, BLUE, 12), O(2, RED, 13), O(3, RED, 11)],
    knows={'r1': [], 'r2': [], 'r3': ['o1', 'o2', 'o3']}, targets={'r1': 0, 'r2': 1, 'r3': 2})

# ---- alternative candidates evaluated and rejected (kept for the record)
addr(id='K2x1', type='capability_2', colours=[RED, BLUE], orders=[O(1, RED, 11), O(2, BLUE, 12)],
     knows={'r1': ['o1', 'o2'], 'r2': ['o1', 'o2']}, can_grasp={'r1': [RED], 'r2': [BLUE]}, targets={'r1': 0, 'r2': 1},
     why='capability alone is not enough: both robots know both orders and each can act on its own colour')
addr(id='K3x1', type='capability_3', colours=[RED, BLUE, RED], orders=[O(1, RED, 11), O(2, RED, 13), O(3, BLUE, 12)],
     knows={'r1': ['o3'], 'r2': ['o1'], 'r3': ['o2']}, can_grasp={'r1': [RED], 'r2': [RED], 'r3': [BLUE]},
     targets={'r1': 0, 'r3': 1, 'r2': 2},
     why='one order per robot (no elimination) but r2 knows a red order it can grasp, so it needs no fact')
addr(id='L3x1', type='orders_concentrated_3', colours=[RED, BLUE, RED], orders=[O(1, RED, 11), O(2, BLUE, 12), O(3, RED, 13)],
     knows={'r1': ['o1', 'o2', 'o3'], 'r2': ['o1', 'o2', 'o3'], 'r3': []}, targets={'r1': 0, 'r2': 1, 'r3': 2},
     why='two robots know all orders and both take the lowest-ID box colour')


def mid_yaw(r, boxes):
    angs = [math.atan2(b['y'] - r['y'], b['x'] - r['x']) for b in boxes]
    ref = angs[0]
    rel = [cs.wrap(a - ref) for a in angs]
    return round(cs.wrap(ref + (min(rel) + max(rel)) / 2), 4)


def build(spec, seed):
    rng = random.Random('%s/%d' % (spec.get('seed_id', spec['id']), seed))
    xlo, xhi, ylo, yhi = cs.X_MIN + 0.4, cs.PART_X - 0.4, cs.Y_MIN + 0.4, cs.Y_MAX - 0.4
    n_b, rids = len(spec['colours']), sorted(spec['targets'])
    g = lambda lo, hi: round(rng.uniform(lo, hi) / 0.05) * 0.05
    for attempt in range(80000):
        pts = [(round(g(xlo, 1.3), 2), round(g(ylo, yhi), 2)) for _ in range(n_b)]
        if any(cs.dist(a, b) < 0.9 for i, a in enumerate(pts) for b in pts[i + 1:]):
            continue
        rob, ok = {}, True
        for rid in rids:
            bx, by = pts[spec['targets'][rid]]
            d, ang = rng.uniform(0.65, 1.05), rng.uniform(0, 2 * math.pi)
            p = (round(round((bx + d * math.cos(ang)) / 0.05) * 0.05, 2), round(round((by + d * math.sin(ang)) / 0.05) * 0.05, 2))
            if not (xlo <= p[0] <= xhi and ylo <= p[1] <= yhi):
                ok = False
                break
            rob[rid] = p
        if not ok or any(cs.dist(rob[a], rob[b]) < 0.8 for a in rids for b in rids if a < b):
            continue
        boxes = [{'id': chr(97 + i), 'colour': spec['colours'][i], 'x': pts[i][0], 'y': pts[i][1]} for i in range(n_b)]
        robots = [{'rid': rid, 'x': rob[rid][0], 'y': rob[rid][1]} for rid in rids]
        for r in robots:
            r['yaw'] = mid_yaw(r, boxes)
        scene = {'id': spec['id'], 'type': spec['type'], 'boxes': boxes, 'robots': robots}
        errs, geo = cs.geometry_report(dict(scene))
        if errs or geo['max_dev_deg'] > 62:
            continue
        can = spec.get('can_grasp') or {}
        good = True
        for r in robots:
            cand = [b for b in boxes if b['colour'] in can.get(r['rid'], BOTH)]
            near = min(cand, key=lambda b: (round(cs.dist(r, b), 9), b['id']))
            if near['id'] != boxes[spec['targets'][r['rid']]]['id']:
                good = False
            ds = sorted(cs.dist(r, b) for b in cand)
            if len(ds) > 1 and ds[1] - ds[0] < 0.15:       # clear margin on the nearest graspable box
                good = False
        if spec.get('extra') == 'cross':
            for r in robots:
                if min(boxes, key=lambda b: cs.dist(r, b))['colour'] in can.get(r['rid'], BOTH):
                    good = False
        if not good:
            continue
        scene.update(orders=spec['orders'], knows=spec['knows'])
        if spec.get('can_grasp'):
            scene['can_grasp'] = spec['can_grasp']
        scene['constraints'] = []
        return scene, attempt
    raise RuntimeError('no layout for %s' % spec['id'])


def fill(scene):
    orac = cs.oracle_search(scene)
    plan = {r['rid']: [] for r in scene['robots']}
    for idx, oid in orac['match'].items():
        plan[orac['dels'][idx]['rid']].append([orac['dels'][idx]['box'], oid])
    scene['oracle_plan'] = plan
    scene['baseline_plan'] = cs.baseline_plan_from_rule(scene)
    assign, _ = cs.plan_to_assign(scene, plan)
    bu, bs = cs.baseline_eval(scene, 'U'), cs.baseline_eval(scene, 'S')
    rids = [r['rid'] for r in scene['robots']]
    carried = [next(b['colour'] for b in scene['boxes'] if b['id'] == a[0]) for a in assign.values()]
    rounds = 2 if len(set(carried)) < len(carried) else 1
    ready = {rid: cs.RANK_WAIT_S * i + cs.MSG_S * rounds for i, rid in enumerate(rids)}
    coop = cs.score(scene, cs.simulate(scene, assign, ready=ready))[1]
    scene['estimate'] = {
        'oracle_correct': orac['correct'], 'oracle_completion_s': round(orac['completion'], 1),
        'coop_completion_s': round(coop, 1), 'message_rounds': rounds,
        'baseline_correct': round(bu['E'], 4), 'baseline_S_correct': round(bs['E'], 4),
        'baseline_p_full': round(bu['p_full'], 4), 'baseline_p_full_S': round(bs['p_full'], 4),
        'baseline_capped_completion_s': round(bu['capped'], 1), 'baseline_active_end_s': round(bu['active_end'], 1)}
    scene['info_flow'] = cs.info_flow(scene)
    return scene


def main():
    scenes, rejected = [], []
    for spec in SPECS:
        scene, tries = build(spec, 1)
        scene = fill(scene)
        res = cs.analyse(scene)
        print(spec['id'], 'tries', tries, 'errors', res['errors'])
        scenes.append(scene)
    for spec in REJECT_SPECS:
        scene, tries = build(spec, 1)
        scene = fill(scene)
        res = cs.analyse(scene)
        undefined = res['U']['conflict'] or res['S']['conflict']
        print('REJ', spec['id'], 'gapU %.2f gapS %.2f' % (res['gap_u'], res['gap_s']), 'conflict' if undefined else '', res['errors'])
        rejected.append({'id': spec['id'], 'type': spec['type'], 'why': spec['why'], 'oracle_correct': res['demand'],
                         'baseline_U_correct': None if undefined else round(res['U']['E'], 3),
                         'baseline_S_correct': None if undefined else round(res['S']['E'], 3),
                         'gap_U': None if undefined else round(res['gap_u'], 3), 'gap_S': None if undefined else round(res['gap_s'], 3),
                         'knows': spec['knows'], 'can_grasp': spec.get('can_grasp'), 'check_errors': res['errors']})
    meta = json.load(open(os.path.join(HERE, 'scenes18b.json')))
    data = {
        'schema': 'coop_scenes.v2',
        'status': 'analytical_candidates_not_experimental_results',
        'scope': 'K2 10, K3 4, L3 3. C3 and S2 (order constraint) dropped on the main session decision after the external review.',
        'units': meta['units'],
        'arena': meta['arena'],
        'knowledge_contract': {
            'knows_references': 'Order IDs only (complete order: colour, count, sign). A robot does not learn that an order it lacks does not exist.',
            'can_grasp': 'Optional {rid: [colours]}: the robot can only grasp those colours. A robot knows its own capability, not the others.',
            'coordinates': 'Evaluator-only. Never give world coordinates, box IDs or oracle plans to the LLM.',
            'one_carry': 'Each robot carries at most one box per run. Demand never exceeds the number of robots.',
            'one_order_per_sign': 'Every scene has distinct signs per order (the second robot may not see a sign behind the first).',
            'constraints': 'Always empty (order constraints dropped).',
            'visibility_verified': False},
        'model': {
            'deadline_s': cs.LIMIT_S, 'survey_s': cs.SURVEY_S,
            'pick_s': 'robot-box distance d: 58*d/0.8 after the survey (58 s at 0.8 m)',
            'carry_s': 'clamp(22.4*(|box-door|+|door-drop|), 100, 120); door entry at the box-door share of the carry',
            'drop_centres': meta['arena']['drop_centres'], 'setdown_s': cs.SETDOWN_S, 'door_slot_s': cs.DOOR_SLOT_S,
            'door': 'one robot at a time, FCFS, ties by rid; queue delay shifts the rest of the carry',
            'message_s': cs.MSG_S, 'rank_wait_s': 'r_k waits 4*(k-1) s before choosing a destination (coordinated runs only)',
            'coop_ready_s': 'rank wait + 2 s per message round (1 round: information; 2 rounds: information + claims when two boxes share a colour)',
            'count_rule': 'sum over orders of min(count, boxes of that colour set down at that sign); wrong boxes score 0, never subtract'},
        'baseline_rules': {
            'U': 'primary T0: a robot that knows an order of a colour it can grasp takes the nearest box of the colour of its lowest-ID such order and sets it down at that sign; otherwise it takes the nearest box it can grasp and picks 11/12/13 uniformly. Differs from DESIGN-18 T0 (abstains without an order); guessing costs nothing under the count rule, so this favours T0.',
            'S': 'stricter test: like U, but a robot without a usable order excludes the signs of orders it knows, and a robot with several usable orders of one colour picks one uniformly.',
            'expectation': 'exact enumeration of all joint random choices, not 1/3 per robot',
            'conflicts': 'two robots choosing the same box is a design error (checker fails)'},
        'scenes': scenes,
        'rejected_candidates': rejected,
        'note': 'yaw = bisector of the bearings to the extreme boxes, so every box lies within 70 deg of the heading for every robot (strictest reading: all boxes, not only graspable ones). Coordinates sampled with fixed seeds on a 0.05 m grid under the geometry rules.'}
    json.dump(data, open(OUT, 'w'), indent=1)
    print('wrote', OUT, len(scenes), 'scenes', len(rejected), 'rejected')


if __name__ == '__main__':
    main()
