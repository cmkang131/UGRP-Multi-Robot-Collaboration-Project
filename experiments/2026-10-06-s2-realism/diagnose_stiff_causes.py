"""Read-only saved-posterior/VO audit; GT is used ONLY for post-hoc scoring.

No filter update, image inference, simulator, parameter fitting or action. Exact
GT poses and ideal map endpoints below are diagnostic queries, never PF inputs.
"""
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

from harness import vision_loc_protocol as vp
from harness import zone_solo_cyan_contract_v106 as contract
from harness.s2_stiff_camera_calibration import runtime_class
from harness.zone_solo_cyan_augmented_start import Runtime
from harness.zone_solo_cyan_likelihood_field import Field, likelihood

ROOT = Path(__file__).resolve().parents[2]
RAW = Path('/Users/changmin/projects/ugrp/outputs/s2-stiff-cal-20261007')


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def world(pose, points):
    c, s = np.cos(pose[2]), np.sin(pose[2])
    return points @ np.array([[c, s], [-s, c]]) + pose[:2]


def audit():
    source_paths = [RAW/'replay-start-on.json', RAW/'replay-stiff-vo-final.json',
                    RAW/'start/eval_only/trajectory.jsonl', RAW/'start/setup_bundle.json',
                    ROOT/'configs/calibration/s2_camera_stiff_target_v1.json']
    saved = read(source_paths[0]); vo = read(source_paths[1]); truth = rows(source_paths[2])
    def gt(t):
        row = min(truth, key=lambda r: abs(r['t']-t))
        return np.r_[row['robot_xyz_m'][:2], row['robot_yaw_rad']]
    def near(px, t):
        delta = px-gt(t)
        return ((np.linalg.norm(delta[:, :2], axis=1) <= .25) &
                (abs(np.arctan2(np.sin(delta[:, 2]), np.cos(delta[:, 2]))) <= math.radians(15)))
    clouds = []
    for cloud in saved['clouds']:
        px, w = np.array(cloud['px']), np.array(cloud['w']); mask = near(px, cloud['t'])
        clouds.append(dict(t=cloud['t'],count=int(mask.sum()),mass=float(w[mask].sum()),
                           distinct_poses=int(len(np.unique(px[mask], axis=0)))))
    final = saved['clouds'][-1]; px, w = np.array(final['px']), np.array(final['w'])
    bins = np.floor(px/[.5, .5, math.pi/18]).astype(int)
    hypotheses = []
    for mode in saved['poses'][-1]['modes']['leading_bins'][:5]:
        mask = np.all(bins == mode['bin'], axis=1); weights = w[mask]/w[mask].sum()
        center = np.r_[weights@px[mask, :2],
                       math.atan2(weights@np.sin(px[mask, 2]), weights@np.cos(px[mask, 2]))]
        hypotheses.append(dict(**mode,pose=center.tolist(),distinct_poses=len(np.unique(px[mask],axis=0)),
            eval_position_error_m=float(np.linalg.norm(center[:2]-gt(final['t'])[:2]))))
    candidates = np.array([h['pose'] for h in hypotheses])
    bundle = read(source_paths[3]); static = contract.hp.resolve(contract.MAP_ID)[0]
    field = Field(static)
    omit = ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')
    kw = {k:v for k,v in bundle['options'].items() if k not in omit}
    kw.update(motion_model=bundle['motion_model'],pulse_calibration=bundle['pulse_calibration'],
        extrinsic_calibration=bundle['extrinsic_calibration'],floor_appearance=bundle['floor_appearance'],
        camera_pitch='stiff_target_v1',servo_stiffness='real_v1',stiff_camera_table=read(source_paths[4]))
    # Only construct fixed projection/geometry objects; never feed GT or frames
    # to the runtime, never call on_frame/update_obs/predict_to.
    runtime = runtime_class(Runtime)(static,ROOT/contract.CALIBRATION,contract.CALIBRATION_SHA,seed=1052,**kw)
    pf = runtime.pose.provider.loc._pf; vl = vp.load_vis3()[0]; views = []
    observed_log = np.zeros(6); ideal_log = np.zeros(6)
    initial_px=np.array(saved['clouds'][0]['px']); initial_log=np.zeros(len(initial_px))
    try:
        for v in saved['views']:
            hypotheses_px = np.vstack([gt(v['t']), candidates])
            points = np.array(v['points']); pose = {int(k):value for k,value in v['pose'].items()}
            cm = pf.column_model_for(pose,columns=np.array(v['columns']))
            predicted, _ = vl.expected_rows(pf.geometry,hypotheses_px,cm)
            selected = np.array(v['b_kind']) == 1
            visible = (predicted >= 0) & (predicted < 480)
            metrics = []
            for j, p in enumerate(hypotheses_px):
                d = field.distances(world(p,points)); both = selected & visible[j]
                residual = abs(np.array(v['b_lo'])[both]-predicted[j,both])
                metrics.append(dict(endpoint_distance_median_m=float(np.median(d)),
                    endpoint_within_20cm_fraction=float(np.mean(d<=.2)),
                    detected_columns_with_visible_map_bottom=int(both.sum()),
                    bottom_abs_residual_median_px=float(np.median(residual)) if len(residual) else None))
            mult = likelihood(field,hypotheses_px,points); observed_log += np.log(mult)
            initial_log += np.log(likelihood(field,initial_px,points))
            # Perfect visible wall-bottom endpoints from the map at GT are an
            # EVALUATION counterfactual, to test structural ambiguity of the
            # exact same scoring function, not a replay or additional update.
            ideal_points = cm.floor_point(cm.t_of_row(predicted[0]))[visible[0]]
            ideal_mult = likelihood(field,hypotheses_px,ideal_points); ideal_log += np.log(ideal_mult)
            views.append(dict(t=v['t'],points=len(points),eval_truth=gt(v['t']).tolist(),
                likelihood=mult.tolist(),metrics=metrics,ideal_eval_points=len(ideal_points),
                ideal_eval_likelihood=ideal_mult.tolist()))
    finally:
        runtime.close()
    # Diagnose the existing pulse audit without re-running tracking or changing
    # acceptance thresholds. All frame manifests are checked against saved hashes.
    for name, digest in vo['sources'].items():
        path=Path(name); assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
        source_paths.append(path)
    status = Counter(); first = Counter(); pulse_rows = []; missing = 0; all_intervals = []
    for pulse in vo['rows']:
        frames=rows(Path(pulse['raw'])/'robots/r3/frames.jsonl')
        by_time={round(f['sim_time'],7):f for f in frames}
        def present(t):
            f=by_time.get(round(t,7))
            return f is not None and (Path(pulse['raw'])/f['path']).is_file()
        assert present(pulse['t'])
        for interval in pulse['intervals']:
            status[interval['status']]+=1; all_intervals.append(interval)
            missing += int(not present(interval['t']))
            if interval['status']=='unknown_frame':
                assert interval['t']-interval['from_t']>.15+1e-8
        failure=next(i for i in pulse['intervals'] if i['status']!='measured')
        first[failure['status']]+=1
        before=max(f['sim_time'] for f in frames if f['sim_time']<pulse['end'])
        after=min(f['sim_time'] for f in frames if f['sim_time']>pulse['end'])
        pulse_rows.append(dict(case=pulse['case'],t=pulse['t'],end=pulse['end'],
            first_reject={k:failure[k] for k in ('t','from_t','status','tracks','cells')},
            measured_intervals=sum(i['status']=='measured' for i in pulse['intervals']),
            end_bracket_s=[before,after],exact_end_available=present(pulse['end']),
            complete=pulse['complete_visual']))
    texture=[i for i in all_intervals if i['status']=='unknown_texture']
    rigid=[i for i in all_intervals if i['status']=='unknown_rigid_consensus']
    attempted=[i for i in all_intervals if 'image_fractions' in i]
    fractions=[f for i in attempted for f in i['image_fractions']]
    assert all(i['tracks']<6 for i in texture)
    assert all(i['tracks']>=6 and i['cells']>=2 for i in rigid)
    tight_delta=initial_px-gt(0.)
    tight=((np.linalg.norm(tight_delta[:,:2],axis=1)<=.1) &
           (abs(np.arctan2(np.sin(tight_delta[:,2]),np.cos(tight_delta[:,2])))<=math.radians(5)))
    near_initial=np.flatnonzero(near(initial_px,0.))
    return dict(schema='ugrp.s2.stiff_causes.v1',scope='saved results only; exploratory diagnosis, not confirmation',
        physics_runs=0,model_calls=0,filter_updates=0,controller_changed=False,
        gt_use='evaluation-only pose queries; no particle selection, control or fitting',
        localization=dict(updates=saved['amcl']['updates'],truth_neighborhood=clouds,
            final_modes=saved['poses'][-1]['modes'],hypotheses=hypotheses,
            score_order=['exact_GT_eval_only']+[h['bin'] for h in hypotheses],views=views,
            observed_log_score=observed_log.tolist(),observed_score_relative_to_GT=np.exp(observed_log-observed_log[0]).tolist(),
            initial_tight_10cm_5deg_count=int(tight.sum()),
            initial_best_observed_score_relative_to_GT=float(np.exp(initial_log.max()-observed_log[0])),
            initial_truth_near_score_ranks=[int(1+np.sum(initial_log>initial_log[i])) for i in near_initial],
            final_mean_position_error_m=float(np.linalg.norm(w@px[:,:2]-gt(final['t'])[:2])),
            ideal_eval_log_score=ideal_log.tolist(),ideal_eval_score_relative_to_GT=np.exp(ideal_log-ideal_log[0]).tolist(),
            scoring_limit='Fixed hypothesis score products are diagnostic; resampling/prior multiplicities mean they are not posterior odds.',
            amcl_resamples=saved['amcl']['resamples'],injected=sum(r['global_localization']['injected'] for r in saved['amcl']['rows']),
            static_walls=[o for o in static['obstacles'] if o.get('kind')=='wall']),
        vo=dict(pulses=len(pulse_rows),intervals=len(all_intervals),interval_status=dict(status),
            first_reject=dict(first),missing_interval_rgb=missing,exact_endpoint_missing=sum(not r['exact_end_available'] for r in pulse_rows),
            texture_tracks=[i['tracks'] for i in texture],texture_cells=[i['cells'] for i in texture],
            rigid_tracks=[i['tracks'] for i in rigid],rigid_cells=[i['cells'] for i in rigid],
            floor_fraction_range=[min(f['usable_floor_image_fraction'] for f in fractions),max(f['usable_floor_image_fraction'] for f in fractions)],
            cyan_fraction_max=max(f['cyan_image_fraction'] for f in fractions),rows=pulse_rows,
            not_executed='GroundBuffer upstream admission not exercised by direct observed_pulse replay'),
        hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in dict.fromkeys(source_paths+[Path(__file__)])})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('new output required')
    result=audit();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(observed_ratio=result['localization']['observed_score_relative_to_GT'],
        ideal_ratio=result['localization']['ideal_eval_score_relative_to_GT'],vo=result['vo']['interval_status'])))
