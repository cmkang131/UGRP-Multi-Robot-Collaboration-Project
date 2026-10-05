"""DEV light run summary: every 'would have stopped here' event + final failure + eval-only contact summary.

Reads only the run's own records: student_record.json (controller/guard events), result.json, and the
eval-only contacts.jsonl (scoring only; never fed back). Usage: scripts/v98_light_summary.py <run_output_dir>
(copy of outputs/v98-probe-tools/light_summary.py used for light2-8, included in PR #383 per independent review P3;
adds dev_light_repeat_limit). Writes <run_output_dir>/light_summary.json."""
import collections, glob, json, os, sys

EVENTS = {'dev_light_would_stop', 'dev_light_repeat_limit', 'pair_collision_guard_log_only', 'pair_collision_guard_veto',
          'job_failed', 'failed'}


def walk(o, out, path=''):
    if isinstance(o, dict):
        if o.get('event') in EVENTS:
            out.append((path, o))
        for k, v in o.items():
            walk(v, out, path + '/' + str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, out, path)


def main(root):
    case = sorted(d for d in glob.glob(os.path.join(root, '*')) if os.path.isdir(d))[0]
    rec = json.load(open(os.path.join(case, 'student_record.json')))
    res = json.load(open(os.path.join(case, 'result.json')))
    rows = []
    walk(rec, rows)
    seen, out = set(), []
    for path, e in rows:
        t = e.get('sim_s', e.get('t'))
        key = (e.get('event'), e.get('robot_id'), t, e.get('would_reason') or (e.get('detail') or {}).get('reason'))
        if key in seen:
            continue
        seen.add(key)
        first = None
        for w in e.get('would_veto') or []:
            fn = w.get('first_negative') or {}
            first = {'site': w.get('site'), 'wall': fn.get('wall_id'), 'clearance_mm': fn.get('clearance_mm'),
                     'sigma_xy_mm': (fn.get('margin_terms') or {}).get('sigma_xy_mm'),
                     'total_margin_mm': (fn.get('margin_terms') or {}).get('total_mm'), 'command': w.get('command')}
            break
        out.append({'t': t, 'robot': e.get('robot_id') or path.split('/')[2] if path.count('/') > 2 else e.get('robot_id'),
                    'event': e.get('event'), 'reason': e.get('would_reason') or e.get('reason')
                    or (e.get('detail') or {}).get('reason'), 'site': e.get('site'), 'occurrence': e.get('occurrence'),
                    'state': e.get('state'), 'seg': e.get('seg'), 'collision': first})
    out.sort(key=lambda r: (r['t'] is None, r['t'] or 0))
    contacts = collections.Counter()
    first_t = {}
    cpath = os.path.join(case, 'eval_only', 'contacts.jsonl')
    if os.path.exists(cpath):
        for line in open(cpath):
            row = json.loads(line)
            for c in row.get('contacts', []):
                pair = tuple(sorted((c['geom1'], c['geom2'])))
                if 'floor' in pair:
                    continue
                contacts[pair] += 1
                first_t.setdefault(pair, row['t'])
    summary = {'run': root, 'status': res.get('status'), 'failure': res.get('failure'), 'check_sim_s': res.get('check_sim_s'),
               'stage_progress': res.get('stage_progress'), 'controller_outcome': res.get('controller_outcome'),
               'would_stop': out,
               'eval_only_contacts_non_floor': [{'pair': list(p), 'samples': n, 'first_t': first_t[p]}
                                                for p, n in contacts.most_common(40)]}
    dst = os.path.join(root, 'light_summary.json')
    json.dump(summary, open(dst, 'w'), indent=1, ensure_ascii=False, default=str)
    print(dst)


if __name__ == '__main__':
    main(sys.argv[1])
