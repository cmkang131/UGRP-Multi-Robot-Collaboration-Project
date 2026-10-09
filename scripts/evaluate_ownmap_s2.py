"""POST-SEAL evaluator only. GT transforms never leave this module for replay."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from harness.ownmap_s2 import GridField
from harness.zone_solo_cyan_likelihood_field import Field
from harness.zone_solo_cyan_landmarks import MapFeatures, landmark_likelihood
from harness.zone_solo_cyan_amcl_sensor import likelihood
from scripts.replay_ownmap_s2 import PLAN, read, rows, sha, write


def rotation(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]])


def to_world(xy, anchor):
    return np.asarray(xy) @ rotation(anchor[2]).T + anchor[:2]


def to_own(xy, anchor):
    return (np.asarray(xy)-anchor[:2]) @ rotation(anchor[2])


def anchored_pose(pose, covariance, anchor):
    xy = to_world(pose[:2], anchor)
    r = rotation(anchor[2])
    return np.r_[xy, pose[2]+anchor[2]], r @ covariance[:2, :2] @ r.T


def truth_arrays(truth):
    return (np.array([q['t'] for q in truth]), np.array([q['robot_xyz_m'][:2] for q in truth]),
            np.unwrap([q['robot_yaw_rad'] for q in truth]))


def interpolate(arrays, times):
    t, xy, yaw = arrays
    return np.c_[np.interp(times, t, xy[:, 0]), np.interp(times, t, xy[:, 1]), np.interp(times, t, yaw)]


def nees_summary(values):
    n = len(values); count = sum(x > 5.991464547107979 for x in values)
    return dict(valid=n, exceed=count, exceed_fraction=count/n if n else None)


def score(poses, truth, anchor, decision_times):
    arrays = truth_arrays(truth)
    times = np.array([p['t_est'] for p in poses])
    gt = interpolate(arrays, times)
    scored = []; comparable = []; all_nees = []
    for q, g in zip(poses, gt):
        if not arrays[0][0]-1e-8 <= q['t_est'] <= arrays[0][-1]+1e-8:
            continue
        cov = np.array(q['cov'], float)
        estimate, covxy = anchored_pose(np.array([q['x'], q['y'], q['yaw']]), cov, anchor)
        error = estimate[:2]-g[:2]
        yaw = abs(math.degrees(math.atan2(math.sin(estimate[2]-g[2]), math.cos(estimate[2]-g[2]))))
        nees = None
        if np.isfinite(covxy).all() and np.linalg.eigvalsh(covxy).min() > 0:
            nees = float(error @ np.linalg.solve(covxy, error))
            all_nees.append(nees)
        modes = (q.get('observation_quality') or {}).get('diagnostics', {}).get('pose_estimate', {})
        cluster = np.array(modes.get('selected_cluster_cov', []))
        if (nees is not None and modes.get('cluster_count') == 1 and cluster.shape == (3, 3)
                and np.allclose(cluster[:2, :2], cov[:2, :2], rtol=1e-7, atol=1e-10)):
            comparable.append(nees)
        scored.append(dict(t=q['t'], t_est=q['t_est'], xy_error_m=float(np.linalg.norm(error)),
            yaw_error_deg=yaw, nees_xy=nees, std_xy_m=q['std_xy_m'],
            pose_uncertain=q['pose_uncertain'], initialized=q.get('initialized', True),
            estimate_world=estimate.tolist(), truth=g.tolist()))
    # The first declaration is selected WITHOUT truth, including any early
    # report outside GT coverage. Missing truth must fail scoring, not vanish.
    first_q = next((q for q in poses if q.get('initialized', True) and q['std_xy_m'] <= .05), None)
    first = None if first_q is None else next((q for q in scored if q['t'] == first_q['t']), None)
    correct = first is not None and first['xy_error_m'] <= .25 and first['yaw_error_deg'] <= 15.
    after = [] if first_q is None else [q for q in scored if q['t'] >= first_q['t']]
    by_time = {round(q['t'], 6): q for q in scored}
    decisions = [by_time[t] for t in decision_times if t in by_time]
    unflagged = [q for q in decisions if not q['pose_uncertain'] and q['xy_error_m'] > .25]
    result = dict(converged=first_q is not None, first_convergence=first, correct_convergence=bool(correct),
        first_convergence_missing_gt=first_q is not None and first is None,
        wrong_mode=first is not None and not correct,
        wrong_mode_xy=first is not None and first['xy_error_m'] > .25,
        wrong_mode_yaw=first is not None and first['yaw_error_deg'] > 15.,
        post_convergence_n=len(after),
        post_convergence_rmse_m=float(np.sqrt(np.mean([q['xy_error_m']**2 for q in after]))) if after else None,
        nees_all=nees_summary(all_nees), nees_comparable=nees_summary(comparable),
        decisions=len(decisions), missing_decision_reports=len(decision_times)-len(decisions),
        unflagged_gt25cm=len(unflagged), unflagged_times=[q['t'] for q in unflagged],
        gt_covered_reports=len(scored), outside_gt_reports=len(poses)-len(scored))
    return result, scored


def gates(pairs):
    completed = [p for p in pairs if 'off' in p and 'own_grid_v1' in p]
    baseline = sum(p['off']['correct_convergence'] for p in completed)
    own = sum(p['own_grid_v1']['correct_convergence'] for p in completed)
    rmse_checks = []
    for p in completed:
        a, b = p['off'], p['own_grid_v1']
        if a['correct_convergence']:
            ok = bool(b['correct_convergence'] and b['post_convergence_rmse_m'] is not None and
                      b['post_convergence_rmse_m'] <= 2*a['post_convergence_rmse_m'])
            rmse_checks.append(dict(pair_id=p['pair_id'], passed=ok))
    def total(k, opt):
        return sum(p[opt][k] for p in completed)
    def nees(opt):
        valid = sum(p[opt]['nees_all']['valid'] for p in completed)
        exceed = sum(p[opt]['nees_all']['exceed'] for p in completed)
        return exceed/valid if valid else None
    an, bn = nees('off'), nees('own_grid_v1')
    checks = dict(all_seven_complete=len(completed) == 7,
        all_baselines_identical=len(completed) == 7 and all(p['baseline_identity'] for p in completed),
        nonzero_correct_baseline=baseline > 0, retention=own >= math.ceil(.8*baseline),
        rmse_all_correct_baseline_pairs=bool(rmse_checks) and all(q['passed'] for q in rmse_checks),
        wrong_modes_nonincreasing=total('wrong_mode', 'own_grid_v1') <= total('wrong_mode', 'off'),
        unflagged_nonincreasing=total('unflagged_gt25cm', 'own_grid_v1') <= total('unflagged_gt25cm', 'off'),
        nees_nonincreasing=an is not None and bn is not None and bn <= an,
        no_missing_scores=all(not p[o]['first_convergence_missing_gt'] and not p[o]['missing_decision_reports']
                             for p in completed for o in ('off', 'own_grid_v1')))
    return dict(passed=all(checks.values()), checks=checks, baseline_correct=baseline, own_correct=own,
        required_correct=math.ceil(.8*baseline), registered_pairs=7, complete_pairs=len(completed),
        rmse_checks=rmse_checks, nees_off=an, nees_own=bn)


class TreeField:
    def __init__(self, points):
        self.tree = cKDTree(points) if len(points) else None
    def distances(self, points):
        p = np.asarray(points)
        if self.tree is None:
            return np.full(p.shape[:-1], 2.)
        return np.minimum(2., self.tree.query(p.reshape(-1, 2))[0].reshape(p.shape[:-1]))


def diagnostics(static, own, anchor, truth, measurements):
    """Geometry/support/semantic diagnostic, never an alternate success run.

    40cm support follows the stated 20--40cm map displacement scale. Both 20cm
    and 40cm coverage are reported. Oracle GT walls are mixed only HERE.
    """
    grid = np.asarray(own['occupancy_grid']['cells']); res = own['occupancy_grid']['resolution_m']
    occupied = (grid[grid[:, 2] > 0, :2]+.5)*res
    occupied_world = to_world(occupied, anchor)
    own_tree = cKDTree(occupied_world); gt_field = Field(static)
    yy, xx = np.nonzero(gt_field.dist == 0)
    gt_cells = gt_field.origin + np.c_[xx, yy]*gt_field.res
    distances = own_tree.query(gt_cells)[0]
    support = gt_cells[distances <= .4]
    partial = TreeField(support)
    ownfield = GridField(own)
    mapped = MapFeatures(static)
    tarr = truth_arrays(truth)
    sampled = []; missing_floor = missing_door = total_floor = total_door = 0
    for row in measurements:
        t = row['t']
        if not tarr[0][0] <= t <= tarr[0][-1]:
            continue
        pose = interpolate(tarr, [t])[0]
        local = np.r_[to_own(pose[:2], anchor), pose[2]-anchor[2]]
        pts = np.asarray(row['wall_points'], float).reshape(-1, 2)
        features = row['features']
        floor = sum(f['kind'] == 'floor_line' for f in features)
        door = sum(f['kind'] == 'door' for f in features)
        total_floor += floor; total_door += door
        missing_floor += floor if not own['observed_floor_edges'] else 0
        missing_door += door if not own['passages'] else 0
        a = float(likelihood(ownfield, local[None, :], pts)[0])
        b = float(likelihood(partial, pose[None, :], pts)[0])
        c = float(likelihood(gt_field, pose[None, :], pts)[0])
        d = float(landmark_likelihood(mapped, pose[None, :], features)[0])
        sampled.append(dict(t=t, own_wall_score=a, observed_support_gt_wall_score=b,
            full_gt_wall_score=c, full_gt_landmark_log_score=float(np.log(max(d, 1e-300))),
            wall_endpoints=len(pts), floor_features=floor, door_features=door))
    wall_error = gt_field.distances(occupied_world)
    return dict(gt_use='EVALUATION_ONLY; not localization/control; no adoption or success claims',
        anchor_world_xyyaw=anchor.tolist(), alignment='first mapping-run GT pose only, no fit/ICP/scale',
        own_occupied_cells=len(occupied), gt_occupied_cells=len(gt_cells),
        occupied_to_gt_wall_m={k:float(v) for k,v in zip(('median','p90','max'), np.quantile(wall_error,[.5,.9,1]))},
        gt_wall_coverage_20cm=float(np.mean(distances <= .2)), gt_wall_coverage_40cm=float(np.mean(distances <= .4)),
        floor_observations=total_floor, floor_without_mapped_edge=missing_floor,
        door_observations=total_door, door_without_mapped_entity=missing_door,
        observed_region_count=len(own['observed_regions']), verified_floor_edges=len(own['observed_floor_edges']),
        oracle_scope='true-pose sensor scores only: geometry correction on observed support, then missing-wall fill, then semantic score; no causal trajectory recovery proof',
        oracle_rows=sampled)


def evaluate(output, report_dir):
    plan = read(PLAN); all_results=[]; traces={}; diagrams={}; errors=[]
    report_dir.mkdir(parents=True, exist_ok=False)
    from harness.zone_solo_cyan_contract_v106 import hp, MAP_ID
    static = hp.resolve(MAP_ID)[0]
    for pair in plan['pairs']:
        row = dict(pair_id=pair['id'], map_seed=Path(pair['map_raw']).name, raw=pair['raw'])
        truth_path=Path(pair['raw'])/'eval_only/trajectory.jsonl'
        map_truth_path=Path(pair['map_raw'])/'eval_only/trajectory.jsonl'
        truth=rows(truth_path); map_truth=rows(map_truth_path)
        q=map_truth[0]; anchor=np.r_[q['robot_xyz_m'][:2], q['robot_yaw_rad']]
        source=read(Path(pair['raw'])/'student_record.json')
        decision_times=[round(q['t'],6) for q in source['global_full_decisions']]
        row['eval_hashes']={str(p):sha(p) for p in (truth_path,map_truth_path)}
        for opt in ('off','own_grid_v1'):
            dest=output/pair['id']/opt
            try:
                prediction=read(dest/'prediction.json')
                for name,digest in prediction['outputs'].items():
                    if sha(dest/name)!=digest: raise ValueError('SEALED_PREDICTION_CHANGED')
                if prediction['registration_sha256']!=sha(PLAN): raise ValueError('REGISTRATION_CHANGED')
                metric,series=score(rows(dest/'poses.jsonl'),truth,np.zeros(3) if opt=='off' else anchor,decision_times)
                row[opt]=metric;traces[(pair['id'],opt)]=series
                if opt=='off':row['baseline_identity']=prediction['baseline_identity']
            except Exception as exc:
                errors.append(dict(pair_id=pair['id'],option=opt,error=repr(exc)))
        own=read(output/pair['id']/'own_grid_v1/own-map.json')
        diag=diagnostics(static,own,anchor,truth,source['sensor_landmarks']['rows'])
        write(report_dir/(pair['id']+'-diagnostic.json'),diag)
        row['diagnostics']={k:v for k,v in diag.items() if k!='oracle_rows'}
        diagrams[pair['id']]=(own,anchor)
        all_results.append(row)
    result=dict(schema='ugrp.ownmaps2a.result.v1',registration_sha256=sha(PLAN),
        replay_root=str(output),physics_runs=0,model_calls=0,tuned=False,closed_loop_success=None,
        gate=gates(all_results),pairs=all_results,errors=errors,gt_scope='evaluation only after predictions sealed')
    write(report_dir/'result.json',result)
    write(report_dir/'series.json',{p+'-'+o:s for (p,o),s in traces.items()})
    plot(report_dir,result,traces,diagrams,static)
    return result


def plot(dest,result,traces,diagrams,static):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig, axes=plt.subplots(7,2,figsize=(13,23),layout='constrained')
    for axs,p in zip(axes,result['pairs']):
        ax,curve=axs;own,anchor=diagrams[p['pair_id']]
        for r in static['obstacles']:
            if r.get('kind')!='wall':continue
            x,y=r['center_m'];a,b=r['half_extents_m']
            ax.add_patch(Rectangle((x-a,y-b),2*a,2*b,color='0.75'))
        cells=np.array(own['occupancy_grid']['cells']);res=own['occupancy_grid']['resolution_m']
        pts=to_world((cells[cells[:,2]>0,:2]+.5)*res,anchor)
        ax.scatter(*pts.T,s=2,c='#ca5229',label='own occupied')
        for opt,color,label in [('off','#1f77b4','provided map'),('own_grid_v1','#ca5229','own map')]:
            values=traces.get((p['pair_id'],opt),[])
            curve.plot([q['t'] for q in values],[q['xy_error_m'] for q in values],c=color,lw=.8,label=label)
        curve.axhline(.25,c='0.35',ls='--',lw=.8);curve.set(xlabel='recorded SIM time (s)',ylabel='XY error (m)')
        curve.legend(fontsize=8);ax.set_aspect('equal');ax.legend(fontsize=8)
        ax.set(title=p['pair_id']+' / '+p['map_seed']+' (GT aligned: evaluation only)',xlabel='world x (m)',ylabel='world y (m)')
    fig.suptitle('ownmaps2a — fixed RGB/command replay; no physics; no tuning',fontsize=14)
    fig.savefig(dest/'comparison.png',dpi=120);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=evaluate(a.replay,a.output)
    print(json.dumps(result['gate'],indent=2))


if __name__=='__main__':main()
