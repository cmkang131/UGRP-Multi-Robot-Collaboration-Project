#!/usr/bin/env python3
"""b-v6h1 sealed-analysis results -> offline-audit derived views for TensorBoard (read-only).

Usage: build_tb_views.py --output <new dir>

Reads ONLY (never writes): the sealed analysis outputs ``sealed_analysis.json`` / ``classifier.json`` of the v2 unblinding and
the 72 recorded cases of the blinded raw (``cases.jsonl``, each case's ``result.json`` and ``commands.json``). One view per
case (72) plus one aggregate per seed (primary 941, sensitivity 943). Each view points at the case's original ``result.json``
(aggregate: ``sealed_analysis.json``) by absolute path + SHA-256; ``scripts/export_offline_audit.py`` refuses changed originals.

The verdict ``success`` is the registered classifier class PASS_CLEAN (both legs standard checks + no wall contact + whole-chain
safety). It is a stage-probe verdict of this SIM cohort (teacher-made start pose, own RGB + static map + own commands), NOT an E2E
success, NOT a real-robot result. The wrapper's own ``passed=false / STAGE_BUDGET_EXHAUSTED`` refers to the destination set-down,
which this cohort does not evaluate (classify_placements.py: "Wrapper passed/outcome_class refer to destination setdown, outside
this task"); it is kept as text, not as a success scalar. GT-derived numbers are evaluation only, never controller input.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

RAW = Path('/Users/changmin/projects/ugrp/outputs/v6h1-confirm-4c6b439f-20260930')
SEALED = Path('/Users/changmin/projects/ugrp/outputs/v6h1-sealed-analysis-v2-20261001')
SCHEMA = 'ugrp.offline_audit_view.v1'
DEF = ('registered classifier (seal v2 5be4330e) class PASS_CLEAN: chain L0 and L1 both pass every standard leg check incl. the '
       '10 cm end-point check, no wall-contact episode, no hard-limit; SIM stage probe from a teacher-made start pose, weld OFF, '
       'model calls 0, floor_light_v1; NOT E2E success and NOT a real-robot result')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(sc, tag, value):
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)) and math.isfinite(value):
        sc[tag] = value


def commands_of(d):
    cmds = json.loads((d / 'commands.json').read_text())
    return sum(1 for r in ('r1', 'r2') for c in cmds.get(r, []) if c['kind'] in ('arm', 'look', 'drive', 'mecanum'))


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0., c - h), min(1., c + h)


def case_view(att, row, source_sha):
    d = RAW / 'cases' / att['case_id'].replace('@', '_').replace(':', '_')
    src = d / 'result.json'
    ok = att['class'] == 'PASS_CLEAN'
    sc = {}
    put(sc, 'offline/pass', ok)
    put(sc, 'offline/hard_limit_violated', att['hard_limit_chain']['violated'])
    put(sc, 'offline/contact_episodes', att['contact_episodes_whole_chain'])
    put(sc, 'offline/max_tilt_deg', att['hard_limit_chain']['max_tilt_deg'])
    put(sc, 'offline/max_pen_m', att['hard_limit_chain']['max_pen_m'])
    put(sc, 'offline/chain_sim_s', att['end_window']['L1_end_sim_s'] - row['entry_sim_s'])
    for k in (0, 1):
        leg = row['chain']['legs'][k]
        put(sc, f'offline/L{k}/pass', att['legs'][f'L{k}']['standard_pass'])
        for key in ('end_error_m', 'cross_track_m', 'leg_error_m', 'yaw_drift_deg', 'tilt_deg', 'lift_m', 'sigma_xy_end_m',
                    'sigma_yaw_end_rad', 'est_err_xy_end_m'):
            put(sc, f'offline/L{k}/{key}', leg.get(key))
        for rid in ('r1', 'r2'):
            s = att['sigma'][f'L{k}']['signed'].get(rid)
            if s:
                put(sc, f'offline/L{k}/nees/{rid}', s['nees'])
                for i, ax in enumerate(('x', 'y', 'yaw')):
                    put(sc, f'offline/L{k}/z2_{ax}/{rid}', s['z2'][i])
                    put(sc, f'offline/L{k}/pf_err_{ax}/{rid}', s['e'][i])
    view = {'schema': SCHEMA, 'derived_view_only': True, 'offline_source': {'path': str(src), 'sha256': sha(src)},
            'offline_scalar_scope': ('one b-v6h1 confirmatory chain stage-probe case (teacher-made start pose, weld OFF, model calls 0, '
                                     'floor_light_v1); values are eval-only GT/tracker/classifier measurements of the recorded run, '
                                     'not controller inputs'),
            'offline_scalars': sc, 'success': ok, 'success_definition': DEF, 'model_calls': 0, 'family': 'b_v6h1_confirm',
            'policy': 'b-v6h1', 'case': row['cell'], 'seed': row['seed'],
            'condition': ('confirm primary s941 chain L0->L1' if row['seed'] == 941 else 'confirm sensitivity s943 chain L0->L1'),
            'outcome': f"{att['class']} L0={'PASS' if att['legs']['L0']['standard_pass'] else 'FAIL'} "
                       f"L1={'PASS' if att['legs']['L1']['standard_pass'] else 'FAIL'}",
            'source_sha': source_sha, 'run_id': att['case_id'], 'contact_profile': 'cargo_noslip_v1', 'scope': 'stage_probe_not_e2e',
            'limits': ('SIM stage probe from a teacher-made start pose; fixed 60-placement observed cohort (not a population rate); '
                       'two PF seeds per placement are not independent; blinded recording was made before the analysis seal '
                       '(unsealed stage-probe admission)'),
            'sim_s': row['stage_sim_s'], 'wall_s': row['wall_s'], 'commands': commands_of(d),
            'hparam_metrics': ['offline/pass', 'offline/L0/end_error_m', 'offline/L1/end_error_m', 'offline/max_tilt_deg']}
    view['texts'] = {'evaluation/checks': {'legs': att['legs'], 'handover': att['handover'], 'end_window': att['end_window'],
                                            'hard_limit_chain': att['hard_limit_chain'],
                                            'recorder_wrapper_label_not_used_for_verdict': {
                                                'passed': row['passed'], 'category': row['category'],
                                                'why': 'wrapper label refers to destination set-down, outside this task'}}}
    return f"{row['cell']}-s{row['seed']}", view


def aggregate(seed, atts, rows, sealed):
    n = len(atts)
    k = sum(a['class'] == 'PASS_CLEAN' for a in atts)
    lo, hi = wilson(k, n)
    sc = {}
    for key, v in (('cases', n), ('passed', k), ('pass_rate', k / n), ('pass_rate_wilson_lo', lo), ('pass_rate_wilson_hi', hi),
                   ('hard_limit_cases', sum(a['hard_limit_chain']['violated'] for a in atts)),
                   ('contact_episodes_total', sum(a['contact_episodes_whole_chain'] for a in atts)),
                   ('max_tilt_deg', max(a['hard_limit_chain']['max_tilt_deg'] for a in atts)),
                   ('max_pen_m', max(a['hard_limit_chain']['max_pen_m'] for a in atts))):
        put(sc, f'offline/{key}', v)
    sig_all = sealed['summary']['sigma_criterion_B']
    sig = sig_all['legs'] if seed == 941 else sig_all['secondary_seed_943']
    for leg in ('L0', 'L1'):
        for i, ax in enumerate(('x', 'y', 'yaw')):
            put(sc, f'offline/{leg}/cov2sigma_placements_{ax}', sig[leg]['covered_placements_xyyaw'][i])
            put(sc, f'offline/{leg}/mean_z2_{ax}', sig[leg]['mean_z2_xyyaw'][i])
    if seed == 941:
        gate_ok = sealed['summary']['full_verdict'] == 'PASS_A_B_SAFETY'
        put(sc, 'gate/criterion_A_48_of_60', sealed['summary']['criterion']['verdict'] == 'PASS_OBSERVED_CRITERION')
        put(sc, 'gate/criterion_B_sigma', sig_all['verdict'] == 'PASS')
        put(sc, 'gate/full_verdict_pass', gate_ok)
    src = SEALED / 'sealed_analysis.json'
    cohort = 'primary s941 (C01-C60, gate >=48/60)' if seed == 941 else 'sensitivity s943 (first 12 placements, not pooled)'
    return {'schema': SCHEMA, 'derived_view_only': True, 'offline_source': {'path': str(src), 'sha256': sha(src)},
            'offline_scalar_scope': f'aggregate of {n} b-v6h1 confirmatory cases, {cohort}; sealed v2 analysis; stage probe, not E2E',
            'offline_scalars': sc, 'success': (k == n) and (seed != 941 or sealed['summary']['full_verdict'] == 'PASS_A_B_SAFETY'),
            'success_definition': 'all cases PASS_CLEAN' + (' and full_verdict PASS_A_B_SAFETY' if seed == 941 else ''),
            'model_calls': 0, 'family': 'b_v6h1_confirm_aggregate', 'policy': 'b-v6h1', 'case': 'all', 'seed': seed,
            'condition': 'confirm primary s941 chain L0->L1' if seed == 941 else 'confirm sensitivity s943 chain L0->L1',
            'outcome': f'{k}/{n} PASS_CLEAN [{100 * lo:.0f}-{100 * hi:.0f}% Wilson, placement level]',
            'source_sha': sealed['seal_commit'], 'run_id': f'v6h1-confirm-aggregate-s{seed}', 'scope': 'stage_probe_not_e2e',
            'limits': ('observed fixed cohort, not a population success rate; sigma coverage is not proof of calibration; '
                       'SIM only, teacher-made start pose'),
            'texts': {'evaluation/summary': {'cases': n, 'passed': k, 'verdict': sealed['summary']['full_verdict'] if seed == 941 else 'sensitivity_only'}},
            'hparam_metrics': ['offline/pass_rate', 'offline/cases', 'offline/passed']}


def write(out, name, view):
    d = out / name
    d.mkdir(parents=True, exist_ok=False)
    (d / 'result.json').write_text(json.dumps(view, ensure_ascii=False, indent=1, allow_nan=False) + '\n')
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    cl = json.loads((SEALED / 'classifier.json').read_text())
    sealed = json.loads((SEALED / 'sealed_analysis.json').read_text())
    rows = {}
    for line in (RAW / 'cases.jsonl').read_text().splitlines():
        r = json.loads(line)
        rows[r['case_id']] = r
    a.output.mkdir(parents=True, exist_ok=False)
    names = []
    by_seed = {941: [], 943: []}
    for att in sorted(cl['attempts'], key=lambda x: (x['seed'], x['placement'])):
        row = rows[att['case_id']]
        name, view = case_view(att, row, cl['source_sha'])
        names.append(write(a.output, name, view))
        by_seed[att['seed']].append(att)
    for seed in (941, 943):
        names.append(write(a.output, f'ALL-s{seed}', aggregate(seed, by_seed[seed], rows, sealed)))
    (a.output / 'index.json').write_text(json.dumps({'views': names, 'raw': str(RAW), 'sealed': str(SEALED),
                                                     'sealed_analysis_sha256': sha(SEALED / 'sealed_analysis.json'),
                                                     'classifier_sha256': sha(SEALED / 'classifier.json')}, indent=1) + '\n')
    print(json.dumps({'views': len(names), 'output': str(a.output)}))


if __name__ == '__main__':
    main()
