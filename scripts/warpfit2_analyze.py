"""Source-host-only warpfit2 analysis. No physics integration, no model calls."""
import argparse
import csv
from collections import Counter
import json
from pathlib import Path
import platform
import sys
from types import SimpleNamespace
from scripts.warpfit import load,dump,digest
from scripts.warpfit_analyze import grip,drive


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if platform.system()!='Linux' or not platform.node().startswith('ugrp-act-l4-gcp6'):
        raise ValueError('gcp6 analysis only')
    import numpy as np
    root=a.root.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    models={k:load(SimpleNamespace(fixture=root/'fixtures'/k,profile='warp_native_contact_v1',engine='warp'))
            for k in ('box','beam','drive')}
    rows=[];rejections=[];frames=[];pulses=[]
    for phase in sorted(root.glob('R[123]')):
        attempts=phase/'attempts.json'
        if not attempts.exists():continue
        for j in json.loads(attempts.read_text()):
            folder=Path(j['output']);rp=folder/'result.json'
            if not rp.exists():
                rows.append(dict(**j,completed=0,HOST_ERROR=1,cap_end=False,error='result_missing'))
                rejections.append(dict(category='HOST_ERROR',count=1,reason='result missing; inspect preserved managed stderr',
                    blocked_object='runtime',minimum_gap_m=None,gap_status='not_geometric',raw=str(folder)))
                continue
            r=json.loads(rp.read_text());k=j['kind'];m,d,f,meta,xml,profile=models[k]
            row={**j,**{key:r.get(key) for key in ('round','nworld','source_sha','completed','HOST_ERROR','cap_end','status','error',
                'physical_gpu_ms_per_step','wall_per_sim_s','amortized_wall_per_world_sim_s','setup_jit_s','runtime_wall_s',
                'capacity','every_step_envelope','sim_s','steps','model','options','effective_tolerance','rgb_recording')}}
            row.update(result_sha256=digest(rp),fixture_sha256=r['fixture_sha256'])
            if (folder/'states.npz').exists():row['states_sha256']=digest(folder/'states.npz')
            if r['completed'] and not r['cap_end']:
                if k!='drive':
                    row['worlds'],points=grip(folder,m,meta)
                    row['points']=points
                else:
                    row['pulses']=drive(folder,m,meta,j['case'])
                    pulses.extend(dict(round=r['round'],profile=j['profile'],raw=str(folder),**v) for v in row['pulses'])
            else:
                rejections.append(dict(category='HOST_ERROR' if r['HOST_ERROR'] else 'cap_end',count=1,
                    reason=r.get('error','fixed tape incomplete'),blocked_object='physics_engine',minimum_gap_m=None,
                    gap_status='not_geometric',raw=str(folder)))
            rows.append(row)
    thresholds={}
    for row in rows:
        if row['profile']=='off' and row.get('points'):
            key=f"{row['round']}/{row['kind']}"
            if key in thresholds:continue
            points=row['points']
            thresholds[key]=dict(height_p05_m=float(np.percentile([v['height_m'] for v in points],5)),
                slip_p95_m=float(np.percentile([v['slip_m'] for v in points],95)),raw=row['output'],
                states_sha256=row['states_sha256'],basis='same-round native-contact-v1 baseline P05/P95, no extra margin')
    for row in rows:
        if not row.get('points'):continue
        points=row.pop('points');ref=thresholds[f"{row['round']}/{row['kind']}"]
        contact=[v for v in points if v['all_fingers']]
        loaded=[v for v in contact if v['height_m']>=.012]  # existing teacher6f057f7e clearance, not fitted
        height=[v for v in loaded if v['height_m']>=ref['height_p05_m']]
        slip=[v for v in height if v['slip_m']<=ref['slip_p95_m']]
        stages=[];previous=len(points)
        for name,values in [('hold_frames',points),('positive_all_fingers',contact),('existing12mm_clearance',loaded),
                            ('native_P05_height',height),('native_P95_slip',slip)]:
            stages.append(dict(gate=name,cumulative_pass=len(values),rejected=previous-len(values)));previous=len(values)
        frames.append(dict(raw=row['output'],unit='world x10Hz hold frame',stages=stages))
        for category,count in [('grasp_contact_loss',len(points)-len(contact)),('height_below_existing12mm',len(contact)-len(loaded)),
            ('native_height_quantile',len(loaded)-len(height)),('native_slip_quantile',len(height)-len(slip))]:
            if count:rejections.append(dict(category=category,count=count,reason=category,
                blocked_object=models[row['kind']][3]['target_body'],minimum_gap_m=None,
                gap_status='not_measured_per_world; world0 contacts preserved',raw=row['output']))
        worlds=row['worlds']
        row.update(fully_retained_worlds=sum(w['loaded_contact_samples']==w['hold_samples'] for w in worlds),
            measured_worlds=len(worlds),height_p05_mm=float(np.percentile([w['height_m']['p05']*1000 for w in worlds],5)),
            slip_p95_mm=float(np.percentile([w['slip_m']['p95']*1000 for w in worlds],95)),
            tilt_max_deg=max(w['tilt_deg']['max'] for w in worlds),threshold=ref)
        row['native_quantile_pass_worlds']=sum(w['loaded_contact_samples']==w['hold_samples'] and
            w['height_m']['p05']>=ref['height_p05_m'] and w['slip_m']['p95']<=ref['slip_p95_m'] for w in worlds)
    box=[]
    for round_ in (1,2,3):
        for pr in ('off','warp_upstream_plane_v1','warp_measured_capacity_v1'):
            matched=sorted([r for r in rows if r.get('round')==round_ and r['profile']==pr and r['kind']=='box'],key=lambda r:r['repeat'])
            selected=[dict(repeat=r['repeat'],raw=r['output'],**w) for r in matched for w in r.get('worlds',[])][:30]
            if selected:box.append(dict(round=round_,profile=pr,selected=len(selected),
                retained=sum(w['loaded_contact_samples']==w['hold_samples'] for w in selected),selection=selected))
    columns=['round','profile','kind','repeat','nworld','status','sim_s','physical_gpu_ms_per_step','wall_per_sim_s',
        'fully_retained_worlds','measured_worlds','height_p05_mm','slip_p95_mm','tilt_max_deg','native_quantile_pass_worlds']
    with (out/'timing.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)
    with (out/'drive.csv').open('w') as f:
        cols=['round','profile','world','case','phase','forward_mm','left_mm','yaw_deg','translation_mm','tilt_max_deg','raw']
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        for r in pulses:
            if r.get('status')=='boundary_not_recorded':continue
            w.writerow({**{k:r[k] for k in ('round','profile','world','case','phase','yaw_deg','translation_mm','raw')},
                'forward_mm':r['delta_xyyaw'][0]*1000,'left_mm':r['delta_xyyaw'][1]*1000,'tilt_max_deg':r['tilt_deg']['max']})
    pairs=[]
    for row in rows:
        if row['profile']=='off' or not row.get('completed'):continue
        base=next((r for r in rows if r.get('round')==row.get('round') and r['kind']==row['kind'] and r['repeat']==row['repeat'] and r['profile']=='off'),None)
        if not base or not base.get('completed'):continue
        pairs.append(dict(round=row['round'],profile=row['profile'],kind=row['kind'],repeat=row['repeat'],
            baseline=base['output'],candidate=row['output'],
            gpu_speedup=base['physical_gpu_ms_per_step']/row['physical_gpu_ms_per_step'],
            wall_speedup=base['wall_per_sim_s']/row['wall_per_sim_s']))
    counts=Counter()
    for r in rejections:counts[r['category']]+=r['count']
    dump(out/'rejection_table.json',dict(stages=[dict(gate='submitted_runs',cumulative_pass=len(rows),rejected=0),
        dict(gate='fixed_work_complete',cumulative_pass=sum(bool(r.get('completed')) for r in rows),rejected=sum(not r.get('completed') for r in rows)),
        dict(gate='no_cap_end',cumulative_pass=sum(bool(r.get('completed')) and not r.get('cap_end') for r in rows),rejected=sum(bool(r.get('cap_end')) for r in rows))],
        sample_funnels=frames,reasons=rejections,distribution=dict(counts),raw=str(root),reproduce=sys.argv))
    dump(out/'rows.json',rows);dump(out/'box30.json',box);dump(out/'thresholds.json',thresholds);dump(out/'pairs.json',pairs)
    dump(out/'summary.json',dict(runs=len(rows),completed=sum(bool(r.get('completed')) for r in rows),
        HOST_ERROR=sum(bool(r.get('HOST_ERROR')) for r in rows),cap_end=sum(bool(r.get('cap_end')) for r in rows),
        box30=[{k:v for k,v in r.items() if k!='selection'} for r in box],pairs=pairs,distribution=dict(counts),
        default_changes=0,teacher_gates=0,models=0,scope='fixed primitive replicas; not independent seeds or teacher/student/E2E acceptance'))
    dump(out/'SHA256.json',{p.name:digest(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(dict(runs=len(rows),completed=sum(bool(r.get('completed')) for r in rows),distribution=dict(counts))))


if __name__=='__main__':main()
