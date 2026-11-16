#!/usr/bin/env python3
"""Validate scenes_designed_v2.json and scenes_random_v2.json (standard library only; no simulation, no LLM).

Usage: python3 check_v2.py [scenes_designed_v2.json [scenes_random_v2.json]]      exit 0 only if every check passes.

Geometry, IDs, one-carry, same-sign, type structure and balance are checked with code written here; oracle plan, baseline and
estimate are recomputed from the raw fields with model_v2 (whose time model is first proven against the DESIGN-18 numbers of
X01 / D01 / C01 / L01). Random scenes: the gap and balance are printed but never enforced; the file must equal a fresh run of
gen_random.py (seed recorded, deterministic).  Every error line starts with a [tag] so mutation tests can grep it.
"""
import itertools
import json
import math
import os
import re
import sys
from collections import Counter

import model_v2 as m

HERE = os.path.dirname(os.path.abspath(__file__))
DEV_EXPOSED = {'X01', 'L01', 'C01', 'D01', 'X02'}
DESIGNED_COUNTS = {'L': 12, 'C': 12, 'X': 3, 'D': 3}
RANDOM_N, RANDOM_SEED = 20, 2026111501
KEYS = ('id', 'type', 'type_code', 'control', 'boxes', 'robots', 'orders', 'knows', 'constraints', 'oracle_plan', 'baseline_plan',
        'estimate', 'balance')
# literals, deliberately not imported from model_v2
WALL_X, WALL_Y = (-1.05 + 0.40, 2.2 - 0.40), (-3.15 + 0.40, 1.45 - 0.40)
BOX_GAP, ROBOT_GAP, NEAR = 0.6, 0.6, (0.6, 1.1)
FOV_RAD, LOS = math.radians(70.0), 0.25
EPS = 1e-6


def d2(a, b):
    return math.hypot(a['x'] - b['x'], a['y'] - b['y'])


def angdiff(a, b):
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def geo(s):
    e = []
    for kind, items in (('box', s['boxes']), ('robot', s['robots'])):
        for it in items:
            if not (WALL_X[0] - EPS <= it['x'] <= WALL_X[1] + EPS and WALL_Y[0] - EPS <= it['y'] <= WALL_Y[1] + EPS):
                e.append('[wall] %s %s (%.2f,%.2f) closer than 0.40 m to a wall' % (kind, it.get('id', it.get('rid')), it['x'], it['y']))
    for a, b in itertools.combinations(s['boxes'], 2):
        if d2(a, b) < BOX_GAP - EPS:
            e.append('[boxgap] boxes %s,%s %.2f m apart' % (a['id'], b['id'], d2(a, b)))
    for a, b in itertools.combinations(s['robots'], 2):
        if d2(a, b) < ROBOT_GAP - EPS:
            e.append('[robotgap] robots %.2f m apart' % d2(a, b))
    for r in s['robots']:
        near = min(d2(r, b) for b in s['boxes'])
        if not (NEAR[0] - EPS <= near <= NEAR[1] + EPS):
            e.append('[near] %s nearest box %.2f m (need 0.6..1.1)' % (r['rid'], near))
        for b in s['boxes']:
            dev = angdiff(math.atan2(b['y'] - r['y'], b['x'] - r['x']), r['yaw'])
            if dev > FOV_RAD + 1e-9:
                e.append('[yaw] %s: box %s is %.1f deg off the heading (limit 70)' % (r['rid'], b['id'], math.degrees(dev)))
            for q in s['robots']:
                if q is not r:
                    vx, vy = b['x'] - r['x'], b['y'] - r['y']
                    t = max(0.0, min(1.0, ((q['x'] - r['x']) * vx + (q['y'] - r['y']) * vy) / (vx * vx + vy * vy)))
                    if math.hypot(q['x'] - r['x'] - t * vx, q['y'] - r['y'] - t * vy) < LOS:
                        e.append('[los] %s blocks the view of %s to box %s' % (q['rid'], r['rid'], b['id']))
    return e


def check_scene(s, kind):
    e = []
    sid = s.get('id', '?')
    miss = [k for k in KEYS if k not in s]
    if miss:
        return ['[format] %s missing keys %s' % (sid, miss)]
    # ids
    pat = r'^(L2|C2|X2|D2)-\d\d$' if kind == 'designed' else r'^RND2-\d\d$'
    if not re.match(pat, sid) or re.match(r'^[XLCDK]\d?\d\d$', sid):
        e.append('[id] %s does not match %s' % (sid, pat))
    if sid in DEV_EXPOSED:
        e.append('[id] %s collides with a dev-exposed scene' % sid)
    if kind == 'designed' and sid[:1] != s['type_code']:
        e.append('[id] %s does not match type_code %s' % (sid, s['type_code']))
    # structure
    if sorted(r['rid'] for r in s['robots']) != ['r1', 'r2']:
        e.append('[robots] robots must be exactly r1,r2')
    if len({b['id'] for b in s['boxes']}) != len(s['boxes']) or len({o['id'] for o in s['orders']}) != len(s['orders']):
        e.append('[ids] duplicate box or order id')
    if any(b['colour'] not in ('red', 'blue') for b in s['boxes']) or any(o['colour'] not in ('red', 'blue') for o in s['orders']):
        e.append('[colour] colour must be red or blue')
    nb = len(s['boxes'])
    want_nb = {'L': 2, 'C': 2, 'X': 2, 'D': 3}.get(s['type_code']) if kind == 'designed' else None
    if (want_nb is not None and nb != want_nb) or nb not in (2, 3):
        e.append('[boxes] %d boxes' % nb)
    e += geo(s)
    # orders
    signs = [o['sign'] for o in s['orders']]
    if any(o['count'] != 1 for o in s['orders']):
        e.append('[count] every order must have count 1')
    if any(sg not in (11, 12, 13) for sg in signs):
        e.append('[sign] sign not in 11/12/13')
    if len(set(signs)) != len(signs):
        e.append('[dupsign] two orders share a sign')
    if sum(o['count'] for o in s['orders']) > 2 or not s['orders']:
        e.append('[demand] demand must be 1..2 (one carry per robot)')
    for o in s['orders']:
        if sum(b['colour'] == o['colour'] for b in s['boxes']) < sum(x['colour'] == o['colour'] for x in s['orders']):
            e.append('[supply] not enough %s boxes for the orders' % o['colour'])
        if not any(o['id'] in v for v in s['knows'].values()):
            e.append('[knows] order %s is known by nobody' % o['id'])
    for rid, lst in s['knows'].items():
        if len(set(lst)) != len(lst) or any(x not in {o['id'] for o in s['orders']} for x in lst):
            e.append('[knows] %s list invalid' % rid)
        if kind == 'designed' and lst != sorted(lst, key=m.oid_key):
            e.append('[knows] %s list not in ID order' % rid)
    # plans: one carry per robot, colours, distinct boxes/orders/signs in the oracle plan
    boxes = {b['id']: b for b in s['boxes']}
    orders = {o['id']: o for o in s['orders']}
    for pname in ('oracle_plan', 'baseline_plan'):
        plan = s[pname]
        if set(plan) != {'r1', 'r2'}:
            e.append('[plan] %s keys' % pname)
            continue
        for rid, items in plan.items():
            if len(items) > 1:
                e.append('[onecarry] %s %s carries %d boxes' % (pname, rid, len(items)))
            for it in items:
                if len(it) != 2 or it[0] not in boxes or it[1] not in orders:
                    e.append('[plan] %s %s item %s invalid' % (pname, rid, it))
                elif boxes[it[0]]['colour'] != orders[it[1]]['colour']:
                    e.append('[plan] %s %s colour mismatch' % (pname, rid))
    op = [it for items in s['oracle_plan'].values() for it in items if len(it) == 2 and it[0] in boxes and it[1] in orders]
    if len({it[0] for it in op}) != len(op):
        e.append('[plan] oracle plan uses a box twice')
    if len({orders[it[1]]['sign'] for it in op}) != len(op):
        e.append('[dupsign] oracle plan puts two boxes on one sign')
    if len({it[1] for it in op}) != len(op):
        e.append('[dupsign] oracle plan serves one order twice')
    if len(op) != len(s['orders']):
        e.append('[plan] oracle plan serves %d of %d orders' % (len(op), len(s['orders'])))
    if e and any(t.startswith(('[plan]', '[ids]', '[knows]', '[format]', '[colour]')) for t in e):
        return e                                     # recomputation needs valid references
    # recomputation
    orc = m.oracle_search(s)
    if s['oracle_plan'] != orc['plan']:
        e.append('[oracle] stored oracle_plan %s != recomputed %s' % (s['oracle_plan'], orc['plan']))
    est = m.estimate(s, orc)
    for k, v in est.items():
        sv = s['estimate'].get(k, 'MISSING')
        if (v is None) != (sv is None) or (v is not None and (sv == 'MISSING' or abs(sv - v) > 2e-3)):
            e.append('[estimate] %s stored %s recomputed %s' % (k, sv, v))
    if s['baseline_plan'] != m.baseline_eval(s, 'first')['plan']:
        e.append('[baseline] stored baseline_plan differs from the first-listed rule B')
    if s['balance'] != m.balance(s):
        e.append('[balance] stored balance %s != recomputed %s' % (s['balance'], m.balance(s)))
    # type structure and gap filter
    t = s['type_code']
    sizes = sorted((len(v) for v in s['knows'].values()), reverse=True)
    gmin = min(est['gap'], est['gap_guess'])
    if kind == 'designed':
        far = max(d2(r, b) for r in s['robots'] for b in s['boxes'])
        dev = max(math.degrees(angdiff(math.atan2(b['y'] - r['y'], b['x'] - r['x']), r['yaw'])) for r in s['robots'] for b in s['boxes'])
        if dev > 65.0 + 1e-6:
            e.append('[dev65] %s heading deviation %.1f deg exceeds the designed margin 65 deg' % (sid, dev))
        if far > 2.6 + 1e-9:
            e.append('[far] %s a robot-box distance of %.2f m exceeds the designed cap 2.6 m (legacy max 2.53)' % (sid, far))
        if t in ('L', 'C') and (s['control'] or gmin < m.GAP_MIN - EPS):
            e.append('[gap] %s oracle - baseline %.3f (primary %.3f, guess %.3f) < 0.5 or marked control' % (sid, gmin, est['gap'], est['gap_guess']))
        if t in ('X', 'D') and not s['control']:
            e.append('[control] %s must be marked control' % sid)
        if t in ('X', 'D') and abs(est['gap']) > EPS:
            e.append('[control] %s control has unequal correct counts' % sid)
        if t == 'L':
            if sizes != [2, 0] or len({o['colour'] for o in s['orders']}) != 2 or len(s['orders']) != 2:
                e.append('[type] L needs knows sizes {2,0}, two orders of different colours')
        elif t == 'C':
            h = [r for r, v in s['knows'].items() if len(v) == 2]
            if sizes != [2, 1] or len({o['colour'] for o in s['orders']}) != 1 or not h or \
                    not set(s['knows'][[r for r in s['knows'] if r not in h][0]]) <= set(s['knows'][h[0]]) or len({b['colour'] for b in s['boxes']}) != 1:
                e.append('[type] C needs holder of 2 orders, partner knows 1 of them, one colour for boxes and orders')
        elif t == 'X':
            if sizes != [1, 1] or len({v[0] for v in s['knows'].values()}) != 2:
                e.append('[type] X needs each robot to know a different single order')
            for r in s['robots']:
                nb_ = min(s['boxes'], key=lambda b: d2(r, b))
                if nb_['colour'] == orders[s['knows'][r['rid']][0]]['colour']:
                    e.append('[type] X: %s knows the order of its own nearest box (not crossed)' % r['rid'])
        elif t == 'D':
            if nb != 3 or len(s['orders']) != 1 or sizes != [1, 0] or sum(b['colour'] != s['orders'][0]['colour'] for b in s['boxes']) != 2:
                e.append('[type] D needs 3 boxes (1 ordered colour, 2 decoys), 1 order, known by one robot')
            if est['baseline_guess_errors'] < 1 - 1e-3 or s['estimate']['oracle_errors'] != 0:
                e.append('[type] D: guess baseline must move a decoy (>=1 expected error), oracle none')
        else:
            e.append('[type] unknown type_code %s' % t)
    else:
        if t != 'RND' or s['type'] != 'random':
            e.append('[type] random scene must have type random / code RND')
    return e


def bal(s):
    """Balance attributes recomputed from the raw fields (the stored copy is compared separately)."""
    try:
        return m.balance(s)
    except Exception:
        return s['balance']


def order_colour(s):
    dr = bal(s)['decision_robot']
    if dr and s['oracle_plan'][dr]:
        oid = s['oracle_plan'][dr][0][1]
        return next(o['colour'] for o in s['orders'] if o['id'] == oid)
    return s['orders'][0]['colour']


def balance_table(scenes, label):
    rows = [(label, 'n', 'holder r1/r2/both/none', 'correct=first listed T/F/-', 'correct sign 11/12/13', 'colour red/blue*', 'gap min..max')]
    codes = []
    for s in scenes:
        if s['type_code'] not in codes:
            codes.append(s['type_code'])
    for c in codes:
        ss = [s for s in scenes if s['type_code'] == c]
        hc = Counter(bal(s)['holder'] for s in ss)
        fc = Counter(bal(s)['correct_is_first_order'] for s in ss)
        sc = Counter(bal(s)['correct_sign'] for s in ss)
        cc = Counter(order_colour(s) for s in ss)
        gaps = [min(s['estimate']['gap'], s['estimate']['gap_guess']) for s in ss]
        rows.append((c, str(len(ss)), '%d/%d/%d/%d' % (hc['r1'], hc['r2'], hc['both'], hc['none']),
                     '%d/%d/%d' % (fc[True], fc[False], fc[None]), '%d/%d/%d' % (sc[11], sc[12], sc[13]),
                     '%d/%d' % (cc['red'], cc['blue']), '%.2f..%.2f' % (min(gaps), max(gaps))))
    return rows


def designed_balance_errors(scenes):
    e = []
    for c in ('L', 'C'):
        ss = [s for s in scenes if s['type_code'] == c]
        if len(ss) != 12:
            continue
        hold = Counter(bal(s)['holder'] for s in ss)
        first = Counter(bal(s)['correct_is_first_order'] for s in ss)
        cells = Counter((bal(s)['holder'], bal(s)['correct_is_first_order']) for s in ss)
        sign = Counter(bal(s)['correct_sign'] for s in ss)
        if hold['r1'] != 6 or hold['r2'] != 6:
            e.append('[balance] %s holder r1/r2 = %d/%d (need 6/6)' % (c, hold['r1'], hold['r2']))
        if first[True] != 6 or first[False] != 6:
            e.append('[balance] %s correct is first-listed in %d, second in %d (need 6/6)' % (c, first[True], first[False]))
        if any(cells[(h, f)] != 3 for h in ('r1', 'r2') for f in (True, False)):
            e.append('[balance] %s holder x first-listed cells %s (need 3 each)' % (c, dict(cells)))
        low = sum(1 for s in ss if bal(s)['correct_is_lower_known_sign'])
        if low != 6:
            e.append('[balance] %s correct sign is the lower of the holder\'s two signs in %d (need 6/12)' % (c, low))
        per_h = Counter(bal(s)['holder'] for s in ss if bal(s)['correct_sign'] == 11)
        per_f = Counter(bal(s)['correct_is_first_order'] for s in ss if bal(s)['correct_sign'] == 11)
        if per_h['r1'] != 3 or per_h['r2'] != 3 or per_f[True] != 3 or per_f[False] != 3:
            e.append('[balance] %s sign-11-correct per holder %s / per first-listed %s (need 3/3 each)' % (c, dict(per_h), dict(per_f)))
        if sign[11] != 6 or sign[12] != 3 or sign[13] != 3:
            e.append('[balance] %s correct sign 11/12/13 = %d/%d/%d (need 6/3/3: half NOT first menu option)' % (c, sign[11], sign[12], sign[13]))
        other = Counter(next((o['sign'] for o in s['orders'] if o['sign'] != bal(s)['correct_sign']), None) for s in ss)
        if sorted(other.get(k, 0) for k in (11, 12, 13)) != [4, 4, 4]:
            e.append('[balance] %s other-order sign counts %s not 4/4/4' % (c, dict(other)))
    d = [s for s in scenes if s['type_code'] == 'D']
    if len(d) == 3 and len({bal(s)['holder'] for s in d}) < 2:
        e.append('[balance] D: holder is the same robot in all 3 scenes')
    x = [s for s in scenes if s['type_code'] == 'X']
    if len(x) == 3 and len({s['orders'][0]['colour'] for s in x}) < 2:
        e.append('[balance] X: first order has the same colour in all 3 scenes')
    return e


def model_sanity():
    """DESIGN-18 numbers (scenes18b calculated_completion_by_scene_s) reproduced by model_v2."""
    pi = math.pi

    def sc(boxes, robots, orders, knows):
        return {'boxes': [dict(id=i, colour=c, x=x, y=y) for i, c, x, y in boxes],
                'robots': [dict(rid=r, x=x, y=y, yaw=pi) for r, x, y in robots],
                'orders': [dict(id=i, colour=c, count=1, sign=sg) for i, c, sg in orders], 'knows': knows}
    cases = [
        ('X01', sc([('a', 'red', .2, .4), ('b', 'blue', .2, -1.6)], [('r1', 1, .4), ('r2', 1, -1.6)], [('o1', 'red', 11), ('o2', 'blue', 12)],
                   {'r1': ['o2'], 'r2': ['o1']}), 198.0, 296.1698),
        ('D01', sc([('a', 'blue', .2, -2.4), ('b', 'blue', .2, .4), ('c', 'red', 1.4, -.4)], [('r1', 1, -2.4), ('r2', 1, .4)], [('o1', 'red', 12)],
                   {'r1': ['o1'], 'r2': []}), 196.8460, 279.8716),
        ('C01', sc([('a', 'blue', .2, .4), ('b', 'blue', .2, -1.6)], [('r1', 1, .4), ('r2', 1, -1.6)], [('o1', 'blue', 11), ('o2', 'blue', 12)],
                   {'r1': ['o1', 'o2'], 'r2': ['o1']}), 198.0, None),
        ('L01', sc([('a', 'red', .2, .4), ('b', 'blue', .2, -1.6)], [('r1', 1, .4), ('r2', 1, -1.6)], [('o1', 'red', 11), ('o2', 'blue', 12)],
                   {'r1': ['o1', 'o2'], 'r2': []}), 198.0, None)]
    e, lines = [], []
    for name, s, orc_ref, base_ref in cases:
        o = m.oracle_search(s)
        b = m.baseline_eval(s, 'first')
        ok = abs(o['completion'] - orc_ref) < 0.01 and (base_ref is None or abs(b['completion'] - base_ref) < 0.01)
        lines.append('  %s oracle %.3f (DESIGN-18 %.3f) baseline %s (DESIGN-18 %s) %s' % (
            name, o['completion'], orc_ref, '%.3f' % b['completion'] if b['completion'] else 'unmet', base_ref, 'ok' if ok else 'MISMATCH'))
        if not ok:
            e.append('[model] %s does not reproduce DESIGN-18' % name)
    return e, lines


def main(argv):
    dpath = argv[1] if len(argv) > 1 else os.path.join(HERE, 'scenes_designed_v2.json')
    rpath = argv[2] if len(argv) > 2 else os.path.join(HERE, 'scenes_random_v2.json')
    errors = []
    print('model sanity (DESIGN-18 time model):')
    me, lines = model_sanity()
    errors += me
    print('\n'.join(lines))
    docs = {}
    for kind, path in (('designed', dpath), ('random', rpath)):
        try:
            with open(path) as fh:
                docs[kind] = json.load(fh)
        except (OSError, ValueError) as ex:
            print('[file] cannot read %s: %s\nFAILED' % (path, ex))
            return 1
        print('\n%s: %s  (%d scenes)' % (kind, path, len(docs[kind]['scenes'])))
    ds, rs = docs['designed']['scenes'], docs['random']['scenes']
    # counts
    cnt = Counter(s.get('type_code') for s in ds)
    for c, n in DESIGNED_COUNTS.items():
        if cnt[c] != n:
            errors.append('[count] designed %s has %d scenes, need %d' % (c, cnt[c], n))
    if len(ds) != sum(DESIGNED_COUNTS.values()):
        errors.append('[count] designed file has %d scenes' % len(ds))
    if len(rs) != RANDOM_N:
        errors.append('[count] random file has %d scenes, need %d' % (len(rs), RANDOM_N))
    ids = [s.get('id') for s in ds + rs]
    if len(set(ids)) != len(ids):
        errors.append('[id] duplicate scene ids across files: %s' % [k for k, v in Counter(ids).items() if v > 1])
    for kind, ss in (('designed', ds), ('random', rs)):
        for s in ss:
            try:
                errors += ['%s: %s' % (s.get('id', '?'), x) for x in check_scene(s, kind)]
            except Exception as ex:                      # a malformed scene must fail the check, never crash it
                errors.append('%s: [crash] %s: %s' % (s.get('id', '?'), type(ex).__name__, ex))
    try:
        errors += designed_balance_errors(ds)
    except Exception as ex:
        errors.append('[crash] balance check %s: %s' % (type(ex).__name__, ex))
    # random: seed, determinism, no filtering
    r = docs['random']
    if r.get('seed') != RANDOM_SEED or r.get('missing'):
        errors.append('[random] seed %s / missing %s' % (r.get('seed'), r.get('missing')))
    if not r.get('missing') and rs:
        sw = sum(1 for s in rs if s['gen']['swapped_AB'])
        if sw != RANDOM_N // 2:
            errors.append('[random] swapped A/B in %d of %d scenes (stratified plan needs %d)' % (sw, len(rs), RANDOM_N // 2))
    import gen_random
    fresh = gen_random.render(gen_random.generate())
    with open(rpath) as fh:
        if fh.read() != fresh:
            errors.append('[random] file differs from a fresh run of gen_random.py (seed %d)' % gen_random.SEED)
    # tables
    print('\nper-type balance (designed; L/C enforced, X/D printed):')
    try:
        for row in balance_table(ds, 'type'):
            print('  %-5s %-3s %-24s %-26s %-22s %-17s %s' % row)
    except Exception as ex:
        errors.append('[crash] balance table %s: %s' % (type(ex).__name__, ex))
    print('  (*) colour = colour of the deciding robot oracle order (L, C, random with a 2-order holder), else of o1')
    print('\nrandom scenes (printed, not enforced):')
    try:
        for row in balance_table(rs, 'type'):
            print('  %-5s %-3s %-24s %-26s %-22s %-17s %s' % row)
        shape = Counter((s['gen']['n_boxes'], s['gen']['total_demand']) for s in rs)
        gaps = Counter(min(s['estimate']['gap'], s['estimate']['gap_guess']) for s in rs)
        print('  (boxes,demand) counts %s; swapped A/B %d/%d; min(gap, gap_guess) values %s' % (
            dict(sorted(shape.items())), sum(s['gen']['swapped_AB'] for s in rs), len(rs), dict(sorted(gaps.items()))))
        print('  holder-scenes by decision robot: %s' % dict(Counter(bal(s)['decision_robot'] for s in rs)))
    except Exception as ex:
        errors.append('[crash] random table %s: %s' % (type(ex).__name__, ex))
    print('\nid check: no scene id in %s; designed/random ids unique: %s' % (sorted(DEV_EXPOSED), len(set(ids)) == len(ids)))
    if errors:
        print('\nFAILED (%d):' % len(errors))
        for x in errors:
            print('  ' + x)
        return 1
    print('\nALL PASS: designed %s, random %d' % (dict(cnt), len(rs)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
