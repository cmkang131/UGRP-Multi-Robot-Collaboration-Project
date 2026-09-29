#!/usr/bin/env python3
"""b-v6h gain-fix chain cohorts -> offline-audit derived views for TensorBoard (read-only; failures included).

Usage: build_tb_views.py --output <new dir> <tag>=<raw dir> [...]      (tags: cA cB cC cD cF rA rB sA sB)

One view per case plus one aggregate per raw. Each view points at the case's original ``result.json`` (aggregate: the raw's
``summary.json``) by absolute path + SHA-256; ``scripts/export_offline_audit.py`` refuses changed originals. The verdict
(``success``) is chain L0 and L1 both PASS_CLEAN (all standard leg checks incl. the 10 cm end-point check, no wall contact); it is a
stage-probe verdict of this exploratory cohort, NOT E2E success and NOT a registered result. GT-derived numbers are evaluation only.
Builds on the door-relax-envelope view builder (same classifier), adds per-axis signed PF error and z^2 at the leg ends.
"""
import argparse
import contextlib
import hashlib
import io
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-30-door-relax-envelope/analysis'))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-29-door-guard-relax/analysis'))
import gain_cohort_analysis as gca  # noqa: E402
import chain_analysis as ca  # noqa: E402
import door_relax_analysis as dra  # noqa: E402

SCHEMA = 'ugrp.offline_audit_view.v1'
DEF = ('exploratory chain verdict, NOT E2E success and NOT a registered result: chain L0 and L1 (stopped at the end of leg 1) both '
       'PASS_CLEAN (all standard leg checks incl. the 10 cm end-point check, no wall contact); stage probe, teacher-staged, weld OFF')
CONFIG = {'cA': 'k1g+p2f', 'cB': 'k1g+p2f+gain', 'cC': 'k1+p2f+gain', 'cD': 'k2+p2f+gain', 'cF': 'k2+p2f',
          'rA': 'k1g+p2f', 'rB': 'k1g+p2f+gain', 'sA': 'k1g+p2f', 'sB': 'k1g+p2f+gain'}
COHORT = {'cA': 'base sheet, 12 placements', 'cB': 'base sheet, 12 placements', 'cC': 'base sheet, 12 placements',
          'cD': 'base sheet, 12 placements', 'cF': 'base sheet, 12 placements', 'rA': 'recorded hR2 setups (10)',
          'rB': 'recorded hR2 setups (10)', 'sA': 'sheet-consistent, 12 placements', 'sB': 'sheet-consistent, 12 placements'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(sc, tag, value):
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)) and math.isfinite(value):
        sc[tag] = value


def commands_of(d):
    p = d / 'commands.json'
    if not p.exists():
        return None
    cmds = json.loads(p.read_text())
    return sum(1 for r in ('r1', 'r2') for c in cmds.get(r, []) if c['kind'] in ('arm', 'look', 'drive', 'mecanum'))


def chain_view(tag, raw, man, r, item):
    d = dra.case_dir(raw, r['case_id'])
    src = d / 'result.json'
    l0, l1 = item['legs'][0], item['legs'][1]
    ok = l0['class'] == 'PASS_CLEAN' and l1['class'] == 'PASS_CLEAN'
    sc = {}
    put(sc, 'offline/pass', ok)
    put(sc, 'offline/l0_pass_clean', l0['class'] == 'PASS_CLEAN')
    put(sc, 'offline/l1_pass_clean', l1['class'] == 'PASS_CLEAN')
    put(sc, 'offline/std_stage_pass', r['passed'])
    put(sc, 'offline/contact_episodes', sum(l.get('contact_episodes', 0) for l in (l0, l1)))
    for k, leg in ((0, l0), (1, l1)):
        if not leg.get('class') or leg.get('reached') is False:
            put(sc, f'offline/L{k}/reached', 0)
            continue
        put(sc, f'offline/L{k}/reached', 1)
        for key in ('sigma_yaw_start_deg', 'sigma_yaw_end_deg', 'sigma_xy_start_m', 'sigma_xy_end_m', 'end_error_m', 'cross_track_m',
                    'tilt_deg', 'max_pen_m', 'min_clear_beam_mm', 'min_clear_chassis_mm', 'est_err_xy_end_m', 'est_err_yaw_end_deg'):
            put(sc, f'offline/L{k}/{key}', leg.get(key))
        for rid in ('r1', 'r2'):
            put(sc, f'offline/L{k}/nees/{rid}', (leg.get('nees') or {}).get(rid))
            s = (leg.get('signed') or {}).get(rid)
            if s:
                for i, ax in enumerate(('x', 'y', 'yaw')):
                    put(sc, f'offline/L{k}/z2_{ax}/{rid}', s['z2'][i])
                    put(sc, f'offline/L{k}/pf_err_{ax}/{rid}', s['e'][i])
    ff = item.get('first_failure')
    cause = f"{ff['phase']} L{ff['leg']} {ff['code']}" if ff else None
    outcome = f"{'PASS' if ok else 'FAIL'} L0={l0['class']} L1={l1['class']}" + (f' [{cause}]' if cause else '')
    view = {'schema': SCHEMA, 'derived_view_only': True, 'offline_source': {'path': str(src), 'sha256': sha(src)},
            'offline_scalar_scope': ('one b-v6h gain-fix chain stage-probe case (teacher-staged, weld OFF, model calls 0); values are '
                                     'eval-only GT/tracker measurements from the recorded run, not controller inputs'),
            'offline_scalars': sc, 'success': ok, 'success_definition': DEF, 'model_calls': 0, 'family': 'b_v6h_gain',
            'policy': f'b-v6h {CONFIG[tag]}', 'case': r['cell'], 'condition': f'{COHORT[tag]}, chain L0->L1', 'seed': r['seed'],
            'outcome': outcome, 'source_sha': man['source']['source_sha'], 'run_id': r['case_id'],
            'contact_profile': 'cargo_noslip_v1', 'scope': 'stage_probe_not_e2e',
            'limits': ('exploratory dev cohort (not preregistered); weld OFF; PF seeds 911/913 change only the PF RNG and gave near-identical '
                       'outcomes, so the effective independent unit is the placement; the wall tracker sees walls only'),
            'hparam_metrics': ['offline/pass', 'offline/contact_episodes']}
    if r.get('stage_sim_s') is not None:
        view['sim_s'] = r['stage_sim_s']
    if r.get('wall_s') is not None:
        view['wall_s'] = r['wall_s']
    n = commands_of(d)
    if n is not None:
        view['commands'] = n
    view['texts'] = {'evaluation/checks': {'legs': {str(k): item['legs'][k] for k in (0, 1)}, 'first_failure': ff,
                                            'std_category': r['category']}}
    return f"{tag}-{CONFIG[tag]}-{r['cell']}-s{r['seed']}", view


def aggregate(tag, raw, man, rows, verdicts):
    src = raw / 'summary.json'
    n, k = len(rows), sum(verdicts)
    lo, hi = ca.wilson(k, n)
    sc = {}
    for key, v in (('cases', n), ('passed', k), ('pass_rate', k / n), ('pass_rate_wilson_lo', lo), ('pass_rate_wilson_hi', hi)):
        put(sc, f'offline/{key}', v)
    return {'schema': SCHEMA, 'derived_view_only': True, 'offline_source': {'path': str(src), 'sha256': sha(src)},
            'offline_scalar_scope': f'aggregate of {n} b-v6h gain-fix chain stage-probe cases; stage probe, not E2E; two PF seeds per '
                                    'placement are not independent (case-level Wilson interval is optimistic)',
            'offline_scalars': sc, 'success': k == n, 'success_definition': 'all cases of this raw passed: ' + DEF,
            'model_calls': 0, 'family': 'b_v6h_gain_aggregate', 'policy': f'b-v6h {CONFIG[tag]}', 'case': 'all',
            'condition': f'{COHORT[tag]}, chain L0->L1', 'outcome': f'{k}/{n} pass [{100 * lo:.0f}-{100 * hi:.0f}% Wilson, case level]',
            'source_sha': man['source']['source_sha'], 'run_id': raw.name, 'scope': 'stage_probe_not_e2e',
            'limits': 'exploratory dev cohort; weld OFF; stage probe', 'texts': {'evaluation/summary': {'raw': str(raw), 'cases': n, 'passed': k}},
            'hparam_metrics': ['offline/pass_rate', 'offline/cases', 'offline/passed']}


def write(out, name, view):
    d = out / name
    d.mkdir(parents=True, exist_ok=False)
    (d / 'result.json').write_text(json.dumps(view, ensure_ascii=False, indent=1, allow_nan=False) + '\n')
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('raws', nargs='+')
    a = ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    names, raws = [], []
    for spec in a.raws:
        tag, _, p = spec.partition('=')
        raw = Path(p)
        raws.append(raw)
        rows = [json.loads(l) for l in open(raw / 'cases.jsonl') if l.strip()]
        man = json.load(open(raw / 'manifest.json'))
        rows.sort(key=lambda r: r['case_id'])
        with contextlib.redirect_stdout(io.StringIO()):
            res = gca.analyse(tag, raw)
        verdicts = []
        for r, item in zip(rows, res['cases']):
            name, view = chain_view(tag, raw, man, r, item)
            verdicts.append(view['success'])
            names.append(write(a.output, name, view))
        names.append(write(a.output, f'ALL-{tag}-{CONFIG[tag]}', aggregate(tag, raw, man, rows, verdicts)))
    (a.output / 'index.json').write_text(json.dumps({'views': names, 'raw': [str(r) for r in raws],
                                                     'summary_sha256': {str(r): sha(r / 'summary.json') for r in raws}}, indent=1) + '\n')
    print(json.dumps({'views': len(names), 'output': str(a.output)}))


if __name__ == '__main__':
    main()
