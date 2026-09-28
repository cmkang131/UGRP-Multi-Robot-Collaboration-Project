"""v6 policy stage-probe tables (eval-only analysis of raw results; no physics). Stage probe, not E2E success.

usage: python analyze_v6_policies.py <probe output dir> [<probe output dir> ...]

Prints, per case: policy, source, cell, verdict, the controller's own relook calls and whether the
pose provider's localizer object was replaced (= posterior discarded), and the eval-only GT remaining
align error at the stage stop. For grasp_lift tolerance-boundary cases it prints the first entry
check that failed per robot, in the controller's own order.
"""
import collections
import json
import re
import sys


def case_dir(out, case_id):
    return f"{out}/cases/{re.sub(r'[^A-Za-z0-9_.+-]+', '_', case_id)}"


def relook_summary(row, rid):
    calls = (row.get('relook_calls') or {}).get(rid, [])
    c = collections.Counter(calls)
    return (f"reloc={c.get('begin_relocalization', 0)} obs={c.get('begin_observation', 0)} "
            f"replaced={(row.get('localizer_replaced') or {}).get(rid, 0)}")


def remaining(row, rid):
    e = (row.get('remaining_at_stop') or {}).get(rid)
    if not e:
        return 'n/a'
    return f"x{e['grip_x_err_m'] * 1000:+.0f}mm y{e['grip_y_err_m'] * 1000:+.0f}mm yaw{e['yaw_err_rad']:+.3f}"


def first_entry_check(result, rid, category, failing_rid):
    """Controller order: standoff fit -> own pose checks -> open grip view/servo -> preclose beam guard
    -> global safety (a+b) -> close/grip -> lift. Returns (check, detail)."""
    ev = (result.get('controller_events') or {}).get(rid, [])
    for e in ev:
        if e['event'] == 'beam_standoff' and not e.get('accepted'):
            return 'standoff_fit', 'beam not measured at the standoff view (PREGRASP_BEAM_UNCERTAIN)'
    for e in ev:
        rep = e.get('report') or {}
        if e['event'] == 'beam_relative' and rep.get('grip_base_m') is None and rep.get('reasons'):
            return 'relative_standoff', ','.join(rep['reasons'])
    for e in ev:
        if e['event'] == 'global_safety' and not (e.get('certificate') or {}).get('clear', True):
            cert = e['certificate']
            return 'global_safety', f"{cert.get('reason')} clearance={cert.get('clearance_m')}"
    for e in ev:
        if e['event'] == 'pregrasp_fix_rejected':
            if e.get('failed_checks'):
                return 'own_pose_checks', ','.join(e['failed_checks'])
            views = [v for v in ev if v['event'] == 'stage_probe_close_view' and v['sim_s'] <= e['sim_s'] + 1e-6]
            guard = [g for g in ev if g['event'] == 'preclose_beam_guard' and g['sim_s'] <= e['sim_s'] + 1e-6]
            if views:
                v = views[-1]
                gv = v.get('grip_view_m2') or {}
                if not v.get('servo_open') or not v.get('servo_match_all'):
                    return 'servo_state', f"open={v.get('servo_open')} match={v.get('servo_match_all')}"
                if not gv.get('seen', True) and not (result.get('controller') or {}).get('pair_policy') == 'a+b':
                    return 'grip_view_m2', (f"dark={gv.get('dark_fraction')} (min .40) beam top/bottom="
                                            f"{gv.get('top_beam_fraction')}/{gv.get('bottom_beam_fraction')}")
            if guard and not guard[-1].get('clear', True):
                return 'preclose_beam_guard', str(guard[-1].get('reason'))
            return 'wait_close_other', 'all pose checks true; see stage_probe_close_view'
    if category == 'PASS':
        return 'pass', ''
    if rid != failing_rid:
        return 'partner', f'partner {failing_rid} failed first'
    return 'after_entry_checks', category


def main(outs):
    rows = []
    for out in outs:
        for line in open(f'{out}/cases.jsonl'):
            if line.strip():
                rows.append((out, json.loads(line)))
    print('== per case (stage, policy, source, cell, verdict | per robot: relook calls, localizer replaced, GT remaining at stop)')
    agg = collections.defaultdict(lambda: [0, 0, collections.Counter()])
    for out, row in sorted(rows, key=lambda x: (x[1]['stage'], x[1].get('pair_policy', 'v5h'), x[1]['source'], x[1]['cell'])):
        pol = row.get('pair_policy', 'v5h')
        key = (row['stage'], pol, row['source'])
        agg[key][0] += 1
        agg[key][1] += int(row['passed'])
        if not row['passed']:
            agg[key][2][row['category']] += 1
        per = ' | '.join(f"{r}: {relook_summary(row, r)} rem {remaining(row, r)}" for r in ('r1', 'r2'))
        print(f"{row['stage']:10s} {pol:6s} {row['source']:18s} {row['cell']:22s} s{row['seed']} "
              f"{row['category']:34s} {per}")
    print('\n== aggregate (stage, policy, source): passed/cases, failures')
    for key, (n, ok, fails) in sorted(agg.items()):
        print(f'{key}: {ok}/{n} {dict(fails)}')
    bd = [(o, r) for o, r in rows if r['source'] == 'tolerance_boundary']
    if bd:
        print('\n== grasp_lift entries at the align-done tolerance boundary: first failing entry check per robot')
        for out, row in sorted(bd, key=lambda x: (x[1].get('pair_policy', 'v5h'), x[1]['cell'])):
            result = json.load(open(case_dir(out, row['case_id']) + '/result.json'))
            failing = (row.get('first_failure') or {}).get('robot_id')
            cells = []
            for rid in ('r1', 'r2'):
                check, detail = first_entry_check(result, rid, row['category'], failing)
                cells.append(f'{rid}={check}' + (f' ({detail})' if detail else ''))
            print(f"{row.get('pair_policy', 'v5h'):6s} {row['cell']:18s} {row['category']:30s} " + ' ; '.join(cells))


if __name__ == '__main__':
    main(sys.argv[1:])
