"""Post-seal source-VM audit; evaluation truth NEVER feeds the estimator.

Compare the unchanged Nav2 likelihood sum/product, and separate projection
residuals from finite-particle coverage. No thresholds are fitted here.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):
        raise ValueError('SOURCE_VM_ONLY')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import numpy as np
    from harness.mapbuild_amcl import StaticField
    from harness.mapbuild_amcl_vendor import algorithms as nav2
    from harness.mapbuild_static_registration import wall_segments
    from harness.servo_camera_fk import transform_from_commands, CARRY_OPTION
    seal = read(a.prediction/'prediction-seal.json')
    for name, value in seal['prediction_sha256'].items():
        if sha(a.prediction/name) != value:
            raise ValueError('PREDICTION_CHANGED')
    static = read(a.input/'static-map.json')
    field = StaticField(static)
    scans, own = read(a.scans), read(a.input/'own.json')['frames']
    truth = read(a.input/'eval-only.json')['frames']
    rows = read(a.prediction/'trajectory.json')
    if not (len(scans) == len(own) == len(truth) == len(rows)):
        raise ValueError('EXACT_FRAME_JOIN_REQUIRED')
    walls = np.asarray(wall_segments(static))
    model = data = states = None
    if a.kinematic_assets is not None:
        import mujoco
        os.chdir(a.kinematic_assets)
        model = mujoco.MjModel.from_xml_string((a.input/'scene.xml').read_text())
        data = mujoco.MjData(model)
        states = np.load(a.input/'eval-state.npz')['qpos']
        if len(states) != len(own):raise ValueError('EXACT_STATE_JOIN_REQUIRED')
        cid = model.camera('r1__robot_cam').id
        from harness.e2e_rgb_vo import K
        inv_k = np.linalg.inv(K)

    def stats(x):
        x = np.asarray(x)
        x = x[np.isfinite(x)]
        return dict(n=len(x), p05=float(np.percentile(x, 5)),
                    p50=float(np.median(x)), p95=float(np.percentile(x, 95)),
                    max=float(x.max()), rms=float(np.sqrt(np.mean(x*x)))) if len(x) else dict(n=0)

    def nearest(p):
        u, v = walls[:, 0], walls[:, 1]-walls[:, 0]
        q = np.clip(np.einsum('nsi,si->ns', p[:, None]-u, v)/np.sum(v*v, axis=1), 0, 1)
        return np.linalg.norm(p[:, None]-(u+q[..., None]*v), axis=-1).min(1)

    def range_bias(origin, points, ranges):
        # Ray/finite wall segment intersection. First visible static wall is
        # descriptive only: dynamic occlusion is not a wall correspondence.
        out = []
        u, v = walls[:, 0], walls[:, 1]-walls[:, 0]
        def cross(x, y): return x[..., 0]*y[..., 1]-x[..., 1]*y[..., 0]
        for point, observed in zip(points, ranges):
            d = (point-origin)/observed
            den = cross(d, v)
            with np.errstate(divide='ignore', invalid='ignore'):
                t, s = cross(u-origin, v)/den, cross(u-origin, d)/den
            hits = t[(abs(den)>1e-12)&(t>0)&(s>=0)&(s<=1)]
            out.append(observed-float(hits.min()) if len(hits) else np.nan)
        return out

    result, distances, biases, reasons = [], [], [], Counter()
    for index, (f, scan, gt, pred) in enumerate(zip(own, scans, truth, rows)):
        if not f['frame_id'] == gt['frame_id'] == pred['frame_id']:
            raise ValueError('EXACT_FRAME_JOIN_REQUIRED')
        columns = scan.get('columns', [])
        camera = np.asarray(scan.get('camera') or [0, 0])
        points = np.array([camera+c['range_m']*np.array([math.cos(c['bearing_rad']), math.sin(c['bearing_rad'])])
                           if c.get('status') == 'hit' and c.get('range_m') is not None
                           else [np.nan, np.nan] for c in columns]).reshape(-1, 2)
        pose = np.asarray(gt['pose'])
        c, s = math.cos(pose[2]), math.sin(pose[2])
        rot = np.array([[c, s], [-s, c]])
        valid = np.isfinite(points).all(axis=1)
        world = points[valid]@rot+pose[:2]
        residual = nearest(world) if len(world) else np.array([])
        fd = field.distances(world)
        origin = camera@rot+pose[:2]
        ranges = [v['range_m'] for v in columns if v.get('status') == 'hit' and v.get('range_m') is not None]
        bias = range_bias(origin, world, ranges)
        likelihood = {}
        for sigma in (.0202, .2):  # previous frozen profile / documented Nav2 default
            likelihood[str(sigma)] = dict(
                additive=float(nav2.likelihood(field, pose[None], points, sigma)[0]),
                log_product=float(np.log(nav2.likelihood_product(field, pose[None], points, sigma)[0])))
        fk, fk_reason = transform_from_commands({int(k):v for k, v in f['servo'].items()}, camera_pose=CARRY_OPTION)
        height = float(fk[0][2]) if fk is not None else None
        nfar = int((fd > .2).sum())  # Nav2 sigma, diagnostic bin ONLY
        bounds = static['bounds_m']
        outside = int(((world[:, 0]<bounds[0])|(world[:, 0]>bounds[1])|
                       (world[:, 1]<bounds[2])|(world[:, 1]>bounds[3])).sum())
        reasons.update([pred['event']['reason']])
        result.append(dict(t=f['t'], frame_id=f['frame_id'], sensor_updated=pred['event']['attempted'],
            scan_segments_available=bool(scan.get('segments')),qualification=scan.get('qualification'),
            hits=int(valid.sum()), original_slots=len(points),
            additive_beams=int(np.isfinite(points[::max(1, (len(points)-1)//59)]).all(1).sum()),
            product_beams=int(np.isfinite(points[::max(1, math.ceil(len(points)/60))]).all(1).sum()),
            nearest_wall_m=stats(residual), field_distance_m=stats(fd), signed_range_bias_m=stats(bias),
            outside_map_n=outside, farther_than_nav2_sigma_n=nfar,
            command_fk_height_m=height, command_fk_status=fk_reason,
            command_fk_camera_xy_delta_m=float(np.linalg.norm(fk[0][:2]-camera)) if fk is not None else None,
            nominal_projected_point_z_m=0., point_height_status='floor-plane projection assumption; not measured height',
            likelihood_at_evaluation_pose=likelihood, reason_category='measurement_audit',
            blocked_object='authored_static_wall_nearest_only', minimum_gap_m=None, gap_status='not_measured'))
        if states is not None:
            data.qpos[:] = states[index]
            mujoco.mj_forward(model, data)  # kinematics only, zero integration/render
            yaw_rot=np.array([[c,-s,0],[s,c,0],[0,0,1]])
            actual_o=yaw_rot.T@(data.cam_xpos[cid]-np.r_[pose[:2],0.])
            actual_r=yaw_rot.T@data.cam_xmat[cid].reshape(3,3)@np.diag([1,-1,-1])
            nominal_o,nominal_r=fk
            angle=math.acos(float(np.clip((np.trace(nominal_r.T@actual_r)-1)/2,-1,1)))
            nominal_point_heights=[]; actual_points=[]
            for col in columns:
                if col['status']!='hit':continue
                ray=inv_k@[col['column'],col['row'],1.]
                nr,ar=nominal_r@ray,actual_r@ray
                nominal_depth=-nominal_o[2]/nr[2]
                nominal_point_heights.append(float((actual_o+nominal_depth*ar)[2]))
                if ar[2]<0:actual_points.append((actual_o-actual_o[2]/ar[2]*ar)[:2])
            actual_points=np.asarray(actual_points).reshape(-1,2)@rot+pose[:2]
            result[-1]['evaluation_camera_fk']=dict(position_error_m=float(np.linalg.norm(nominal_o-actual_o)),
                rotation_error_deg=math.degrees(angle),actual_height_m=float(actual_o[2]),
                nominal_minus_actual_height_m=float(nominal_o[2]-actual_o[2]),
                nominal_depth_point_height_m=stats(nominal_point_heights),
                actual_camera_floor_projection_wall_distance_m=stats(nearest(actual_points)) if len(actual_points) else dict(n=0))
        distances.extend(residual.tolist()); biases.extend(bias)
    output = dict(scope='post-seal measurement audit only; no tuning or estimator truth',
        frames=len(result), rows=result, all_wall_residual_m=stats(distances), signed_range_bias_m=stats(biases),
        prior_rejection_distribution=dict(reasons), truth_to_estimator=0, threshold_fitting=0,
        cpu_integration_steps=0,render_calls=0,
        sources={str(p):sha(p) for p in [a.scans, a.input/'own.json', a.input/'eval-only.json', a.input/'static-map.json', a.prediction/'prediction-seal.json', Path(__file__)]},
        reproduction=sys.argv)
    if states is not None:
        output['sources'].update({str(p):sha(p) for p in [a.input/'eval-state.npz',a.input/'scene.xml']})
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x') as handle:
        json.dump(output, handle, indent=2, allow_nan=False); handle.write('\n')
    print(json.dumps({k:v for k,v in output.items() if k not in ('rows','sources')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'scans', 'prediction', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--kinematic-assets', type=Path)
    main(parser.parse_args())
