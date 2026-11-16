#!/usr/bin/env python3
"""Seeded, deterministic random-scene generator (standard library only; no simulation, no LLM, no network).

Implements the random-scene rules of the design review with the sample-space
changes forced by the v2 task rules (declared in the output file under `deviations_from_proposal`):
  20 slots (RND2-01..20); order signs drawn WITHOUT replacement (no count=2, never two boxes for one sign); 0.40 m wall margin
  for boxes and robots, boxes >= 0.6 m apart, robots >= 0.6 m apart; yaw = bisector of the bearings to ALL boxes and every box
  within 70 deg of it (rejection); no robot body on a line of sight; A/B -> r1/r2 by a stratified 10/10 plan.
Nothing here reads or computes oracle/baseline/gap values before the scene is fixed; estimates are filled in afterwards and are
never used to accept, reject or replace a scene. Heldout seeds 8342000-8342002 are not used.

Random stream: SHA-256("random-scene-v2|<seed>|<i>|<stream>|<a>|<k>"), first 8 bytes big-endian / 2**64.
Usage: python3 gen_random.py [out.json]
"""
import hashlib
import json
import os
import sys

import model_v2 as m

SEED = 2026111501
VERSION = 'random-scene-v2'
N_SCENES = 20
MAX_TRY = 1000
LETTERS = ('a', 'b', 'c')
X_LO, X_HI = m.X_MIN + m.CLEAR, m.PART_X - m.CLEAR      # -0.65 .. 1.80
Y_LO, Y_HI = m.Y_MIN + m.CLEAR, m.Y_MAX - m.CLEAR       # -2.75 .. 1.05


class Stream:
    def __init__(self, i, name, a=0):
        self.i, self.name, self.a, self.k = i, name, a, 0

    def u(self):
        key = '%s|%d|%d|%s|%d|%d' % (VERSION, SEED, self.i, self.name, self.a, self.k)
        self.k += 1
        return int.from_bytes(hashlib.sha256(key.encode('utf-8')).digest()[:8], 'big') / 2.0 ** 64

    def below(self, n):
        return int(n * self.u())

    def uniform(self, lo, hi):
        return lo + (hi - lo) * self.u()

    def shuffle(self, seq):
        for j in range(len(seq) - 1, 0, -1):
            r = self.below(j + 1)
            seq[j], seq[r] = seq[r], seq[j]
        return seq


def content(i):
    s = Stream(i, 'content', 0)
    n = 2 + s.below(2)
    q = 1 + s.below(2)
    colours = [m.COLOURS[s.below(2)] for _ in range(n)]
    idx = s.shuffle(list(range(n)))[:q]
    pool, dests = list(m.SIGNS), []
    for _ in range(q):
        dests.append(pool.pop(s.below(len(pool))))
    holders = [s.below(3) for _ in range(q)]            # 0: A only, 1: B only, 2: A and B
    return {'n': n, 'q': q, 'colours': colours, 'demands': [(colours[ix], d) for ix, d in zip(idx, dests)], 'holders': holders}


def geometry(i, n, attempt):
    s = Stream(i, 'geometry', attempt)
    pts = [(round(s.uniform(X_LO, X_HI), 2), round(s.uniform(Y_LO, Y_HI), 2)) for _ in range(n)]
    ra = (round(s.uniform(X_LO, X_HI), 2), round(s.uniform(Y_LO, Y_HI), 2))
    rb = (round(s.uniform(X_LO, X_HI), 2), round(s.uniform(Y_LO, Y_HI), 2))
    return pts, ra, rb


def swap_plan():
    plan = [False] * (N_SCENES // 2) + [True] * (N_SCENES - N_SCENES // 2)
    return Stream(0, 'swapplan', 0).shuffle(plan)


def make_scene(i, plan):
    c = content(i)
    n = c['n']
    for attempt in range(1, MAX_TRY + 1):
        pts, ra, rb = geometry(i, n, attempt)
        boxes = [{'id': LETTERS[j], 'colour': c['colours'][j], 'x': p[0], 'y': p[1]} for j, p in enumerate(pts)]
        robots = []
        for rid, pos in (('A', ra), ('B', rb)):
            yaw, _ = m.bisector_yaw(pos[0], pos[1], pts)
            robots.append({'rid': rid, 'x': pos[0], 'y': pos[1], 'yaw': round(yaw, 4)})
        if not m.geometry_errors({'boxes': boxes, 'robots': [dict(r, rid=('r1', 'r2')[k]) for k, r in enumerate(robots)]}):
            break
    else:
        return None, MAX_TRY
    # labels (stream order: robot map, order IDs, r1 list, r2 list, box IDs, box array)
    lab = Stream(i, 'labels', 0)
    swapped = plan[i - 1]
    rmap = {'A': 'r2', 'B': 'r1'} if swapped else {'A': 'r1', 'B': 'r2'}
    perm = lab.shuffle(list(range(c['q'])))             # perm[k] = demand index that gets ID o(k+1)
    oid = {d: 'o%d' % (k + 1) for k, d in enumerate(perm)}
    orders = [{'id': oid[d], 'colour': col, 'count': 1, 'sign': sg} for d, (col, sg) in enumerate(c['demands'])]
    orders.sort(key=lambda o: m.oid_key(o['id']))
    known = {'r1': [], 'r2': []}
    for d, h in enumerate(c['holders']):
        for who in ('A', 'B') if h == 2 else (('A',) if h == 0 else ('B',)):
            known[rmap[who]].append(oid[d])
    knows = {'r1': lab.shuffle(known['r1']), 'r2': lab.shuffle(known['r2'])}
    ids = lab.shuffle(list(LETTERS[:n]))
    boxes = [dict(b, id=ids[j]) for j, b in enumerate(boxes)]
    boxes = [boxes[j] for j in lab.shuffle(list(range(n)))]
    robots = sorted([dict(r, rid=rmap[r['rid']]) for r in robots], key=lambda r: r['rid'])
    scene = {'id': 'RND2-%02d' % i, 'type': 'random', 'type_code': 'RND', 'control': False, 'boxes': boxes, 'robots': robots,
             'orders': orders, 'knows': knows, 'constraints': [], 'gen': {'n_boxes': n, 'total_demand': c['q'], 'attempts': attempt,
                                                                          'swapped_AB': swapped}}
    return scene, attempt


def generate():
    plan = swap_plan()
    scenes, missing = [], []
    for i in range(1, N_SCENES + 1):
        scene, tries = make_scene(i, plan)
        if scene is None:
            missing.append({'id': 'RND2-%02d' % i, 'reason': 'no geometry accepted in %d attempts' % tries})
            continue
        m.annotate(scene)                                # estimates only AFTER the scene is fixed; never used to accept/replace
        scenes.append(scene)
    return {
        'schema': 'scenes_v2.random.v1',
        'status': 'analytical_candidates_not_experimental_results',
        'seed': SEED, 'stream_version': VERSION, 'n_slots': N_SCENES, 'max_attempts_per_slot': MAX_TRY,
        'units': {'position': 'm', 'yaw': 'rad', 'time': 's'},
        'arena': m.ARENA,
        'rules': {'robots': 2, 'one_carry_per_robot': True, 'order_count': 1, 'one_order_per_sign': True,
                  'unordered_move_is_error': True, 'idle_robot_may_finish': True, 'dev_exposed_excluded': list(m.DEV_EXPOSED)},
        'selection': 'NONE: no scene is filtered, replaced or tuned by oracle/baseline/gap; only the geometry rules reject attempts.',
        'deviations_from_proposal': [
            '20 slots instead of 10 (RND2-01..20)',
            'order signs drawn without replacement: no count=2 order, never two boxes for one sign',
            'wall margin 0.40 m for boxes AND robots; boxes >= 0.6 m apart; robots >= 0.6 m apart (proposal: 0.04 / 0.40)',
            'yaw = bisector of bearings to all boxes (not random) and every box within 70 deg; line of sight not blocked by the other robot',
            'A/B -> r1/r2 by a seeded stratified plan (exactly 10 swapped, 10 not) instead of an independent coin per scene',
            'continuous coordinates rounded to 0.01 m'],
        'knowledge_contract': {'knows_references': 'Order IDs only; lists are in presentation order (random per robot).',
                               'coordinates': 'Evaluator-only. Never give world coordinates, box IDs, all-box lists, oracle or baseline to the LLM.',
                               'visibility_verified': False},
        'model': m.MODEL,
        'baseline_rules': m.BASELINE_RULES,
        'missing': missing,
        'scenes': scenes,
    }


def render(doc):
    return json.dumps(doc, indent=1, ensure_ascii=False) + '\n'


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes_random_v2.json')
    d = generate()
    with open(out, 'w') as fh:
        fh.write(render(d))
    print('wrote %s: %d scenes, %d missing, seed %d' % (out, len(d['scenes']), len(d['missing']), SEED))
    print('attempts per scene: %s' % [s['gen']['attempts'] for s in d['scenes']])
