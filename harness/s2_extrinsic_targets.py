"""Known calibration fixture and RGB-only PnP, never a task observation.

K/D are held fixed. The board's measured pose in the floor/fixture frame is an
input, as it would be with a surveyed board and a level chassis jig on hardware.
Nominal camera geometry only chooses where to put the board, never fits it.
"""
import copy
import cv2
import numpy as np
from harness import zone_solo_cyan_camera_v3 as old
from harness import zone_s2_realism_contract_v123 as contract
from harness.zone_pair_highpose import HIGH, VIA_110, VIA_130
from harness.zone_final_pair_vision import grasp_postures
from harness.zone_final_pair_contract import camera_record
from sim.masterpi_camera_profile import scaled_camera_matrix, CAMERA_FISHEYE_D

OPTION = 'v3_extrinsic_v1'
PATTERN = (8, 5)
FIXTURE = np.array([1., -1., .0325])
K = scaled_camera_matrix(640, 480)
D = np.asarray(CAMERA_FISHEYE_D, float)


def key(pose):
    return ','.join(str(pose[s]) for s in (3, 4, 5, 6))


def inherited():
    return old.camera_calibration(contract.old.hp.base.read(contract.ROOT/contract.old.CALIBRATION))


def poses():
    cal = inherited()
    empty = [dict(zip((3, 4, 5, 6), map(int, k.split(',')))) for k in cal['camera_models']['unloaded']]
    hover, descent = grasp_postures()
    extra = [hover, *descent, VIA_110, VIA_130, HIGH]
    empty = list({key(p): p for p in [*empty, *extra]}.values())
    # A cyan is placed manually in the calibration jig between these groups.
    # No contacts or pose labels decide this fixed command order.
    # Match S2: lift immediately after its .5 s close + .4 s settle. Survey the
    # floor pose after lowering, not by pressing against the floor for 8 s first.
    loaded = [hover, VIA_110, VIA_130, HIGH, descent[-1]]
    return [('unloaded', p) for p in empty] + [('loaded', p) for p in loaded]


def capture_poses(pose_set='default'):
    if pose_set == 'default':
        return poses()
    if pose_set == 'real_carry_v1':
        # Single empty-gripper pose, no loaded jig retry or grasping.
        return [('unloaded', {3:600,4:2200,5:1400,6:1500})]
    raise ValueError('unsupported calibration pose set')


def nominal(pose):
    cal = inherited()
    for state in ('unloaded', 'loaded'):
        if key(pose) in cal['camera_models'][state]:
            rec = camera_record(cal, state, pose)
            return np.asarray(rec['origin_m']), np.asarray(rec['rotation'])
    # Layout aid only, never an estimate or a PnP initialization.
    from harness.visual_arm_v3 import camera_extrinsics
    from sim.masterpi_camera_review_v1 import quat_matrix
    from sim import masterpi_camera_profile as a, masterpi_camera_review_v3 as b
    origin, axes = camera_extrinsics(pose)
    gripper = np.asarray(axes).T @ (quat_matrix(a.CAMERA_LOCAL_QUAT_WXYZ) @ np.diag([1., -1., -1.])).T
    return (np.asarray(origin) + gripper @ (np.asarray(b.POSITION_M)-a.CAMERA_LOCAL_POS_M),
            gripper @ quat_matrix(b.QUAT_WXYZ) @ np.diag([1., -1., -1.]))


def boards(pose):
    origin, r = nominal(pose)
    distance = min(.22, max(.035, (origin[2]-.018)/(max(.1, -r[2, 2])+.22)))
    square = distance*.045
    result = []
    for index, angle in enumerate((-12., 12., 0.)):
        delta, _ = cv2.Rodrigues(np.array([np.radians(angle), np.radians(angle/2), 0.]))
        axes = r @ delta
        center = origin + r @ np.array([(index-1)*distance*.04, 0., distance])
        # Board coordinates are right/down, with the front surface at z=0.
        obj = np.array([[(x-3.5)*square, (y-2.)*square, 0.] for y in range(5) for x in range(8)])
        result.append(dict(index=index, role='holdout' if index==2 else 'fit',
            square_m=square, origin_m=center.tolist(), rotation=axes.tolist(),
            object_points_floor_m=(obj @ axes.T+center).tolist()))
    return result


def detect(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    ok, corners = cv2.findChessboardCornersSB(gray, PATTERN,
        flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY | cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not ok:
        raise ValueError('CHECKERBOARD_NOT_DETECTED')
    corners = corners.reshape(-1, 2).astype(float)
    # The labelled board top stays at image top (jig tilts <=12 degrees).
    if corners[0, 1] > corners[-1, 1]:
        corners = corners[::-1].copy()
    return corners


def fit(samples):
    """Accept only RGB-derived pixels and known target points; no GT argument."""
    train = [s for s in samples if s['role']=='fit']
    test = [s for s in samples if s['role']=='holdout']
    if len(train)<2 or not test:
        raise ValueError('two fit views and one held-out target pose required')
    points = np.concatenate([s['object_points_floor_m'] for s in train]).astype(float)
    pixels = np.concatenate([s['corners_px'] for s in train]).astype(float)
    normal = cv2.fisheye.undistortPoints(pixels.reshape(-1, 1, 2), K, D).reshape(-1, 2)
    ok, rv, tv = cv2.solvePnP(points, normal, np.eye(3), None, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise ValueError('PNP_FAILED')
    rv, tv = cv2.solvePnPRefineLM(points, normal, np.eye(3), None, rv, tv)
    r, _ = cv2.Rodrigues(rv)
    origin = -r.T @ tv.ravel()
    residuals = {}
    for role in ('fit', 'holdout'):
        errors=[]
        for row in (s for s in samples if s['role']==role):
            obj=np.asarray(row['object_points_floor_m'],float)
            if np.any((obj@r.T+tv.ravel())[:,2]<=0):raise ValueError('PNP_BEHIND_CAMERA')
            pred,_=cv2.fisheye.projectPoints(obj.reshape(1,-1,3),rv,tv,K,D)
            errors.extend(np.linalg.norm(pred.reshape(-1,2)-row['corners_px'],axis=1).tolist())
        residuals[role]=dict(rms_px=float(np.sqrt(np.mean(np.square(errors)))),max_px=max(errors),points=len(errors))
    if residuals['holdout']['rms_px']>1. or residuals['fit']['rms_px']>1.:
        raise ValueError('PNP_REPROJECTION_REJECTED: '+str(residuals))
    # Chassis is level at the known jig height. The legacy composition now
    # carries measured PnP rather than inherited loaded arm/body transforms.
    rec=dict(frame='optical_to_actual_chassis',origin_m=(origin-[0,0,FIXTURE[2]]).tolist(),
        rotation=r.T.tolist(),chassis_to_floor=dict(origin_m=[0,0,float(FIXTURE[2])],rotation=np.eye(3).tolist()))
    return rec, residuals
