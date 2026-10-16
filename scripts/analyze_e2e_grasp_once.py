#!/usr/bin/env python3
"""Offline diagnostic only: saved RGB decisions, SIM clocks and source hashes."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess


def read(path, lines=False):
    p=Path(path);raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if p.suffix=='.zst':raw=subprocess.check_output(['zstd','-qdc',str(p)])
    if lines:
        data=[]
        for line in raw.decode().splitlines():
            try:data.append(json.loads(line))
            except ValueError:pass  # console headings are not JSON records
    else:data=json.loads(raw)
    return data,dict(path=str(p),sha256=digest,decoded_sha256=hashlib.sha256(raw).hexdigest())


def distribution(values):
    return dict(n=len(values),median=statistics.median(values) if values else None,
                max=max(values) if values else None,values=values)


def dwell(rows,start,end):
    times=collections.Counter()
    for a,b in zip(rows,rows[1:]):
        dt=max(0.,min(b['t'],end)-max(a['t'],start))
        if dt:times[(a.get('carrier_approach') or {}).get('status','unknown')]+=dt
    return {k:round(v,3) for k,v in sorted(times.items())}


def losses(frames,start,end):
    out=[]
    for a,b in zip(frames,frames[1:]):
        if not start<=b['t']<=end or not a.get('own_beam') or b.get('own_beam'):continue
        det=(b.get('own_beam_observation')or{}).get('result',{})
        diag=b.get('carrier_approach')or{}
        out.append(dict(t=b['t'],last_seen=a['t'],reason=det.get('reason'),
            previous_status=diag.get('status'),path_phase=(diag.get('rpp')or{}).get('phase'),
            rgb_sha256=b.get('sha256'),pose_own_m=b.get('pose_own_m')))
    return out


def raw_run(root):
    events,eh=read(root/'transport-trace.json');final,fh=read(root/'e2e-progress.json')
    result,rh=read(root/'result.json')
    phases=[e for e in events if e.get('event')=='phase']
    starts=[e['t'] for e in phases if e['state']=='align']
    end=final['sim_s'];start=starts[0] if starts else None
    next_phase=next((e for e in phases if start is not None and e['t']>start and e['state']!='align'),None)
    if next_phase:end=next_phase['t']
    report=dict(run=root.parent.name,align_started=start is not None,align_start_s=start,
        observed_end_s=end,align_completed=bool(next_phase and next_phase['state']=='grasp_lift'),
        elapsed_censored_s=None if start is None else round(end-start,3),
        failure=result.get('failure') or result.get('error'),robots={},sources=[eh,fh,rh])
    if start is None:return report
    for rid in ('r1','r2'):
        frames,h=read(root/f'robots/{rid}/ownmap.jsonl.zst',True);report['sources'].append(h)
        t=dwell(frames,start,end)
        relevant=[e for e in events if e.get('robot_id')==rid and start<=e['t']<=end]
        lost=losses(frames,start,end)
        report['robots'][rid]=dict(stage_dwell_s=t,
            acquire_dwell_s=round(sum(v for k,v in t.items() if k.startswith('acquire_')),3),
            acquisition_begins=sum(e.get('event')=='own_pregrasp_acquisition_begin' for e in relevant),
            station_retirements=[dict(t=e['t'],age_s=e['last_seen_age_s']) for e in relevant if e.get('event')=='own_stale_station_retired'],
            loss_reasons=dict(collections.Counter(e['reason'] for e in lost)),
            max_acquire_cycle=max(((f.get('carrier_approach')or{}).get('cycle',0) for f in frames if start<=f['t']<=end),default=0))
    return report


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--r69-inputs',type=Path,required=True)
    ap.add_argument('--r69-logs',type=Path,required=True);ap.add_argument('--r76-root',type=Path)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    data,source=read(a.r69_inputs);r69=[]
    for log in sorted(a.r69_logs.glob('*-log.txt')):
        rows,h=read(log,True);rows=[r for r in rows if 'sim_s'in r and 'robots'in r]
        start=next(r['sim_s'] for r in rows if r.get('phase')=='align')
        end=next(r['sim_s'] for r in rows if r['sim_s']>start and r.get('phase')!='align')
        item=dict(run=log.stem,start_sample_s=start,end_sample_s=end,duration_sample_s=end-start,robots={},source=h)
        for rid in ('r1','r2'):
            rr=[dict(t=r['sim_s'],carrier_approach=r['robots'][rid].get('carrier_approach')) for r in rows]
            d=dwell(rr,start,end);ev=[e for e in data['events'] if e.get('robot_id')==rid]
            item['robots'][rid]=dict(dwell_s=d,acquire_s=sum(v for k,v in d.items() if k.startswith('acquire_')),
                acquisition_begins=sum(e['event']=='own_pregrasp_acquisition_begin' for e in ev),
                retirements=[dict(t=e['t'],age_s=e['last_seen_age_s']) for e in ev if e['event']=='own_stale_station_retired'])
        item['alignment_trajectory_sha256']=hashlib.sha256(json.dumps(
            [(r['sim_s'],r['robots']['r1'].get('carrier_approach'),r['robots']['r2'].get('carrier_approach'))
             for r in rows if start<=r['sim_s']<end],sort_keys=True).encode()).hexdigest()
        r69.append(item)
    first_losses={rid:losses(r['frames'],70,511) for rid,r in data['robots'].items()}
    runs=[]
    if a.r76_root:
        for root in sorted(a.r76_root.glob('azure*-runs/*-r76/raw')):
            runs.append(raw_run(root))
    aligned=[r for r in runs if r['align_started']]
    out=dict(schema='ugrp.grasp_once_diagnostic.v1',scope='offline saved observations; no new physics',
        r69=dict(source=source,source_sha=data['source_sha'],runs=r69,loss_onsets=first_losses,
                 distinct_alignment_trajectories=len({r['alignment_trajectory_sha256'] for r in r69}),
                 events_source='v324 only; v329 sampled trajectory is identical, events not separately measured'),
        r76=dict(total_runs=len(runs),align_subset=len(aligned),completed_align_n=sum(r['align_completed'] for r in aligned),
            censored_alignment_durations_s=distribution([r['elapsed_censored_s'] for r in aligned]),
            robots={rid:dict(acquire_time_s=distribution([r['robots'][rid]['acquire_dwell_s'] for r in aligned]),
                acquisition_begins=distribution([r['robots'][rid]['acquisition_begins'] for r in aligned]),
                max_cycle=distribution([r['robots'][rid]['max_acquire_cycle'] for r in aligned])) for rid in ('r1','r2')},runs=runs),
        held_evaluation=dict(n=None,N=None,reason='controller phase is not physical held; no held labels joined'),
        candidate_trials=dict(submitted=0,completed=0,success_n=None,N=0,reason='checkpoint and supervisor stage runner pending'))
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(r69_distinct=out['r69']['distinct_alignment_trajectories'],r76_total=len(runs),r76_align=len(aligned),
        r76_align_completed=out['r76']['completed_align_n'],report=str(a.output),bytes=a.output.stat().st_size)))

if __name__=='__main__':main()
