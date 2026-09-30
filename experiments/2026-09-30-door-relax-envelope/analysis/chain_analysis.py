#!/usr/bin/env python3
"""Chain (L0 -> handover -> L1) analysis of stage-probe raws recorded with --stage chain --chain-stop-leg 1.

Usage: chain_analysis.py [--json out.json] <label>=<raw dir> ...

Per raw and per leg (0 = approach to the door, 1 = door crossing): standard leg checks (lift, tilt, jaws, end_error,
leg_error from harness.pair_chain_probe), an eval-only outcome class from the wall-contact tracker inside the leg window
(PASS_CLEAN / PASS_CONTACT_RECOVERED / FAIL_HARD_LIMIT / FAIL), the own sigma at leg start/end (gate hits are the
controller failures), NEES / +-2 sigma coverage of the PF at the leg end, and the smallest GT clearance of beam / chassis
to the door posts. GT is the analysis target only (never a controller input).
A leg counts as reached only if the chain got there; a case that failed before leg 1 counts as an L1 failure with
its first-failure phase/code recorded ("chain" denominator = all cases, not only those that reached L1).
"""
import argparse
import collections
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-29-door-guard-relax/analysis'))
from harness import pair_chain_probe as pcp  # noqa: E402
import door_relax_analysis as dra  # noqa: E402

HARD = {'max_tilt_deg': 15., 'max_penetration_m': .005}


def wilson(k, n, z=1.96):
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0., c - h), min(1., c + h))


def fmt_ci(k, n):
    lo, hi = wilson(k, n)
    return f'{k}/{n} [{100 * lo:.0f}-{100 * hi:.0f}%]'


def leg_windows(chain):
    return {l['leg']: (l['start_sim_s'], l['end_sim_s']) for l in chain['legs'] if l['recorded']}


def contacts_in(episodes, t0, t1):
    return [e for e in episodes if e['t_last'] >= t0 - 1e-9 and e['t_first'] <= t1 + 1e-9]


def hard_limit_violated(eps, tilt_max):
    pen = max((e['max_pen_m'] for e in eps), default=0.)
    return pen > HARD['max_penetration_m'] or (tilt_max is not None and tilt_max > HARD['max_tilt_deg'])


def leg_class(leg, eps, tilt_max):
    if not leg['recorded']:
        return 'FAIL'
    # Hard limits first: any single violation forbids success, even when an ordinary check also failed (prereg).
    if hard_limit_violated(eps, tilt_max):
        return 'FAIL_HARD_LIMIT'
    if not all(pcp.leg_checks(leg).values()):
        return 'FAIL'
    return 'PASS_CONTACT_RECOVERED' if eps else 'PASS_CLEAN'


def nees_of(trace, t, rid):
    rows = [x for x in trace if 'pf' in x and x['t'] <= t + 1e-6 and x['pf'][rid].get('initialized')]
    if not rows:
        return None
    x = rows[-1]
    p, g = x['pf'][rid], x['robots'][rid]
    e = np.array([g[0] - p['x'], g[1] - p['y'], dra.wrap(g[2] - p['yaw'])])
    C = np.array(p['cov'])
    return {'nees': float(e @ np.linalg.solve(C, e)), 'z': [float(v) for v in np.abs(e) / np.sqrt(np.diag(C))]}


def analyse(label, root, legs_wanted=(0, 1)):
    rows = [json.loads(l) for l in open(root / 'cases.jsonl')]
    rows.sort(key=lambda r: r['case_id'])
    man = json.load(open(root / 'manifest.json'))
    print(f'\n== {label}: {root.name} n={len(rows)} load start/end={[round(v, 1) for v in man["environment"].get("loadavg_at_start", [])]}/'
          f'{[round(v, 1) for v in man["environment"].get("loadavg_at_end", [])]} source={man["source"]["source_sha"][:8]} changed={man.get("source_changed")}')
    out = {'label': label, 'raw': str(root), 'cases': []}
    tally = {k: collections.Counter() for k in legs_wanted}
    honesty = []
    print('case | ' + ' | '.join(f'L{k}: class, sigma_yaw start/end deg, end_err mm, min clr beam/chassis mm' for k in legs_wanted) + ' | first failure')
    for r in rows:
        d = dra.case_dir(root, r['case_id'])
        res = json.load(open(d / 'result.json'))
        chain = r.get('chain')
        tag = r['case_id'].split(':', 2)[2]
        trace = [json.loads(x) for x in open(d / 'eval_only/trace.jsonl')] if (d / 'eval_only/trace.jsonl').exists() else []
        eps = ((res.get('wall_contact') or {}).get('episodes')) or []
        item = {'case': tag, 'wall_s': r.get('wall_s'), 'first_failure': (chain or {}).get('first_failure'),
                'localizer_replaced_events': (chain or {}).get('localizer_replaced_events'), 'legs': {},
                'door_relax_overrides': r.get('door_relax_overrides')}
        all_tilt = max((x.get('tilt_deg', 0.) for x in trace), default=None)
        item['hard_limit_chain'] = {'violated': hard_limit_violated(eps, all_tilt), 'max_pen_m': max((e['max_pen_m'] for e in eps), default=0.),
                                    'max_tilt_deg': all_tilt}
        cells = []
        for k in legs_wanted:
            leg = chain['legs'][k] if chain else {'recorded': False}
            if leg['recorded']:
                t0, t1 = leg['start_sim_s'], leg['end_sim_s']
                win = [x for x in trace if t0 - 1e-6 <= x['t'] <= t1 + 1e-6]
                tilt = max((x.get('tilt_deg', 0.) for x in win), default=None)
                ce = contacts_in(eps, t0, t1)
                cls = leg_class(leg, ce, tilt)
                clr_b = round(1000 * min(dra.min_dist_to_posts(dra.beam_points(x['beam_xyz'], x['beam_yaw'])) for x in win), 1) if win else None
                clr_c = round(1000 * min(dra.min_dist_to_posts(dra.chassis_points(x['robots'][rid])) for x in win for rid in ('r1', 'r2')), 1) if win else None
                nz = {rid: nees_of(trace, t1, rid) for rid in ('r1', 'r2')}
                honesty += [{**v, 'leg': k} for v in nz.values() if v]
                item['legs'][k] = {'class': cls, 'checks': pcp.leg_checks(leg), 'sigma_yaw_start_deg': math.degrees(leg['sigma_yaw_start_rad']),
                                   'sigma_yaw_end_deg': math.degrees(leg['sigma_yaw_end_rad']), 'sigma_xy_start_m': leg['sigma_xy_start_m'],
                                   'sigma_xy_end_m': leg['sigma_xy_end_m'], 'end_error_m': leg['end_error_m'], 'cross_track_m': leg['cross_track_m'],
                                   'tilt_deg': leg['tilt_deg'], 'contact_episodes': len(ce), 'max_pen_m': max((e['max_pen_m'] for e in ce), default=0.),
                                   'contact_who': sorted({e['who'] for e in ce}), 'min_clear_beam_mm': clr_b, 'min_clear_chassis_mm': clr_c,
                                   'est_err_xy_end_m': leg.get('est_err_xy_end_m'), 'est_err_yaw_end_deg': math.degrees(leg['est_err_yaw_end_rad']),
                                   'nees': {rid: (v or {}).get('nees') for rid, v in nz.items()},
                                   'z': {rid: (v or {}).get('z') for rid, v in nz.items()}, 'start_sim_s': t0, 'end_sim_s': t1,
                                   'handover_s': leg.get('handover_from_prev_end_s')}
                cells.append(f"{cls}, {item['legs'][k]['sigma_yaw_start_deg']:.2f}/{item['legs'][k]['sigma_yaw_end_deg']:.2f}, "
                             f"{1000 * leg['end_error_m']:.0f}, {clr_b}/{clr_c}")
            else:
                cls = 'FAIL'
                item['legs'][k] = {'class': 'FAIL', 'reached': False}
                cells.append('FAIL (not reached)')
            tally[k][cls] += 1
        ff = item['first_failure']
        print(' ', tag, '|', ' | '.join(cells), '|', (f"{ff['phase']} L{ff['leg']} {ff['code']} {ff.get('sub') or ''} ({ff['source']})" if ff else '-'))
        out['cases'].append(item)
    out['tally'] = {f'L{k}': dict(v) for k, v in tally.items()}
    n = len(rows)
    for k in legs_wanted:
        c = tally[k]
        clean, rec = c.get('PASS_CLEAN', 0), c.get('PASS_CONTACT_RECOVERED', 0)
        print(f'L{k}: n={n} PASS_CLEAN={fmt_ci(clean, n)} PASS_any={fmt_ci(clean + rec, n)} '
              f'PASS_CONTACT_RECOVERED={rec} FAIL_HARD_LIMIT={c.get("FAIL_HARD_LIMIT", 0)} FAIL={c.get("FAIL", 0)}')
    both = sum(1 for it in out['cases'] if all(it['legs'][k]['class'] in ('PASS_CLEAN', 'PASS_CONTACT_RECOVERED') for k in legs_wanted))
    print(f'chain L0->L1 both legs pass: {fmt_ci(both, n)}')
    out['both_pass'] = both
    hl = sum(1 for it in out['cases'] if it['hard_limit_chain']['violated'])
    out['hard_limit_chain_cases'] = hl
    print(f'hard limit (pen > {1000 * HARD["max_penetration_m"]:.0f} mm or tilt > {HARD["max_tilt_deg"]:.0f} deg) anywhere in the run '
          f'(all legs, set-down, regrasp): {hl}/{n} cases')
    if honesty:
        out['honesty'] = {}
        for label_, sel in (('all', honesty), *[(f'L{k}', [h for h in honesty if h['leg'] == k]) for k in legs_wanted]):
            if not sel:
                continue
            nn = np.array([h['nees'] for h in sel])
            z = np.array([h['z'] for h in sel])
            cov = (z <= 2).mean(0)
            out['honesty'][label_] = {'n': len(sel), 'mean_nees': float(nn.mean()), 'median_nees': float(np.median(nn)),
                                      'cov2sigma_xyyaw': cov.tolist()}
            print(f'PF honesty {label_} at the leg ends (case-robot samples): n={len(sel)} meanNEES={nn.mean():.2f} '
                  f'median={np.median(nn):.2f} cov2sigma x/y/yaw={cov.round(3).tolist()}')
    return out


CLASSIFIER_NOTE = (
    "NOTE: 'SELF_POSE_UNCERTAIN gate_not_ok_dwell_or_hysteresis' in the first-failure column is the name the existing classifier "
    "(harness/pair_stage_probe.py ~855-868) gives an abort; the raw controller reason in these runs is POSE_UNCERTAIN_PROGRESS "
    "(ProgressMonitor no-progress stop), not a pose gate.\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', type=Path)
    ap.add_argument('raws', nargs='+')
    a = ap.parse_args()
    print(CLASSIFIER_NOTE, end='')
    res = []
    for spec in a.raws:
        label, _, path = spec.partition('=')
        res.append(analyse(label, Path(path)))
    if a.json:
        a.json.write_text(json.dumps(res, indent=1, default=float))


if __name__ == '__main__':
    main()
