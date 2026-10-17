"""Own occupancy maps and same-input static/augmented AMCL; source VM CPU only.

Prediction seals files before separate score opens evaluation labels. Mapping
uses unqualified estimates, never truth. All acceptance thresholds are inherited.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import numpy as np
from scripts.mapbuild10_mc import read, sha, dump, truth_for

NAMES=('off','static','static_own')


def load_long(a):
    b=a.input
    paths=[b/n for n in ('own.json','online-trajectory.json','scans.json','static-map.json','public-start-zone.json')]
    inputs={str(p):sha(p) for p in paths}
    own=read(paths[0])['frames'];tr=read(paths[1]);scans=read(paths[2]);frames=[];off=np.zeros(3)
    from harness.e2e_rgb_vo import compose
    if not len(own)==len(tr)==len(scans):raise ValueError('FRAME_JOIN_REQUIRED')
    for f,r,s in zip(own,tr,scans):
        if not f['t']==r['t']==s['t']:raise ValueError('TIME_JOIN_REQUIRED')
        if sha(b/f['rgb'])!=f['sha256']:raise ValueError('RGB_CHANGED')
        off=compose(off,r['motion_delta'])
        frames.append(dict(t=f['t'],frame_id=f['frame_id'],servo=f['servo'],scan=s,own_delta=r['motion_delta'],off_pose=off.tolist(),stage=r['stage']))
    return [dict(id='long',static=read(paths[3]),prior=read(paths[4]),frames=frames,
                 evaluation_source=str(b/'eval-only.json'),world=None,rid=None)],inputs


def load_streams(a):
    paths=[a.input/n for n in ('own-streams.json','own-seal.json','priors.json')]
    own=read(paths[0]);seal=read(paths[1]);priors=read(paths[2])
    if sha(paths[0])!=seal['own_streams_sha256']:raise ValueError('OWN_SEAL_CHANGED')
    for p,h in seal['sources'].items():
        if sha(Path(p))!=h:raise ValueError('SOURCE_CHANGED')
    for s in own['streams']:
        s['prior']=priors['streams'][s['id']][0]
        for f in s['frames']:f['stage']='sparse_release'
    return own['streams'],{str(p):sha(p) for p in paths}


def predict(a):
    from harness.mapbuild_amcl import StaticAMCL,OPTION as AMCL
    from harness.mapbuild_own_grid import OwnGrid,AugmentedField,OPTION
    from harness.e2e_rgb_vo import compose,between
    queue=read(a.queue)
    if not Path(queue['rejection_table']).is_file() or not read(a.stack_check)['ok']:raise ValueError('ADMISSION_RECORD_REQUIRED')
    a.output.mkdir(exist_ok=False)
    streams,inputs=(load_long if a.kind=='long' else load_streams)(a)
    for p in [a.calibration,a.requirements,a.queue,a.stack_check,Path(__file__),Path('harness/mapbuild_own_grid.py'),Path('harness/mapbuild_amcl.py'),Path('harness/mapbuild_amcl_vendor/algorithms.py'),Path('harness/self_odom_grid.py')]:inputs[str(p)]=sha(p)
    index=[]
    for s in streams:
        filters={n:StaticAMCL(s['static'],read(a.calibration),read(a.requirements),option=AMCL,profile='nav2_rgb_field_v1',
                     seed=2026101700,initial_prior_option='start_zone_prior_v1',initial_prior=s['prior']) for n in NAMES[1:]}
        grids={n:OwnGrid() for n in NAMES}
        for n,m in filters.items():m.field=AugmentedField(m.field,grids[n],option=OPTION if n=='static_own' else 'off')
        rows=[]
        for f in s['frames']:
            entry=dict(t=f['t'],frame_id=f['frame_id'],stage=f['stage'],models={})
            for n in NAMES:
                if n=='off':p=f['off_pose'];v=dict(candidate=p,ready=False,attempted=False,reason='off')
                else:
                    m=filters[n];e=m.step(f['t'],f['frame_id'],f['own_delta'],f['scan'],servo=f['servo'])
                    p=compose(m.current['candidate_pose'],between(m.sensor_odom,m.odom)).tolist() if m.current else None
                    v=dict(candidate=p,ready=bool(m.current and m.current['converged']),attempted=e['attempted'],reason=e['reason'],
                           xy95=e.get('xy_p95_m'),yaw95=e.get('yaw_p95_rad'),ess=e.get('ess'),stable_reference_cells=m.field.stable_n,
                           reference_t=m.field.last_reference_t,production_qualified=False)
                    if e['attempted'] and n=='static_own' and m.field.last_reference_t is not None and m.field.last_reference_t>=f['t']:raise ValueError('CURRENT_SCAN_LEAK')
                # ALL mapping happens after this frame's measurement update.
                event=grids[n].insert(f['t'],p,f['scan']);v['insertion']=event
                entry['models'][n]=v
            rows.append(entry)
        dump(a.output/(s['id']+'-predictions.json'),rows)
        dump(a.output/(s['id']+'-maps.json'),{n:g.export() for n,g in grids.items()})
        index.append(dict(id=s['id'],frames=len(rows),evaluation_source=s['evaluation_source'],world=s['world'],rid=s['rid'],static=s['static'],
            off_poses=[f['off_pose'] for f in s['frames']],times=[f['t'] for f in s['frames']],
            reasons={n:dict(Counter(r['models'][n]['reason'] for r in rows)) for n in NAMES}))
        print(json.dumps(dict(stream=s['id'],frames=len(rows),map_cells={n:len(g.cells) for n,g in grids.items()})),flush=True)
    dump(a.output/'index.json',index)
    outputs={str(p):sha(p) for p in sorted(a.output.glob('*.json'))}
    dump(a.output/'prediction-seal.json',dict(inputs=inputs,outputs=outputs,truth_inputs=0,top_inputs=0,physics_steps=0,
        render_calls=0,own_reference='previous frames only; saturated distinct-frame cells; single union field',reproduction=sys.argv))


def verify(a):
    seal=read(a.output/'prediction-seal.json')
    for p,h in {**seal['inputs'],**seal['outputs']}.items():
        if sha(Path(p))!=h:raise ValueError('SEALED_FILE_CHANGED:'+p)
    return seal


def score(a):
    verify(a)
    from harness.e2e_rgb_vo import compose,between
    from harness.mapbuild_amcl import StaticField
    from harness.mapbuild_own_grid import RESOLUTION,transform
    req=read(a.requirements)['handoff'];results=[];allerrors={}
    for s in read(a.output/'index.json'):
        # Explicitly separate evaluation process: only here open exact poses.
        truth=read(Path(s['evaluation_source']))
        gt=truth['frames'] if s['world'] is None else [r for r in truth['rows'] if r['world']==s['world'] and r['rid']==s['rid']]
        poses=[r['pose' if s['world'] is None else 'truth_pose'] for r in gt]
        pred=read(a.output/(s['id']+'-predictions.json'))
        if len(gt)!=len(pred) or [r['t'] for r in gt]!=[r['t'] for r in pred]:raise ValueError('EVAL_JOIN_REQUIRED')
        rows=[];path=0.;last=None
        for r,g in zip(pred,poses):
            if last is not None and (a.kind!='long' or r['stage']=='diagnostic_route'):path+=float(np.linalg.norm(np.asarray(g[:2])-last[:2]))
            last=np.asarray(g);entry=dict(t=r['t'],stage=r['stage'],path_m=path,models={})
            for n in NAMES:
                v=dict(r['models'][n]);p=v['candidate']
                if p is None:v.update(xy_m=None,yaw_deg=None,coupled_deg=None,requirement_pass=False)
                else:
                    if n=='off':p=compose(poses[0],p)
                    xy=float(np.linalg.norm(np.asarray(p[:2])-g[:2]));yaw=abs(float(between(g,p)[2]));coupled=yaw+math.atan2(xy,req['nominal_target_range_m']-xy)
                    v.update(xy_m=xy,yaw_deg=math.degrees(yaw),coupled_deg=math.degrees(coupled),requirement_pass=xy<=req['position_error_m'] and coupled<=req['yaw_error_rad'])
                entry['models'][n]=v
            rows.append(entry)
        route=[r for r in rows if a.kind!='long' or r['stage']=='diagnostic_route']
        def metrics(rs,n):
            vs=[r['models'][n] for r in rs if r['models'][n]['xy_m'] is not None];xy=np.array([v['xy_m'] for v in vs]);ready=[v for v in vs if v['ready'] and v['attempted']]
            if not len(vs):return None
            return dict(frames=len(vs),end_xy_mm=float(xy[-1]*1000),max_xy_mm=float(xy.max()*1000),rmse_xy_mm=float(np.sqrt(np.mean(xy*xy))*1000),
                end_yaw_deg=vs[-1]['yaw_deg'],max_yaw_deg=max(v['yaw_deg'] for v in vs),end_coupled_deg=vs[-1]['coupled_deg'],
                requirement_frames=sum(v['requirement_pass'] for v in vs),coupled_fail_frames=sum(not v['requirement_pass'] for v in vs),
                converged_updates=len(ready),wrong_converged_updates=sum(not v['requirement_pass'] for v in ready))
        maps=read(a.output/(s['id']+'-maps.json'));field=StaticField(s['static'],full_wall_extent=True);quality={}
        for n,j in maps.items():
            cells=np.array(j['cells'],float).reshape(-1,5);points=(cells[:,:2]+.5)*RESOLUTION
            if n=='off':points=transform(points,poses[0])  # gauge ONLY for evaluation
            d=field.distances(points);occ=cells[:,2]>0;free=cells[:,2]<0
            # Cell/wall overlap proxy: cell circumradius, no tuned tolerance.
            # Static field .01m quantization is explicitly retained.
            overlap=d<=RESOLUTION/math.sqrt(2)
            quality[n]=dict(observed_cells=len(cells),occupied_cells=int(occ.sum()),free_cells=int(free.sum()),stable_cells=int(((cells[:,2]>=math.log(9))&(cells[:,3]>=j['stable_min_hits'])).sum()),
                occupied_static_overlap_ratio=float(np.mean(overlap[occ])) if occ.any() else None,
                occupied_outside_static_ratio=float(np.mean(~overlap[occ])) if occ.any() else None,
                free_on_static_wall_ratio=float(np.mean(d[free]==0)) if free.any() else None,
                evaluation='outside_static is a discrepancy proxy; unmodeled real obstacles are NOT verified false occupancy')
        bins=[]
        for k in range(math.floor(path/.5)+1):
            rs=[r for r in route if k*.5<=r['path_m']<(k+1)*.5]
            if rs:bins.append(dict(start_m=k*.5,end_m=(k+1)*.5,models={n:metrics(rs,n) for n in NAMES}))
        funnels={}
        for n in NAMES:
            remaining=route;stages=[]
            for name,test in [('finite_candidate',lambda v:v['xy_m'] is not None),('actual_xy_budget',lambda v:v['xy_m']<=req['position_error_m']),('actual_coupled_budget',lambda v:v['requirement_pass']),('qualified_distribution',lambda v:v['ready'])]:
                before=len(remaining);remaining=[r for r in remaining if test(r['models'][n])];stages.append(dict(stage=name,input_n=before,cumulative_pass_n=len(remaining),rejected_n=before-len(remaining)))
            funnels[n]=stages
        results.append(dict(id=s['id'],path_m=path,route={n:metrics(route,n) for n in NAMES},whole={n:metrics(rows,n) for n in NAMES},map_quality=quality,bins=bins,frame_funnels=funnels,
            own_field_used_updates=sum(r['models']['static_own']['attempted'] and r['models']['static_own']['stable_reference_cells']>0 for r in pred),
            raw=s['evaluation_source'],truth_sha256=sha(Path(s['evaluation_source']))))
        allerrors[s['id']]=rows
    dump(a.output/'frame-errors.json',allerrors)
    summary=dict(status='OFFLINE_ONLY_NOT_READY',kind=a.kind,streams=results,requirements=req,production_qualified=False,physics_steps=0,render_calls=0,reproduction=sys.argv)
    dump(a.output/'summary.json',summary)
    dump(a.output/'rejection_table.json',dict(streams=[dict(id=s['id'],frames=s['frame_funnels']) for s in results],
         category='offline_localization_budget',blocked_object='own_observed_wall_identity_not_measured',minimum_gap_m=None,gap_status='not_measured',raw=str(a.input),reproduction=sys.argv))
    print(json.dumps({**summary,'streams':[{k:v for k,v in s.items() if k not in ('bins','frame_funnels')} for s in results]}),flush=True)


def plots(a):
    verify(a)
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from harness.mapbuild_own_grid import RESOLUTION,transform
    summary=read(a.output/'summary.json');errors=read(a.output/'frame-errors.json')
    for s in read(a.output/'index.json'):
        rows=[r for r in errors[s['id']] if a.kind!='long' or r['stage']=='diagnostic_route'];sm=next(v for v in summary['streams'] if v['id']==s['id'])
        fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True)
        for n in NAMES:
            rs=[r for r in rows if r['models'][n]['xy_m'] is not None]
            axes[0].plot([r['path_m'] for r in rs],[r['models'][n]['xy_m']*1000 for r in rs],label=n)
            axes[1].plot([r['path_m'] for r in rs],[r['models'][n]['yaw_deg'] for r in rs],label=n)
        axes[0].axhline(summary['requirements']['position_error_m']*1000,c='k',ls='--');axes[1].set_xlabel('actual path m (evaluation only)')
        axes[0].set_ylabel('XY error mm');axes[1].set_ylabel('yaw error deg')
        for ax in axes:ax.legend();ax.grid();ax.set_xticks(np.arange(0,sm['path_m']+.5,.5))
        fig.suptitle('Same saved RGB; conditional maps, no production acceptance');fig.tight_layout();fig.savefig(a.output/(s['id']+'-error-curves.png'),dpi=130);plt.close(fig)
        with (a.output/(s['id']+'-half-metre.csv')).open('x') as f:
            w=csv.writer(f);w.writerow(['start_m','end_m','model','end_xy_mm','max_xy_mm','end_yaw_deg','requirement_frames','frames'])
            for b in sm['bins']:
                for n,m in b['models'].items():
                    if m:w.writerow([b['start_m'],b['end_m'],n,*[m[k] for k in ('end_xy_mm','max_xy_mm','end_yaw_deg','requirement_frames','frames')]])
        truth=read(Path(s['evaluation_source']));g=truth['frames'][0]['pose'] if s['world'] is None else next(r['truth_pose'] for r in truth['rows'] if r['world']==s['world'] and r['rid']==s['rid'])
        maps=read(a.output/(s['id']+'-maps.json'));fig,axes=plt.subplots(1,3,figsize=(15,5))
        for ax,n in zip(axes,NAMES):
            j=maps[n];cells=np.array(j['cells'],float).reshape(-1,5);points=(cells[:,:2]+.5)*RESOLUTION
            if n=='off':points=transform(points,g)
            colors=np.where(cells[:,2]>0,'black','lightgray');ax.scatter(points[:,0],points[:,1],c=colors,s=2,marker='s',rasterized=True)
            for o in s['static']['obstacles']:
                if 'wall' not in o['id']:continue
                hx,hy=o['half_extents_m'];q=transform([[-hx,-hy],[hx,-hy],[hx,hy],[-hx,hy],[-hx,-hy]],[*o['center_m'],o.get('yaw_rad',0)])
                ax.plot(q[:,0],q[:,1],color='tab:red',lw=.6)
            ax.set_aspect('equal');ax.set_title(n+' own occupancy');ax.grid()
        # Same viewport includes all three maps; no concealed off-map drift.
        xlim=(min(ax.get_xlim()[0] for ax in axes),max(ax.get_xlim()[1] for ax in axes));ylim=(min(ax.get_ylim()[0] for ax in axes),max(ax.get_ylim()[1] for ax in axes))
        for ax in axes:ax.set_xlim(xlim);ax.set_ylim(ylim)
        fig.suptitle('Black occupied / gray free / white unknown; red authored walls (evaluation overlay)');fig.tight_layout();fig.savefig(a.output/(s['id']+'-own-map-before-after.png'),dpi=130);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',choices=['gcp5','gcp3'],required=True);p.add_argument('--kind',choices=['long','streams'],required=True)
    p.add_argument('--stage',choices=['predict','score','plots'],required=True)
    for n in ('input','output','calibration','requirements','queue','stack-check'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-'+a.host):raise ValueError('ORIGINAL_VM_ONLY')
    globals()[a.stage](a)
