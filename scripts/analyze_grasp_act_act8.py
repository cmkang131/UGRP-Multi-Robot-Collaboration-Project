"""ACT7 saved-evidence audit only: no simulator, renderer, model or network."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np

from harness.grasp_act_data import read_rows, read_json, sha256, write_json
from harness import grasp_act_contract as c


PHASES = ('approach', 'align')


def distribution(values):
    a = np.asarray(values, float)
    return dict(N=len(a), **({str(q): float(np.percentile(a, q)) for q in (0, 50, 90, 95, 99, 100)} if len(a) else {}))


def effort(command):
    """Issued pulse integral / control period, inverse of fixed wheel_mix."""
    w = np.asarray(command['wheels']) * np.minimum(command['duration_s'], .1) / .1
    return np.array([w.sum(), -w[0]+w[1]+w[2]-w[3], -w[0]+w[1]-w[2]+w[3]]) / 4


def relay(rows, key):
    """Pure command relay replay at the saved 1 ms physics clock; no physics.

    A pulse is overwritten at the next 100 ms control tick. Expiration is
    quantized up to 1 ms by DutyActPort.tick. Same sign can retain a latch.
    """
    state = np.zeros(4, int)
    attempted = np.zeros(4); blocked = np.zeros(4); integral = np.zeros(4)
    for row in rows:
        c = row[key]; w = np.asarray(c['wheels']); d = np.asarray(c['duration_s'])
        steps = np.clip(np.ceil((d-1e-9)/.001), 0, 100)
        active_s = steps*.001
        sign = np.sign(w).astype(int)
        on = (abs(w) > .325) | ((state != 0) & (sign == state) & (abs(w) > 1/12))
        attempted += (w != 0)*active_s
        blocked += ((w != 0) & ~on)*active_s
        integral += np.where(on, w-sign/12, 0.)*active_s
        state = np.where(on & (steps == 100), sign, 0)
    return {'attempted_wheel_s': attempted.tolist(), 'blocked_wheel_s': blocked.tolist(),
            'blocked_fraction': (blocked/np.maximum(attempted, 1e-12)).tolist(),
            'signed_effective_integral_u_s': integral.tolist()}


def stalled_intervals(rows, evaluations, *, window_s=3., progress_m=.01, require_motion=False):
    """Consecutive 3 s windows with <1 cm NET XY movement during approach.

    This is a descriptive net-progress measure, not path length or a cause.
    The union length of overlapping windows is reported separately.
    """
    n = round(window_s/.1); mask = np.zeros(len(rows), bool); windows = []
    xy = np.array([r['base_xyz'][:2] for r in evaluations])
    for i in range(len(rows)-n):
        if all(r['phase_before'] == 'approach' and r['phase_after'] == 'approach' for r in rows[i:i+n+1]):
            if require_motion and not all(any(r['clean_teacher_command']['wheels']) for r in rows[i:i+n+1]):
                continue
            if np.linalg.norm(xy[i+n]-xy[i]) < progress_m:
                mask[i:i+n+1] = True; windows.append(i)
    groups = np.split(np.flatnonzero(mask), np.where(np.diff(np.flatnonzero(mask)) > 1)[0]+1)
    spans = [{'start_t': rows[g[0]]['t'], 'end_t': rows[g[-1]]['t'],
              'duration_s': rows[g[-1]]['t']-rows[g[0]]['t']} for g in groups if len(g)]
    return {'windows_N': len(windows), 'intervals': spans,
            'longest_s': max((s['duration_s'] for s in spans), default=0.)}


def visibility_events(teachers):
    seen = False; lost = None; events = []
    for row in teachers:
        if row['phase'] not in (*PHASES, 'relook'):
            seen = False; lost = None; continue
        visible = row['visible_target'] is not None
        if seen and not visible: lost = row['t']
        if visible and lost is not None:
            events.append({'lost_t': lost, 'reacquired_t': row['t'], 'blind_s': row['t']-lost}); lost = None
        seen = visible
    return events


def analyze(outputs, destination):
    outputs = Path(outputs); admin = outputs/'e2e18-admin/gcp-reports'
    summary_path = admin/'act7-efb002ad.json'; summary = read_json(summary_path)
    sources = {str(summary_path): sha256(summary_path)}
    baseline = defaultdict(list); baseline_ids = defaultdict(list)
    baseline_commands = defaultdict(list); missing_baseline = []
    # Use only originals actually present here; the full census summary does
    # not contain pulse widths or target states for the missing originals.
    for seed in range(86000, 86050):
        root = outputs/f'gcp1-runs/solo-record-{seed}-6f057f7e/raw'
        path = root/'teacher-r1.jsonl.zst'
        if not path.exists():
            missing_baseline.append(seed); continue
        rows = read_rows(path); sources[str(path)] = sha256(path)
        kind = read_json(root/'plan.json')['kind']
        for r in rows:
            if r['teacher_phase'] in PHASES:
                key = ('pooled_box', r['teacher_phase']); correction = effort(r['clean_teacher_command'])
                baseline[key].append(correction)
                baseline_ids[key].append(seed); baseline_commands[key].append(correction)
    support = {}
    scale = np.array([.1, .1, .05])
    for key, points in baseline.items():
        a = np.array(points)/scale; ids = np.array(baseline_ids[key]); nearest = []
        for seed in np.unique(ids):
            query = a[ids == seed]; ref = a[ids != seed]
            nearest.extend(np.sqrt(((query[:, None]-ref[None, :])**2).sum(2).min(1)))
        support[key] = {'points': a, 'radius': float(np.percentile(nearest, 99)),
                        'correction_p99': float(np.percentile(np.linalg.norm(baseline_commands[key], axis=1), 99)),
                        'correction_max': float(np.linalg.norm(baseline_commands[key], axis=1).max())}
    runs = []; success_corrections = []; success_axes = []
    for entry in summary['runs']:
        seed = entry['seed']; name = entry['run']; root = outputs/'gcp1-runs'/name
        local_summary = read_json(admin/f'act7-efb002ad-ops/{name}-summary.json')
        if not root.exists():
            root = Path(local_summary['raw_local'])
        paths = [root/'recovery-commands.jsonl.zst', root/'raw/teacher-commands.jsonl.zst', root/'raw/eval-only.jsonl.zst']
        rows, teachers, evaluation = map(read_rows, paths)
        evaluation = [r for r in evaluation if 'base_xyz' in r]  # separate lookaround evaluation rows share timestamps
        for path in paths: sources[str(path)] = sha256(path)
        if not (len(rows) == len(teachers) == len(evaluation)): raise ValueError('unpaired evidence')
        if any(abs(a['t']-b['t']) > 1e-8 or abs(a['t']-e['t']) > 1e-8 for a,b,e in zip(rows,teachers,evaluation)):
            raise ValueError('unpaired timestamps')
        result_path = root/'raw/result.json'
        if not result_path.exists(): result_path = result_path.with_suffix('.json.zst')
        result = read_json(result_path); sources[str(result_path)] = sha256(result_path)
        if sha256(result_path) != entry['result_sha256']: raise ValueError('result hash differs from ACT7 summary')
        phases = [r for r in rows if r['phase_before'] == 'approach' and r['phase_after'] == 'approach']
        active = [r for r in rows if r['disturbance'] is not None]
        clipped = 0
        for row in active:
            candidate = np.array(c.encode_action(row['clean_teacher_command']))
            candidate[:8] += row['disturbance']['noise']
            clipped += bool((abs(candidate[:4])>.4).any() or (candidate[4:8]<0).any() or (candidate[4:8]>1).any())
            decoded = c.decode_action(candidate)
            expected = c.command({'t':row['t'],'wheels':decoded['wheels'],'duration_s':decoded['duration_s'],
                                  'pwm':row['clean_teacher_command']['pwm']})
            if not np.allclose(c.encode_action(expected),c.encode_action(row['applied_command']),rtol=0,atol=1e-12):
                raise ValueError('stored noise does not reproduce applied command')
        if clipped != local_summary['clipping']['bound_clip_ticks']:raise ValueError('clipping census differs')
        metrics = defaultdict(list); outside = 0; correction_tail = 0; correction_outside = 0; support_N = 0
        for r,t in zip(rows,teachers):
            if r['phase_before'] not in PHASES or t['visible_target'] is None: continue
            key = ('pooled_box', r['phase_before']); model = support[key]; m = t['visible_target']
            point = effort(r['clean_teacher_command'])/scale
            distance = float(np.sqrt(((model['points']-point)**2).sum(1).min()))
            correction = float(np.linalg.norm(effort(r['clean_teacher_command'])))
            outside += distance > model['radius']; correction_tail += correction > model['correction_p99']+1e-9
            correction_outside += correction > model['correction_max']+1e-9; support_N += 1
            metrics['nearest_correction_distance'].append(distance); metrics['clean_correction_norm'].append(correction)
        a = np.array([r['applied_command']['wheels'] for r in active])
        d = np.array([r['applied_command']['duration_s'] for r in active])
        ce = np.array([effort(r['clean_teacher_command']) for r in phases])
        ae = np.array([effort(r['applied_command']) for r in phases])
        run = {'seed': seed, 'kind': entry['kind'], 'physical_success': entry['physical_success'],
               'raw_local': str(root), 'approach_s': len(phases)*.1,
               'stall': stalled_intervals(rows,evaluation),
               'active_command_stall': stalled_intervals(rows,evaluation,require_motion=True),
               'visibility_reacquisitions': visibility_events(teachers),
               'support': {'N': support_N, 'correction_support_outside_loo99_N': int(outside),
                           'correction_above_p99_N': int(correction_tail), 'correction_above_max_N': int(correction_outside),
                           **{k: distribution(v) for k,v in metrics.items()}},
               'noise': {'ticks': len(active), 'bound_clip_ticks': clipped, 'stored_projection_reproduced':True,
                         'below_start_nonzero_N_per_wheel': ((abs(a) > 0) & (abs(a) <= .325)).sum(0).tolist(),
                         'nonzero_N_per_wheel': (a != 0).sum(0).tolist(),
                         'pulse_ms_per_wheel': [distribution(d[:,i][a[:,i] != 0]*1000) for i in range(4)],
                         'raw_noise_dimensions': [distribution([r['disturbance']['noise'][i] for r in active]) for i in range(8)]},
               'approach_clean_effort_axes': [distribution(ce[:,i]) for i in range(3)],
               'approach_applied_effort_axes': [distribution(ae[:,i]) for i in range(3)],
               'approach_clean_axis_sign_flips': ((ce[1:]*ce[:-1]) < 0).sum(0).tolist(),
               'relay_applied': relay(rows,'applied_command'), 'relay_clean_command_only': relay(rows,'clean_teacher_command')}
        run['relay_noisy_ticks'] = relay(active,'applied_command')
        if entry['physical_success']:
            success_corrections.extend(metrics['clean_correction_norm'])
            success_axes.extend(effort(r['clean_teacher_command']) for r in rows if r['phase_before'] in PHASES)
        if seed == 8316627:
            idx = [i for i,r in enumerate(rows) if 24-1e-8 <= r['t'] <= 60+1e-8]
            pos = np.array([evaluation[i]['base_xyz'][:2] for i in idx]); late = [rows[i] for i in idx]
            run['late_t24_60'] = {'N': len(idx), 'net_xy_m': float(np.linalg.norm(pos[-1]-pos[0])),
                'path_xy_m': float(np.linalg.norm(np.diff(pos,axis=0),axis=1).sum()),
                'xy_bbox_m': np.ptp(pos,axis=0).tolist(),
                'target_yaw_range_rad': distribution([teachers[i]['visible_target']['yaw'] for i in idx]),
                'finger_force_max_N': np.max([evaluation[i]['finger_forces'] for i in idx],axis=0).tolist(),
                'cargo_xy_range_m': np.ptp([evaluation[i]['cargo_xyz'][:2] for i in idx],axis=0).tolist(),
                'clean_zero_ticks': sum(not any(r['clean_teacher_command']['wheels']) for r in late),
                'visible_station_error_m': distribution([float(np.linalg.norm(
                    np.array(teachers[i]['visible_target']['xyz'][:2])-.2002*np.array([
                        np.cos(teachers[i]['visible_target']['yaw']),np.sin(teachers[i]['visible_target']['yaw'])]))) for i in idx]),
                'clean_effort_axes': [distribution([effort(r['clean_teacher_command'])[i] for r in late]) for i in range(3)],
                'applied_effort_axes': [distribution([effort(r['applied_command'])[i] for r in late]) for i in range(3)],
                'relay_applied': relay(late,'applied_command'), 'relay_clean_command_only': relay(late,'clean_teacher_command')}
        runs.append(run)
    successes = [r for r in runs if r['physical_success']]
    report = {'schema':'ugrp.act8.saved_audit.v1','source_act':'efb002ad9ecfda23b66c7f6b9c83d912765f8494',
        'teacher_dependency':'6f057f7e97c1a3aec9e8c398b8d9068e27b25df8',
        'physical_runs':0,'render_calls':0,'training_steps':0,'remote_connections':0,
        'baseline_episodes_available':50-len(missing_baseline),'missing_baseline_seeds':missing_baseline,
        'observed':29,'successes':28,'unsubmitted_blocked':11,'runs':runs,
        'success28': {'approach_s':distribution([r['approach_s'] for r in successes]),
            'longest_net_stall_s':distribution([r['stall']['longest_s'] for r in successes]),
            'runs_with_net_stall':sum(r['stall']['longest_s']>0 for r in successes),
            'longest_active_command_stall_s':distribution([r['active_command_stall']['longest_s'] for r in successes]),
            'runs_with_active_command_stall':sum(r['active_command_stall']['longest_s']>0 for r in successes),
            'visibility_reacquisitions':sum(len(r['visibility_reacquisitions']) for r in successes),
            'runs_with_reacquisition':sum(bool(r['visibility_reacquisitions']) for r in successes),
            'clean_correction_norm':distribution(success_corrections),
            'clean_correction_axes':[distribution(np.array(success_axes)[:,i]) for i in range(3)],
            'formal_full_baseline_state_ood_N':None,
            'support':{k:sum(r['support'][k] for r in successes) for k in ('N','correction_support_outside_loo99_N','correction_above_p99_N','correction_above_max_N')}},
        'definitions':{'correction_support':'same phase pooled-box noise-free2/50 available command trajectories clean issued correction (f,l,yaw effort), scale(.1,.1,.05); nearest distance > leave-one-episode-out p99 radius. Proxy for state novelty only; full state OOD unmeasured because 48/50 original command/visible-target logs are unavailable locally',
            'correction':'norm of clean teacher issued wheel pulse integrals, inverse wheel_mix / .1s; command magnitude, not measured motion',
            'causality':'support novelty and reacquisition describe noisy trajectories; no matched noise-off runs, so noise causation is unmeasured',
            'relay':'deterministic fixed v7 command relay replay; not wheel rotation/physics counterfactual',
            'contact_limit':'saved evaluation records target finger forces only; no base/roller/non-target contact pairs or wheel angle/velocity; physical obstruction cannot be excluded'},
        'baseline_support':{f'{k[0]}/{k[1]}':{a:b for a,b in v.items() if a!='points'} for k,v in support.items()},
        'artifacts':sources}
    write_json(destination,report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outputs',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); r=analyze(a.outputs,a.output)
    print(json.dumps({'success28':r['success28'],'failure':next(x for x in r['runs'] if not x['physical_success'])},indent=2))


if __name__=='__main__':main()
