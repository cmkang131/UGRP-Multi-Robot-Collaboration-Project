"""Static feasibility audit for solo_lift_inspect_pose_v1; never runs a world.

The production wrist camera and a rigidly held object share the gripper frame.
Post-grasp arm PWM therefore cancels out of camera-to-object geometry. This
probe is deliberately NOT an executable inspect motion or a holding detector.
It reuses the current camera chain, command FK and analytic ray intersections.
No measured joints, contacts, live cargo pose, image renderer or physics input.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import cv2
import numpy as np

from harness.servo_camera_fk import (
    axis_rotation, commanded_joints, fixed_transform, model,
)
from harness.visual_arm_v3 import forward_grip, tool_pose
from harness.zone_own_perception import _usable_region
from harness.zone_own_perception_v3 import _pixel_rays, _ray_box, _ray_cylinder
from sim.grasp_act_solo_teacher import cargo
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'tests/fixtures/solo_rgb_lift_v3/manifest.json'
WIDTH, HEIGHT = 640, 480
EDGE_MARGIN_PX = 16


def nominal_transforms(pwm):
    """Static gripper/camera transforms, not the unloaded runtime FK API.

    servo_camera_fk.transform_from_commands intentionally rejects loaded poses.
    We leave that guard intact. Here we compose its frozen structural chain to
    prove a rigid-body identity, without claiming loaded sag calibration.
    """
    _, joints = commanded_joints(pwm)
    spec = model()
    t = np.eye(4)
    t[:3, 3] = spec['floor_to_chassis_translation_m']
    for link in spec['chain']:
        t = t @ fixed_transform(link)
        if 'servo' in link:
            q = joints[link['servo']]
            if not link['range_rad'][0] <= q <= link['range_rad'][1]:
                raise ValueError('command outside mechanical joint range')
            joint = np.eye(4)
            joint[:3, :3] = axis_rotation(link['joint_axis'], q)
            t = t @ joint
    camera = t @ fixed_transform(spec['camera'])
    camera[:3, :3] = camera[:3, :3] @ np.diag([1., -1., -1.])
    return t, camera


def object_in_gripper(kind, grasp_pwm):
    """Catalogue hypothesis frozen at grasp; never re-upright after the lift.

    The object is initially upright, centred between the pads at the existing
    catalogue grasp height. Real grasp offset/slip is NOT estimated here.
    """
    spec = cargo(kind)
    gripper, _ = nominal_transforms(grasp_pwm)
    obj = np.eye(4)
    obj[:3, :3] = axis_rotation([0, 0, 1], np.deg2rad(tool_pose(grasp_pwm).yaw_left_deg))
    obj[:3, 3] = np.asarray(forward_grip(grasp_pwm)) + [0., 0., spec.dims_m[2]/2-spec.grip_z_m]
    return np.linalg.inv(gripper) @ obj


def camera_object_transform(kind, grasp_pwm, current_pwm):
    gripper, camera = nominal_transforms(current_pwm)
    return np.linalg.inv(camera) @ gripper @ object_in_gripper(kind, grasp_pwm)


def geometry_metrics(kind, camera_object, *, near_clip_m=0.):
    """Analytic pixel-ray membership, not rendering or a visible-colour claim.

    Zero near clip and no gripper occlusion give an optimistic upper bound.
    The old perception module's .0297 m near clip is NOT the current scene's
    .0004 * compiled extent; don't silently reuse that old clipping constant.
    """
    spec = cargo(kind)
    rotation, centre = camera_object[:3, :3], camera_object[:3, 3]
    origin = -rotation.T @ centre
    rays = _pixel_rays(WIDTH, HEIGHT) @ rotation
    if kind == 'can':
        entry, exit_ = _ray_cylinder(origin, rays, np.zeros(3),
                                    spec.dims_m[0]/2, spec.dims_m[2]/2)
        # The legacy helper uses fmax/fmin to handle cap-parallel rays: a
        # negative radial discriminant then also falls back to cap depths.
        # Explicitly reject those rays rather than counting the infinite cap
        # plane outside the cylinder as cargo. Do not change its old callers.
        a = np.sum(rays[:, :2]**2, axis=1)
        b = 2*(rays[:, :2] @ origin[:2])
        c = np.sum(origin[:2]**2)-(spec.dims_m[0]/2)**2
        radial_hit = ((a > 1e-20) & (b*b-4*a*c >= 0)) | ((a <= 1e-20) & (c <= 0))
    else:
        entry, exit_ = _ray_box(origin, rays, np.zeros(3), np.asarray(spec.dims_m)/2, np.eye(3))
        radial_hit = np.ones(len(rays), dtype=bool)
    hit = (np.isfinite(entry) & np.isfinite(exit_) & (exit_ >= entry) &
           (entry > near_clip_m) & radial_hit).reshape(HEIGHT, WIDTH)
    usable = _usable_region(WIDTH, HEIGHT)
    interior = cv2.erode(usable.astype(np.uint8),
                        np.ones((2*EDGE_MARGIN_PX+1,)*2, np.uint8),
                        borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    observed = hit & usable
    y, x = np.nonzero(observed)
    # Ratio of surface grid locations inside the usable image.
    # This denominator includes off-image surface samples; it is not pixel area
    # or an occlusion-aware visible-surface fraction.
    samples = surface_samples(kind)
    optical = samples @ rotation.T + centre
    front = optical[:, 2] > 0
    projected = np.full((len(samples), 2), -1e6)
    projected[front] = cv2.fisheye.projectPoints(
        optical[front].reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
        scaled_camera_matrix(WIDTH, HEIGHT), np.asarray(CAMERA_FISHEYE_D))[0].reshape(-1, 2)
    px = np.rint(projected).astype(int)
    inside = front & (px[:, 0] >= 0) & (px[:, 0] < WIDTH) & (px[:, 1] >= 0) & (px[:, 1] < HEIGHT)
    within = np.zeros(len(samples), bool)
    within[inside] = interior[px[inside, 1], px[inside, 0]]
    return dict(raw_pixels=int(hit.sum()), usable_pixels=int(observed.sum()),
                margin_pixels=int((hit & interior).sum()),
                image_fraction=float(observed.mean()),
                usable_bbox_xyxy=[int(x.min()), int(y.min()), int(x.max()), int(y.max())] if len(x) else None,
                surface_samples_inside_margin=int(within.sum()), surface_samples_N=len(samples),
                surface_sample_inside_ratio=float(within.mean()),
                near_clip_m=near_clip_m, occlusion_model='none; optimistic bound')


def surface_samples(kind):
    half = np.asarray(cargo(kind).dims_m)/2
    if kind == 'can':
        angles = np.linspace(0, 2*np.pi, 72, endpoint=False)
        side = [[half[0]*np.cos(a), half[0]*np.sin(a), z]
                for a in angles for z in np.linspace(-half[2], half[2], 21)]
        caps = [[r*np.cos(a), r*np.sin(a), z] for z in (-half[2], half[2])
                for r in half[0]*np.sqrt(np.linspace(0, 1, 21)) for a in angles]
        return np.asarray(side+caps)
    points = []
    for axis, sign in itertools.product(range(3), (-1, 1)):
        others = [i for i in range(3) if i != axis]
        for a, b in itertools.product(np.linspace(-1, 1, 21), repeat=2):
            p = np.zeros(3)
            p[axis] = sign*half[axis]
            p[others] = [a*half[others[0]], b*half[others[1]]]
            points.append(p)
    return np.asarray(points)


def joint_grid():
    """Finite numerical cross-check of an identity valid for every arm pose."""
    for s3, s4, s5, s6 in itertools.product(range(600, 2500, 300), repeat=4):
        pwm = {1: 1500, 3: s3, 4: s4, 5: s5, 6: s6}
        try:
            nominal_transforms(pwm)
        except ValueError:
            continue
        yield pwm


def payload_bounds(kind):
    """Conservative payload-only m*g*L versus configured simulation limits.

    Sum link lengths and maximum COM offset from the catalogue grip. This is
    an all-orientation upper bound; excludes link self-weight and dynamics.
    No claim about real servo torque, friction, grip retention or safe motion.
    """
    spec = cargo(kind)
    from sim.masterpi_geometry_v3 import PHYSICAL_V3
    half = np.asarray(spec.dims_m)/2
    half[2] += abs(spec.dims_m[2]/2-spec.grip_z_m)
    offset = float(np.linalg.norm(half))
    wrist = PHYSICAL_V3.pad_center_from_wrist_m + offset
    levers = {5: .065+.062+wrist, 4: .062+wrist, 3: wrist}
    caps = {5: 2.2, 4: 1.8, 3: 1.0}  # masterpi_dynamics_v2.py actuator forcerange
    return {str(s): dict(lever_bound_m=length, payload_torque_bound_nm=spec.mass_kg*9.80665*length,
                        configured_cap_nm=caps[s],
                        remaining_payload_only_nm=caps[s]-spec.mass_kg*9.80665*length)
            for s, length in levers.items()}


def audit():
    manifest = json.loads(MANIFEST.read_text())
    grid = list(joint_grid())
    rows = []
    # Compute camera<-gripper independently for every allowed sampled PWM.
    relatives = []
    for pwm in grid:
        gripper, camera = nominal_transforms(pwm)
        relatives.append(np.linalg.inv(camera) @ gripper)
    residual = float(np.max(np.abs(np.asarray(relatives)-relatives[0])))
    for run in manifest['runs']:
        grasp = {int(k): v for k, v in run['commands'][0]['pwm'].items()}
        final = {int(k): v for k, v in run['commands'][-1]['pwm'].items()}
        before = camera_object_transform(run['kind'], grasp, grasp)
        after = camera_object_transform(run['kind'], grasp, final)
        rows.append(dict(run=run['run'], kind=run['kind'], grasp_pwm=grasp, lift_pwm=final,
                         grasp_pitch_deg=tool_pose(grasp).pitch_deg,
                         geometry=geometry_metrics(run['kind'], before),
                         lift_transform_max_abs_error=float(np.max(np.abs(before-after))),
                         payload_bounds=payload_bounds(run['kind'])))
    files = ['harness/servo_camera_fk.py', 'harness/data/servo_camera_v3_chain.json',
             'harness/visual_arm_v3.py', 'sim/s2_realism_camera_binding.py',
             'sim/masterpi_camera_review_v3.py', 'sim/masterpi_camera_profile.py',
             'sim/masterpi_dynamics_v2.py', 'tests/fixtures/solo_rgb_lift_v3/manifest.json',
             'scripts/probe_solo_lift_inspect_pose.py']
    return dict(schema='solo_inspect_pose_static_audit_v1', status='infeasible_post_grasp_rigid_motion',
                requested_toggle='solo_lift_inspect_pose_v1', implemented_motion=False,
                source_commands_sha=manifest['source_sha'],
                proof='inv(T_base_gripper * T_gripper_camera) * T_base_gripper * T_gripper_object = inv(T_gripper_camera) * T_gripper_object',
                allowed_joint_grid_N=len(grid), grid_max_abs_transform_error=residual,
                pwm_grid=list(range(600, 2500, 300)), pwm_hardware_limits=[500, 2500],
                camera_servo='none; camera parent is gripper; servo 6 rotates both',
                edge_margin_px=EDGE_MARGIN_PX, min_part_pixels=3072, runs=rows,
                physical_runs=0, render_runs=0, diagnostic_runs=0, gate_runs=0,
                source_sha256={f: hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
                limitations=['Nominal rigid hold, not measured grip offset/slip.',
                             'No near clipping or occlusion: geometry overestimates available evidence.',
                             'Payload torque only, not total actuator or real hardware margin.',
                             'All original six runs are provenance inputs, not new successes.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: result[k] for k in ('status', 'allowed_joint_grid_N', 'grid_max_abs_transform_error')}))


if __name__ == '__main__':
    main()
