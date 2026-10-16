#!/usr/bin/env python3
"""Door-relax envelope raws -> offline-audit derived views for TensorBoard (read-only; failures included).

Usage: build_tb_views.py --output <new dir> <raw dir> [<raw dir> ...]

One view per case plus one aggregate per raw. Each view points at the case's original ``result.json`` (aggregates at the raw's
``summary.json``) by absolute path + SHA-256; ``scripts/export_offline_audit.py`` refuses changed originals.  The verdict in
``evaluation/reported_success`` is the ENVELOPE verdict of this experiment (chain: L0 and L1 both PASS_CLEAN; carry/envelope: leg
traversed with no wall contact, end-point check ignored) - NOT the standard stage-probe pass, NOT E2E success.  Class definitions:
``analysis/chain_analysis.py`` and ``analysis/envelope_analysis.py``.  GT-derived numbers are evaluation only.
"""
import argparse
import contextlib
import hashlib
import io
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-29-door-guard-relax/analysis'))
import chain_analysis as ca  # noqa: E402
import envelope_analysis as ea  # noqa: E402
import door_relax_analysis as dra  # noqa: E402

SCHEMA = 'ugrp.offline_audit_view.v1'
CHAIN_DEF = ('door-relax envelope verdict, NOT the standard stage pass and NOT E2E success: chain L0 and L1 (stopped at the end of leg 1) '
             'both PASS_CLEAN (all standard leg checks incl. the 10 cm end-point check, no wall contact); stage probe, teacher-staged')
ENV_DEF = ('door-relax envelope verdict, NOT the standard stage pass and NOT E2E success: the carry leg was traversed by the '
           "controller with lift/tilt/jaws/leg-length checks holding and no wall contact (end-point check ignored, 'TRAVERSED_CLEAN')")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def slug(text):
    return re.sub(r'[^A-Za-z0-9_+-]+', '_', text).strip('_')


def put(scalars, tag, value):
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)) and math.isfinite(value):
        scalars[tag] = value


def variant_short(variant):
    return variant.replace('b-v6h.', '').replace('b-v6g', 'base')


def commands_of(d):
    p = d / 'commands.json'
    if not p.exists():
        return None
    cmds = json.loads(p.read_text())
    return sum(1 for r in ('r1', 'r2') for c in cmds.get(r, []) if c['kind'] in ('arm', 'look', 'drive', 'mecanum'))


def base_view(raw, man, r, src, scalars, success, definition, name_case, condition, outcome, d):
    view = {'schema': SCHEMA, 'derived_view_only': True,
            'offline_source': {'path': str(src), 'sha256': sha(src)},
            'offline_scalar_scope': ('one door-relax envelope stage-probe case (teacher-staged, weld OFF, model calls 0); values are '
                                     'eval-only GT/tracker measurements from the recorded run, not controller inputs'),
            'offline_scalars': scalars, 'success': success, 'success_definition': definition, 'model_calls': 0,
            'family': 'door_relax_envelope', 'policy': '','case': name_case, 'condition': condition,
            'seed': r['seed'], 'outcome': outcome, 'source_sha': man['source']['source_sha'], 'run_id': r['case_id'],
            'contact_profile': 'cargo_noslip_v1', 'scope': 'stage_probe_not_e2e',
            'limits': ('dev; weld OFF; seeds change only the PF RNG (seed 911/912 gave identical results, not independent evidence); '
                       'the wall tracker sees walls only'),
            'hparam_metrics': ['offline/pass'] + [t for t in ('offline/contact_episodes',) if t in scalars]}
    if r.get('stage_sim_s') is not None:
        view['sim_s'] = r['stage_sim_s']
    if r.get('wall_s') is not None:
        view['wall_s'] = r['wall_s']
    n = commands_of(d)
    if n is not None:
        view['commands'] = n
    return view


def chain_view(raw, man, r, item):
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
            for i, ax in enumerate(('x', 'y', 'yaw')):
                z = (leg.get('z') or {}).get(rid)
                put(sc, f'offline/L{k}/z_{ax}/{rid}', None if z is None else z[i])
    variant = ea.variant_of(r['case_id'])
    ff = item.get('first_failure')
    cause = f"{ff['phase']} L{ff['leg']} {ff['code']}" if ff else None
    outcome = f"{'PASS' if ok else 'FAIL'} L0={l0['class']} L1={l1['class']}" + (f' [{cause}]' if cause else '')
    view = base_view(raw, man, r, src, sc, ok, CHAIN_DEF, r['cell'], 'chain L0->L1', outcome, d)
    view['policy'] = variant
    view['texts'] = {'evaluation/checks': {'legs': {str(k): {kk: vv for kk, vv in item['legs'][k].items()} for k in (0, 1)},
                                            'first_failure': ff, 'std_category': r['category']}}
    return f"ch-{variant_short(variant)}-{r['cell']}-s{r['seed']}", view


def env_view(raw, man, r):
    d = dra.case_dir(raw, r['case_id'])
    src = d / 'result.json'
    cell = ea.parse_cell(r['case_id'])
    cls = ea.envelope_class(r)
    f = dra.case_facts(raw, r)
    wc = r.get('wall_contact') or {}
    m = r.get('metrics') or {}
    sy = r.get('sigma_yaw_max') or {}
    ok = cls == 'TRAVERSED_CLEAN'
    sc = {}
    put(sc, 'offline/pass', ok)
    put(sc, 'offline/std_stage_pass', r['passed'])
    put(sc, 'offline/place_y_m', cell['y'])
    put(sc, 'offline/place_heading_deg', cell['heading_deg'])
    put(sc, 'offline/prior_bias_y_m', cell['bias_y_m'])
    put(sc, 'offline/prior_bias_yaw_deg', cell['bias_yaw_deg'])
    put(sc, 'offline/contact_episodes', len(wc.get('episodes') or []) if isinstance(wc.get('episodes'), list) else (wc.get('episodes') or 0))
    put(sc, 'offline/max_penetration_m', wc.get('max_penetration_m'))
    put(sc, 'offline/max_tilt_deg_stage', wc.get('max_tilt_deg_stage'))
    for key in ('cross_track_m', 'end_error_m', 'yaw_drift_deg', 'travel_m', 'lift_m', 'tilt_deg'):
        put(sc, f'offline/{key}', m.get(key))
    put(sc, 'offline/sigma_yaw_max_deg', math.degrees(max(sy.values())) if sy else None)
    put(sc, 'offline/min_clear_beam_mm', f['min_clear_beam_mm'])
    put(sc, 'offline/min_clear_chassis_mm', f['min_clear_chassis_mm'])
    for rid, p in (f['pf'] or {}).items():
        put(sc, f'offline/nees/{rid}', p['nees'])
    variant = ea.variant_of(r['case_id'])
    leg = ea.leg_of(r)
    cohort = 'pos' if 'pos' in raw.name else ('bias' if (cell['bias_y_m'] or cell['bias_yaw_deg']) else 'env')
    ff = r.get('first_failure') or {}
    outcome = f"{cls}" + (f" [{r['cause']}{'/' + r['cause_sub'] if r.get('cause_sub') else ''}]" if r.get('cause') else '')
    condition = f"carry leg{leg} {cohort}" + (' (positive control)' if cohort == 'pos' else '')
    view = base_view(raw, man, r, src, sc, ok, ENV_DEF, r['cell'], condition, outcome, d)
    view['policy'] = variant
    view['texts'] = {'evaluation/checks': {'envelope_class': cls, 'std_outcome_class': r.get('outcome_class'), 'category': r['category'],
                                            'first_failure': ff or None, 'wall_contact': {k: wc.get(k) for k in
                                            ('episodes', 'who', 'wall_geoms', 'max_penetration_m', 'first_contact_sim_s')}}}
    tag = f"{cohort}-{variant_short(variant)}-L{leg}-y{cell['y']:+.2f}-h{cell['heading_deg']:+.0f}"
    if cell['bias_y_m'] or cell['bias_yaw_deg']:
        tag += f"-b{cell['bias_y_m']:+.2f}_{cell['bias_yaw_deg']:+.0f}"
    return tag, view


def aggregate(raw, man, rows, verdicts, kind):
    src = raw / 'summary.json'
    n = len(rows)
    k = sum(verdicts)
    sc = {}
    put(sc, 'offline/cases', n)
    put(sc, 'offline/passed', k)
    put(sc, 'offline/pass_rate', k / n)
    lo, hi = ca.wilson(k, n)
    put(sc, 'offline/pass_rate_wilson_lo', lo)
    put(sc, 'offline/pass_rate_wilson_hi', hi)
    variants = sorted({ea.variant_of(r['case_id']) for r in rows})
    return {'schema': SCHEMA, 'derived_view_only': True, 'offline_source': {'path': str(src), 'sha256': sha(src)},
            'offline_scalar_scope': f'aggregate of {n} door-relax envelope stage-probe cases ({kind}); stage probe, not E2E; '
                                    'cases are not independent when the seed differs only in the PF RNG',
            'offline_scalars': sc, 'success': k == n,
            'success_definition': 'all cases of this raw passed the door-relax envelope verdict (' + (CHAIN_DEF if kind == 'chain' else ENV_DEF) + ')',
            'model_calls': 0, 'family': 'door_relax_envelope_aggregate', 'policy': ','.join(variants), 'case': 'all',
            'condition': f'{kind} {raw.name.split("-", 3)[-1]}', 'outcome': f'{k}/{n} pass [{100 * lo:.0f}-{100 * hi:.0f}% Wilson]',
            'source_sha': man['source']['source_sha'], 'run_id': raw.name, 'scope': 'stage_probe_not_e2e',
            'limits': 'dev; weld OFF; stage probe', 'texts': {'evaluation/summary': {'raw': str(raw), 'cases': n, 'passed': k}},
            'hparam_metrics': ['offline/pass_rate', 'offline/cases', 'offline/passed']}


def write(out, name, view):
    d = out / name
    d.mkdir(parents=True, exist_ok=False)
    (d / 'result.json').write_text(json.dumps(view, ensure_ascii=False, indent=1, allow_nan=False) + '\n')
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('raws', nargs='+', type=Path)
    a = ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    names, skipped = [], []
    for raw in a.raws:
        rows = [json.loads(l) for l in open(raw / 'cases.jsonl') if l.strip()]
        man = json.load(open(raw / 'manifest.json'))
        if not rows:
            skipped.append({'raw': str(raw), 'reason': 'no completed cases (aborted run)'})
            continue
        rows.sort(key=lambda r: r['case_id'])
        tag = raw.name.split('-')[-1]
        verdicts = []
        if rows[0]['stage'] == 'chain':
            with contextlib.redirect_stdout(io.StringIO()):
                res = ca.analyse(tag, raw)
            for r, item in zip(rows, res['cases']):
                name, view = chain_view(raw, man, r, item)
                verdicts.append(view['success'])
                names.append(write(a.output, name if name not in names else f'{name}-{tag}', view))
            kind = 'chain'
        else:
            for r in rows:
                name, view = env_view(raw, man, r)
                verdicts.append(view['success'])
                names.append(write(a.output, name if name not in names else f'{name}-{tag}', view))
            kind = 'carry envelope'
        names.append(write(a.output, f'ALL-{slug(tag)}', aggregate(raw, man, rows, verdicts, kind)))
    index = {'views': names, 'raw': [str(r) for r in a.raws], 'skipped': skipped,
             'summary_sha256': {str(r): sha(r / 'summary.json') for r in a.raws if (r / 'summary.json').exists()}}
    (a.output / 'index.json').write_text(json.dumps(index, indent=1) + '\n')
    print(json.dumps({'views': len(names), 'skipped': skipped, 'output': str(a.output)}))


if __name__ == '__main__':
    main()
