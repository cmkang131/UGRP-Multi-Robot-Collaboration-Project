"""GCP2-only evaluation of existing originals; no simulation or control input."""
import collections, hashlib, json, math, platform, subprocess
from pathlib import Path
import numpy as np

RUNS=Path('/home/ugrp/ugrp-sim/runs')
OUT=RUNS/'reloc18-audit'

def read(p):
    if p.exists(): return p.read_text()
    return subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)

def obj(p): return json.loads(read(p))
def rows(p): return [json.loads(s) for s in read(p).splitlines() if s.strip()]
def dist(x):
    return dict(N=len(x),**({f'p{q}':float(np.percentile(x,q)) for q in (50,95,99)} if x else {}))

def audit():
    assert platform.node().startswith('ugrp-sim-gcp2')
    OUT.mkdir(exist_ok=True)
    reports=[]
    for p in sorted(RUNS.glob('reloc1[67]-r*-carry-*/raw')):
        if not (p/'result.json').exists() and not (p/'result.json.zst').exists():continue
        d=obj(p/'result.json')
        if d.get('status')!='complete':continue
        c=rows(p/'teacher-commands.jsonl');e=rows(p/'eval-only.jsonl')
        phases=collections.Counter(x['phase'] for x in c)
        carry=d['teacher']['carry'];region=obj(p/'carry-static-map.json')['regions']['zone_'+d['destination_zone']]
        cx,cy=region['center_m'];hx,hy=region['half_extents_m']
        margins=[min(hx-abs(x-cx),hy-abs(y-cy)) for x,y in e[-1]['footprint_xy']]
        events=carry.get('recovery_events',[])
        reasons=collections.Counter(x.get('reason',x.get('event','unspecified_original')) for x in events)
        times=[];old=None
        for x in c:
            if x['phase']!=old:
                times.append(dict(t=x['t'],phase=x['phase']));old=x['phase']
        by={round(x['t'],5):x for x in e}
        travel=[]
        for x in c:
            if x['phase']=='carry_to_zone':
                y=by.get(round(x['t'],5),{})
                travel.append(dict(t=x['t'],xy_error=y.get('map_pose_error_xy_m'),yaw_error_deg=None if y.get('map_pose_error_yaw_rad') is None else math.degrees(y['map_pose_error_yaw_rad']),pose=x.get('map_pose',{}).get('pose_estimate')))
        r=dict(run=p.parent.name,raw=str(p),seed=obj(p/'plan.json').get('seed'),source_sha=d['source_sha'],
            termination=d.get('termination_category'),sim_s=d['sim_s'],phases=dict(phases),timeline=times,
            cumulative=dict(ticks=len(c),pickup_ticks=sum(x['phase'] in ('close','lift','lift_settle','hold') for x in c),travel_ticks=phases['carry_to_zone'],place_view_ticks=phases['zone_place_view'],place_advance_ticks=phases['zone_place_advance'],final_lower_ticks=phases['lower'],final_open_ticks=phases['open'],place_success=int(d['zone_placement_success'])),
            rejection_reasons=dict(reasons),recovery_events=events,
            place_predicates={k:d.get(k) for k in ('lift_success','zone_placement_success','release_success','no_drop_during_carry','final_footprint_inside_zone','criteria')},
            final=dict(phase=d['teacher']['phase'],goal=carry.get('stand_off_xy'),slot=carry.get('slot_xy'),arrival=carry.get('map_arrival_estimated_t'),failure=carry.get('failure'),zone_margin_min_m=min(margins),cargo_xyz=e[-1].get('cargo_xyz'),base_xyz=e[-1].get('base_xyz'),xy_error_m=e[-1].get('map_pose_error_xy_m'),yaw_error_deg=math.degrees(e[-1]['map_pose_error_yaw_rad']),clearance_m=e[-1]['min_z']-e[-1]['support_z'],tilt_deg=e[-1]['tilt_deg'],speed=e[-1]['speed'],open_issued=e[-1]['open_issued']),
            travel_samples=travel,
            source_hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in (p/'result.json',p/'result.json.zst',p/'teacher-commands.jsonl',p/'teacher-commands.jsonl.zst',p/'eval-only.jsonl',p/'eval-only.jsonl.zst') if f.exists()})
        reports.append(r)
        r['cumulative_runs']=dict(started=1,lift_success=int(d['lift_success']),travel_entered=int(phases['carry_to_zone']>0),
            authored_arrival=int(carry.get('map_arrival_estimated_t') is not None),place_view=int(phases['zone_place_view']>0),
            place_advance=int(phases['zone_place_advance']>0),lower=int(phases['lower']>0),open=int(phases['open']>0),place_success=int(d['zone_placement_success']))
    data=dict(analysis_host='gcp2',scope='evaluation only; stage counts are ticks, not independent success trials',runs=reports,reproduce=f'python {__file__}')
    (OUT/'audit-full.json').write_text(json.dumps(data,indent=2)+'\n')
    lite=[{k:v for k,v in r.items() if k not in ('recovery_events','travel_samples')} for r in reports]
    (OUT/'audit.json').write_text(json.dumps(dict(data,runs=lite),indent=2)+'\n')
    reject=dict(source=str(OUT/'audit-full.json'),reproduce=data['reproduce'],runs=[dict(run=r['run'],raw=r['raw'],cumulative=r['cumulative_runs'],stage_tick_counts=r['cumulative'],rejections=[dict(category=k,N=n,blocked_object='pose_uncertainty_budget' if 'budget' in k else 'original_recovery_event',minimum_gap_m=None,gap_scope='not_applicable_localization_or_missing_in_original') for k,n in r['rejection_reasons'].items()]) for r in reports])
    (OUT/'rejection-table.json').write_text(json.dumps(reject,indent=2)+'\n')
    lines=['|run|travel ticks|place view/advance|lower/open|end|zone margin m|xy error m|reasons|','|---|---:|---:|---:|---|---:|---:|---|']
    for r in reports:
        z=r['cumulative'];f=r['final']
        lines.append(f"|{r['run']}|{z['travel_ticks']}|{z['place_view_ticks']}/{z['place_advance_ticks']}|{z['final_lower_ticks']}/{z['final_open_ticks']}|{r['termination']} {f['phase']}|{f['zone_margin_min_m']:.3f}|{f['xy_error_m']:.3f}|{r['rejection_reasons']}|")
    (OUT/'place-table.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))

if __name__=='__main__':audit()
