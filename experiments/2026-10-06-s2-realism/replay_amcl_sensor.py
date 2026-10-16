"""s2v38: same frozen replay loop, best-cluster ON in both sensor conditions."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path

import numpy as np

from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_best_cluster import runtime_class as best_runtime, OPTION as BEST
from harness.zone_solo_cyan_amcl_sensor import runtime_class as sensor_runtime, OPTION, likelihood
from harness.zone_solo_cyan_likelihood_field import likelihood as old_likelihood, Field
from harness import zone_solo_cyan_contract_v106 as contract

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('saved_best_cluster_replay', HERE/'replay_best_cluster.py')
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
CRITERIA = HERE/'amcl-sensor-criteria.json'
read, rows, sha = old.read, old.rows, old.sha


def replay(which, option, out, criteria):
    instances = []

    def factory(base):
        Runtime = sensor_runtime(best_runtime(base))
        def create(*args, pose_estimate, **kwargs):
            # The frozen replay loop's condition selector is translated only
            # here. Both arms use the same best-cluster pose; sensor alone varies.
            r = Runtime(*args, pose_estimate=BEST,
                sensor_model=OPTION if option == 'on' else 'off', **kwargs)
            instances.append(r)
            return r
        return create

    run = bind(old.replay, runtime_class=factory, CRITERIA=CRITERIA)
    run(which, option, out, criteria)
    audit = dict(sensor_model=OPTION if option == 'on' else 'off', pose_estimate=BEST,
        gt_inputs=False, sensor=copy.deepcopy(getattr(instances[0], 'sensor_audit', None)))
    (out/f'{which}-{option}-sensor.json').write_text(json.dumps(audit)+'\n')


def score(out, criteria):
    # Every off/on prediction is already closed before reading any GT below.
    assert all((out/f'{case}-{opt}.json').is_file()
               for case in criteria['recordings'] for opt in ('off', 'on'))
    result = dict(schema='ugrp.s2.amcl_sensor.result.v1', criteria=criteria,
        gt_use='evaluation only after all predictions close', physics_runs=0, model_calls=0, recordings={})
    for which, cfg in criteria['recordings'].items():
        truth = rows(Path(cfg['raw'])/'eval_only/trajectory.jsonl')
        times = np.array([r['t'] for r in truth]); xy = np.array([r['robot_xyz_m'][:2] for r in truth])
        predictions = [read(out/f'{which}-{opt}.json') for opt in ('off', 'on')]
        ref = read(Path(cfg['baseline_poses']))['poses']
        metrics = []
        for pred in predictions:
            poses = pred['poses']; begin, end = cfg['window']
            errors = [float(np.linalg.norm(np.array([p['x'], p['y']])-
                [np.interp(p['t_est'], times, xy[:, j]) for j in (0, 1)])) for p in poses]
            ix = [i for i, p in enumerate(poses) if begin <= p['t'] < end]
            fix = sorted({p['t'] for p in pred['amcl']['rows'] if p.get('visual_weight_update') and begin <= p['t'] < end})
            m = dict(option=pred['option'], frames=len(poses), final_error_m=errors[-1],
                window_xy_rmse_m=float(np.sqrt(np.mean([errors[i]**2 for i in ix]))),
                window_end_error_m=errors[ix[-1]], window_visual_updates=len(fix),
                window_max_fix_gap_s=float(max(np.diff([begin, *fix, end]))),
                final_cluster=poses[-1]['cluster'])
            if which == 'start1052':
                z = np.load(out/f"{which}-{pred['option']}-clouds.npz")
                j = len(pred['snapshots'])-1; p = z[f'p{j}']; w = z[f'w{j}']
                g = min(truth, key=lambda t:abs(t['t']-pred['snapshots'][-1]['t']))
                near = np.linalg.norm(p[:, :2]-g['robot_xyz_m'][:2], axis=1) <= .25
                dy = p[:, 2]-g['robot_yaw_rad']
                near &= abs(np.arctan2(np.sin(dy), np.cos(dy))) <= np.deg2rad(15)
                m.update(truth_near_mass=float(w[near].sum()), truth_near_count=int(near.sum()))
            metrics.append(m)
        off, on = predictions
        result['recordings'][which] = dict(conditions=metrics,
            baseline_frames_equal=len(off['poses']) == len(ref),
            baseline_max_pose_delta=max(abs(p[k]-q[k]) for p,q in zip(off['poses'],ref) for k in ('x','y','yaw')),
            off_on_max_pose_delta=max(abs(p[k]-q[k]) for p,q in zip(off['poses'],on['poses']) for k in ('x','y','yaw')),
            particle_trajectory_bytes_equal=off['cloud_trajectory_sha256'] == on['cloud_trajectory_sha256'])
    # Same pre-registered false pose from the earlier diagnostic, never pick a
    # new false candidate for the option. No evaluation data enters replay().
    saved = read(Path(criteria['likelihood_probe']['source']))
    field = Field(contract.hp.resolve(contract.MAP_ID)[0]); probes = []
    wrong = np.array(criteria['likelihood_probe']['fixed_false_pose'])
    for opt, kernel in (('off', old_likelihood), ('on', likelihood)):
        detail = []
        for v in saved['views']:
            values = kernel(field, np.array([saved['views'][0]['truth'], wrong]), v['points'])
            detail.append(dict(t=v['t'], valid_beams=len(v['points']), GT=float(values[0]),
                false=float(values[1]), GT_over_false=float(values[0]/values[1])))
        probes.append(dict(option=opt, views=detail, six_view_GT_over_false=float(np.prod([v['GT_over_false'] for v in detail]))))
    result['likelihood_probe'] = probes
    result['gates'] = dict(start_error_within_25cm=result['recordings']['start1052']['conditions'][1]['final_error_m'] <= .25,
        baseline_reproduced=all(x['baseline_frames_equal'] and x['baseline_max_pose_delta'] <= 1e-9 for x in result['recordings'].values()))
    result['physical_start_admitted'] = all(result['gates'].values())
    result['source_sha'] = read(out/'start1052-on.json')['source_sha']
    result['hashes'] = {p.name:sha(p) for p in out.iterdir() if p.is_file()}
    result['sources'] = {str(CRITERIA):sha(CRITERIA), criteria['likelihood_probe']['source']:sha(Path(criteria['likelihood_probe']['source']))}
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(gates=result['gates'], metrics=result['recordings'], likelihood_probe=probes)), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--score', action='store_true'); a = p.parse_args(); criteria = read(CRITERIA)
    a.output.mkdir(parents=True, exist_ok=True)
    if a.score:
        assert not (a.output/'result.json').exists(); score(a.output, criteria)
    else:
        for which in criteria['recordings']:
            for opt in ('off', 'on'):
                assert not (a.output/f'{which}-{opt}.json').exists()
                replay(which, opt, a.output, criteria)
