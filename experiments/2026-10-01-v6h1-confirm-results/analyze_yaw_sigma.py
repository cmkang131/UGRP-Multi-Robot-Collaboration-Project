#!/usr/bin/env python3
"""Post-unblinding EXPLORATORY tabulation; no controller/PF/physics imports.

Reads existing JSON only. Does not rerun the sealed classifier or change its
PASS_A_B_SAFETY verdict. Optional figures are statistical plots, not SIM renders.
"""
import argparse
import ast
import csv
import dataclasses
import hashlib
import json
import math
import statistics
import subprocess
from collections import Counter
from pathlib import Path

RAW = Path('/Users/changmin/projects/ugrp/outputs/v6h1-confirm-4c6b439f-20260930')
SEALED = Path('/Users/changmin/projects/ugrp/outputs/v6h1-sealed-analysis-v2-20261001')
EXEC = '4c6b439f3f7c9a147c901f8b260a1e214d4eb396'
SEAL = '5be4330eca9b23d2cbde3657dcbb215ee1923b25'
PREFIX = 'experiments/2026-09-30-pair-v6h-carry/analysis/'
OLD = math.radians(3) * 1000
EPS = 1e-6


def quantile(values, p):
    v = sorted(values)
    k = (len(v) - 1) * p
    i = int(k)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (k - i)


def dist(v):
    return dict(n=len(v), min=min(v), median=statistics.median(v),
                p90=quantile(v, .9), max=max(v))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def source_gate(receipts):
    """Read exact historical blobs, not the current main's controller."""
    def blob(sha, name):
        data = subprocess.check_output(['git', 'show', f'{sha}:{name}'])
        receipts[f'{sha}:{name}'] = digest(data)
        return data
    policy = ast.parse(blob(EXEC, 'harness/zone_pair_v6_policy.py'))
    node = next(n for n in policy.body if isinstance(n, ast.Assign)
                and ast.unparse(n.targets[0]) == "POLICIES['b-v6h1']")
    flags = {k.arg: ast.literal_eval(k.value) for k in node.value.keywords}
    assert flags['loaded_gate_yaw_deg'] == (5., 4.)
    assert flags['loaded_k_xy'] == flags['loaded_k_yaw'] == 1.
    assert flags['door_relax_sigma_scope'] == 'probe_all_sweeps'
    guard_source = blob(EXEC, 'harness/zone_own_guards.py')
    # Pure historical gate smoke: isolated AST definitions only, no imports of
    # the controller, localizer, rendering, or simulation modules.
    names = {'GateProfile', 'loaded_gate_profile', '_finite', 'UncertaintyGate'}
    nodes = [n for n in ast.parse(guard_source).body
             if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names]
    ns = dict(dataclass=dataclasses.dataclass, replace=dataclasses.replace, math=math, Mapping=dict)
    exec(compile(ast.Module(body=nodes[:1], type_ignores=[]), 'frozen-gate', 'exec'), ns)
    base = ns['GateProfile']('loaded', .07, math.radians(3), .06, math.radians(2.5))
    ns.update(GATE_LOADED=base, GATE_UNLOADED=base)
    exec(compile(ast.Module(body=nodes[1:], type_ignores=[]), 'frozen-gate', 'exec'), ns)
    gate = ns['UncertaintyGate'](ns['loaded_gate_profile'](flags['loaded_gate_yaw_deg']))
    assert [gate.update(t, True, .04, .03) for t in (0., .2, .4)] == [None, None, 'exited']
    assert gate.allows(True, .04, .05219) and gate.allows(True, .04, math.radians(4.5))
    assert not gate.allows(True, .04, math.radians(5.01))
    assert gate.update(.5, True, .04, math.radians(5.01)) is None and gate.ok
    assert gate.update(1.1, True, .04, math.radians(5.01)) == 'entered'
    assert base.high_yaw_rad == math.radians(3)
    for name in ('m1_owncam_delivery', 'zone_pair_guards', 'zone_pair_geometry',
                 'zone_pair_executor', 'zone_own_executor', 'zone_own_team_host',
                 'owncam_localizer', 'owncam_pose_source', 'owncam_recovery_v6', 'owncam_carry_v6e'):
        blob(EXEC, f'harness/{name}.py')
    blob(EXEC, 'scripts/run_pair_stage_probes.py')
    gate = json.loads(blob(SEAL, PREFIX + 'analysis_gate.json'))
    blob(SEAL, PREFIX + 'classify_placements.py')
    assert gate['execution_source_sha'] == EXEC
    return flags, math.radians(flags['loaded_gate_yaw_deg'][0]) * 1000


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, default=RAW)
    p.add_argument('--sealed', type=Path, default=SEALED)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--figures', action='store_true')
    p.add_argument('--tb-derived', type=Path, help='NEW local derived-view directory')
    args = p.parse_args()
    for output in (args.output_dir, args.tb_derived):
        if output:
            assert not any(output.resolve() == x.resolve() or x.resolve() in output.resolve().parents
                           for x in (args.raw, args.sealed)), 'raw/sealed output forbidden'
    receipts, source_receipts = {}, {}
    flags, high = source_gate(source_receipts)

    def read(path, lines=False):
        data = path.read_bytes()
        receipts[str(path.resolve())] = digest(data)
        return [json.loads(x) for x in data.splitlines()] if lines else json.loads(data)

    sealed = read(args.sealed / 'sealed_analysis.json')
    assert sealed['summary']['full_verdict'] == 'PASS_A_B_SAFETY'
    classifier = read(args.sealed / 'classifier.json')
    rows = read(args.raw / 'cases.jsonl', lines=True)
    assert len(rows) == len({r['case_id'] for r in rows}) == 72
    assert Counter(r['seed'] for r in rows) == {941: 60, 943: 12}
    assert {r['case_id'] for r in rows} == {r['case_id'] for r in classifier['attempts']}
    assert all(r['class'] == 'PASS_CLEAN' for r in classifier['attempts'])
    cases, robots_out, curves = [], [], {}
    counts, frame_gaps, trace_gaps, pf_ages, pf_gaps = (Counter() for _ in range(5))
    frame_gaps_active, growth, slopes, snapshots = Counter(), [], [], []
    if args.tb_derived:
        args.tb_derived.mkdir(parents=True, exist_ok=False)
    for row in sorted(rows, key=lambda r: (r['seed'], r['cell'])):
        case_dir = args.raw / 'cases' / row['case_id'].replace('@', '_').replace(':', '_')
        robots = read(case_dir / 'robots.json')
        commands = read(case_dir / 'commands.json')
        result = read(case_dir / 'result.json')
        trace = read(case_dir / 'eval_only/trace.jsonl', lines=True)
        assert result['controller']['pair_policy'] == 'b-v6h1'
        assert result['door_relax'] is None and not result['door_relax_overrides']
        assert result['diag_patch'] is None and not row['first_failure']
        stop, entry = row['stop_sim_s'], row['entry_sim_s']
        l1 = row['chain']['legs'][1]
        tr = [s for s in trace if s['t'] >= entry - EPS]
        trace_gaps.update(round(b['t'] - a['t'], 6) for a, b in zip(tr, tr[1:]))
        pf = [s for s in tr if 'pf' in s]
        pf_gaps.update(round(b['t'] - a['t'], 6) for a, b in zip(pf, pf[1:]))
        pair, series = [], {}
        for rid in ('r1', 'r2'):
            frames = [f for f in robots[rid]['frames'] if f['t'] >= entry - EPS]
            active = [f for f in frames if f['t'] <= stop + EPS]
            peak = max(f['report']['std_yaw_rad'] for f in frames)
            peaks = [f for f in frames if f['report']['std_yaw_rad'] == peak]
            first, last = peaks[0], peaks[-1]
            phase = [s for s in row['chain']['timelines'][rid] if s[0] <= first['t'] + EPS][-1]
            assert peak == row['sigma_yaw_max'][rid]
            assert all(b['t'] > a['t'] for a, b in zip(frames, frames[1:]))
            gaps = [round(b['t'] - a['t'], 4) for a, b in zip(frames, frames[1:])]
            frame_gaps.update(gaps)
            frame_gaps_active.update(round(b['t'] - a['t'], 4) for a, b in zip(active, active[1:]))
            l1f = [f for f in active if f['t'] >= l1['start_sim_s'] - EPS]
            deltas = [1000 * (b['report']['std_yaw_rad'] - a['report']['std_yaw_rad'])
                      for a, b in zip(l1f, l1f[1:])]
            counts['L1_decreasing_frame_intervals'] += sum(d < -1e-9 for d in deltas)
            counts['L1_informative_frames'] += sum(f['report']['observation_quality'].get('informative', False) for f in l1f)
            growth.extend(deltas)
            slopes.append((l1f[-1]['report']['std_yaw_rad'] - l1f[-11]['report']['std_yaw_rad']) * 1000)
            ps = [s['pf'][rid] for s in pf]
            pf_ages.update(round(s['t'] - s['pf'][rid]['t'], 4) for s in pf)
            snapshots.extend(s['std_yaw_rad'] * 1000 for s in ps)
            counts['frame_samples'] += len(frames)
            counts['pf_samples'] += len(ps)
            counts['frames_over_3deg'] += sum(f['report']['std_yaw_rad'] * 1000 > OLD for f in frames)
            counts['frames_over_5deg'] += sum(f['report']['std_yaw_rad'] * 1000 > high for f in frames)
            counts['pf_over_3deg'] += sum(s['std_yaw_rad'] * 1000 > OLD for s in ps)
            counts['pf_over_5deg'] += sum(s['std_yaw_rad'] * 1000 > high for s in ps)
            after = [c for c in commands[rid] if c['t'] > first['t'] + EPS]
            hold = [c for c in commands[rid] if c['kind'] == 'hold' and abs(c['t'] - stop) < EPS]
            assert hold and not after and phase[1:] == [1, 'wait_lower']
            assert abs(first['t'] - stop - .2) < EPS and abs(last['t'] - stop - .4) < EPS
            counts['peak_plateau_stop_plus_0p2_to_0p4'] += 1
            counts['raw_peak_matches'] += 1
            counts['localizer_resets'] += row['localizer_resets_stat'][rid]
            counts['localizer_replacements'] += row['localizer_replaced'][rid]
            assert row['relook_calls'][rid] == ['begin_observation']
            counts['begin_observation_calls'] += 1
            counts['pregrasp_look_entries'] += sum(s[2] == 'pregrasp_look' for s in row['chain']['timelines'][rid])
            rec = dict(case=row['cell'], seed=row['seed'], robot=rid,
                       peak_mrad=peak * 1000, active_peak_mrad=max(f['report']['std_yaw_rad'] for f in active) * 1000,
                       peak_first_sim_s=first['t'], peak_last_sim_s=last['t'], peak_leg=phase[1], peak_stage=phase[2],
                       stop_sim_s=round(stop, 4), termination_sim_s=result['termination']['sim_s'],
                       peak_minus_stop_s=round(first['t'] - stop, 4), L1_duration_s=round(l1['end_sim_s'] - l1['start_sim_s'], 4),
                       last_fix_s=round(first['report']['last_fix_t'], 4), fix_age_at_peak_s=round(first['report']['fix_age_s'], 4),
                       gate_5deg_margin_mrad=high - peak * 1000, reference_3deg_margin_mrad=OLD - peak * 1000,
                       frame_max_gap_s=max(gaps), commands_after_peak=len(after),
                       PF_snapshot_peak_mrad=max(s['std_yaw_rad'] for s in ps) * 1000)
            robots_out.append(rec)
            pair.append(rec)
            series[rid] = [(f['t'], f['report']['std_yaw_rad'] * 1000) for f in frames]
        peak = max(pair, key=lambda r: r['peak_mrad'])
        cases.append({**peak, 'robot': peak['robot'], 'r1_peak_mrad': pair[0]['peak_mrad'], 'r2_peak_mrad': pair[1]['peak_mrad'],
                      'active_peak_mrad': max(r['active_peak_mrad'] for r in pair),
                      'PF_snapshot_peak_mrad': max(r['PF_snapshot_peak_mrad'] for r in pair)})
        name = f"{row['cell']}-s{row['seed']}"
        curves[name] = dict(series=series, stop=stop, l1=l1, timeline=row['chain']['timelines']['r1'])
        if args.tb_derived:
            view = dict(schema='ugrp.offline_audit_view.v1', derived_view_only=True,
                        offline_source=dict(path=str((case_dir / 'robots.json').resolve()), sha256=receipts[str((case_dir / 'robots.json').resolve())]),
                        offline_scalar_scope='EXPLORATORY post-unblinding own yaw reports; PASS_A_B_SAFETY unchanged; no new runs',
                        family='v6h1_yaw_exploratory', policy='b-v6h1', case=row['cell'], seed=row['seed'],
                        condition='exploratory primary' if row['seed'] == 941 else 'exploratory sensitivity', source_sha=EXEC,
                        offline_scalars={'offline/peak_mrad': peak['peak_mrad'], 'offline/actual_margin_mrad': peak['gate_5deg_margin_mrad']},
                        hparam_metrics=['offline/peak_mrad', 'offline/actual_margin_mrad'])
            view['texts'] = {'provenance/limits': '3 deg is historical reference; active gate 5 deg, low 4 deg. No model response time exists.'}
            d = args.tb_derived / name
            d.mkdir()
            write_json(d / 'result.json', view)
    summary = dict(scope='EXPLORATORY post-unblinding; no new trials; PASS_A_B_SAFETY unchanged',
                   execution_sha=EXEC, seal_sha=SEAL, policy_flags=flags,
                   gate_high_mrad=high, gate_low_mrad=math.radians(4) * 1000, reference_3deg_mrad=OLD,
                   frozen_gate_smoke='PASS (isolated pure AST definitions, no controller import)',
                   counts=dict(counts), frame_gap_s_counts=dict(frame_gaps), active_frame_gap_s_counts=dict(frame_gaps_active),
                   trace_gap_s_counts=dict(trace_gaps), pf_record_gap_s_counts=dict(pf_gaps), pf_age_s_counts=dict(pf_ages),
                   PF_snapshot_peak_mrad=max(snapshots), L1_frame_increment_mrad=dist(growth),
                   L1_last_second_slope_mrad_s=dist(slopes),
                   peak_stages=dict(Counter(f"L{r['peak_leg']}/{r['peak_stage']}" for r in robots_out)),
                   peak_first_sim_s=dist([r['peak_first_sim_s'] for r in cases]),
                   fix_age_at_peak_s=dist([r['fix_age_at_peak_s'] for r in robots_out]), distributions={})
    for seed, group in [('primary941', [r for r in cases if r['seed'] == 941]),
                        ('sensitivity943', [r for r in cases if r['seed'] == 943]), ('all72_descriptive_only', cases)]:
        summary['distributions'][seed] = {k: dist([r[k] for r in group]) for k in
            ('peak_mrad', 'active_peak_mrad', 'gate_5deg_margin_mrad', 'reference_3deg_margin_mrad')}
    # Re-read every used raw/sealed file: detects changes during this analysis.
    assert all(digest(Path(name).read_bytes()) == value for name, value in receipts.items())
    summary['input_sha256'] = receipts
    summary['source_blob_sha256'] = source_receipts
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / 'yaw_sigma_cases.csv', cases)
    write_csv(args.output_dir / 'yaw_sigma_robots.csv', robots_out)
    write_json(args.output_dir / 'yaw_sigma_summary.json', summary)
    if args.figures:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
        ax = axes[0]
        for seed, color in ((941, '#176ca4'), (943, '#e17a16')):
            group = [r for r in cases if r['seed'] == seed]
            ax.scatter([int(r['case'][1:]) for r in group], [r['peak_mrad'] for r in group], s=17, color=color, label=f'seed {seed}, n={len(group)}')
        ax.set(xlabel='Placement (C01-C60)', ylabel='Case peak yaw sigma (mrad)', title='72 recorded case peaks (not pooled inference)')
        ax = axes[1]
        c = curves['C59-s941']
        for rid in ('r1', 'r2'):
            ts, vs = zip(*c['series'][rid])
            ax.plot(ts, vs, label=rid, linewidth=1.3)
        ax.axvspan(c['l1']['start_sim_s'], c['stop'], alpha=.09, color='green', label='L1')
        ax.axvline(c['stop'], color='grey', linewidth=.8)
        ax.set(xlabel='SIM time (s)', ylabel='Own yaw sigma (mrad)', title='Largest recorded peak: C59, seed 941')
        for ax in axes:
            ax.axhline(high, color='#a32020', linestyle='--', label='Active HIGH: 5 deg')
            ax.axhline(math.radians(4)*1000, color='#947e00', linestyle=':', label='Active LOW: 4 deg')
            ax.axhline(OLD, color='grey', linestyle='--', label='Historical reference: 3 deg')
            ax.set_ylim(0, 96)
            ax.legend(fontsize=7, loc='upper left')
        fig.suptitle('EXPLORATORY after unblinding - PASS_A_B_SAFETY unchanged', fontsize=11)
        target = args.output_dir / 'yaw_sigma_margin.png'
        fig.savefig(target, dpi=150, metadata={'Software': 'analyze_yaw_sigma.py'})
        plt.close(fig)
        assert target.stat().st_size < 1024**2
    print(json.dumps({k: v for k, v in summary.items() if k not in ('input_sha256', 'source_blob_sha256')}, indent=2))


if __name__ == '__main__':
    main()
