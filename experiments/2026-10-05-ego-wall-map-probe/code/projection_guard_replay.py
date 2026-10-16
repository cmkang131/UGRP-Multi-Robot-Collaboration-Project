"""Offline insertion-only ablation: preserve the saved RBPF100 pose lineage.

No fresh RBPF inference, simulation, renderer, model or timing benchmark. The
prediction phase accepts own detections/command camera calibration and previously
estimated poses. GT is opened only after guarded map artifacts are frozen.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import map_error_oracle as diag
import odom_grid_replay as base
from own_map_csm_replay import predict as predict_off
from harness.wall_projection_guard import VALUES, filter_segments, floor_depths

ROOT = base.ROOT
CASES = [f's{s}-{r}' for s in (911,912,913) for r in ('r1','r2')]
BASELINE = ROOT/'outputs/self-map-odom-grid-v1-complete'
RBPF = ROOT/'outputs/self-map-prob-rbpf-v1-complete/rbpf100'
DIAG = ROOT/'experiments/2026-10-05-ego-wall-map-probe/results/map_error_oracle_v2'


def load(path):
    return json.loads(Path(path).read_text())


def own_camera(frame):
    import markerless_probe as mp
    import wall_probe as wp
    from ego_wall_map import ARM_AXIS_OFFSET_M
    servo = {int(k): int(v) for k,v in frame['commanded_servo'].items()}
    cm = mp.column_model(servo, wp.detector_bias(servo, wp.is_loaded(servo), True), mp.column_positions(96,2))
    return cm.origin+[ARM_AXIS_OFFSET_M,0.,0.], cm._rot


def guarded_rows(rows, frames, robot, mode):
    """Pure own-data adapter; no truth/static map fields accepted or read."""
    kept, logs = [], []
    for row in rows:
        frame = frames[row['frame_id']]
        if frame['robot_id'] != robot or frame['camera'] != 'robot_cam':
            raise ValueError('FOREIGN_CAMERA')
        if abs(frame['sim_time']-row['t']) > 1e-8:
            raise ValueError('CONTACT_TIME_MISMATCH')
        origin, rotation = (None, None) if mode == 'off' else own_camera(frame)
        if mode != 'off' and not np.allclose(origin[:2], row['camera'], atol=1e-12, rtol=0):
            raise ValueError('CAMERA_FRAME_MISMATCH')
        local, event = filter_segments(row['segments'], wall_projection_guard=mode,
                                       camera_origin=origin, camera_rotation=rotation)
        if event is not None:
            event.update(t=row['t'], frame_id=row['frame_id'])
            logs.append(event)
        if len(local):
            kept.append({**row, 'segments': local})
    return kept, logs


def rebuild(robot, rows):
    grid = base.OdomGrid(robot)
    hit, miss = grid.hit, grid.miss
    for row in rows:
        weight = row.get('insertion_weight', 1.)
        grid.hit, grid.miss = hit*weight, miss*weight
        grid.insert(base.transform([row['camera']], row['pose'])[0],
                    [base.transform(s, row['pose']) for s in row['segments']])
    return grid


def criterion(reference, guarded, *, behind_false_cells, invalid_endpoints, golden, pose_fixed):
    return {'zero_invalid_endpoints': invalid_endpoints == 0,
            'zero_behind_camera_false_cells': abs(behind_false_cells) < 1e-12,
            'precision_nondecrease': guarded['precision_015']+1e-12 >= reference['precision_015'],
            'visible_recall_loss_at_most_2pp': guarded['recall_visible']+1e-12 >= reference['recall_visible']-.02,
            'off_bytes': all(golden.values()), 'poses_fixed': pose_fixed}


def run_case(name, output, mode):
    robot = name[-2:]
    before = load(BASELINE/name/'summary.json')
    episode = Path(before['episode'])
    frames_path = episode/f'robots/{robot}/frames.jsonl'
    commands_path = episode/f'robots/{robot}/commands.jsonl'
    frames_list = base.read_rows(frames_path)
    frames = {r['frame_id']: r for r in frames_list}
    rbpf_path = RBPF/name
    ledger_path = rbpf_path/'map_ledger.jsonl'
    # Verify archived own data and estimated-pose inputs before any use.
    archived = load(DIAG/name/'summary.json')
    source_hashes = {r['path']: r['sha256'] for r in archived['sources']}
    for p in (frames_path, ledger_path, rbpf_path/'grid.json'):
        assert base.sha(p) == source_hashes[str(p)]
    ledger = base.read_rows(ledger_path)
    contacts = [{k:r[k] for k in ('t','frame_id','camera','segments')}
                for r in base.read_rows(BASELINE/name/'observations.jsonl')]
    off, off_poses, _, _, _ = predict_off(base.read_rows(commands_path), frames_list, contacts, robot, 'off')
    legacy = rebuild(robot, ledger)
    disabled, _ = guarded_rows(ledger, frames, robot, 'off')
    disabled_grid = rebuild(robot, disabled)
    assert disabled == ledger
    guarded, logs = guarded_rows(ledger, frames, robot, mode)
    grid = rebuild(robot, guarded)
    output.mkdir(parents=True, exist_ok=False)
    # Prediction artifacts frozen here, BEFORE opening GT camera/state/map data.
    for label, g in (('off',off.self_map),('rbpf100',legacy),('rbpf100_guard',grid)):
        base.dump(output/f'{label}-grid.json', g.export())
        text = g.text() if label == 'off' else g.text().replace('drift uncorrected','drift uncertain')
        (output/f'{label}-llm.txt').write_text(text+'\n')
    diag.write_rows(output/'guarded-ledger.jsonl', guarded)
    diag.write_rows(output/'projection-decisions.jsonl', logs)
    shutil.copyfile(rbpf_path/'poses.jsonl',output/'rbpf100-fixed-poses.jsonl')
    frozen = {p.name:base.sha(p) for p in output.iterdir() if p.is_file()}
    old_off = base.OdomGrid(robot)
    old_off.cells = {(x,y):v for x,y,v in load(BASELINE/name/'grid.json')['cells']}
    golden = {
        'off_pose_bytes': ''.join(json.dumps(r,allow_nan=False)+'\n' for r in off_poses).encode() == (BASELINE/name/'poses.jsonl').read_bytes(),
        'off_cells_bytes': json.dumps(off.self_map.export()['cells']).encode() == json.dumps(load(BASELINE/name/'grid.json')['cells']).encode(),
        'off_llm_bytes': off.self_map.text().encode() == old_off.text().encode(),
        'rbpf100_guard_off_cells_bytes': json.dumps(disabled_grid.export()['cells']).encode() == json.dumps(load(rbpf_path/'grid.json')['cells']).encode(),
        'rbpf100_guard_off_llm_bytes': (disabled_grid.text().replace('drift uncorrected','drift uncertain')+'\n').encode() == (rbpf_path/'llm.txt').read_bytes(),
    }
    assert all(golden.values()), (name,golden)
    old_by_frame = {r['frame_id']:r for r in ledger}
    pose_fixed = (base.sha(output/'rbpf100-fixed-poses.jsonl') == base.sha(rbpf_path/'poses.jsonl')
                  and all(r['pose'] == old_by_frame[r['frame_id']]['pose'] for r in guarded))
    assert pose_fixed
    invalid = 0
    for row in guarded:
        origin, rotation = own_camera(frames[row['frame_id']])
        z, ray_t, valid = floor_depths(row['segments'], origin, rotation)
        invalid += int((~valid).sum())
    # Evaluation starts here. All saved estimates stay immutable.
    times, truth_array = base.ground_truth(episode,robot)
    truth = dict(zip(np.round(times,6),truth_array))
    origin = np.array(before['origin_eval_only'])
    walls = [w for w in load(episode/'inputs/static_map.json')['obstacles'] if w.get('kind') == 'wall']
    rects = np.array([w['center_m']+w['half_extents_m'] for w in walls])
    saved_visibility = load(DIAG/name/'wall_samples.json')
    samples = np.array(saved_visibility['xy'])
    masks = {k:np.array(saved_visibility[k]) for k in archived['visibility_counts']}
    oracle_rows = [{**r,'pose':diag.relative_pose(truth[round(r['t'],6)],origin).tolist()} for r in guarded]
    oracle = rebuild(robot,oracle_rows)
    base.dump(output/'gt_guard-grid.json',oracle.export())
    labels = {r['frame_id']:r for r in base.read_rows(episode/f'eval_only/{robot}/camera_labels.jsonl')}
    states = {round(r['t'],6):r for r in base.read_rows(episode/'eval_only/trajectory.jsonl')}
    evidence = diag.Evidence(diag.SavedGeometry(episode/'scene.xml'),frames,labels,states)
    audited, breakdown, false_cells = diag.audited_grid(robot,guarded,truth,origin,rects,evidence)
    assert audited.export()['cells'] == grid.export()['cells']
    metrics = {label:diag.measure(g,origin,rects,samples,masks) for label,g in
               (('off',off.self_map),('rbpf100',legacy),('rbpf100_guard',grid),('gt_guard',oracle))}
    for c in ('off','rbpf100'):
        assert metrics[c] == archived['conditions'][c]['original']
    checks = criterion(metrics['rbpf100'],metrics['rbpf100_guard'],behind_false_cells=breakdown['behind_camera_cell_equivalents'],
                       invalid_endpoints=invalid,golden=golden,pose_fixed=pose_fixed)
    diag.write_rows(output/'guard-false-cells.jsonl',false_cells)
    diag.write_rows(output/'pixel-evidence.jsonl',evidence.records)
    for name_,h in frozen.items():
        assert base.sha(output/name_) == h
    rbpf_summary = load(rbpf_path/'summary.json')
    sources = list(dict.fromkeys([frames_path,commands_path,BASELINE/name/'observations.jsonl',BASELINE/name/'grid.json',
        BASELINE/name/'poses.jsonl',ledger_path,rbpf_path/'poses.jsonl',rbpf_path/'grid.json',rbpf_path/'summary.json',
        DIAG/name/'summary.json',DIAG/name/'wall_samples.json',episode/'scene.xml',episode/'inputs/static_map.json',
        episode/'eval_only/trajectory.jsonl',episode/f'eval_only/{robot}/camera_labels.jsonl']))
    result = {'case':name,'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              'split':'development' if name.startswith('s911') else 'confirmation_replay',
              'wall_projection_guard':mode,'scope':'map-insertion ablation with frozen RBPF100 final-particle poses; not fresh SLAM',
              'metrics':metrics,'visibility_counts':archived['visibility_counts'],'origin_eval_only':origin.tolist(),
              'attribution':breakdown,'accepted_invalid_endpoints':invalid,'golden':golden,'checks':checks,'success':all(checks.values()),
              'guard':{'input_frames':len(ledger),'inserted_frames':len(guarded),
                       'input_segments':sum(len(r['segments']) for r in ledger),'inserted_segments':sum(len(r['segments']) for r in guarded),
                       'reasons':dict(Counter(s['reason'] for l in logs for s in l['segments']))},
              'unchanged_rbpf_pose_metrics':{k:rbpf_summary[k] for k in ('end_position_error_m','end_yaw_error_deg','path_position_error')},
              'prediction_hashes':frozen,'sources':[{'path':str(p),'sha256':base.sha(p)} for p in sources]}
    base.dump(output/'summary.json',result)
    print(name,json.dumps({'metrics':{k:{m:v[m] for m in ('precision_015','wall_coverage','recall_visible','wall_error_rmse_m')} for k,v in metrics.items()},
                          'guard':result['guard'],'checks':checks}),flush=True)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--wall-projection-guard',choices=VALUES,default='off')
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    results=[]
    for i,case in enumerate(CASES):
        assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip() == source_sha
        if i==2:
            base.dump(args.output/'development_fixed.json',{'source_sha':source_sha,'wall_projection_guard':args.wall_projection_guard,
                      'development':[{'case':r['case'],'success':r['success']} for r in results],
                      'tuning':False,'confirmation_cases':CASES[2:]})
        results.append(run_case(case,args.output/case,args.wall_projection_guard))
    base.dump(args.output/'cohort.json',{'source_sha':source_sha,'cases':[{'case':r['case'],'success':r['success']} for r in results],
              'development_pass':sum(r['success'] for r in results[:2]),'confirmation_pass':sum(r['success'] for r in results[2:])})


if __name__=='__main__':
    main()
