"""Recount terminal GCP2 runs; all truth access stays in this evaluator."""
import argparse,collections,hashlib,json,math,platform
from pathlib import Path
import numpy as np
from baseline_analyzer import carry,verify
from scripts.analyze_reloc11_selfmap import rows,obj
from scripts.analyze_reloc14 import selfmap
from scripts.analyze_reloc13 import distribution
from harness.natural_floor_slam import compose,wrap,transform
from harness.selfmap4_geometry import static_input
from harness.own_map_amcl_vendor.landmarks import MapFeatures

def errors(es):
    return dict(N=len(es),xy_m=distribution([x[0] for x in es]),yaw_deg=distribution([x[1] for x in es]))

def analysis(folder):
    raw=folder/'raw';trace=rows(raw/'trace.jsonl');truth={round(r['t'],6):r for r in rows(raw/'eval_only/trajectory.jsonl')}
    actual0=None;command=[];local=[];drivecmd=[];registered=0;matches=[];angles=[];scored=[];fresh=[]
    static,_=static_input();mapped=MapFeatures(static)
    for r in trace:
        gt=truth.get(round(r['t'],6));s=r.get('static_registration',{});packet=s.get('reloc12',{}).get('replay',{})
        if gt is None:continue
        actual=np.array([*gt['robot_xyz_m'][:2],gt['robot_yaw_rad']])
        if actual0 is None:actual0=actual
        def err(p):return [float(np.linalg.norm(p[:2]-actual[:2])),abs(math.degrees(wrap(p[2]-actual[2])))]
        used=r.get('stage') in ('frontier_drive','frontier','drive') or r.get('issued_command',{}).get('kind') in ('drive','move')
        own=packet.get('own_odometry_pose')
        if own is not None:
            e=err(compose(actual0,own));command.append(e)
            if used:drivecmd.append(e)
        local.append(err(compose(actual0,r['pose'])))
        registered+=bool(s.get('registered'))
        if s.get('registered') and s.get('updated'):
            fresh.append(dict(t=r['t'],pf_error=err(np.asarray(s['world_pose'])),sigma_yaw_deg=math.degrees(math.sqrt(max(0.,np.asarray(s.get('raw_covariance',s['covariance']))[2,2])))))
        # Evaluation-only nearest same-hue line residual. Correspondence here
        # is for scoring camera bias and NEVER enters a controller packet.
        for f in packet.get('lines',[]):
            if f['kind']!='floor_line':continue
            world=transform(f['endpoints'],actual);angle=math.atan2(f['normal'][1],f['normal'][0])+actual[2];candidates=[]
            for e in mapped.edges:
                hd=abs(e['hue']-f['hue']);hd=min(hd,180-hd)
                if hd>12:continue
                a,b=np.asarray(e['a']),np.asarray(e['b']);v=b-a
                residual=world-a-np.clip((world-a)@v/(v@v),0,1)[:,None]*v
                candidates.append((float(np.linalg.norm(residual,axis=1).max()),abs(math.degrees(wrap(angle-math.atan2(e['normal'][1],e['normal'][0]))))))
            if candidates:
                d,a=min(candidates);matches.append(d);angles.append(a)
                scored.append(dict(t=r['t'],distance_m=d,normal_error_deg=a))
    return dict(command_only_replay=errors(command),local_execution_drift=errors(local),command_only_same_drive_frames=errors(drivecmd),
        evaluation_alignment='initial evaluator world pose used ONLY for analysis alignment, never supplied to controller; local drift and absolute registered error are separate',registered_frames=registered,
        floor_line_residuals=dict(distance_m=distribution(matches),normal_deg=distribution(angles),scope='all same-hue features; no truth-based outlier exclusion; nearest finite edge in evaluator'),
        fresh_pose_evaluation=fresh,residual_frames=scored)

def main(queuefile,output=None):
    assert platform.node().startswith('ugrp-sim-gcp2')
    queuefile=Path(queuefile);queue=obj(queuefile);reports=[]
    for t in queue['runs']:
        folder=Path(t['raw']).parent;result=obj(Path(t['raw'])/'result.json')
        assert result.get('status') and result['status'] not in ('running','RUNNING'),t['name']
        r={k:t.get(k) for k in ('name','kind','condition','seed','source_sha','raw')}
        r.update(status=result['status'],termination=result.get('termination_category'),integrity=verify(Path(t['raw'])))
        if t['kind']=='selfmap' and result.get('frames',0):
            base=selfmap(folder);extra=analysis(folder)
            (folder/'analysis-full.json').write_text(json.dumps(dict(base=base,extra=extra),indent=2)+'\n')
            r.update({k:base[k] for k in ('drive_errors','registered_errors','false_registration_events','registration_frame_funnel','known_mode_measurement_funnel','first30','input_audit','termination')})
            r.update({k:v for k,v in extra.items() if k not in ('fresh_pose_evaluation','residual_frames')})
            r['fresh_pose_error']=errors([e['pf_error'] for e in extra['fresh_pose_evaluation']])
        elif t['kind']=='carry' and result['status']=='complete':r.update(carry(folder,result))
        else:r.update(failure=result.get('failure'),frames=result.get('frames',0))
        r['source_hashes']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(t['raw'])/'result.json',folder/'task.json') if p.exists()}
        reports.append(r)
    data=dict(schema='ugrp.reloc17.analysis.v1',analysis_host='gcp2',source_queue=str(queuefile),reproduce=f'PYTHONPATH=. {__file__} --queue {queuefile}',runs=reports)
    out=Path(output) if output else queuefile.parent;out.mkdir(exist_ok=True,parents=True);(out/'summary.json').write_text(json.dumps(data,indent=2)+'\n')
    rejection=dict(source_queue=str(queuefile),runs=[dict(run=r['name'],raw=r['raw'],**r['registration_frame_funnel']) if 'registration_frame_funnel' in r else dict(run=r['name'],heading=r.get('heading'),failure=r.get('failure')) for r in reports])
    (out/'rejection-table.json').write_text(json.dumps(rejection,indent=2)+'\n')
    lines=['# 분해/폐루프 재집계','', '|조건·시드|상태·종료|등록 프레임|절대 주행 xy 중앙/p95|동일 주행 명령만 xy 중앙/p95|명령만 전체 xy 중앙/p95|','|---|---|---:|---|---|---|']
    def fmt(x):
        d=x.get('xy_m',{});return f"{d['p50']:.4f}/{d['p95']:.4f} (N={x['N']})" if x.get('N') else '미측정 N=0'
    for r in reports:
        if r['kind']=='selfmap':lines.append(f"|{r.get('condition') or r['name']} {r['seed']}|{r['status']} {r.get('termination')}|{r.get('registered_frames','?')}|{fmt(r.get('drive_errors',{}))}|{fmt(r.get('command_only_same_drive_frames',{}))}|{fmt(r.get('command_only_replay',{}))}|")
    (out/'table.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--queue',required=True);p.add_argument('--output');a=p.parse_args();main(a.queue,a.output)
