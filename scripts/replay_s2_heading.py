"""Saved v141 own-estimate/plan replay. No physics, image rerendering or GT."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np

from harness import zone_solo_cyan_path_heading as heading
from harness.zone_solo_cyan_pulse_cal import Runtime as Pulse, select_pulse, action_of
from scripts.run_final_environment_checks import write


def byte_hash(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def command_time(rows, end=None):
    """One live base command; arm/look do not interrupt it, expiry/hold do."""
    totals = dict(moving_s=0., lateral_s=0., forward_s=0., turn_s=0.)
    live = None
    def finish(now):
        nonlocal live
        if live is None:
            return
        start, expiry, a = live
        dt = max(0., min(now, expiry)-start)
        totals['moving_s'] += dt
        for axis in ('forward', 'turn'):
            if a.get(axis, 0): totals[axis+'_s'] += dt
        if a.get('left', 0): totals['lateral_s'] += dt
        live = None
    for a in rows:
        if a['kind'] not in ('hold', 'drive', 'mecanum'):
            continue
        finish(a['t'])
        if a['kind'] != 'hold' and any(a.get(k,0) for k in ('forward','left','turn')):
            live = (a['t'], a['t']+a['duration_s'], a)
    finish(math.inf if end is None else end)
    totals['lateral_fraction_moving'] = totals['lateral_s']/totals['moving_s'] if totals['moving_s'] else 0.
    if end is not None:
        start = rows[0]['t'] if rows else 0.
        totals['elapsed_sim_s'] = end-start
        totals['lateral_fraction_sim'] = totals['lateral_s']/(end-start) if end > start else 0.
    return totals


def proposal_time(proposals):
    t = 0.; rows = []
    for a in proposals:
        rows.append(dict(t=t, **a))
        t += a.get('duration_s',0)
    return command_time(rows)


def fixed_inputs(record):
    profiles = record['pulse_motion_model']['model']['profiles']
    decisions = {r['t']: r for r in record['global_full_decisions']}
    paths = [e for e in record['events'] if e['event']=='path']
    traces = []; current=[]; new=[]; identical=0
    for row in record['pulse_motion_model']['transformations']:
        score = row['score']
        if 'body_error_m' not in score or row['t'] not in decisions:
            raise ValueError('missing own input for recorded pulse')
        report = decisions[row['t']]['report']
        path = next((p['plan'] for p in reversed(paths) if p['t']<=row['t']), None)
        # Legacy DEV direct fallback writes no path event. Its sole waypoint
        # is the goal; mark it explicitly rather than inventing an A* receipt.
        goal = row['waypoint'] if path is None else path['goal_m']
        distance = math.dist((report['x_m'],report['y_m']),goal)
        loaded = row['profile_key'].startswith('1:')
        old, _ = select_pulse(profiles,loaded,score['body_error_m'],score['yaw_rad'])
        old_action = dict(kind='hold') if old is None else action_of(old)
        same = json.dumps(old_action).encode()==json.dumps(row['issued']).encode()
        identical += same
        p, audit = heading.select(profiles,loaded,score['body_error_m'],score['yaw_rad'],distance)
        action = dict(kind='hold') if p is None else action_of(p)
        current.append(row['issued']); new.append(action)
        traces.append(dict(t=row['t'],state=row['state'],goal=goal,waypoint=row['waypoint'],
            plan_available=path is not None,
            body_error_m=score['body_error_m'],yaw_rad=score['yaw_rad'],
            baseline=row['issued'],off_replayed=old_action,off_identical=same,on=action,decision=audit))
    return dict(count=len(traces),off_matches=identical,off_byte_identical=identical==len(traces),
                baseline=proposal_time(current),on=proposal_time(new),rows=traces)


def replay_paths(record):
    profiles = record['pulse_motion_model']['model']['profiles']
    decisions = record['global_full_decisions']
    results=[]
    # Reuse each saved A* path verbatim, including failed/deviated-run plans.
    for event in record['events']:
        if event['event']!='path': continue
        plan=event['plan']; pose=min(decisions,key=lambda q:abs(q['t']-event['t']))
        initial=pose['report']; loaded=pose['state']=='carry'
        pair={}
        for mode in ('off','on'):
            cls = Pulse if mode=='off' else heading._HeadingPulse
            r=object.__new__(cls); r.pulse_option='v7_pulse_cal_v1'
            if mode=='on':r.heading_mode=heading.OPTION
            r.pulse_profiles=profiles;r.path=[list(p) for p in plan['waypoints_m'][1:]] or [list(plan['goal_m'])]
            r.path_goal=tuple(plan['goal_m']);r.state=pose['state'];r.robot_id='r3'
            r.pose=NS(provider=NS(loc=NS(_pf=NS(load=NS(loaded=loaded)))))
            r.cal_rows=[];r.heading_rows=[];r.soft_counts={};r.events=[]
            xy=np.array(plan['start_m']);yaw=initial['yaw_rad'];done=False;commands=[];t=0.
            for _ in range(2000):
                r.last_report=NS(x_m=xy[0],y_m=xy[1],yaw_rad=yaw,initialized=True,
                    std_xy_m=.01,std_yaw_rad=.01,last_fix_t=t)
                actions,done=r.drive(plan['goal_m'],t)
                if done:break
                a=actions[0]
                if a['kind']=='hold':break
                commands.append(dict(t=t,**a));p=profiles[r.cal_rows[-1]['profile_key']]
                d=p['mean_delta'];c,s=math.cos(yaw),math.sin(yaw)
                xy+=np.array([[c,-s],[s,c]])@d[:2];yaw=heading.wrap(yaw+d[2])
                # Same pulse coast plus delayed estimate; MODEL time only.
                t+=p['times'][-1]+.16
            pair[mode]=dict(model_goal_reached=done,commands=len(commands),
                final_xy=xy.tolist(),final_yaw=yaw,model_time_s=t,
                timing=command_time(commands,t),command_sha256=byte_hash(commands))
        results.append(dict(t=event['t'],plan_sha256=plan['plan_sha256'],state=pose['state'],**pair))
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('new output required')
    a.output.mkdir(parents=True)
    summary=[]
    for source in a.source:
        record=json.loads((source/'student_record.json').read_text())
        result=json.loads((source/'result.json').read_text())
        fixed=fixed_inputs(record);paths=replay_paths(record)
        seed=result['seed'];write(a.output/f's{seed}-fixed.json',fixed);write(a.output/f's{seed}-paths.json',paths)
        summary.append(dict(seed=seed,source=str(source),
            source_sha256=hashlib.sha256((source/'student_record.json').read_bytes()).hexdigest(),
            fixed_inputs={k:v for k,v in fixed.items() if k!='rows'},
            stored_plan_count=len(paths),model_goals_reached={m:sum(r[m]['model_goal_reached'] for r in paths) for m in ('off','on')},
            actual_baseline_commands=command_time(record['commands'],record['poses'][-1]['t']),
            baseline_evaluation=result['evaluation']))
    write(a.output/'summary.json',dict(scope='fixed own inputs and mean pulse model; not closed-loop physics',
        gt_inputs=False,runs=summary))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
