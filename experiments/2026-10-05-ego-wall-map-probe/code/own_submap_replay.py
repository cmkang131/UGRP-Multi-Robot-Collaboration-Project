"""Frozen own-ledger global SLAM, then separate evaluation; no simulator.

Reuse the six admitted positive-depth ledgers and final RBPF100 lineage. Frontend
estimation is not rerun or scored with truth. This is an offline backend test.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import projection_guard_replay as guard
from own_map_csm_replay import acceptance, path_errors, predict, write_rows
from harness.self_pose_graph import GraphOptions, VALUES, apply_pose_graph, rebuild

base=guard.base
SOURCE=base.ROOT/'outputs/wall-projection-guard-v1-complete'


def sha_source():
    return subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()


def graph_criteria(off,baseline,on,invalid,golden):
    check=acceptance(off,on)['checks']
    check.update(zero_invalid_endpoints=invalid==0,zero_behind_camera_evidence=invalid==0,
                 guard_precision_nondecrease=on['final']['precision_015']+1e-12>=baseline['final']['precision_015'],
                 guard_visible_recall_within_2pp=on['final']['recall_visible']+1e-12>=baseline['final']['recall_visible']-.02,
                 off_bytes=all(golden.values()))
    return check


def run_case(name,out,mode):
    robot=name[-2:]
    source=SOURCE/name
    prior=guard.load(source/'summary.json')
    baseline_summary=guard.load(guard.BASELINE/name/'summary.json')
    episode=Path(baseline_summary['episode'])
    framepath=episode/f'robots/{robot}/frames.jsonl'
    commandpath=episode/f'robots/{robot}/commands.jsonl'
    for path,h in prior['prediction_hashes'].items():
        assert base.sha(source/path)==h, path
    expected={r['path']:r['sha256'] for r in prior['sources']}
    for path in (framepath,commandpath):
        assert base.sha(path)==expected[str(path)]
    out.mkdir(parents=True,exist_ok=False)
    ledger=base.read_rows(source/'guarded-ledger.jsonl')
    old_path=base.read_rows(source/'rbpf100-fixed-poses.jsonl')
    # Explicit own-frame provenance; do not trust a label added to peer data.
    frames_list=base.read_rows(framepath)
    frames={r['frame_id']:r for r in frames_list}
    assert all(f['robot_id']==robot and f['camera']=='robot_cam' for f in frames_list)
    assert [r['t'] for r in old_path]==[f['sim_time'] for f in frames_list]
    assert all(r['frame_id'] in frames and r['t']==frames[r['frame_id']]['sim_time'] for r in ledger)
    invalid=0
    for row in ledger:
        origin,rotation=guard.own_camera(frames[row['frame_id']])
        _,_,valid=guard.floor_depths(row['segments'],origin,rotation)
        invalid+=int((~valid).sum())
    assert invalid==0
    own_rows=[{**r,'robot_id':robot} for r in ledger]
    own_path=[{**r,'robot_id':robot} for r in old_path]
    # Run off pass even when on. Exact returned input objects audit inertness.
    disabled_rows,disabled_poses,_=apply_pose_graph(ledger,old_path,robot_id=robot)
    assert disabled_rows is ledger and disabled_poses is old_path
    print(name,'graph prediction started',flush=True)
    corrected,corrected_path,diagnostic=apply_pose_graph(own_rows,own_path,robot_id=robot,pose_graph=mode)
    graph_grid=rebuild(robot,corrected)
    rbpf_grid=rebuild(robot,disabled_rows)
    graph_poses=[{k:r[k] for k in ('t','pose')} for r in corrected_path]
    contacts=[{k:r[k] for k in ('t','frame_id','camera','segments')} for r in base.read_rows(guard.BASELINE/name/'observations.jsonl')]
    off,off_poses,*_=predict(base.read_rows(commandpath),frames_list,contacts,robot,'off')
    golden={
        'graph_off_ledger_bytes':''.join(json.dumps(r,allow_nan=False)+'\n' for r in disabled_rows).encode()==(source/'guarded-ledger.jsonl').read_bytes(),
        'graph_off_pose_bytes':''.join(json.dumps(r,allow_nan=False)+'\n' for r in disabled_poses).encode()==(source/'rbpf100-fixed-poses.jsonl').read_bytes(),
        'graph_off_cells_bytes':json.dumps(rbpf_grid.export()['cells']).encode()==json.dumps(guard.load(source/'rbpf100_guard-grid.json')['cells']).encode(),
        'graph_off_llm_bytes':(rbpf_grid.text().replace('drift uncorrected','drift uncertain')+'\n').encode()==(source/'rbpf100_guard-llm.txt').read_bytes(),
        'dr_off_pose_bytes':''.join(json.dumps(r,allow_nan=False)+'\n' for r in off_poses).encode()==(guard.BASELINE/name/'poses.jsonl').read_bytes(),
        'dr_off_cells_bytes':json.dumps(off.self_map.export()['cells']).encode()==json.dumps(guard.load(source/'off-grid.json')['cells']).encode(),
        'dr_off_llm_bytes':(off.self_map.text()+'\n').encode()==(source/'off-llm.txt').read_bytes(),
    }
    assert all(golden.values()),golden
    for a,b in zip(own_rows,corrected):
        assert {k:v for k,v in a.items() if k!='pose'}=={k:v for k,v in b.items() if k!='pose'}
    for label,grid in [('off',off.self_map),('rbpf100_guard',rbpf_grid),('graph',graph_grid)]:
        base.dump(out/f'{label}-grid.json',grid.export())
    (out/'graph-llm.txt').write_text(graph_grid.text().replace('drift uncorrected','own submap graph; drift uncertain')+'\n')
    write_rows(out/'graph-ledger.jsonl',corrected)
    write_rows(out/'graph-poses.jsonl',graph_poses)
    write_rows(out/'off-poses.jsonl',off_poses)
    shutil.copyfile(source/'rbpf100-fixed-poses.jsonl',out/'rbpf100_guard-poses.jsonl')
    if diagnostic is not None:
        write_rows(out/'loops.jsonl',diagnostic['loops'])
        base.dump(out/'submaps.json',diagnostic['submaps'])
        base.dump(out/'constraints.json',diagnostic['constraints'])
        base.dump(out/'optimization.json',diagnostic['optimization'])
    frozen={p.name:base.sha(p) for p in out.iterdir() if p.is_file()}
    print(name,'prediction frozen; evaluation starts',flush=True)
    # Evaluation only from here: initial GT alignment, walls, fixed visibility.
    origin=np.array(prior['origin_eval_only'])
    walls=[w for w in guard.load(episode/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall']
    rects=np.array([w['center_m']+w['half_extents_m'] for w in walls])
    visible=guard.load(guard.DIAG/name/'wall_samples.json')
    samples=np.array(visible['xy'])
    masks={k:np.array(visible[k]) for k in prior['visibility_counts']}
    gt_grid=base.OdomGrid(robot)
    gt_grid.cells={(x,y):v for x,y,v in guard.load(source/'gt_guard-grid.json')['cells']}
    base.dump(out/'gt_guard-grid.json',gt_grid.export())
    quality={c:guard.diag.measure(g,origin,rects,samples,masks) for c,g in
             [('off',off.self_map),('rbpf100_guard',rbpf_grid),('graph',graph_grid),('gt_guard',gt_grid)]}
    for c in ('off','rbpf100_guard','gt_guard'):
        assert quality[c]==prior['metrics'][c]
    metrics={}
    for c,poses in [('off',off_poses),('rbpf100_guard',old_path),('graph',graph_poses)]:
        dist,errors=path_errors(episode,robot,poses)
        metrics[c]={'final':quality[c],'path_position_error':dist,'end_position_error_m':errors[-1]['xy_error_m'],
                    'end_yaw_error_deg':errors[-1]['yaw_error_deg']}
        write_rows(out/f'{c}-path-errors.jsonl',errors)
    metrics['gt_guard']={'final':quality['gt_guard'],'scope':'evaluation-only map; not estimator performance'}
    assert metrics['rbpf100_guard']['path_position_error']==prior['unchanged_rbpf_pose_metrics']['path_position_error']
    checks=graph_criteria(metrics['off'],metrics['rbpf100_guard'],metrics['graph'],invalid,golden)
    for path,h in frozen.items():
        assert base.sha(out/path)==h
    sources=[source/'summary.json',source/'guarded-ledger.jsonl',source/'rbpf100-fixed-poses.jsonl',
             source/'gt_guard-grid.json',source/'projection-decisions.jsonl',framepath,commandpath,
             guard.BASELINE/name/'observations.jsonl',guard.DIAG/name/'wall_samples.json',episode/'inputs/static_map.json',
             episode/'eval_only/trajectory.jsonl']
    result={'case':name,'source_sha':sha_source(),'pose_graph':mode,'split':'development' if name.startswith('s911') else 'confirmation_replay',
        'options':asdict(GraphOptions()),'metrics':metrics,'checks':checks,'success':all(checks.values()),'golden':golden,
        'origin_eval_only':origin.tolist(),'visibility_counts':prior['visibility_counts'],'accepted_invalid_endpoints':invalid,
        'loop_counts':diagnostic['loop_counts'] if diagnostic else {},'optimization':diagnostic['optimization'] if diagnostic else {'reason':'off'},
        'changed':diagnostic['changed'] if diagnostic else False,'submaps':len(diagnostic['submaps']) if diagnostic else 0,
        'inserted_scans':len(corrected),'path_frame_count':len(graph_poses),'prediction_hashes':frozen,
        'scope':'offline global backend on final-particle ledger; local estimator unchanged; no new simulation',
        'path_convention':'apply latest final-lineage scan local/global transform to saved online max-particle path',
        'sources':[{'path':str(p.resolve()),'sha256':base.sha(p)} for p in sources]}
    base.dump(out/'summary.json',result)
    print(name,json.dumps({'loops':result['loop_counts'],'optimization':result['optimization'],'checks':checks,
                           'end_xy_m':metrics['graph']['end_position_error_m'],'map':quality['graph']}),flush=True)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--pose-graph',choices=VALUES,default='off')
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    sha=sha_source()
    options=asdict(GraphOptions())
    files=[Path('harness/self_pose_graph.py'),Path('harness/self_wall_memory.py'),Path(__file__)]
    hashes={str(p):base.sha(p) for p in files}
    environment={k:version(k) for k in ('numpy','scipy')}
    base.dump(args.output/'environment.json',{'packages':environment,'new_installations':False,'timing_benchmark':False})
    results=[]
    for i,case in enumerate(guard.CASES):
        assert sha_source()==sha and all(base.sha(p)==h for p,h in hashes.items())
        if i==2:
            base.dump(args.output/'development_fixed.json',{'source_sha':sha,'source_hashes':hashes,'pose_graph':args.pose_graph,
                'options':options,'development':[{'case':r['case'],'success':r['success']} for r in results],
                'tuning':False,'confirmation_cases':guard.CASES[2:]})
        results.append(run_case(case,args.output/case,args.pose_graph))
    assert environment=={k:version(k) for k in environment}
    base.dump(args.output/'cohort.json',{'source_sha':sha,'source_hashes':hashes,'pose_graph':args.pose_graph,'options':options,
        'cases':[{'case':r['case'],'success':r['success']} for r in results],
        'development_pass':sum(r['success'] for r in results[:2]),'confirmation_pass':sum(r['success'] for r in results[2:])})


if __name__=='__main__':
    main()
