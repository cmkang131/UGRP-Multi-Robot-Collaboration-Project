"""Compare paired execution artifacts. Exit 2 means a failed or unmeasurable gate."""
import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import zip_longest
import json
import math
from pathlib import Path
import random
import sys


def read(path):
    return json.loads(path.read_bytes())


def rows(path):
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def receipt_pair(left, right, mode):
    a, b = (read(path / 'receipt.json') for path in (left, right))
    for r in (a, b):
        require(r['exit_code'] == 0 and r['mode'] == mode and r['wall_s'] > 0, 'unfinished or wrong run type')
    for field in ('inputs', 'frozen_source', 'cap_s'):
        require(a[field] == b[field], f'different paired {field}')
    return a, b


def robot_summary(case, rid):
    summary = read(case / 'run' / ('out-' + rid) / 'summary.json')
    require(summary['complete'] and summary['status'] == 'complete', f'incomplete {case}/{rid}')
    return summary


def teams(args):
    receipts = receipt_pair(args.off, args.on, 'team')
    pair = [read(path / 'run/team.json') for path in (args.off, args.on)]
    for record in pair:
        require(record['status'] == 'complete' and record['brain']['kind'] == 'fixed_plan', 'expected completed oracle process')
        require(record['scene'] == f'P2_N{args.robots:02}_S01' and len(set(record['robots'])) == args.robots,
                'incorrect scene or robot count')
        require(sorted(record['finished']) == sorted(record['robots']), 'incomplete robot reports')
    for field in ('robots', 'starts', 'scene', 'required_boxes', 'knows'):
        require(pair[0][field] == pair[1][field], 'different ' + field)
    require(pair[0].get('conditions') == pair[1].get('conditions'), 'different task conditions')
    return pair, receipts


def window(timeline, lo, hi):
    samples = list(rows(timeline))
    require(lo < hi and samples and samples[0]['sim_s'] <= lo < hi <= samples[-1]['sim_s'], 'timing window is not covered')

    def wall_at(t):
        for a, b in zip(samples, samples[1:]):
            if a['sim_s'] <= t <= b['sim_s'] and a['sim_s'] < b['sim_s']:
                frac = (t - a['sim_s']) / (b['sim_s'] - a['sim_s'])
                return a['wall_s'] + frac * (b['wall_s'] - a['wall_s']), [a['sim_s'], b['sim_s']]
        raise ValueError('missing timing endpoint')

    x, start = wall_at(lo)
    y, end = wall_at(hi)
    require(y > x, 'non-increasing wall clock')
    return {'s_per_sim_s': (y - x) / (hi - lo), 'wall_s': y - x, 'endpoint_brackets': [start, end]}


def speed(args):
    _, receipts = teams(args)
    off, on = (window(case / 'speed/timeline.jsonl', args.from_s, args.to_s) for case in (args.off, args.on))
    return {'ok': True, 'window_s': [args.from_s, args.to_s], 'off': off, 'on': on,
            'wall_saving_percent': 100 * (1 - on['wall_s'] / off['wall_s']),
            'process_wall_s': [r['wall_s'] for r in receipts]}


def payload(raw, kind):
    row = json.loads(raw)
    if kind == 'student-inputs':
        return [frame['sha256'] for frame in row['rgb']]
    cmd = row['command']
    return [cmd['wheels'], cmd['duration_s'], cmd['pwm'], row['skill'], row['done_requested'], row.get('source')]


def compare_file(a, b, kind):
    n = different = changed = 0
    counts = [0, 0]
    hashes = [hashlib.sha256(), hashlib.sha256()]
    first = None
    with a.open('rb') as left, b.open('rb') as right:
        for n, (x, y) in enumerate(zip_longest(left, right), 1):
            for i, raw in enumerate((x, y)):
                if raw is not None:
                    counts[i] += 1
                    hashes[i].update(raw)
            if x != y:
                different += 1
                if first is None:
                    first = n
                changed += int(x is None or y is None or payload(x, kind) != payload(y, kind))
    require(n > 0 and min(a.stat().st_size, b.stat().st_size) > 0, f'empty {kind} stream')
    return {'rows': n, 'byte_differences': different, 'first_different_line': first,
            'rows_off_on': counts, 'sha256_off_on': [h.hexdigest() for h in hashes],
            'payload_differences': changed, 'payload_mismatch_rate': changed / n}


def streams(args):
    pair, _ = teams(args)
    require(min(r['end_s'] for r in pair) >= args.min_s - 0.11, 'insufficient simulation time')
    result = {}
    for rid in pair[0]['robots']:
        summaries = [robot_summary(p, rid) for p in (args.off, args.on)]
        for p, summary in zip((args.off, args.on), summaries):
            require(summary['seed'] == pair[0]['seed'], f'seed mismatch {p}/{rid}')
        result[rid] = {}
        for kind in ('commands', 'student-inputs'):
            sub = Path('run', 'out-' + rid, kind + '.jsonl')
            comp = compare_file(args.off / sub, args.on / sub, kind)
            field = 'actions' if kind == 'commands' else 'valid_inputs'
            for i, s in enumerate(summaries):
                require(comp['rows_off_on'][i] == s['funnel'][field] and
                        comp['sha256_off_on'][i] == s['artifacts'][sub.name], f'truncated or altered {rid}/{sub.name}')
            result[rid][kind] = comp
    identical = all(v['byte_differences'] == 0 for robot in result.values() for v in robot.values())
    return {'ok': identical or not args.exact, 'byte_identical': identical, 'robots': result}


def decisions(case, team):
    root = case / 'run'
    markers = defaultdict(list)
    for rid in team['robots']:
        tags = robot_summary(case, rid)['robot_tags']
        require(tags['enabled'], 'tag detector disabled')
        for name, group, expected in [('signs-seen', 'signs', sum(tags['signs_seen'].values())),
                                      ('tags-seen', 'tags', tags['frames_with_a_tag'])]:
            path = root / ('out-' + rid) / (name + '.jsonl')
            if not path.exists():
                require(expected == 0, f'missing marker log {path}')
                continue
            observed = 0
            for row in rows(path):
                observed += len(row[group]) if group == 'signs' else 1
                bucket = markers[rid, round(10 * row['t'])]
                for tag in row[group]:
                    bucket.append(('sign', tag['sign']) if group == 'signs' else ('robot', tag['robot'], tag['side_seen']))
            require(observed == expected, f'incomplete marker log {path}')
    counts = Counter()
    result = {}
    trace = list(rows(root / 'decision-inputs.jsonl'))
    log = team['brain']['decisions']
    require(trace and len(trace) == len(log), 'empty or incomplete decision trace')
    for row, issued in zip(trace, log):
        rid, point = row['rid'], row['point']
        require((rid, point, row['t']) == (issued['rid'], issued['point'], issued['t']), 'decision trace order mismatch')
        idx = counts[rid, point]
        counts[rid, point] += 1
        result[rid, point, idx] = {'options': row['options'], 'boxes': row['boxes'],
                                   'markers': sorted(markers[rid, round(10 * row['t'])])}
    return result


def compare_decisions(a, b):
    keys = sorted(a.keys() | b.keys())
    require(keys, 'no decision points')
    bad = [k for k in keys if a.get(k) != b.get(k)]
    k = bad[0] if bad else None
    return {'points': len(keys), 'mismatches': len(bad), 'rate': len(bad) / len(keys),
            'first': {'key': k, 'off': a.get(k), 'on': b.get(k)} if k else None, 'ok': len(bad) / len(keys) <= .01}


def quantile(values, frac):
    v = sorted(values)
    t = frac * (len(v) - 1)
    return v[int(t)] + (v[math.ceil(t)] - v[int(t)]) * (t - int(t))


def compare_durations(a, b):
    result = {}
    for phase in ('move', 'door', 'grasp', 'place'):
        left = {r: v[phase] for r, v in a.items() if v[phase] is not None}
        right = {r: v[phase] for r, v in b.items() if v[phase] is not None}
        ok = bool(left) and left.keys() == right.keys()
        stats = {}
        if left and right:
            for label, q, limit in [('median', .5, .05), ('p90', .9, .10)]:
                x, y = quantile(left.values(), q), quantile(right.values(), q)
                stats[label] = {'off_s': x, 'on_s': y, 'delta_s': y - x}
                ok &= abs(y - x) <= max(.1, limit * x) + 1e-8
        result[phase] = {'off_s': left, 'on_s': right, **stats, 'ok': ok}
    return result


def team_metrics(case, team):
    times, completion = {}, {}
    start = {}
    for q in team['brain']['decisions']:
        if q['point'] == 'pick' and q['option'].startswith('box:'):
            start.setdefault(q['rid'], q['t'])
    for rid in team['robots']:
        s = robot_summary(case, rid)
        require(s['termination'] == 'student_done', 'censored full episode: ' + rid)
        first = act = go = None
        count = Counter()
        for row in rows(case / 'run' / ('out-' + rid) / 'commands.jsonl'):
            t = row['command']['t']
            if first is None:
                first = t
            source = row['source']
            count[source] += 1
            if source == 'act' and act is None:
                act = t - first
            if source == 'carry_code' and go is None:
                go = t - first
        through = team['events'][rid].get('door_passed')
        require(through is None or (go is not None and through >= go - 1e-7), 'missing or reversed door clock')
        require(act is None or (rid in start and act >= start[rid] - 1e-7), 'missing or reversed approach clock')
        times[rid] = {'move': max(0., act - start[rid]) if act is not None and rid in start else None,
                      'door': through - go if through is not None and go is not None else None,
                      'grasp': .1 * count['act'] if count['act'] else None,
                      'place': .1 * count['release_code'] if count['release_code'] else None}
        completion[rid] = [s['lift_success'], 'grasp' in s['done_times'], 'release' in s['done_times'],
                           team['events'][rid].get('carry_finished', {}).get('outcome')]
    layout = robot_summary(case, team['robots'][0])['layout']
    audit = team['delivery_audit']
    require(audit['samples'] > 0 and abs(audit['last_s'] - team['end_s']) < .11 and
            set(audit['scoring_keys']) == {b['id'] for b in layout}, 'incomplete physical delivery audit')
    settled = audit['settled']
    groups = defaultdict(list)
    for key, delivery in settled.items():
        groups[delivery['at_s']].append(key)
    zones = {key: (b['zone'], b['correct'], b['wrong_place']) for key, b in team['boxes'].items()}
    for box in layout:
        key = audit['scoring_keys'][box['id']]
        zone, correct, _ = zones[key]
        if correct:
            require(settled.get(box['id'], {}).get('zone') == zone, 'unconfirmed final delivery: ' + box['id'])
    brain = team['brain']
    def delivery_for(rid):
        key = brain['targets'][rid]['box']
        delivery = settled.get(key)
        correct_zone = brain['assignment'][rid][1]
        if delivery and delivery['zone'] == correct_zone and zones[audit['scoring_keys'][key]][1]:
            return delivery['at_s']
        return None

    precedence = {}
    for later, earlier in brain.get('after', {}).items():
        for prior in earlier:
            x, y = delivery_for(prior), delivery_for(later)
            precedence[prior + '<' + later] = x < y if x is not None and y is not None else None
    outcomes = {'boxes': zones, 'orders': team['orders'], 'correct': team['correct_boxes'],
                'wrong_place': team['wrong_place_boxes'], 'settled_zones': {k: v['zone'] for k, v in settled.items()},
                'delivery_order': [sorted(groups[t]) for t in sorted(groups)], 'precedence': precedence,
                'task_success': team['correct_boxes'] == team['required_boxes'] and all(v is True for v in precedence.values()),
                'completion': completion}
    return times, outcomes


def compare_team(args):
    pair, receipts = teams(args)
    paths = (args.off, args.on)
    obs = compare_decisions(*(decisions(p, t) for p, t in zip(paths, pair)))
    if args.mode == 'decisions':
        return obs
    (a, oa), (b, ob) = [team_metrics(p, t) for p, t in zip(paths, pair)]
    times = compare_durations(a, b)
    ends = [t['end_s'] for t in pair]
    cost = [{'wall_s': r['wall_s'], 'sim_s': end, 's_per_sim_s': r['wall_s'] / end} for end, r in zip(ends, receipts)]
    return {'ok': oa == ob and all(v['ok'] for v in times.values()) and obs['ok'] and abs(ends[1] - ends[0]) <= 3. + 1e-8,
            'end_delta_s': ends[1] - ends[0], 'decisions': obs, 'phase_times': times,
            'outcomes_equal': oa == ob, 'off': oa, 'on': ob, 'whole_process': cost}


def poses(args):
    base = read(args.plan)
    rid = base['robot_id']
    x, y, z, yaw = base['spawns'][rid]
    target = base['target_setup_xy']
    require(.6 <= math.dist((x, y), target) <= 1.1, 'expected a registered teacher-start plan')
    require(args.n > 0, 'positive pose count required')
    rng = random.Random(20261118)
    manifest = {}
    args.directory.mkdir(parents=True, exist_ok=False)
    for i in range(args.n):
        while True:
            spawn = [x + rng.uniform(-.025, .025), y + rng.uniform(-.025, .025), z, yaw + rng.uniform(-.07, .07)]
            distance = math.dist(spawn[:2], target)
            if .6 <= distance <= 1.1:
                break
        plan = dict(base, spawns={**base['spawns'], rid: spawn}, start_to_cargo_m=distance, skill='grasp_release',
                    approach_code_v1=False)
        path = args.directory / f'{i:03}.json'
        path.write_text(json.dumps(plan, indent=2, allow_nan=False) + '\n')
        manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (args.directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return {'ok': True, 'poses': args.n, 'seed': 20261118, 'item': base['item_id']}


def upper_probability(k, n):
    """One side of a 97.5% Clopper-Pearson interval (one tail 0.0125)."""
    if k == n:
        return 1.
    if k == 0:
        return -math.expm1(math.log(.0125) / n)
    coeff = [math.lgamma(n + 1) - math.lgamma(j + 1) - math.lgamma(n - j + 1) for j in range(k + 1)]
    lo, hi = 0., 1.
    for _ in range(55):
        p = (lo + hi) / 2
        cdf = math.fsum(math.exp(c + j * math.log(p) + (n - j) * math.log1p(-p)) for j, c in enumerate(coeff))
        if cdf > .0125:
            lo = p
        else:
            hi = p
    return hi


def paired_rate(pairs):
    n = len(pairs)
    gain, loss = pairs.count((False, True)), pairs.count((True, False))
    low = 1 - upper_probability(n - gain, n) - upper_probability(loss, n)
    high = upper_probability(gain, n) - (1 - upper_probability(n - loss, n))
    return {'n': n, 'off_rate': sum(x for x, _ in pairs) / n, 'on_rate': sum(y for _, y in pairs) / n,
            'gains': gain, 'losses': loss, 'delta_pp': 100 * (gain - loss) / n,
            'ci95_pp': [100 * low, 100 * high], 'ok': -.02 <= low <= 0 <= high <= .02}


def pose_gap(a, b):
    keys = {'base', 'box', 'finger0', 'finger1'}
    require(a['item'] == b['item'] and set(a['poses']) == set(b['poses']) == keys, 'unmatched ACT starting object or poses')
    dist = angle = 0.
    for key in keys:
        (xyz, mat), (other, rot) = a['poses'][key], b['poses'][key]
        require(len(xyz) == len(other) == 3 and len(mat) == len(rot) == 9 and
                all(math.isfinite(v) for v in (*xyz, *other, *mat, *rot)), 'invalid ACT pose')
        dist = max(dist, math.dist(xyz, other))
        trace = sum(x * y for x, y in zip(mat, rot))
        angle = max(angle, math.degrees(math.acos(max(-1., min(1., (trace - 1) / 2)))))
    return dist, angle


def grasp_result(case, plan):
    run = case / 'run'
    s = read(run / 'summary.json')
    require(s['status'] == 'complete' and s['complete'] and s['student_execution'] and not s['teacher_assisted']
            and s['inference_latency_s']['n'] > 0 and s['weld'] == 'off', 'missing physical ACT attempt: ' + str(case))
    require(read(run / 'plan.json') == plan and s['act_start']['item'] == plan['item_id'], 'incorrect staged plan')
    lift_t = s['first_pass_sim_t'].get('lift_confirmation')
    require(s['lift_success'] == (lift_t is not None), 'inconsistent lift evidence')
    drop = False
    saw_act = releasing = False
    for cmd, ev in zip(rows(run / 'commands.jsonl'), rows(run / 'eval-only.jsonl'), strict=True):
        require(cmd['command']['t'] == ev['t'] and not ev['weld'], 'unmatched physical data')
        saw_act |= cmd['source'] == 'act'
        releasing |= cmd['source'] == 'release_code'
        if lift_t is not None and ev['t'] > lift_t and not releasing and max(ev['forces']) < .1:
            if ev['clearance'] > .012 or ev['clearance'] <= .006:
                drop = True
    require(saw_act, 'no ACT commands')
    require(lift_t is None or releasing or drop, 'lift with censored transport or release: ' + str(case))
    return s['act_start'], {'grasp': 'grasp' in s['first_pass_sim_t'], 'lift': s['lift_success'], 'drop': drop}


def compare_grasps(args):
    manifest = read(args.plans / 'manifest.json')
    require(len(manifest) >= args.n > 0, 'missing prespecified cases')
    metrics = defaultdict(list)
    unique = set()
    gaps = []
    cohort = None
    for i in range(args.n):
        path = args.plans / f'{i:03}.json'
        plan = read(path)
        left, right = args.off / path.stem, args.on / path.stem
        a, b = receipt_pair(left, right, 'grasp')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == a['inputs']['plan'] == manifest[path.name], 'plan digest mismatch')
        sample = (a['frozen_source'], a['cap_s'], {k: v for k, v in a['inputs'].items() if k != 'plan'},
                  [(r['source'], r['switches'], r['env']) for r in (a, b)], plan['item_id'], plan['seed'], plan['robot_id'])
        if cohort is None:
            cohort = sample
        require(cohort == sample, 'cohort uses different boxes, models, or conditions')
        unique.add((plan['item_id'], *plan['spawns'][plan['robot_id']]))
        (p, x), (q, y) = [grasp_result(case, plan) for case in (left, right)]
        gaps.append(pose_gap(p, q))
        for key in x:
            metrics[key].append((x[key], y[key]))
    require(len(unique) == args.n, 'duplicate starting poses')
    rates = {k: paired_rate(v) for k, v in metrics.items()}
    after_lift = {}
    for i, name in enumerate(('off', 'on')):
        lifted = sum(pair[i] for pair in metrics['lift'])
        dropped = sum(pair[i] for pair in metrics['drop'])
        after_lift[name] = {'lifts': lifted, 'drops': dropped, 'drop_rate': dropped / lifted if lifted else None}
    pos, deg = map(max, zip(*gaps))
    return {'ok': args.n >= 256 and pos <= .002 and deg <= 1 and rates['lift']['off_rate'] > 0
            and all(r['ok'] for r in rates.values()), 'pairs': args.n, 'rates': rates,
            'max_start_translation_m': pos, 'max_start_rotation_deg': deg, 'drop_after_lift': after_lift}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='mode', required=True)
    for name in ('speed', 'streams', 'decisions', 'team', 'grasp'):
        sub = commands.add_parser(name)
        sub.add_argument('off', type=Path)
        sub.add_argument('on', type=Path)
        if name == 'grasp':
            sub.add_argument('--plans', type=Path, required=True)
            sub.add_argument('--n', type=int, default=256)
        else:
            sub.add_argument('--robots', type=int, required=True, choices=(3, 9))
        if name == 'streams':
            sub.add_argument('--min-s', type=float, default=25.)
            sub.add_argument('--exact', action='store_true', help='fail if either stream differs by even one byte')
        if name == 'speed':
            sub.add_argument('--from-s', type=float, default=7.3)
            sub.add_argument('--to-s', type=float, default=25.1)
    sub = commands.add_parser('poses')
    sub.add_argument('plan', type=Path)
    sub.add_argument('directory', type=Path)
    sub.add_argument('--n', type=int, default=256)
    args = p.parse_args(argv)
    try:
        handler = {'poses': poses, 'streams': streams, 'decisions': compare_team, 'team': compare_team,
                   'grasp': compare_grasps, 'speed': speed}[args.mode]
        result = handler(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'ok': False, 'error': str(exc)}
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
