"""Read-only old-raw decomposition. Evaluation truth never enters a controller."""
import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path


def diagnose(raw):
    files = ('student_record.json', 'pair-grip-epochs.jsonl', 'pair-route.json',
             'eval_only/referee_truth.jsonl')
    s = json.loads((raw/files[0]).read_text())
    epochs = [json.loads(v) for v in (raw/files[1]).read_text().splitlines()]
    truth = [json.loads(v) for v in (raw/files[3]).read_text().splitlines()]
    times = [v['t'] for v in truth]
    def at(t):
        row = truth[min(len(truth)-1, bisect.bisect_left(times, t))]
        return dict(t=row['t'], **row['items']['beam_1'])
    def delta(a, b): return [b[k]-a[k] for k in ('x', 'y')]
    route = json.loads((raw/files[2]).read_text())['r1']['route']
    events = s['pair']['pair'][0]['robots']['r1']['events']
    rows = []
    for plan in (v for v in events if v['event'] == 'synchronized_carry_plan'):
        seg = plan['seg']
        own = [v for v in epochs if v['robots'].get('r1', {}).get('seg') == seg]
        carry = [v for v in own if v['robots']['r1']['state'] == 'carry']
        lower = [v for v in own if v['robots']['r1']['state'] in ('lower', 'wait_lower')]
        if not carry: continue
        a, b = at(carry[0]['t']), at(carry[-1]['t']+.05)
        la = at(lower[0]['t']) if lower else b
        finish = at(own[-1]['t'])
        step = plan['calibrated_step_m']
        rows.append(dict(seg=seg, plan=plan, carry_start=a, carry_end=b,
            lower_start=la, segment_end=finish, carry_delta_xy=delta(a, b),
            after_carry_delta_xy=delta(b, finish), lower_delta_xy=delta(la, finish),
            predicted_pulse_distance_m=plan['pulses']*step,
            rounding_excess_m=plan['pulses']*step-plan['distance_m']))
    final = at(times[-1])
    initial = at(times[0])
    gaps = sum(rows[i]['carry_start']['y']-rows[i-1]['segment_end']['y'] for i in range(1,len(rows)))
    pre = rows[0]['carry_start']['y']-initial['y'] if rows else 0.
    carry_dy = sum(v['carry_delta_xy'][1] for v in rows)
    after_dy = sum(v['after_carry_delta_xy'][1] for v in rows)
    tail = final['y']-rows[-1]['segment_end']['y'] if rows else 0.
    localization={}; trajectories=[]
    for rid in ('r1','r2'):
        name=f'eval_only/{rid}/trajectory.jsonl';trajectories.append(name)
        actual=[json.loads(v) for v in (raw/name).read_text().splitlines()]
        ts=[v['t'] for v in actual]; errors=[]
        for pose in s['localizers'][rid]['poses']:
            # Report both own-estimate timestamp and publication timestamp;
            # they differ by input delay, so no timing ambiguity is hidden.
            row={'t':pose['t'],'t_est':pose.get('t_est',pose['t'])}
            for clock in ('t','t_est'):
                t=row[clock];i=bisect.bisect_left(ts,t)
                q=min(actual[max(0,i-1):min(len(actual),i+1)],key=lambda v:abs(v['t']-t))
                xy=[pose[k]-q['robot_xyz_m'][axis] for axis,k in enumerate(('x','y'))]
                row[clock+'_error_xy_m']=xy
            errors.append(row)
        localization[rid]={'samples':len(errors),'first':errors[0] if errors else None,
            'last':errors[-1] if errors else None,
            'max_xy_error_at_estimate_time_m':max((math.hypot(*e['t_est_error_xy_m']) for e in errors),default=None),
            'used_to_adjust_loaded_carry_pulse_count':False}
    return dict(raw=str(raw), route_endpoint=route[-1], B_eval_center=[4.6, -2.1],
        endpoint_minus_B=[route[-1][0]-4.6, route[-1][1]+2.1],
        initial=initial,final=final, final_error_xy=[final['x']-4.6, final['y']+2.1], segments=rows,
        y_telescoping=dict(initial=initial['y'], before_first_carry=pre, during_carry=carry_dy,
            after_carry=after_dy, between_epochs=gaps, tail=tail,
            reconstruction_error=initial['y']+pre+carry_dy+after_dy+gaps+tail-final['y']),
        lateral_rounding_excess_m=sum(r['rounding_excess_m'] for r in rows if r['plan']['cmd']['left']),
        lateral_actual_signed_dy_m=sum(r['carry_delta_xy'][1] for r in rows if r['plan']['cmd']['left']),
        all_after_carry_dy_m=sum(r['after_carry_delta_xy'][1] for r in rows),
        localization=localization,
        files={p:hashlib.file_digest((raw/p).open('rb'), 'sha256').hexdigest() for p in (*files,*trajectories)})


def main():
    p = argparse.ArgumentParser(); p.add_argument('root', type=Path); a=p.parse_args()
    rows = {d.name:diagnose(d/'raw') for d in sorted(a.root.glob('s4live11-*-s601-v182'))}
    print(json.dumps(dict(research_result=False, evaluation_only=True, runs=rows), indent=2))


if __name__ == '__main__': main()
