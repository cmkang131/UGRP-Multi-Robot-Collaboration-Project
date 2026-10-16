"""GCP2-only reporting ratios and reversal strata; no acceptance retuning."""
import argparse
from collections import Counter
from pathlib import Path

from harness import grasp_act_contract as c
from harness.grasp_act_data import read_json,write_json
from scripts.analyze_grasp_act_act16a import require_cpu,stats


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();require_cpu();m=read_json(a.report/'metrics.json');runs=read_json(a.report/'runs.json')
    rows={}
    for scope,key,copy_key in [('issued','errors_by_phase','copycat'),('refresh_only','refresh_only_errors','refresh_only_copycat')]:
        rows[scope]={}
        for phase in ('ALL','approach','align','relook'):
            if phase not in m[key]:continue
            x=m[key][phase];cp=m[copy_key][phase]
            rows[scope][phase]=dict(n=x['act']['wheel_mae']['n'],
                act_wheel_mae=x['act']['wheel_mae']['mean'],persistence_wheel_mae=x['persistence']['wheel_mae']['mean'],
                wheel_mae_improvement_percent=(1-x['act']['wheel_mae']['mean']/x['persistence']['wheel_mae']['mean'])*100,
                act_sign_mismatch=x['act']['wheel_sign_mismatch']['mean'],persistence_sign_mismatch=x['persistence']['wheel_sign_mismatch']['mean'],
                act_pulse_mae_ms=x['act']['pulse_mae_ms']['mean'],persistence_pulse_mae_ms=x['persistence']['pulse_mae_ms']['mean'],
                act_pwm_mae=x['act']['pwm_mae']['mean'],persistence_pwm_mae=x['persistence']['pwm_mae']['mean'],
                previous_sign_agreement=cp['agree']/cp['wheel_rows'] if cp['wheel_rows'] else None,
                corrective_wheels=cp['corrective'],copied_on_correction=cp['copied']/cp['corrective'] if cp['corrective'] else None,
                matched_on_correction=cp['correct']/cp['corrective'] if cp['corrective'] else None)
    events=read_json(a.report/'reversal-events.json')
    long=[r for r in events if r['requires_response'] and r['target_dwell_s']+1e-8>=c.CHUNK*c.PERIOD_S]
    reverse=dict(stratum_min_dwell_s=c.CHUNK*c.PERIOD_S,
        basis='existing8-action chunk x0.1s; descriptive stratum, not an added acceptance criterion',events=len(long),
        **{policy:dict(matched=sum(r[policy+'_delay_s'] is not None for r in long),
            censored=sum(r[policy+'_delay_s'] is None for r in long),
            matched_delay_s=stats([r[policy+'_delay_s'] for r in long if r[policy+'_delay_s'] is not None])) for policy in ('act','persistence')})
    done=[r for r in runs if r['done_times']]
    record=dict(rows=rows,long_dwell_reversals=reverse,
        done=dict(requested=len(done),without_stable_lift=sum(not r['stable_lift'] for r in done),
            times_world_sim_s=stats([next(iter(r['done_times'].values())) for r in done]),
            first_failed_gate=dict(Counter(r['first_failed_gate'] for r in done))),
        original_recovery_training_fraction=6161/22852,
        recovery_fraction_scope='Original ACT15 row counts from saved data report, not a measured perturbation diversity distribution',
        candidate_evidence=dict(history='persistence-relative errors, refresh-only corrective copying and post-hoc mask sensitivity; causal effect pending matched retraining',
            rgb='visual boundary loss also occurs in successful teacher; resolution-vs-shift benefit unmeasured',
            recovery='original recovery share~27%; off-policy labels are not actual expert future trajectories; full distribution unavailable'))
    write_json(a.report/'compact-metrics.json',record)
    print(record)


if __name__=='__main__':main()
