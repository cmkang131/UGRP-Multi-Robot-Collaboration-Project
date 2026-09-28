"""Root-cause tally for the align stage probes (eval-only analysis of raw results; no physics).

usage: python analyze_align_failures.py <probe output dir>   (produced align_failure_analysis.txt for grid1)
"""
import collections, json, re, statistics, sys
from harness import pair_stage_probe as sp

O = sys.argv[1]
rows = [json.loads(l) for l in open(O + '/cases.jsonl')]
stats = collections.Counter(); rej_std = []; relook_idx = collections.Counter(); gterr = []; roots = collections.Counter()
for row in rows:
    if row['stage'] != 'align':
        continue
    d = O + '/cases/' + re.sub(r'[^A-Za-z0-9_.+-]+', '_', row['case_id'])
    r = json.load(open(d + '/result.json'))
    fails = [e for e in r['event_log'] if e.get('event') == 'job_failed' and e['robot_id'] in ('r1', 'r2')
             and not str(e['detail'].get('reason', '')).startswith('EPISODE_END')]
    fails.sort(key=lambda e: (e['sim_s'], str(e['detail'].get('reason')).startswith('PARTNER')))
    root = fails[0]; rid = root['robot_id']; roots[root['detail']['reason']] += 1
    ev = r['controller_events'][rid]
    relook_idx[sum(e['event'] == 'align_relook_trigger' for e in ev)] += 1
    rej = [e for e in ev if e['event'] == 'align_relook_fix_rejected']
    if rej:
        stats[tuple(rej[-1]['failed_checks'])] += 1
    fr = json.load(open(d + '/robots.json'))[rid]['frames']
    last = [f for f in fr if f['t'] <= root['sim_s'] + 1e-6][-1]['report']
    if last.get('std_xy_m') is not None:
        rej_std.append(last['std_xy_m'])
    tr = [json.loads(l) for l in open(d + '/eval_only/trace.jsonl')]
    t = [x for x in tr if x['t'] <= root['sim_s'] + 1e-6][-1]
    geo = sp.stations([t['beam_xyz'][0], t['beam_xyz'][1], t['beam_yaw']])
    for q in ('r1', 'r2'):
        e = sp.grip_errors(t['robots'][q], geo['grip_xyz'][q][:2], geo['station'][q][2])
        gterr.append((row['case_id'], q, e['grip_x_err_m'], e['grip_y_err_m'], e['yaw_err_rad']))
print('root reasons', roots)
print('relook count of failing robot at failure', relook_idx)
print('last rejection failed checks', stats)
print('std_xy at failure: median %.3f min %.3f max %.3f' % (statistics.median(rej_std), min(rej_std), max(rej_std)))
gx = [abs(g[2]) for g in gterr]; gy = [abs(g[3]) for g in gterr]
print('GT |grip_x err| at root failure median %.3f max %.3f; |grip_y| median %.3f max %.3f'
      % (statistics.median(gx), max(gx), statistics.median(gy), max(gy)))
ok = sum(abs(g[2]) <= .017 and abs(g[3]) <= .012 and abs(g[4]) <= .052 for g in gterr)
print('robots already within GT align criteria at failure: %d/%d' % (ok, len(gterr)))
