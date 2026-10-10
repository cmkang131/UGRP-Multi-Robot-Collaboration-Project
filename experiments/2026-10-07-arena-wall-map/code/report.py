"""Saved-result report and read-only posthoc diagnostics. Never fits parameters."""
from pathlib import Path
import hashlib
import json
import math
import subprocess
import numpy as np
import replay as r
from harness.self_odom_grid import OdomGrid,transform
from harness.self_pose_graph import between
from harness.self_pulse_odom import model,profile_key
c,ROOT,EXP,RAW=r.c,r.ROOT,r.EXP,r.RAW


def summarize(v):
    v=np.asarray(v)
    return dict(n=len(v),median=float(np.median(v)),p90=float(np.percentile(v,90)),max=float(np.max(v))) if len(v) else dict(n=0)


def main():
    table=[]
    for n in range(1042,1048):
        path=ROOT/f'experiments/2026-10-05-ego-wall-map-probe/results/v3_confidence_v1/s{n}.json'
        old=c.read(path)
        metric=old['metrics']['v3_unloaded_extrinsic_v1__confidence']
        table.append(dict(case=f's{n}',plant='off / old transport',estimator='M1 + RBPF100 + graph + confidence',
            samples=old['wall_samples'],source=str(path.relative_to(ROOT)),sha256=c.sha(path),**metric))
    oldpath=ROOT/'experiments/2026-10-07-servo-stiffness/results/short-map.json'
    old=c.read(oldpath)
    table.append(dict(case='egomap19 30s',plant='real_v1 / short route',estimator='v122 + RBPF100 + graph + confidence',
        samples=329,source=str(oldpath.relative_to(ROOT)),sha256=c.sha(oldpath),final=old['quality'],**old['path']))
    diagnostics={}
    for case in ('forward','reverse'):
        out=RAW/'predictions'/case
        receipt=c.read(out/'baseline-prediction.json')
        assert all(c.sha(out/p)==h for p,h in receipt['hashes'].items())
        result=c.read(EXP/'results'/(case+'.json'))
        for estimator in ('dr','rbpf_graph'):
            table.append(dict(case='egomap20 '+case,plant='real_v1 / tour',estimator=estimator,
                samples=result['wall_sample_count'],**result['metrics'][estimator]))
        ep=RAW/case
        truth=c.old.current_truth(ep)
        times=np.array(sorted(truth))
        origin=truth[min(truth)]
        rects=np.array([w['center_m']+w['half_extents_m'] for w in c.read(ep/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall'])
        grid=OdomGrid('r3')
        grid.cells={(x,y):v for x,y,v in c.read(out/'frontend-grid.json')['cells']}
        poses=c.old.base.read_rows(out/'frontend-poses.jsonl')
        pre=dict(final=c.old.base.quality(transform(grid.occupied_points(),origin),rects,c.old.base.wall_samples(rects))[0],
                 **c.old.path_score(poses,truth))
        graph=c.read(out/'graph-diagnostics.json')
        ledger=c.old.base.read_rows(out/'frontend-ledger.jsonl')
        loops=[]
        for event in graph['loops']:
            if not event['accepted']:continue
            sub=graph['submaps'][event['submap']]
            base=origin if event['submap']==0 else truth[round(sub['interval'][0],6)]
            target=truth[round(ledger[event['scan']]['t'],6)]
            delta=between(base,target)
            estimated=np.array(event['relative_pose'])
            yaw=(estimated[2]-delta[2]+np.pi)%(2*np.pi)-np.pi
            loops.append(dict(submap=event['submap'],scan=event['scan'],
                translation_error_m=float(np.linalg.norm(estimated[:2]-delta[:2])),yaw_error_deg=float(abs(np.degrees(yaw)))))
        pulses={}
        _,commands=c.old.own_inputs(ep,'r3')
        for cmd in commands:
            if cmd['kind']!='mecanum':continue
            key=profile_key(cmd,False)
            profile=model()['profiles'][key]
            end=round(cmd['t']+(.8 if cmd['left'] else .2),6)
            start=round(cmd['t'],6)
            if start not in truth or end not in truth:continue
            gt=between(truth[start],truth[end])
            prediction=np.asarray(profile['mean_curve'][-1])
            pulses.setdefault(key,[]).append(dict(t=start,expected=prediction.tolist(),actual=gt.tolist()))
        pulse_summary={k:dict(n=len(v),actual_yaw_deg=summarize([math.degrees(x['actual'][2]) for x in v]),
            expected_yaw_deg=math.degrees(v[0]['expected'][2]),
            translation_residual_m=summarize([np.linalg.norm(np.array(x['expected'][:2])-x['actual'][:2]) for x in v])) for k,v in pulses.items()}
        contact_rows=c.old.base.read_rows(ep/'eval_only/contacts.jsonl')
        walls=[dict(t=row['t'],**contact) for row in contact_rows for contact in row['contacts']
               if any(str(contact.get(k,'')).startswith('r3__') for k in ('geom1','geom2'))
               and any('wall' in str(contact.get(k,'')) for k in ('geom1','geom2'))]
        diagnostics[case]=dict(role='posthoc evaluation only; no coefficient or gate changes',frontend=pre,
            optimization=graph['optimization'],accepted_loop_errors=loops,pulse_summary=pulse_summary,wall_contacts=walls)
    c.dump(EXP/'results/comparison.json',table)
    c.dump(EXP/'results/posthoc-diagnostics.json',diagnostics)
    columns=['|녹화·강성|추정|P %|전체 R/덮임 % (분모)|벽 RMSE m|자세 RMSE m|종료 XY m|',
             '|---|---|---:|---:|---:|---:|---:|']
    for row in table:
        q=row['final']
        columns.append(f"|{row['case']} · {row['plant']}|{row['estimator']}|{q['precision_015']*100:.1f}|{q['wall_coverage']*100:.1f} ({row['samples']})|{q['wall_error_rmse_m']:.3f}|{row['path_position_error']['rmse_m']:.3f}|{row['end_position_error_m']:.3f}|")
    (EXP/'results/table.md').write_text('\n'.join(columns)+'\n')
    # Recording and source integrity, including unsuccessful physics.
    physical=[]
    for case in ('forward','reverse'):
        ep=RAW/case
        manifest=c.read(ep/'artifacts.sha256.json')
        assert all(c.sha(ep/p)==h for p,h in manifest.items())
        physical.append(c.read(ep/'result.json'))
    frozen=c.read(EXP/'freeze.json')
    assert all(c.sha(ROOT/p)==h for p,h in frozen['files'].items())
    from scripts.run_wall_parallax_strafe import USER_FILES
    assert all(c.sha(ROOT/p)==h for p,h in USER_FILES.items())
    managed=[]
    for p in sorted((ROOT/'outputs/simulation-runs').glob('*arena-wall-map*/manifest.json')):
        j=c.read(p)
        assert not j['source_changed_during_run'] and not j['inputs_changed_during_run']
        managed.append(dict(path=str(p.relative_to(ROOT)),sha256=c.sha(p),status=j['status'],exit_code=j['exit_code'],source=j['source']['source_sha']))
    assert len(managed)==2
    files={str(p.relative_to(RAW)):dict(bytes=p.stat().st_size,sha256=c.sha(p)) for p in sorted(RAW.rglob('*')) if p.is_file()}
    total=sum(v['bytes'] for v in files.values())
    assert total<=350*1024**2
    c.dump(EXP/'results/raw-manifest.json',dict(root=str(RAW),remote_raw_backup=False,files=files))
    c.dump(EXP/'results/execution.json',dict(physical=physical,managed=managed,frozen_files=len(frozen['files']),
        raw_files=len(files),raw_bytes=total,preserved_user_files=USER_FILES,model_calls=0,freeze=False,
        fitting=False,extra_recording=False,export_implemented=False))
    print('\n'.join(columns))
    for case,d in diagnostics.items():print(case,'frontend',d['frontend'],'loops',d['accepted_loop_errors'],'pulse',d['pulse_summary'])


if __name__=='__main__':main()
