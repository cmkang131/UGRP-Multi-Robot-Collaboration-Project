#!/usr/bin/env python3
"""Read-only r69 own-input replay; counterfactual budgets are NOT SIM results."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness import e2e_approach_efficiency as policy


def read(path):
    raw=Path(path).read_bytes()
    if str(path).endswith('.zst'):
        import zstandard
        raw=zstandard.ZstdDecompressor().decompress(raw,max_output_size=30_000_000)
    return json.loads(raw),hashlib.sha256(raw).hexdigest()


def report(data, log):
    profiles=json.loads((ROOT/'configs/s2_v133_full_template.json').read_text())['pulse_calibration']['profiles']
    rows=[]
    for line in Path(log).read_text().splitlines():
        try:r=json.loads(line)
        except ValueError:continue
        if 'sim_s' in r and 'phase' in r and 'robots' in r:rows.append(r)
    result=dict(scope='saved own observations/issued commands; no simulator and no future-frame prediction',robots={})
    replay=[]
    for rid,own in data['robots'].items():
        statuses=collections.Counter();rpp_time=collections.Counter()
        for a,b in zip(rows,rows[1:]):
            if a['phase']!='align':continue
            d=a['robots'][rid].get('carrier_approach') or {};dt=b['sim_s']-a['sim_s']
            statuses[d.get('status','unknown')]+=dt
            if d.get('status')=='navigate_pregrasp':rpp_time[(d.get('rpp')or{}).get('phase','unknown')]+=dt
        fs=own['frames'];commands=[dict(c,t=round(c['t']-own['command_time_origin'],8)) for c in own['commands']]
        diags={f['carrier_approach']['t']:f['carrier_approach'] for f in fs if f.get('carrier_approach')}
        nav={t:d for t,d in diags.items() if d.get('status')=='navigate_pregrasp' and 76<=t<511}
        issued={c['t']:c for c in commands if c['kind']=='mecanum' and c.get('forward',0)>0}
        forward_times=[];estimated_rate_gain=0.;opportunities=0;curve_or_near=0
        for t,d in nav.items():
            rpp=d.get('rpp',{});c=issued.get(round(t,8))
            if rpp.get('phase')!='forward_path' or not c:continue
            forward_times.append(t)
            distance=d['distance_m']
            # The saved path polyline is absent. Count rate opportunities only
            # outside .6 m: integrated length >= Euclidean distance suffices.
            period=policy.pulse_period(rpp['body_error_m'],distance,max(distance,.6)) if distance>=.6 else .4
            eligible=d.get('projected_clear',False) and period<.4-1e-8
            if eligible:
                opportunities+=1;estimated_rate_gain+=.4-period
            else:curve_or_near+=1
            replay.append(dict(robot_id=rid,t=t,kind='pulse_rate',eligible=eligible,period_s=period,
                projected_clear=d.get('projected_clear'),distance_m=distance,issued=c,
                source='saved own geometry plus fixed calibration; future second-pulse clearance not replayed'))
        ev=[e for e in data['events'] if e.get('robot_id')==rid and 76<=e['t']<511]
        gaze=[e for e in ev if e['event']=='own_gaze_settle']
        # Gaze target selection may use a different visible endpoint. Only use
        # inspect-mode records, for which the controller uses assigned grip.
        gaze_suppressed=0;gaze_eligible=0
        for e in gaze:
            t=e['t'];f=max((f for f in fs if f['t']<=t),key=lambda f:f['t'])
            d=diags.get(t)
            if not d or d.get('camera')!='inspect' or not d.get('grip_own_m'):continue
            pan=1500
            for c in commands:
                if c['t']>=t:break
                if c['kind']=='look':pan=c['pan_pulse']
            r=NS(goal=NS(explorer=NS(local_pose=f['pose_own_m'])),servo={6:pan})
            tr=NS(approach_efficiency=policy.OPTION,approach={rid:{}},robots={rid:r})
            needed=policy.gaze_needed(tr,rid,d['grip_own_m']);gaze_eligible+=1
            gaze_suppressed+=not needed
            replay.append(dict(robot_id=rid,t=t,kind='gaze_deadband',needed=needed,pan_before=pan,
                own_pose=f['pose_own_m'],assigned_grip=d['grip_own_m']))
        windows=[e for e in ev if e['event']=='own_acquisition_navigation_window_end']
        window_gain=sum(max(0,e['elapsed_s']-policy.PARAMS['search_explore_s']) for e in windows)
        fresh=[f['t'] for f in fs if f.get('own_beam') is not None]
        intervals=[round(b-a,4) for a,b in zip(fresh,fresh[1:]) if b-a>2.]
        changes=[math.dist(a['station_own_m'][:2],b['station_own_m'][:2])
                 for a,b in zip(list(nav.values()),list(nav.values())[1:])]
        result['robots'][rid]=dict(status_sampled_sim_s=dict(statuses),navigate_substate_sampled_sim_s=dict(rpp_time),
            unique_navigation_evaluations=len(nav),navigation_evaluations_per_resident_sim_s=len(nav)/statuses['navigate_pregrasp'],
            goal_revisions_over_5cm=sum(d>.05 for d in changes),
            gaze_events=len(gaze),gaze_reserved_sim_s=round(sum(e['until']-e['t'] for e in gaze),3),
            replayed_inspect_gazes=gaze_eligible,small_gazes_suppressed=gaze_suppressed,
            nominal_gaze_budget_reduction_s=round(.8*gaze_suppressed,3),
            actual_forward_at_navigation_evaluation=len(forward_times),rate_opportunities=opportunities,
            nominal_same_pulse_count_rate_reduction_s=round(estimated_rate_gain,3),
            completed_exploration_windows=len(windows),exploration_window_durations_s=[e['elapsed_s'] for e in windows],
            nominal_same_window_count_budget_reduction_s=round(window_gain,3),
            observed_reacquisitions=len(intervals),own_end_missing_intervals_s=intervals,
            pulse_forward_delta_m=profiles['0:forward:0.35:0.10']['mean_delta'][0],
            baseline_nominal_forward_m_s=profiles['0:forward:0.35:0.10']['mean_delta'][0]/.4,
            candidate_max_nominal_forward_m_s=profiles['0:forward:0.35:0.10']['mean_delta'][0]/.2,
            projection_rejected_navigation_evaluations=sum(not d.get('projected_clear',False) for d in nav.values()))
    result['limitations']=[
        '1 s status samples can retain a preceding status during camera/queue holds; gaze budgets overlap navigation residence.',
        'Counterfactual component budgets assume the same pulses/views/windows. They must not be added or subtracted from paired 435 s.',
        'No full historical costmap/path or changed-trajectory camera frames: second-pulse clearance, replanning savings and scan success not inferred.',
        'v324 and v329 align trajectories are identical: not independent evidence. New parent v350 changes body/protocol.',
        'Reacquisition count uses >2 s gaps between accepted own visible-end frames; no physical grasp/contact labels.'
    ]
    return result,replay


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--log',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();data,digest=read(a.input);out,replay=report(data,a.log)
    out.update(input_path=a.input,input_uncompressed_sha256=digest,raw_files=data['files'],source_sha=data['source_sha'],
        log_path=a.log,log_sha256=hashlib.sha256(Path(a.log).read_bytes()).hexdigest(),replay_rows=replay)
    raw=(json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode()
    import zstandard
    compressed=zstandard.ZstdCompressor().compress(raw)
    assert zstandard.ZstdDecompressor().decompress(compressed)==raw
    Path(a.output).write_bytes(compressed)
    print(json.dumps({k:v for k,v in out.items() if k!='replay_rows'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
