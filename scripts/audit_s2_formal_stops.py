"""s2v41: saved-record audit only. No simulator, controller edits or thresholds."""
import argparse
import bisect
import hashlib
import json
import math
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

OUTPUTS = Path('/Users/changmin/projects/ugrp/outputs')
RUNS = {1051: 's2-realism-b2de2b30-s1051-landmark-full',
        1053: 's2-realism-027c567c-s1053-v133-reproduction',
        1054: 's2-realism-027c567c-s1054-v133-reproduction'}
# Reporting references, NOT proposed controller settings: preserve all three
# sensitivity budgets. 25cm is the earlier start diagnostic criterion, not an
# E2E safe-navigation guarantee. Yaw5deg is reported separately.
ERROR_BUDGETS_M = (.05, .10, .25)
YAW_REFERENCE_RAD = math.radians(5)


def read(p): return json.loads(p.read_text())
def rows(p): return [json.loads(x) for x in p.read_text().splitlines()]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def wrap(x): return math.atan2(math.sin(x), math.cos(x))
def uncertain(p): return p['std_xy_m'] > .05 or p['std_yaw_rad'] > YAW_REFERENCE_RAD or p['last_fix_t'] is None


def decisions(record):
    """Every drive call: selected pulse OR arrived checkpoint/search transition.

    No pulse-resolution/path failure/recovery branches occurred in this cohort.
    Assert completeness against counters AND every downsampled occurrence/time.
    """
    assert not record.get('slip_recovery', {}).get('recoveries', 0)
    assert all(record['dev_light_would_stop'].get(k, 0) == 0 for k in
               ('PULSE_RESOLUTION_LIMIT', 'PATH_COLLISION_GUARD', 'SLIP_RECOVERY_EXHAUSTED'))
    poses = {round(p['t'], 6): p for p in record['poses']}
    times = {r['t']: r['state'] for r in record['pulse_motion_model']['transformations']}
    for e in record['events']:
        if e['event'] == 'carry_checkpoint': times[e['t']] = 'carry'
        if e['event'] == 'state' and e['state'] == 'search': times[e['t']] = 'search_move'
    output = [dict(t=t, phase='carry' if state == 'carry' else 'start_approach',
                   state=state, pose=poses[round(t, 6)], alarm=uncertain(poses[round(t, 6)]))
              for t, state in sorted(times.items())]
    alarms = [q for q in output if q['alarm']]
    assert len(alarms) == record['dev_light_would_stop']['POSE_UNCERTAIN']
    for e in record['events']:
        if e.get('event') == 'dev_light_would_stop' and e.get('code') == 'POSE_UNCERTAIN':
            assert abs(alarms[e['occurrence']-1]['t'] - e['t']) < 1e-8
    return output


def truth_at(truth, t):
    times = [q['t'] for q in truth]
    if not times[0] <= t <= times[-1]:
        raise ValueError('evaluation time outside recorded trajectory')
    xyz = [np.interp(t, times, [q['robot_xyz_m'][j] for q in truth]) for j in (0, 1)]
    yaw = np.interp(t, times, np.unwrap([q['robot_yaw_rad'] for q in truth]))
    return [*xyz, float(yaw)]


def distribution(values):
    return dict(zip(('min', 'median', 'p90', 'max'), map(float, np.quantile(values, [0, .5, .9, 1])))) if values else None


def pose_audit(record, truth):
    output = []
    for q in decisions(record):
        p = q['pose']; gt = truth_at(truth, p['t_est'])
        e = np.array([p['x']-gt[0], p['y']-gt[1]])
        modes = p['observation_quality'].get('diagnostics', {}).get('pose_estimate', {})
        covariance = np.asarray(modes.get('selected_cluster_cov', []))
        # Overall covariance is not saved as a matrix in PoseReport. It equals
        # the saved cluster XY covariance only with one cluster and matching trace.
        nees = None
        valid_cov = (modes.get('cluster_count') == 1 and covariance.shape == (3, 3)
                     and np.isclose(np.trace(covariance[:2, :2]), p['std_xy_m']**2, rtol=1e-7, atol=1e-10)
                     and np.linalg.eigvalsh(covariance[:2, :2]).min() > 0)
        if valid_cov: nees = float(e @ np.linalg.solve(covariance[:2, :2], e))
        fix_age = None if p['last_fix_t'] is None else p['t_est']-p['last_fix_t']
        output.append(dict(t=q['t'], t_est=p['t_est'], phase=q['phase'], alarm=q['alarm'],
            xy_error_m=float(np.linalg.norm(e)), yaw_error_deg=abs(math.degrees(wrap(p['yaw']-gt[2]))),
            std_xy_m=p['std_xy_m'], std_yaw_deg=math.degrees(p['std_yaw_rad']),
            trigger=dict(xy_sigma=p['std_xy_m']>.05, yaw_sigma=p['std_yaw_rad']>YAW_REFERENCE_RAD,
                         missing_fix=p['last_fix_t'] is None),
            fix_age_s=fix_age, cluster_count=modes.get('cluster_count'),
            maximum_cluster_mass=modes.get('maximum_cluster_weight'),
            low_mass_multimodal=modes.get('uncertain'), nees_xy=nees,
            nees_scope='one cluster and matching overall trace only; XY Gaussian approximation; descriptive, temporally correlated'))
    def summarize(samples):
        return dict(count=len(samples), xy_error_m=distribution([q['xy_error_m'] for q in samples]),
            std_xy_m=distribution([q['std_xy_m'] for q in samples]),
            yaw_error_deg=distribution([q['yaw_error_deg'] for q in samples]),
            std_yaw_deg=distribution([q['std_yaw_deg'] for q in samples]),
            fix_age_s=distribution([q['fix_age_s'] for q in samples if q['fix_age_s'] is not None]),
            triggers=dict(Counter('+'.join(k for k,v in q['trigger'].items() if v) or 'none' for q in samples)),
            clusters=dict(Counter(str(q['cluster_count']) for q in samples)),
            low_mass_multimodal=sum(q['low_mass_multimodal'] is True for q in samples),
            below_budget={str(b):sum(q['xy_error_m']<=b for q in samples) for b in ERROR_BUDGETS_M},
            below_25cm_and_5deg=sum(q['xy_error_m']<=.25 and q['yaw_error_deg']<=5 for q in samples),
            nees=dict(available=sum(q['nees_xy'] is not None for q in samples),
                distribution=distribution([q['nees_xy'] for q in samples if q['nees_xy'] is not None]),
                above_chi2_95=sum(q['nees_xy'] is not None and q['nees_xy']>5.991464547107979 for q in samples)),
            fix_age_over_30s=sum(q['fix_age_s'] is not None and q['fix_age_s']>30 for q in samples))
    flagged = [q for q in output if q['alarm']]
    return dict(decision_rows=output, alarm_count=len(flagged), all_alarms=summarize(flagged),
        no_alarm=summarize([q for q in output if not q['alarm']]),
        phases={phase:summarize([q for q in flagged if q['phase']==phase])
                for phase in ('start_approach', 'pick', 'carry', 'place')},
        completeness='all counter totals and sparse occurrence timestamps exactly reproduced')


def arm_audit(record, truth, contacts):
    from harness import zone_solo_cyan_v106 as v
    from harness.zone_solo_cyan_contract_v106 import MAP_ID
    from harness.zone_own_guards import OwnPose
    guard = v.SweepGuardV3(v.hp.resolve(MAP_ID)[0])
    poses = {round(p['t'],6):p for p in record['poses']}
    commands = record['commands']; initial = commands[0]
    assert initial['kind'] == 'initial_servo_command'
    targets = [(1.4+1.5*i, {**v.LOOK_P20,6:pan}) for i,pan in enumerate(v.LOOK_PANS)]
    targets.append((10.4, {**v.pose_of('search'),1:2000}))
    output = []
    for t, target in targets:
        servo = {int(k):val for k,val in initial['pulses'].items()}
        for cmd in commands:
            if cmd['t']>=t-1e-8:break
            if cmd['kind']=='arm':servo[cmd['servo_id']]=cmd['pulse']
            if cmd['kind']=='look':servo[6]=cmd['pan_pulse']
        p=poses[round(t,6)];own=OwnPose(p['x'],p['y'],p['yaw'],p['std_xy_m'],p['std_yaw_rad'])
        gt=truth_at(truth,t);actual=OwnPose(*gt,0.,0.)
        diag=guard.transition_diagnostic(servo,target,own,loaded=False)
        no_sigma=guard.transition_diagnostic(servo,target,replace(own,std_xy=0.,std_yaw=0.),loaded=False)
        gt_diag=guard.transition_diagnostic(servo,target,actual,loaded=False)
        assert not guard.transition_clear(servo,target,own,loaded=False)
        output.append(dict(t=t,phase='initial_scan' if t<10.4 else 'SEARCH_return',
            target=target,current=servo,own=diag['limiting'],same_estimate_zero_sigma=no_sigma['limiting'],
            eval_gt_zero_sigma=gt_diag['limiting'],
            wall_positive_force_samples=sum(any(c['normal_force_n']>0 for c in row['contacts'])
                for row in contacts if t<=row['t']<t+1.5)))
    assert len(output)==record['dev_light_would_stop']['ARM_COLLISION_GUARD']
    return dict(rows=output,scope='all seven initial scan queue vetoes; GT static sweep is posthoc only; wall contact logs do not certify self/other-robot clearance',
        limiting_walls=dict(Counter(q['own']['wall_id'] for q in output)),
        eval_gt_clearance_mm=distribution([q['eval_gt_zero_sigma']['clearance_mm'] for q in output]),
        actual_wall_contact_samples=sum(q['wall_positive_force_samples'] for q in output))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);runs=[]
    for seed, name in RUNS.items():
        raw=OUTPUTS/name;record=read(raw/'student_record.json');truth=rows(raw/'eval_only/trajectory.jsonl')
        result=dict(seed=seed,raw=str(raw),pose=pose_audit(record,truth),
            arm=arm_audit(record,truth,rows(raw/'eval_only/wall-contacts.jsonl')),
            hashes={k:sha(raw/k) for k in ['student_record.json','result.json','bundle.json',
                'eval_only/trajectory.jsonl','eval_only/wall-contacts.jsonl']})
        (args.output/f's{seed}.json').write_text(json.dumps(result,indent=2)+'\n')
        summary={**result,'pose':{k:v for k,v in result['pose'].items() if k!='decision_rows'}}
        runs.append(summary);print(seed,summary['pose']['all_alarms'],flush=True)
    out=dict(schema='ugrp.s2.formal_stop_audit.v1',physics_runs=0,controller_changes=0,
        threshold_changes=0,source_sha='14a48b2d043389393fcf8e82e88a33bfb7172eb7',
        reference_budgets_m=ERROR_BUDGETS_M,not_formal_safety_qualification=True,runs=runs,
        raw=str(args.output),hashes={q.name:sha(q) for q in args.output.glob('s*.json')})
    (args.output/'result.json').write_text(json.dumps(out,indent=2)+'\n')

if __name__=='__main__':main()
