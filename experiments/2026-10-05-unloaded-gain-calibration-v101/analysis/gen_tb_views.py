#!/usr/bin/env python3
"""Derived TensorBoard views for the v101 unloaded gain calibration (collection, fit/held-out, replay selection).

Reads hashed raw files only and writes one derived-view result.json per run under <out>.
scripts/export_offline_audit.py then converts each view to events (new snapshot, raw untouched).
Nothing here is recomputed from truth: window NEES / errors are copied from sel_summary.json (written by
analysis/sel_summary.py from the replay jsonl + eval-only truth); held-out errors are copied from heldout.json.
Usage: gen_tb_views.py <out_dir>
"""
import hashlib
import json
import math
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
O = Path('/Users/changmin/projects/ugrp/outputs')
COL = O / 'calib-gain-v101-341ce3b9-20261005T0350Z'
COL_P2 = O / 'calib-gain-v101-341ce3b9-20261005T0340Z'
FIT_P = O / 'calib-gain-v101-fit-20261005/fit.json'
HELD_P = O / 'calib-gain-v101-heldout-20261005/heldout.json'
PROD_C = O / 'calib-gain-v101-product-20261005/C/calibration_dev_pilot_unloaded_v101.json'
PROD_C2 = O / 'calib-gain-v101-product-20261005/C2/calibration_dev_pilot_unloaded_v101.json'
PF = O / 'pf-gaincal-v101-20261005'
SEL_P = PF / 'sel_summary.json'
TRUTH_P = O / 'v98-dev-probe-raise_high-1f7fb800/zone_wide_door_geometry_v3/eval_only/trajectory.jsonl'
COLLECT_SHA = '341ce3b9aeda6aca38fac57c6d5030b9c458760d'
REPLAY_BASE_SHA = '94d083ba'      # #363 HEAD used for the replays (loaded modules byte-identical to 11f6d7c3)
BOUND, MEDIAN = 13.8, 1.386
WINS = ['10-20', '20-30', '30-40', '40-50', '50-60']
SEL_WINS = ['30-40', '40-50', '50-60']
SEEDS = [0, 101, 102, 103, 104]
CFG_TAG = {'HEAD': 'base', 'B': 'B', 'C': 'C', 'C2': 'C2'}
CFG_TEXT = {
    'HEAD': '#363 HEAD as is: old DEV fill gain/lag, no registered noise overlay (reference only)',
    'B': 'old DEV gain/lag + registered r4/r5 measured noise overlay (the coordinator-registered baseline)',
    'C': 'measured unloaded gain/lag (this calibration) + registered r4/r5 noise (SELECTED by the pre-registered rule)',
    'C2': 'measured gain/lag + noise measured in this calibration (EXCLUDED from selection: coverage gate 0.788 < 0.90; supplementary)'}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ref(p, **kw):
    p = Path(p)
    assert p.is_file() and not p.is_symlink(), p
    return dict(path=str(p), sha256=sha(p), **kw)


def write(name, view):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=False)
    (d / 'result.json').write_text(json.dumps(view, ensure_ascii=False, indent=2) + '\n')


def rms(xs):
    return math.sqrt(sum(x * x for x in xs) / len(xs))


held = json.loads(HELD_P.read_text())
fit = json.loads(FIT_P.read_text())
sel = json.loads(SEL_P.read_text())
assert held['fit_sha256'] == sha(FIT_P) and held['status'] == 'VALIDATED_DEV'
HELD_FORMS = ('linear_diag', 'dev_fill', 'r4r5')
SCOPE_COL = ('DEV calibration collection (unloaded r1, SIM time, model calls 0). COLLECTED_UNQUALIFIED: protocol complete, '
             'not a robot task success, not a timing benchmark; loadavg is recorded per run, not controlled.')

# ---- 1) six collection runs -------------------------------------------------------------------------------
roles = {'fitA1': 'fit', 'fitA2': 'fit', 'heldA3': 'heldout', 'heldM1': 'heldout', 'heldP1': 'heldout', 'heldP2': 'heldout'}
for run, role in roles.items():
    root = (COL_P2 if run == 'heldP2' else COL) / run
    case_p, top_p = root / run / 'result.json', root / 'result.json'
    case = json.loads(case_p.read_text())
    assert case['run_id'] == run and case['role'] == role and case['status'] == 'COLLECTED_UNQUALIFIED'
    assert case['protocol_complete'] is True and case['model_calls'] == 0 and case['physical_success'] is None
    sc = {'offline/seed': float(case['seed']), 'offline/reset_sim_s': case['reset_sim_s'],
          'offline/total_incl_reset_cap_s': case['total_including_reset_cap_s'],
          'offline/loadavg1_start': case['loadavg_start'][0], 'offline/loadavg1_end': case['loadavg_end'][0],
          'offline/concurrent_sim_holders_start': float(len(case['host_start']['concurrent_holders'])),
          'gate/protocol_complete': 1.0}
    if role == 'heldout':
        for form in HELD_FORMS:
            c = held['candidates'][form]
            ws = [w for w in c['selection_windows'] + c['leg_windows'] if w['run'] == run]
            assert ws, (run, form)
            sc[f'offline/heldout_windows_{form}'] = float(len(ws))
            sc[f'offline/heldout_end_err_rms_mm_{form}'] = 1000. * rms([w['end_err_m'] for w in ws])
            sc[f'offline/heldout_max_pos_err_mm_{form}'] = 1000. * max(w['max_pos_err_m'] for w in ws)
            sc[f'offline/heldout_end_over_path_max_{form}'] = max(w['end_over_path'] for w in ws)
    hp = ['evaluation/reported_success', 'result/sim_s', 'result/model_calls', 'offline/loadavg1_start',
          'offline/loadavg1_end', 'offline/reset_sim_s'] + (
        ['offline/heldout_end_err_rms_mm_linear_diag', 'offline/heldout_end_err_rms_mm_dev_fill',
         'offline/heldout_max_pos_err_mm_linear_diag'] if role == 'heldout' else [])
    write(f'col-{run}', {
        'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
        'family': 'v101-gain-collection', 'policy': 'zone-final-environment-gaincal-v101 (1.0.0)',
        'case': case['check'], 'condition': f'unloaded r1, {role}, zone_wide_two_doors_final_v3, weld OFF, SIM time (non-timing sim slot)',
        'split': role, 'judgment': 'COLLECTED_UNQUALIFIED', 'belief': f'role={role}',
        'scenario': case['map_id'], 'contact_profile': 'wrench_drive_provisional', 'seed': case['seed'],
        'outcome': case['status'], 'source_sha': COLLECT_SHA[:8], 'run_id': f'v101-{run}',
        'scope': SCOPE_COL, 'limits': 'Collection record only. Held-out errors (heldout runs) are the replay of the recorded commands through the fitted/other mean models, offline.',
        'stop_reason': f'{run}: protocol complete, check_sim_s {case["check_sim_s"]:.1f} (+ reset {case["reset_sim_s"]:.1f}); recorded self-issued commands vs SIM ground-truth displacement, ground truth read offline only.',
        'offline_source': ref(case_p),
        'offline_source_pointer': 'run result.json: check_sim_s, reset_sim_s, total_including_reset_cap_s, loadavg_start/end, host_start.concurrent_holders; heldout runs also heldout.json candidates.*.selection_windows/leg_windows filtered by run',
        'records': {'run_result_json': ref(top_p), **({'heldout_json': ref(HELD_P), 'fit_json': ref(FIT_P)} if role == 'heldout' else {'fit_json': ref(FIT_P)})},
        'offline_scalars': sc,
        'offline_scalar_scope': 'Run bookkeeping copied from the raw collection record; held-out end/max position errors (mm) copied from heldout.json for the three mean models (linear_diag = chosen, dev_fill = old DEV default, r4r5). SIM seconds; not wall/timing evidence.',
        'sim_s': case['check_sim_s'], 'model_calls': 0.0, 'success': True,
        'success_definition': 'calibration protocol complete (COLLECTED_UNQUALIFIED gate); not a robot task success, not a research result.',
        'hparam_metrics': hp,
        'texts': {'notes/no_model': 'No model calls (0). Commands recorded per run are not counted here (not recorded as a scalar in the collection result); response time not applicable.',
                  'notes/load': 'loadavg1 is the host 1-minute load at run start/end (parallel SIM-time collection allowed; not a timing benchmark).'}})

# ---- 2) fit + held-out summary ---------------------------------------------------------------------------------
lin = fit['forms']['linear_diag']
sc = {'offline/gain_forward': lin['gain'][0][0], 'offline/gain_left': lin['gain'][1][1], 'offline/gain_turn': lin['gain'][2][2],
      'offline/tau_forward_s': lin['tau_axis_s'][0], 'offline/tau_left_s': lin['tau_axis_s'][1], 'offline/tau_turn_s': lin['tau_axis_s'][2],
      'offline/tau_stop_s': lin['tau_stop_s'], 'offline/rmse_weighted': lin['rmse_weighted'], 'offline/fit_windows': float(fit['n_windows']),
      'offline/replicate_spread_rel': fit['replicate_spread_rel'],
      'offline/direct_gain_forward': fit['direct_usage_weighted_gain']['forward'],
      'offline/direct_gain_left': fit['direct_usage_weighted_gain']['left'],
      'offline/direct_gain_turn': fit['direct_usage_weighted_gain']['turn'],
      'offline/devfill_gain_forward': fit['comparators']['dev_fill']['gain'][0], 'offline/devfill_gain_left': fit['comparators']['dev_fill']['gain'][1],
      'offline/devfill_gain_turn': fit['comparators']['dev_fill']['gain'][2],
      'offline/noise_coverage_overall': held['noise_measured_coverage']['overall'],
      'gate/validated_dev': float(held['status'] == 'VALIDATED_DEV')}
for form in HELD_FORMS:
    c = held['candidates'][form]
    sc[f'offline/heldout_sel_rms_end_mm_{form}'] = 1000. * c['sel_rms_end_err_m']
    sc[f'offline/heldout_leg_rms_pos_mm_{form}'] = 1000. * c['leg_rms_pos_err_m']
for k, v in held['checks'].items():
    sc[f'gate/{k}'] = float(bool(v))
write('fit-linear_diag', {
    'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
    'family': 'v101-gain-fit', 'policy': 'zone-final-environment-gaincal-v101 (1.0.0) / fit_unloaded_gain_calibration.py',
    'case': 'calibration-gain-v101', 'condition': 'linear_diag form (chosen: baseline form), fit on fitA1+fitA2, evaluated on heldA3/heldM1/heldP1/heldP2',
    'split': 'fit+heldout', 'judgment': 'VALIDATED_DEV', 'belief': 'form=linear_diag',
    'scenario': 'zone_wide_two_doors_final_v3', 'contact_profile': 'wrench_drive_provisional', 'seed': 0,
    'outcome': held['status'], 'source_sha': COLLECT_SHA[:8], 'run_id': 'v101-fit-linear_diag',
    'scope': 'Unloaded r1 mean-model fit (gain, lag) and held-out replay of recorded commands. DEV_PILOT, not MEASURED_SIM. VALIDATED_DEV concerns the mean model; noise_measured_coverage_ok=false gates only the measured-noise variant (C2).',
    'limits': 'Provisional wrench drive model (SIM), unloaded r1 only; loaded model and sigma gates are not re-verified. Not real hardware.',
    'stop_reason': f'status {held["status"]}; chosen form {held["chosen_form"]} ({held["chosen_reason"]}); product C sha256 {sha(PROD_C)}',
    'offline_source': ref(HELD_P),
    'offline_source_pointer': 'heldout.json: candidates.<form>.sel_rms_end_err_m / leg_rms_pos_err_m, checks, noise_measured_coverage, status; fit.json: forms.linear_diag gain/tau_axis_s/tau_stop_s/rmse_weighted, comparators, direct_usage_weighted_gain',
    'records': {'fit_json': ref(FIT_P), 'product_C': ref(PROD_C), 'product_C2': ref(PROD_C2)},
    'offline_scalars': sc,
    'offline_scalar_scope': 'Fitted mean-model parameters and held-out end-position errors (mm) copied from fit.json/heldout.json. gain order forward/left/turn, tau order x/y/yaw (s). Gate flags are the pre-registered acceptance checks (1=pass).',
    'model_calls': 0.0, 'success': bool(held['status'] == 'VALIDATED_DEV'),
    'success_definition': 'pre-registered held-out acceptance rules passed for the mean model (VALIDATED_DEV); not a robot task success.',
    'hparam_metrics': ['evaluation/reported_success', 'result/model_calls', 'offline/gain_forward', 'offline/gain_left', 'offline/gain_turn',
                       'offline/tau_stop_s', 'offline/heldout_sel_rms_end_mm_linear_diag', 'offline/heldout_sel_rms_end_mm_dev_fill',
                       'offline/heldout_leg_rms_pos_mm_linear_diag', 'offline/noise_coverage_overall'],
    'texts': {'notes/no_model': 'No model calls (0); response time not applicable.'}})

# ---- 3) replay selection: per (config, seed) and per-config ensemble -----------------------------------------------
REPLAY_SCOPE = ('Offline replay of recorded v98 DEV probe inputs (r1, r2; until 60 s; seeds offset 0,101..104) through the #363 HEAD '
                f'{REPLAY_BASE_SHA} PF provider with candidate calibrations; truth scores the replay offline and never drives it. '
                f'NEES(2) bound chi2 99.9% = {BOUND}, median {MEDIAN}. DEV_PILOT, open-loop replay: not a robot task success, no SIM run, no model calls.')
tools = {'sel_summary_py': ref(PF / 'tools/sel_summary.py'), 'analyze_pf_py': ref(PF / 'tools/analyze_pf.py'), 'truth_trajectory_eval_only': ref(TRUTH_P, use='scoring only (evaluation, never control)')}
S_TABLE = sel['table']
sel_pre = sel['decision']['selected']
for cfg, tag in CFG_TAG.items():
    rows = {rid: sel['res'][f'{tag}/{rid}'] for rid in ('r1', 'r2')}
    rec_files = {f'replay_{rid}_s{s}': ref(PF / f'replay/ens_{tag}_{rid}_s{s}_until60.jsonl') for rid in ('r1', 'r2') for s in SEEDS}
    for seed in SEEDS:
        sc = {}
        for rid in ('r1', 'r2'):
            ps = rows[rid]['per_seed'][str(seed)]
            for win in WINS:
                sc[f'offline/nees_{rid}_w{win.replace("-", "_")}'] = ps['nees'][win]
            sc[f'offline/err_mm_{rid}'] = ps['err_mm']
            sc[f'gate/nees_in_bound_{rid}'] = float(all(ps['nees'][w] <= BOUND for w in SEL_WINS))
        write(f'sel-{cfg}-s{seed}', {
            'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
            'family': 'v101-replay-selection', 'policy': f'config {cfg}', 'case': 'raise_high probe replay (r1+r2, until 60 s)',
            'condition': CFG_TEXT[cfg], 'split': 'dev-ensemble', 'judgment': 'selected by pre-registered rule' if cfg == sel_pre else ('supplementary (excluded)' if cfg == 'C2' else 'compared'),
            'belief': f'cfg={cfg}', 'scenario': 'zone_wide_door_geometry_v3', 'contact_profile': 'cargo_noslip_v1', 'seed': seed,
            'outcome': 'REPLAYED', 'source_sha': REPLAY_BASE_SHA, 'run_id': f'v101-sel-{cfg}-s{seed}',
            'scope': REPLAY_SCOPE, 'limits': 'NEES/error windows are medians of per-tick values inside each window; err_mm = median |position error| 30-60 s (mm). Per-seed values; the registered score S uses medians over the 5 seeds.',
            'stop_reason': f'{cfg} seed {seed}: replay complete to 60 s, both robots scored offline.',
            'offline_source': ref(SEL_P),
            'offline_source_pointer': f'sel_summary.json res.{tag}/r1 and res.{tag}/r2 per_seed.{seed} (nees windows, err_mm)',
            'records': {**tools, **{k: v for k, v in rec_files.items() if k.endswith(f'_s{seed}')}},
            'offline_scalars': sc,
            'offline_scalar_scope': 'Per-seed window-median NEES(2) and median |error| copied from sel_summary.json (computed offline by sel_summary.py from the replay jsonl and eval-only truth). gate/nees_in_bound = windows 30-40/40-50/50-60 all <= 13.8.',
            'model_calls': 0.0,
            'hparam_metrics': ['result/model_calls', 'offline/err_mm_r1', 'offline/err_mm_r2', 'offline/nees_r1_w30_40', 'offline/nees_r1_w50_60',
                               'offline/nees_r2_w30_40', 'offline/nees_r2_w50_60', 'gate/nees_in_bound_r1', 'gate/nees_in_bound_r2'],
            'texts': {'notes/no_model': 'No model calls (0); replay of recorded inputs, no LLM, response time not applicable.',
                      'notes/eval_only': 'offline/nees_* and offline/err_mm_* are EVALUATION ONLY (scored from eval-only truth after the replay; never fed to control).'}})
    sc = {'offline/sel_score_S': S_TABLE[tag]['S'], 'offline/median_err_mm_r1_r2': S_TABLE[tag]['median_err_mm_r1_r2'],
          'gate/selected_by_prereg': float(cfg == sel_pre), 'gate/excluded_coverage': float(cfg == 'C2'), 'offline/n_seeds': 5.0}
    for rid in ('r1', 'r2'):
        e = rows[rid]
        assert e['n'] == 5 and e['seeds'] == SEEDS
        sc[f'offline/err_mm_{rid}'] = e['median_err_mm']
        sc[f'offline/err_min_mm_{rid}'], sc[f'offline/err_max_mm_{rid}'] = e['err_min_max']
        sc[f'offline/sigma_x_mm_{rid}'] = e['sigma_x_mm']
        for win in WINS:
            w = win.replace('-', '_')
            sc[f'offline/nees_{rid}_w{w}'] = e['median_nees'][win]
            sc[f'offline/seeds_in_bound_{rid}_w{w}'] = float(sum(e['per_seed'][str(s)]['nees'][win] <= BOUND for s in SEEDS))
    write(f'sel-{cfg}-ens', {
        'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
        'family': 'v101-replay-selection', 'policy': f'config {cfg}', 'case': 'raise_high probe replay ensemble (5 seeds, r1+r2, until 60 s)',
        'condition': CFG_TEXT[cfg], 'split': 'dev-ensemble', 'judgment': 'selected by pre-registered rule' if cfg == sel_pre else ('supplementary (excluded)' if cfg == 'C2' else 'compared'),
        'belief': f'cfg={cfg}', 'scenario': 'zone_wide_door_geometry_v3', 'contact_profile': 'cargo_noslip_v1', 'seed': 'ens5',
        'outcome': 'ENSEMBLE', 'source_sha': REPLAY_BASE_SHA, 'run_id': f'v101-sel-{cfg}-ens',
        'scope': REPLAY_SCOPE, 'limits': 'S = sum over r1,r2 and windows 30-40/40-50/50-60 of |log10(median NEES2 / 1.386)| (pre-registered; lower is better). Selection rule: C vs B only; C2 supplementary.',
        'stop_reason': f'{cfg}: S={S_TABLE[tag]["S"]:.3f}; median |err| 30-60 s (r1,r2 median) {S_TABLE[tag]["median_err_mm_r1_r2"]:.1f} mm; pre-registered decision: {sel_pre}.',
        'offline_source': ref(SEL_P),
        'offline_source_pointer': f'sel_summary.json table.{tag} and res.{tag}/r1, res.{tag}/r2 (median_nees, median_err_mm, err_min_max, sigma_x_mm, per_seed)',
        'records': {**tools, **rec_files},
        'offline_scalars': sc,
        'offline_scalar_scope': 'Ensemble statistics copied from sel_summary.json: nees_* = median over 5 seeds of per-seed window-median NEES(2); err_mm = median |position error| 30-60 s over seeds; seeds_in_bound = #seeds with window NEES <= 13.8 (of 5). Offline replay; not a task success.',
        'model_calls': 0.0,
        'hparam_metrics': ['result/model_calls', 'offline/sel_score_S', 'offline/err_mm_r1', 'offline/err_mm_r2', 'offline/nees_r1_w50_60', 'offline/nees_r2_w50_60',
                           'offline/seeds_in_bound_r1_w30_40', 'offline/seeds_in_bound_r2_w30_40', 'gate/selected_by_prereg'],
        'texts': {'notes/no_model': 'No model calls (0); replay of recorded inputs, no LLM, response time not applicable.',
                  'notes/eval_only': 'All offline/* values here are EVALUATION ONLY (scored from eval-only truth after the replay; never fed to control).',
                  'notes/selection': f'Pre-registered selection (PREREGISTRATION.md section 7 + ADDENDUM_selection_rule.md): candidates B and C, lowest S wins -> {sel_pre}. C2 excluded (coverage gate failed); HEAD as is is reference only.'}})
print('views written to', OUT, 'n =', len(list(OUT.iterdir())))
