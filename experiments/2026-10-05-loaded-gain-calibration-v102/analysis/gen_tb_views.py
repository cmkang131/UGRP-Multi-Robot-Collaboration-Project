#!/usr/bin/env python3
"""Derived TensorBoard views for the v102 loaded gain calibration (collection, fit/held-out, fcc5215f input replay).

Reads hashed raw/derived files only and writes one derived-view result.json per run under <out>.
scripts/export_offline_audit.py then converts each view to events (new snapshot, raw untouched).
Nothing is recomputed from truth here: collection bookkeeping is copied from the run result.json, fit and held-out
numbers from fit.json/heldout.json, replay numbers from leg_ens_summary.json / window_summary.json (written by
analysis/leg_ens_summary.py and analysis/window_summary.py from the replay jsonl and eval-only truth).
Usage: gen_tb_views.py <out_dir>
"""
import hashlib
import json
import math
import sys
from pathlib import Path

OUT = Path(sys.argv[1])
O = Path('/Users/changmin/projects/ugrp/outputs')
COL = O / 'calib-loaded-gain-v102-274a6206-20261005T0306Z'
FIT_P = O / 'calib-loaded-gain-v102-fit-20261005/fit.json'
HELD_P = O / 'calib-loaded-gain-v102-heldout-20261005/heldout.json'
PROD_P = O / 'calib-loaded-gain-v102-product-20261005/calibration_dev_pilot_loaded_v102.json'
PF = O / 'pf-loadedgain-v102-20261005'
SETS = {   # replay sets, both on #363 HEAD 14ba8b5e (the 7194637e replays were stopped before any finished; see README)
    'plan': dict(dir='replay_14ba8b5e', leg=PF / 'leg_ens_summary_replay_14ba8b5e.json', win=PF / 'window_summary_replay_14ba8b5e.json',
                 text='live partner plan armed (606/606 plan ticks matched as in the live run); UNFINISHED set: full replays only, rec 3-4 of 5 seeds, v102 5 of 5'),
    'noplan': dict(dir='replay_noplan', leg=PF / 'leg_ens_summary_replay_noplan.json', win=PF / 'window_summary_replay_noplan.json',
                   text='no partner plan (less faithful to the live run: 17 vs 14 resamples); complete 5-seed set incl. dead reckoning'),
}
RAW = O / 'v98-dev-probe-align_to_carry-fcc5215f/zone_wide_door_geometry_v3'
TRUTH_P = RAW / 'eval_only/trajectory.jsonl'
COLLECT_SHA = '274a6206cbfae194a318f5b0eb4e7495e3a7c89b'
REPLAY_BASE_SHA = '14ba8b5e'          # #363 HEAD the finished replays were run against (fcc5215f is the recorded run); 7194637e replays were stopped
SEEDS = [0, 101, 102, 103, 104]
WINS = ['20-60', '60-90', '90-140', '140-210', '210-260', '260-330', '330-360', '360-430', '20-430']
CFG_TEXT = {
    'rec': '#363 HEAD 14ba8b5e as is: the calibration the run was recorded with (v101 unloaded C aba4ac58 + old DEV loaded gain/lag, ramp map)',
    'v102': '#363 HEAD + v102 patch (affine dead zone u0) + v102 loaded calibration ce447ada (measured loaded gain/lag, affine map)'}
MODE_TEXT = {'meas': 'full replay (own frames update the PF)', 'nomeas': 'pure dead reckoning (every frame rejected)'}


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


def finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


fit = json.loads(FIT_P.read_text())
held = json.loads(HELD_P.read_text())
assert held['fit_sha256'] == sha(FIT_P) and held['status'] == 'VALIDATED_DEV'
prod = json.loads(PROD_P.read_text())
assert prod['loaded_gain_calibration']['bundle_id'] == 'zone-final-pair-loaded-gaincal-v102'
CAL_SHA = sha(PROD_P)
assert CAL_SHA == 'ce447ada62295d24c7f7a5929ce878e70fa297651e16ca192536f4a403cd8c5f', CAL_SHA
SCOPE_COL = ('DEV calibration collection (loaded pair carry, 2 robots + beam, SIM time, model calls 0). COLLECTED_UNQUALIFIED: protocol complete, '
             'not a robot task success, not a timing benchmark; loadavg is recorded per run, not controlled.')

# ---- 1) four collection runs -------------------------------------------------------------------------------
for run in ('latA', 'latB', 'fwdA', 'fwdB'):
    root = COL / run
    case_p, top_p = root / run / 'result.json', root / 'result.json'
    case = json.loads(case_p.read_text())
    assert case['run_id'] == run and case['status'] == 'COLLECTED_UNQUALIFIED' and case['protocol_complete'] is True and case['model_calls'] == 0
    g = fit['gate'][run]
    rows = [r for r in held['steady_table_all'] if r['run'] == run]
    n_fit = sum(r['role'] == 'fit' for r in rows)
    n_held = sum(r['role'] == 'heldout' for r in rows)
    sc = {'offline/seed': float(case['seed']), 'offline/reset_sim_s': case['reset_sim_s'], 'offline/check_sim_s': case['check_sim_s'],
          'offline/loadavg1_start': case['loadavg_start'][0], 'offline/loadavg1_end': case['loadavg_end'][0],
          'offline/concurrent_sim_holders_start': float(len(case['host_start']['concurrent_holders'])),
          'offline/steady_windows_fit': float(n_fit), 'offline/steady_windows_heldout': float(n_held),
          'offline/beam_z_min_m': g['beam_z_min'], 'offline/carrier_sep_min_m': g['sep_min'], 'offline/carrier_sep_max_m': g['sep_max'],
          'offline/yaw_drift_rad': g['yaw_drift_rad'],
          'gate/protocol_complete': 1.0, 'gate/carry_valid_all_samples': float(g['carry_valid_all_samples'])}
    write(f'col-{run}', {
        'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
        'family': 'v102-loaded-collection', 'policy': 'zone-final-pair-loaded-gaincal-v102 (1.0.0)',
        'case': case['check'], 'condition': f'loaded pair carry, {case["axis"]} axis run {run}, zone_wide_two_doors_final_v3, weld OFF, SIM time (non-timing sim slot)',
        'split': 'fit+heldout', 'judgment': 'COLLECTED_UNQUALIFIED', 'belief': f'axis={case["axis"]}',
        'scenario': case['map_id'], 'contact_profile': 'wrench_drive_provisional', 'seed': case['seed'],
        'outcome': case['status'], 'source_sha': COLLECT_SHA[:8], 'run_id': f'v102-{run}',
        'scope': SCOPE_COL, 'limits': 'Collection record only. Windows are scored offline against the recorded self-issued commands; ground truth is read offline only.',
        'stop_reason': f'{run}: protocol complete, check_sim_s {case["check_sim_s"]:.1f} (+ reset {case["reset_sim_s"]:.1f}); carry stayed valid on every sample (beam z min {g["beam_z_min"]:.3f} m).',
        'offline_source': ref(case_p),
        'offline_source_pointer': 'run result.json (check_sim_s, reset_sim_s, loadavg_start/end, host_start.concurrent_holders); fit.json gate.<run> (beam_z_min, sep_min/max, yaw_drift_rad); heldout.json steady_table_all filtered by run and role',
        'records': {'run_result_json': ref(top_p), 'fit_json': ref(FIT_P), 'heldout_json': ref(HELD_P)},
        'offline_scalars': sc,
        'offline_scalar_scope': 'Run bookkeeping copied from the raw collection record; validity gate values from fit.json; window counts from heldout.json steady_table_all. SIM seconds, loadavg is the host 1-minute load; not wall/timing evidence.',
        'sim_s': case['check_sim_s'], 'model_calls': 0.0, 'success': True,
        'success_definition': 'calibration protocol complete and carry valid on every sample (COLLECTED_UNQUALIFIED gate); not a robot task success, not a research result.',
        'hparam_metrics': ['evaluation/reported_success', 'result/sim_s', 'result/model_calls', 'offline/loadavg1_start', 'offline/loadavg1_end',
                           'offline/steady_windows_fit', 'offline/steady_windows_heldout', 'offline/beam_z_min_m'],
        'texts': {'notes/no_model': 'No model calls (0). Response time not applicable (calibration collection, scripted commands).',
                  'notes/load': 'loadavg1 is the host 1-minute load at run start/end (parallel SIM-time collection allowed; not a timing benchmark).'}})

# ---- 2) fit + held-out summary ---------------------------------------------------------------------------------
A = dict(zip(fit['forms']['A']['names'], fit['forms']['A']['params']))
sc = {'offline/gain_forward': A['forward.g'], 'offline/gain_left': A['left.g'], 'offline/u0_forward': A['forward.u0'], 'offline/u0_left': A['left.u0'],
      'offline/tau_forward_s': A['forward.tau'], 'offline/tau_left_s': A['left.tau'], 'offline/tau_stop_s': A['tau_stop'],
      'offline/rms_weighted_A': fit['forms']['A']['rms_weighted_residual'], 'offline/rms_weighted_R0': fit['forms']['R0']['rms_weighted_residual'],
      'offline/rms_weighted_R1': fit['forms']['R1']['rms_weighted_residual'], 'offline/fit_windows': float(fit['n_fit_windows']),
      'offline/tau_spread_rel_forward': held['tau_spread']['forward']['relative_spread'], 'offline/tau_spread_rel_left': held['tau_spread']['left']['relative_spread'],
      'offline/h3_fcc_leg_max_rel_diff': held['h3_fcc_leg']['max_rel_diff'], 'gate/validated_dev': float(held['status'] == 'VALIDATED_DEV'),
      'gate/h3_contact_profile_supported': float(held['h3_fcc_leg']['h3_supported'])}
for ax in ('forward', 'left'):
    pa = held['per_axis'][ax]
    for form in ('A', 'R0', 'R1'):
        m = pa['forms'][form]['metrics']
        sc[f'offline/heldout_rms_rel_{ax}_{form}'] = m['rms_rel']
        sc[f'offline/heldout_worst_step_rel_{ax}_{form}'] = m['worst_step_rel']
        sc[f'offline/heldout_worst_leg_rel_{ax}_{form}'] = m['worst_leg_rel']
        sc[f'gate/heldout_passes_{ax}_{form}'] = float(pa['forms'][form]['passes'])
    m = pa['current_model']['metrics']
    sc[f'offline/heldout_rms_rel_{ax}_current'] = m['rms_rel']
    sc[f'offline/heldout_worst_step_rel_{ax}_current'] = m['worst_step_rel']
    sc[f'offline/heldout_worst_leg_rel_{ax}_current'] = m['worst_leg_rel']
write('fit-affine', {
    'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
    'family': 'v102-loaded-fit', 'policy': 'zone-final-pair-loaded-gaincal-v102 (1.0.0) / fit_loaded_gain_calibration.py',
    'case': 'calibration-loaded-v102', 'condition': 'form A (affine dead zone, per-axis gain and lag) chosen by the pre-registered rule; fit on the fit windows of latA/latB/fwdA/fwdB, evaluated on the held-out windows',
    'split': 'fit+heldout', 'judgment': 'VALIDATED_DEV', 'belief': 'form=A',
    'scenario': 'zone_wide_two_doors_final_v3', 'contact_profile': 'wrench_drive_provisional', 'seed': 0,
    'outcome': held['status'], 'source_sha': COLLECT_SHA[:8], 'run_id': 'v102-fit-affine',
    'scope': 'Loaded pair mean-model fit (forward/left gain, dead zone u0, lag, stop lag) and held-out replay of recorded commands. DEV_PILOT, not MEASURED_SIM. Turn axis is NOT calibrated (unchanged).',
    'limits': 'Provisional wrench drive model (SIM); loaded forward/left only; turn axis, sigma gates and the loaded noise model are not re-verified. Not real hardware.',
    'stop_reason': f'status {held["status"]}; chosen form {held["chosen_form"]}; product sha256 {CAL_SHA}',
    'offline_source': ref(HELD_P),
    'offline_source_pointer': 'heldout.json: per_axis.<axis>.forms.<form>.metrics/passes, per_axis.<axis>.current_model.metrics, tau_spread, h3_fcc_leg, status; fit.json: forms.A/R0/R1 params and rms_weighted_residual, n_fit_windows',
    'records': {'fit_json': ref(FIT_P), 'product_calibration': ref(PROD_P)},
    'offline_scalars': sc,
    'offline_scalar_scope': 'Fitted mean-model parameters (gain order forward/left; u0 in command units; tau in s) and held-out relative displacement errors copied from fit.json/heldout.json. Gate flags are the pre-registered acceptance checks (1 = pass). "current" = the loaded model the run was recorded with (old DEV ramp), evaluated on the same held-out windows.',
    'model_calls': 0.0, 'success': bool(held['status'] == 'VALIDATED_DEV'),
    'success_definition': 'pre-registered held-out acceptance rules passed for the chosen mean model (VALIDATED_DEV); not a robot task success.',
    'hparam_metrics': ['evaluation/reported_success', 'result/model_calls', 'offline/gain_forward', 'offline/gain_left', 'offline/u0_forward', 'offline/u0_left',
                       'offline/tau_stop_s', 'offline/heldout_worst_step_rel_left_A', 'offline/heldout_worst_step_rel_left_R0', 'offline/heldout_worst_step_rel_left_current',
                       'offline/h3_fcc_leg_max_rel_diff'],
    'texts': {'notes/no_model': 'No model calls (0); response time not applicable.'}})

# ---- 3) replay of the recorded fcc5215f inputs (two sets, both on #363 14ba8b5e) -----------------------------------------
tools = {k: ref(PF / 'tools' / k) for k in ('replay_pf.py', 'analyze_pf.py', 'leg_summary.py', 'leg_ens_summary.py', 'window_summary.py')}
tools['truth_trajectory_eval_only'] = ref(TRUTH_P, use='scoring only (evaluation, never control)')
LEG_LIMIT = ('d_err = est - truth displacement over the leg (mm, estimate heading frame at leg start; includes the PF heading spread in dead-reckoning mode). '
             'ratio_vel = integral of the PF mean body velocity / truth displacement (model-only, heading-independent). nees2 = chi2(2) NEES at the leg end (median 1.386). '
             'Medians over the PF seeds that finished (n_seeds).')
for sname, S in SETS.items():
    leg = json.loads(S['leg'].read_text())
    win = json.loads(S['win'].read_text())
    crit = leg['criterion_median_abs_derr_mm']
    scope = ('Offline replay of the recorded fcc5215f own-camera frames and self-issued commands (r1, r2; whole run ~430 s; PF seed offsets 0,101..104) through the '
             f'#363 HEAD {REPLAY_BASE_SHA} PF provider ({S["text"]}); truth scores the replay offline and never drives it. '
             'DEV_PILOT, open-loop replay: not a robot task success, no SIM run, no model calls. The #363 7194637e replays were stopped (coordinator) and are not used.')
    legs_of = {}
    for key, v in leg['per_leg'].items():
        cfg, mode, rid, k = key.split('/')
        legs_of.setdefault((cfg, mode), {}).setdefault(rid, {})[int(k)] = v
    for (cfg, mode), per in sorted(legs_of.items()):
        sc = {}
        for rid, ks in per.items():
            for k, v in sorted(ks.items()):
                tag = f'{rid}_leg{k}_{v["axis"]}'
                for name, field in (('d_err_mm', 'd_err_mm'), ('ratio_vel', 'ratio_vel'), ('ratio_est', 'ratio_est'), ('nees2', 'nees2')):
                    if finite(v[field]):
                        sc[f'offline/{name}_{tag}'] = v[field]
        sc['offline/n_seeds_min'] = float(min(v['n'] for ks in per.values() for v in ks.values()))
        if mode == 'meas':
            for rid in ('r1', 'r2'):
                for w in WINS:
                    e = win[f'{rid}/{w}'][cfg]
                    tag = f'{rid}_w{w.replace("-", "_")}'
                    sc[f'offline/win_err_mm_{tag}'], sc[f'offline/win_nees2_{tag}'], sc[f'offline/win_max_err_mm_{tag}'] = e
        for axis in ('left', 'forward'):
            if finite(crit[f'{cfg}/{mode}/{axis}']):
                sc[f'offline/crit_median_abs_derr_mm_{axis}'] = crit[f'{cfg}/{mode}/{axis}']
        if mode == 'nomeas':
            sc['gate/crit_nomeas_left_le_20mm'] = float(crit[f'{cfg}/nomeas/left'] <= 20.)
        hp = ['result/model_calls', 'offline/crit_median_abs_derr_mm_left', 'offline/crit_median_abs_derr_mm_forward', 'offline/n_seeds_min']
        if mode == 'meas':
            hp += ['offline/win_err_mm_r1_w20_430', 'offline/win_err_mm_r2_w20_430', 'offline/win_nees2_r1_w20_430', 'offline/win_nees2_r2_w20_430']
        write(f'rep-{sname}-{cfg}-{mode}', {
            'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
            'family': 'v102-fcc5215f-replay', 'policy': f'config {cfg}', 'case': f'align_to_carry fcc5215f input replay ({sname} set, r1+r2, whole run)',
            'condition': f'{CFG_TEXT[cfg]}; {MODE_TEXT[mode]}; {S["text"]}', 'split': 'dev-replay', 'judgment': 'compared',
            'belief': f'cfg={cfg}, mode={mode}, set={sname}', 'scenario': 'zone_wide_door_geometry_v3', 'contact_profile': 'cargo_noslip_v1', 'seed': 'ens',
            'outcome': 'REPLAYED', 'source_sha': REPLAY_BASE_SHA, 'run_id': f'v102-rep-{sname}-{cfg}-{mode}',
            'scope': scope, 'limits': LEG_LIMIT + ' Window values: median over seeds of the per-seed window median |position error| (mm) / NEES2 / max error (mm); the windows are ad hoc, not registered.',
            'stop_reason': f'{sname}/{cfg}/{mode}: median |d_err| left legs {crit[f"{cfg}/{mode}/left"]:.1f} mm, forward legs {crit[f"{cfg}/{mode}/forward"]:.1f} mm.',
            'offline_source': ref(S['leg']),
            'offline_source_pointer': f'{S["leg"].name} per_leg.{cfg}/{mode}/<robot>/<leg> and criterion_median_abs_derr_mm; {S["win"].name} <robot>/<window>.{cfg}',
            'records': {**tools, 'window_summary_json': ref(S['win']), 'calibration_v102': ref(PROD_P)},
            'offline_scalars': sc,
            'offline_scalar_scope': 'Per-leg medians over the PF seeds that finished and window medians copied from the summary jsons (computed offline from the replay jsonl and eval-only truth). Evaluation only.',
            'model_calls': 0.0, 'hparam_metrics': hp,
            'texts': {'notes/no_model': 'No model calls (0); replay of recorded inputs, no LLM, response time not applicable.',
                      'notes/eval_only': 'All offline/* values are EVALUATION ONLY (scored from eval-only truth after the replay; never fed to control).',
                      'notes/legs': 'leg index per robot follows the commands.jsonl order: 0-2 forward (0.0443), 3-4 lateral carry (0.0622), 5 align (0.0208).'}})
    # rec vs v102 comparison of this set
    sc, modes = {}, [m for m in ('nomeas', 'meas') if finite(crit[f'rec/{m}/left']) and finite(crit[f'v102/{m}/left'])]
    for mode in modes:
        for axis in ('left', 'forward'):
            a, b = crit[f'rec/{mode}/{axis}'], crit[f'v102/{mode}/{axis}']
            sc[f'offline/crit_{mode}_{axis}_rec_mm'], sc[f'offline/crit_{mode}_{axis}_v102_mm'], sc[f'offline/crit_{mode}_{axis}_delta_mm'] = a, b, b - a
    if 'nomeas' in modes:
        sc['gate/crit_nomeas_left_le_20mm_v102'] = float(crit['v102/nomeas/left'] <= 20.)
        sc['gate/crit_nomeas_left_v102_lt_rec'] = float(crit['v102/nomeas/left'] < crit['rec/nomeas/left'])
    if 'meas' in modes:
        sc['gate/crit_meas_left_v102_le_rec'] = float(crit['v102/meas/left'] <= crit['rec/meas/left'])
        sc['gate/crit_meas_forward_v102_within_5mm'] = float(crit['v102/meas/forward'] - crit['rec/meas/forward'] <= 5.)
        for rid in ('r1', 'r2'):
            for w in WINS:
                sc[f'offline/win_diff_mm_{rid}_w{w.replace("-", "_")}'] = win[f'{rid}/{w}']['diff_mm']
            sc[f'gate/windows_within_5mm_{rid}'] = float(sum(win[f'{rid}/{w}']['diff_mm'] <= 5. for w in WINS[:-1]))
    hp = ['result/model_calls'] + [f'offline/crit_{m}_left_{c}_mm' for m in modes for c in ('rec', 'v102')] + [f'offline/crit_{m}_forward_delta_mm' for m in modes]
    hp += (['gate/crit_nomeas_left_le_20mm_v102'] if 'nomeas' in modes else []) + (['gate/crit_meas_left_v102_le_rec', 'gate/windows_within_5mm_r1', 'gate/windows_within_5mm_r2'] if 'meas' in modes else [])
    write(f'rep-{sname}-compare', {
        'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
        'family': 'v102-fcc5215f-replay', 'policy': f'v102 minus rec ({sname} set)', 'case': 'align_to_carry fcc5215f input replay: registered criteria (PREREGISTRATION section 8)',
        'condition': f'difference between the v102 configuration and the recorded configuration, same replay; {S["text"]}', 'split': 'dev-replay',
        'judgment': 'criteria reported as measured (see gate/*)', 'belief': f'cfg=v102 vs rec, set={sname}', 'scenario': 'zone_wide_door_geometry_v3', 'contact_profile': 'cargo_noslip_v1', 'seed': 'ens',
        'outcome': 'REPLAYED', 'source_sha': REPLAY_BASE_SHA, 'run_id': f'v102-rep-{sname}-compare', 'scope': scope,
        'limits': 'gate/* are the registered replay criteria read from the numbers (1 = met, 0 = not met); modes absent from this set are not reported. windows_within_5mm_<robot> counts the 8 ad hoc windows (not the whole-run row) where v102 is at most 5 mm worse than rec.',
        'stop_reason': ' / '.join(f'{m}: left legs v102 {crit[f"v102/{m}/left"]:.1f} mm vs rec {crit[f"rec/{m}/left"]:.1f} mm' for m in modes),
        'offline_source': ref(S['leg']), 'offline_source_pointer': f'{S["leg"].name} criterion_median_abs_derr_mm; {S["win"].name} <robot>/<window>.diff_mm',
        'records': {**tools, 'window_summary_json': ref(S['win']), 'calibration_v102': ref(PROD_P)},
        'offline_scalars': sc,
        'offline_scalar_scope': 'Median |d_err| over (seed, leg, robot) values for the lateral and forward carry legs, per mode and config, plus the window differences (v102 minus rec, mm). Copied from the summary jsons. Evaluation only.',
        'model_calls': 0.0, 'hparam_metrics': hp,
        'texts': {'notes/no_model': 'No model calls (0); replay of recorded inputs, no LLM, response time not applicable.',
                  'notes/eval_only': 'All offline/* values are EVALUATION ONLY (scored from eval-only truth after the replay; never fed to control).'}})
print('views written to', OUT, 'n =', len(list(OUT.iterdir())))
