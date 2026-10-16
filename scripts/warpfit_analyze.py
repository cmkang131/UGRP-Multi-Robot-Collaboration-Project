"""gcp2-only analysis of immutable warpfit evaluator records; no stepping."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys


def dump(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def stats(values):
    import numpy as np
    x=np.asarray(values)
    return dict(min=float(x.min()),p05=float(np.percentile(x,5)),p50=float(np.median(x)),
                p95=float(np.percentile(x,95)),max=float(x.max()))


def pose(q):
    import numpy as np
    w,x,y,z=q[3:7]/np.linalg.norm(q[3:7])
    return np.array([q[0],q[1],math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))])


def tilt(q):
    import numpy as np
    w,x,y,z=q[3:7]/np.linalg.norm(q[3:7])
    return float(np.degrees(np.arccos(np.clip(1-2*(x*x+y*y),-1,1))))


def model(folder,assets):
    import mujoco
    meta=json.loads((folder/'fixture.json').read_text())
    os.chdir(assets)
    xml=(folder/'scene.xml').read_text()
    xml=xml.replace('/home/ugrp/ugrp-sim/src/warpfit-teacher-6f057f7e',str(assets))
    xml=xml.replace('/home/ugrp/ugrp-sim/runs/warpfit/inputs/src/drivecheck-renderer-5974a181',str(assets))
    m=mujoco.MjModel.from_xml_string(xml)
    f=__import__('numpy').load(folder/'fixture.npz')
    for k in ('cam_pos','cam_quat','cam_resolution','cam_sensorsize','cam_intrinsic'):
        if k in f:getattr(m,k)[:]=f[k]
    return m,meta,f


def grip(folder,m,meta):
    import numpy as np
    import mujoco
    s=np.load(folder/'states.npz');t=s['t'];qp=s['qpos'];force=s['finger_force']
    selected=np.flatnonzero(t>meta['hold_start_s']+1e-8)
    target=m.body(meta['target_body']).id
    gids=[m.geom(n).id for n in meta['target_geoms']]
    grippers=[m.body(rid+'__gripper').id for rid in (('r1',) if meta['kind']=='box' else ('r1','r2'))]
    d=mujoco.MjData(m);rows=[];temporal=[]
    for w in range(qp.shape[1]):
        heights=[];rel=[];tilts=[]
        for i in selected:
            d.qpos[:]=qp[i,w];mujoco.mj_kinematics(m,d)
            heights.append(min(float(d.geom_xpos[g,2]-np.abs(d.geom_xmat[g].reshape(3,3)[2])@m.geom_size[g]) for g in gids))
            center=np.mean([d.xpos[g] for g in grippers],axis=0)
            # Relative load COM in r1 gripper axes removes common base motion.
            rel.append(d.xmat[grippers[0]].reshape(3,3).T@(d.xpos[target]-center))
            base=int(m.jnt_qposadr[m.body_jntadr[m.body('r1__robot').id]])
            tilts.append(tilt(qp[i,w,base:base+7]))
        if not heights:continue
        slip=np.linalg.norm(np.asarray(rel)-rel[0],axis=1)
        contacts=np.all(force[selected,w]>0,axis=1)
        temporal.extend(dict(world=w,t=float(t[i]),height_m=float(h),slip_m=float(sl),all_fingers=bool(c))
                        for i,h,sl,c in zip(selected,heights,slip,contacts))
        rows.append(dict(world=w,hold_samples=len(selected),all_finger_samples=int(sum(contacts)),
                         # Existing frozen teacher's12mm loaded-clearance
                         # criterion, not a newly fitted slip tolerance.
                         loaded_contact_samples=int(sum(c and h>=.012 for c,h in zip(contacts,heights))),
                         height_m=stats(heights),slip_m=stats(slip),tilt_deg=stats(tilts)))
    return rows,temporal


def drive(folder,m,meta,case):
    import numpy as np
    s=np.load(folder/'states.npz');t=s['t'];qp=s['qpos']
    cases={r['id']:r for r in meta['cases']}
    mapping=meta.get('groups',{}).get(case,[case]);rows=[]
    base=int(m.jnt_qposadr[m.body_jntadr[m.body('r1__robot').id]])
    def at(value):
        ids=np.flatnonzero(np.abs(t-value)<1e-8)
        return int(ids[0]) if len(ids) else None
    for w in range(qp.shape[1]):
        name=mapping[w%len(mapping)];row=cases[name]
        start=at(row['settle_s']);end=at(row['settle_s']+row['duration_s']);stop=at(row['settle_s']+row['duration_s']+row['tail_s'])
        if start is None or end is None or stop is None:
            rows.append(dict(world=w,case=name,status='boundary_not_recorded'));continue
        for phase,i in [('pulse',end),('pulse_plus_stop',stop)]:
            a,b=pose(qp[start,w,base:base+7]),pose(qp[i,w,base:base+7]);delta=b-a
            delta[2]=(delta[2]+math.pi)%(2*math.pi)-math.pi
            c,z=math.cos(a[2]),math.sin(a[2]);delta[:2]=np.array([[c,z],[-z,c]])@delta[:2]
            pred=row.get('v122');prediction=None
            prediction_time=None;elapsed=float(t[i]-t[start])
            if pred:
                prediction_time=float(np.clip(elapsed,pred['times'][0],pred['times'][-1]))
                prediction=[float(np.interp(prediction_time,pred['times'],np.array(pred['mean_curve'])[:,j])) for j in range(3)]
            actual=abs(delta[2]) if row['axis']=='turn' else np.linalg.norm(delta[:2])
            pv=None if prediction is None else (abs(prediction[2]) if row['axis']=='turn' else np.linalg.norm(prediction[:2]))
            rows.append(dict(world=w,case=name,phase=phase,delta_xyyaw=delta.tolist(),
                translation_mm=float(np.linalg.norm(delta[:2])*1000),yaw_deg=float(np.degrees(delta[2])),
                actual_over_prediction=None if not pv else float(actual/pv),v122_delta=prediction,
                prediction_sample_time_s=prediction_time,prediction_elapsed_s=elapsed,
                prediction_tail_endpoint_held=prediction_time is not None and elapsed>prediction_time+1e-8,
                tilt_deg=stats([tilt(qp[j,w,base:base+7]) for j in range(start,i+1)])))
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--assets',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not os.uname().nodename.startswith('ugrp-sim-gcp2'):raise ValueError('gcp2 analysis only')
    import numpy as np
    a.output.mkdir(parents=True,exist_ok=False)
    models={'original':{k:model(a.root/k,a.assets) for k in ('box','beam','drive')}}
    if (a.root/'primitive-v1').exists():
        models['primitive-v1']={k:model(a.root/'primitive-v1'/k,a.assets) for k in ('box','beam','drive')}
    def protocol(report):return 'primitive-v1' if '/primitive-v1/' in report.get('fixture','') else 'original'
    results=[];rejections=[];thresholds={};sample_funnels=[]
    folders=sorted(a.root.glob('R*/**/result.json'))
    for rp in folders:
        r=json.loads(rp.read_text());folder=rp.parent
        if r.get('engine')=='cpu' and r.get('completed') and not r.get('cap_end'):
            kind='box' if 'box' in folder.name else 'beam' if 'beam' in folder.name else None
            if kind:
                pr=protocol(r);m,meta,f=models[pr][kind];rows,points=grip(folder,m,meta)
                if points:
                    thresholds[pr+'/'+kind]=dict(height_p05_m=float(np.percentile([v['height_m'] for v in points],5)),
                        slip_p95_m=float(np.percentile([v['slip_m'] for v in points],95)),
                        samples=len(points),positive_finger_samples=sum(v['all_fingers'] for v in points),
                        source=str(folder),source_states_sha256=hashlib.sha256((folder/'states.npz').read_bytes()).hexdigest(),
                        basis='fixed C3.12 reference temporal P05 height / P95 relative-hand displacement; no extra tolerance',
                        # Frozen teacher min_clearance_m=.012, source6f057f7e
                        # sim/grasp_act_solo_evaluation.py:10. Only establishes
                        # that the reference is loaded; candidate bounds below
                        # are measured C percentiles, with no invented margin.
                        established=all(v['all_fingers'] for v in points) and min(v['height_m'] for v in points)>=.012)
    for rp in folders:
        r=json.loads(rp.read_text());folder=rp.parent
        row=dict(path=str(folder),**{k:r.get(k) for k in ('engine','round','nworld','status','completed','HOST_ERROR','cap_end','sim_s',
            'physical_gpu_ms_per_step','wall_per_sim_s','amortized_wall_per_world_sim_s','setup_jit_s','runtime_wall_s','max_ncon','max_nefc','error')},
            profile=r['profile']['profile'])
        argv=r['reproduce'];case=argv[argv.index('--case')+1] if '--case' in argv else 'tape'
        kind='box' if 'box' in folder.name else 'beam' if 'beam' in folder.name else 'drive'
        row['kind']=kind;row['case']=case;row['protocol']=protocol(r)
        if r.get('completed') and not r.get('cap_end'):
            m,meta,f=models[row['protocol']][kind]
            if kind in ('box','beam'):
                worlds,points=grip(folder,m,meta);row['worlds']=worlds;ref=thresholds.get(row['protocol']+'/'+kind)
                row['threshold']=ref
                if points:
                    row['loaded_contact_rate']=sum(w['loaded_contact_samples'] for w in worlds)/len(points)
                    row['fully_retained_worlds']=sum(w['loaded_contact_samples']==w['hold_samples'] for w in worlds)
                if ref and ref['established']:
                    for w in worlds:
                        wp=[v for v in points if v['world']==w['world']]
                        w['pass_samples']=sum(v['all_fingers'] and v['height_m']>=ref['height_p05_m'] and v['slip_m']<=ref['slip_p95_m'] for v in wp)
                    row['hold_contact_rate']=sum(v['all_fingers'] for v in points)/len(points)
                    row['acceptance_sample_rate']=sum(w['pass_samples'] for w in worlds)/len(points)
                    contact=[v for v in points if v['all_fingers']]
                    height=[v for v in contact if v['height_m']>=ref['height_p05_m']]
                    retained=[v for v in height if v['slip_m']<=ref['slip_p95_m']]
                    sample_funnels.append(dict(raw=str(folder),unit='world x recorded hold frame; repeated fixture, not independent seeds',
                        stages=[dict(gate='hold_frames',cumulative_pass=len(points),rejected=0),
                            dict(gate='all_fingers_positive',cumulative_pass=len(contact),rejected=len(points)-len(contact)),
                            dict(gate='height_at_least_C_p05',cumulative_pass=len(height),rejected=len(contact)-len(height)),
                            dict(gate='relative_slip_at_most_C_p95',cumulative_pass=len(retained),rejected=len(height)-len(retained))]))
                    for category,count in [('grasp_contact_loss',len(points)-len(contact)),
                                           ('height_below_C_p05',len(contact)-len(height)),
                                           ('slip_above_C_p95',len(height)-len(retained))]:
                        if count:
                            rejections.append(dict(category=category,count=count,reason=category,
                                blocked_object=meta['target_body'],minimum_gap_m=None,
                                gap_status='not_measured_per_world; world0 contact distances retained',raw=str(folder)))
                row['slip_p95_mm']=stats([w['slip_m']['p95']*1000 for w in worlds]) if worlds else None
            else:
                row['pulses']=drive(folder,m,meta,case)
                row['valid_for_odom_calibration']=False
                row['fixture_limit']='unchanged drivecheck initial chassis/cargo_box_00 overlap; causal fix owned by drivecheck'
        if not r.get('completed'):
            error=r.get('error','incomplete')
            # Pinned OverflowType.LS_ITERATIONS=1024. Historical benchmark
            # error text said CAPACITY_OVERFLOW for every overflow bit; retain
            # it verbatim while distinguishing the actual solver limit.
            category='solver_line_search_limit' if '1024' in error else 'HOST_ERROR'
            row['rejection_category']=category
            rejections.append(dict(category=category,reason=error,blocked_object='physics_engine',minimum_gap_m=None,gap_status='not_geometric',raw=str(folder)))
        results.append(row)
    dump(a.output/'thresholds.json',thresholds)
    dump(a.output/'rows.json',results)
    dump(a.output/'rejection_table.json',dict(stages=[dict(gate='recorded_runs',cumulative_pass=len(results),rejected=0),
        dict(gate='fixed_work_complete',cumulative_pass=sum(bool(r['completed']) for r in results),rejected=sum(not r['completed'] for r in results)),
        dict(gate='full_protocol_not_smoke',cumulative_pass=sum(bool(r['completed']) and not r['cap_end'] for r in results),rejected=sum(bool(r['cap_end']) for r in results))],reasons=rejections,
        sample_funnels=sample_funnels,raw=str(a.root),reproduce=sys.argv))
    dump(a.output/'summary.json',dict(runs=len(results),completed=sum(bool(r['completed']) for r in results),
        HOST_ERROR=sum(bool(r['HOST_ERROR']) for r in results),thresholds=thresholds,default_changes=0,source='gcp6 only; gcp2 analysis; C references separate',reproduce=sys.argv))
    print(json.dumps(dict(runs=len(results),HOST_ERROR=sum(bool(r['HOST_ERROR']) for r in results),thresholds=thresholds)))


if __name__=='__main__':main()
