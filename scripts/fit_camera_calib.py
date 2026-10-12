"""Offline extrinsic calibration fit: board frames + marked chassis placements -> data/camera_calib_measured_v1.json.

usage: fit_camera_calib.py <frames_dir (placements.json + jpgs)> <out.json> [--holdout-every 4]
Inputs are only images, the board spec and the marked chassis placements (lab fixture). OpenCV fisheye undistort ->
findChessboardCorners(SB) -> per-frame solvePnP (independent estimate) -> joint robust reprojection fit of one
(origin, rotation) per arm posture. Ground-truth simulator camera pose is never read.
"""
import hashlib, json, math, sys
from pathlib import Path
import cv2, numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation as Rot
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix
from harness.servo_camera_fk import transform_from_commands

W, H = 640, 480
K = np.asarray(scaled_camera_matrix(W, H), float)
D = np.asarray(CAMERA_FISHEYE_D, float).reshape(4, 1)


def board_points(board):
    (nx, ny), s = board['squares'], board['square_m']
    cx, cy = board['center_m']
    ic = board['inner_corners']
    pts = [(cx+(i+1-nx/2)*s, cy+(j+1-ny/2)*s, board['top_z_m']) for j in range(ic[1]) for i in range(ic[0])]
    return np.asarray(pts, float)


def undistort(rgb):
    return cv2.fisheye.undistortImage(rgb, K, D, Knew=K)


def detect(rgb, inner):
    gray = cv2.cvtColor(undistort(rgb), cv2.COLOR_RGB2GRAY)
    ok, c = cv2.findChessboardCorners(gray, tuple(inner), flags=cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE)
    if ok:
        c = cv2.cornerSubPix(gray, c, (4, 4), (-1, -1), (cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER, 50, 1e-3))
    else:
        ok, c = cv2.findChessboardCornersSB(gray, tuple(inner), flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
    if not ok:
        return None
    return c.reshape(-1, 2).astype(float)


def refine_guided(rgb, predicted, max_move_px=3.0):
    """Sub-pixel refinement of corners predicted from the current calibration (used only after an unguided stage-1 fit)."""
    gray = cv2.cvtColor(undistort(rgb), cv2.COLOR_RGB2GRAY)
    if (predicted < 6).any() or (predicted[:, 0] > W-7).any() or (predicted[:, 1] > H-7).any():
        return None
    ref = cv2.cornerSubPix(gray, predicted.reshape(-1, 1, 2).astype(np.float32), (4, 4), (-1, -1),
                           (cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER, 50, 1e-3)).reshape(-1, 2).astype(float)
    return ref if np.linalg.norm(ref-predicted, axis=1).max() <= max_move_px else None


def fk(servo):
    (o, r), _ = transform_from_commands({int(k): v for k, v in servo.items()}, camera_pose='servo_fk_v1')
    return np.asarray(o, float), np.asarray(r, float)


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.]])


def world_cam(base, o_r, r_rc):
    x, y, yaw = base
    return np.array([x, y, 0.]) + rz(yaw)@o_r, rz(yaw)@r_rc


def project(pts_w, origin_w, r_wc):
    pc = (np.asarray(pts_w)-origin_w)@r_wc
    return (pc[:, :2]/pc[:, 2:3])*[K[0, 0], K[1, 1]]+[K[0, 2], K[1, 2]]


def angles(o, r):
    f = r[:, 2]; right = r[:, 0]
    return dict(pitch_deg=math.degrees(math.asin(f[2])), yaw_deg=math.degrees(math.atan2(f[1], f[0])),
                roll_deg=math.degrees(math.asin(np.clip(right[2], -1, 1))), height_m=float(o[2]),
                forward_m=float(o[0]), left_m=float(o[1]))


def ground_error(corners, base, o_r, r_rc, pts_w):
    """Back-project undistorted corner pixels to the board plane through (o_r, r_rc); error (m) vs the board point (robot frame)."""
    ray = np.c_[(corners-[K[0, 2], K[1, 2]])/[K[0, 0], K[1, 1]], np.ones(len(corners))]@r_rc.T
    t = (pts_w[0, 2]-o_r[2])/ray[:, 2]
    est = o_r[:2]+ray[:, :2]*t[:, None]
    x, y, yaw = base
    true = (rz(-yaw)@(pts_w-[x, y, 0.]).T).T[:, :2]
    return np.linalg.norm(est-true, axis=1), np.linalg.norm(true, axis=1)


def main():
    srcs = [Path(x) for x in sys.argv[1].split(',')]; out = Path(sys.argv[2])
    every = int(sys.argv[sys.argv.index('--holdout-every')+1]) if '--holdout-every' in sys.argv else 4
    meta = dict(board=None, placements=[])
    for d in srcs:
        part = json.loads((d/'placements.json').read_text())
        assert meta['board'] in (None, part['board']), 'all capture sessions must share one board'
        meta['board'] = part['board']
        meta['placements'] += [dict(p, _dir=str(d)) for p in part['placements']]
    board = meta['board']; obj = board_points(board)
    by_posture = {}
    for p in meta['placements']:
        by_posture.setdefault(p['posture'], []).append(p)
    postures, report = [], {}
    for name, frames in by_posture.items():
        servo = frames[0]['servo']; o0, r0 = fk(servo)
        rows = []
        for idx, p in enumerate(frames):
            raw = (Path(p['_dir'])/p['file']).read_bytes()
            rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(raw, np.uint8), 1), cv2.COLOR_BGR2RGB)
            c = detect(rgb, board['inner_corners'])
            row = dict(file=p['file'], sha256=hashlib.sha256(raw).hexdigest(), detected=c is not None, guided=False, rgb=rgb, idx=idx,
                       base=p['base_xy_yaw'], corners=c)
            if c is not None:  # nominal FK prior only to resolve the 180-deg corner ordering
                ow, rw = world_cam(p['base_xy_yaw'], o0, r0)
                g = c.reshape(board['inner_corners'][1], board['inner_corners'][0], 2)
                variants = [g.reshape(-1, 2), g[::-1].reshape(-1, 2), g[:, ::-1].reshape(-1, 2), g[::-1, ::-1].reshape(-1, 2)]
                errs = [np.linalg.norm(project(obj, ow, rw)-cc, axis=1).mean() for cc in variants]
                row['corners'] = variants[int(np.argmin(errs))]; row['prior_px'] = float(min(errs))
            rows.append(row)
        def fit_rows(rs):
            def res_(v):
                o_r = o0+v[:3]; r_rc = Rot.from_rotvec(v[3:]).as_matrix()@r0
                out_ = []
                for r in rs:
                    ow, rw = world_cam(r['base'], o_r, r_rc)
                    out_.append((project(obj, ow, rw)-r['corners']).ravel())
                return np.concatenate(out_)
            sol_ = least_squares(res_, np.zeros(6), loss='soft_l1', f_scale=1.0)
            return sol_, res_
        stage1 = [r for r in rows if r['detected']]
        sol1, _ = fit_rows(stage1)
        o1 = o0+sol1.x[:3]; r1 = Rot.from_rotvec(sol1.x[3:]).as_matrix()@r0
        for _ in range(2):  # guided stage: predict from the current fit, refine, refit
            for r in rows:
                if r['detected'] and not r['guided']: continue
                ow, rw = world_cam(r['base'], o1, r1)
                pc = (obj-ow)@rw
                if (pc[:, 2] < .05).any(): continue
                ref = refine_guided(r['rgb'], project(obj, ow, rw))
                if ref is not None:
                    r.update(corners=ref, detected=True, guided=True)
            soln, _ = fit_rows([r for r in rows if r['detected']])
            o1 = o0+soln.x[:3]; r1 = Rot.from_rotvec(soln.x[3:]).as_matrix()@r0
        det = [r for r in rows if r['detected']]
        train = [r for r in det if r['idx'] % every != every-1]; hold = [r for r in det if r['idx'] % every == every-1]
        pnp = []
        for r in det:
            ok, rvec, tvec = cv2.solvePnP(obj, r['corners'], K, None, flags=cv2.SOLVEPNP_ITERATIVE)
            if not ok: continue
            rcw = cv2.Rodrigues(rvec)[0]
            cam_w = (-rcw.T@tvec).ravel(); r_wc = rcw.T
            x, y, yaw = r['base']
            pnp.append(angles(rz(-yaw)@(cam_w-[x, y, 0.]), rz(-yaw)@r_wc))
        unguided_angles = angles(o0+sol1.x[:3], Rot.from_rotvec(sol1.x[3:]).as_matrix()@r0)
        sol, residual = fit_rows(train)
        o_r = o0+sol.x[:3]; r_rc = Rot.from_rotvec(sol.x[3:]).as_matrix()@r0
        rms = float(np.sqrt(np.mean(residual(sol.x)**2)))
        # parameter uncertainty from the Jacobian
        jac = sol.jac; cov = np.linalg.inv(jac.T@jac)*(rms**2)
        sig = np.sqrt(np.diag(cov))
        def gerr(o, r, rows_):
            e, rg = [], []
            for rr in rows_:
                a, b = ground_error(rr['corners'], rr['base'], o, r, obj); e.append(a); rg.append(b)
            return np.concatenate(e), np.concatenate(rg)
        stats = {}
        for label, rs in (('train', train), ('holdout', hold)):
            if not rs: continue
            for mode, (o, r) in (('nominal_fk', (o0, r0)), ('measured_v1', (o_r, r_rc))):
                e, rg = gerr(o, r, rs)
                stats[f'{label}_{mode}'] = dict(n_frames=len(rs), n_points=int(e.size), median_cm=float(np.median(e)*100),
                    p90_cm=float(np.percentile(e, 90)*100), max_cm=float(e.max()*100), mean_range_m=float(rg.mean()),
                    median_pct_of_range=float(np.median(e/rg)*100))
        entry = dict(posture=name, servo_pulses_1_3_4_5_6=[int(servo[str(k)] if str(k) in servo else servo[k]) for k in (1, 3, 4, 5, 6)],
                     origin_m=[float(v) for v in o_r], rotation_cam_in_robot=[[float(v) for v in row] for row in r_rc],
                     fitted=angles(o_r, r_rc), nominal_fk=angles(o0, r0),
                     param_sigma=dict(origin_m=[float(v) for v in sig[:3]], rotvec_deg=[float(math.degrees(v)) for v in sig[3:]]),
                     reprojection_rms_px=rms, n_frames=len(frames), n_detected=len(det), n_train=len(train), n_holdout=len(hold),
                     per_frame_pnp=dict(n=len(pnp), **{k: dict(median=float(np.median([a[k] for a in pnp])), std=float(np.std([a[k] for a in pnp])))
                                                         for k in ('pitch_deg', 'roll_deg', 'yaw_deg', 'height_m', 'forward_m', 'left_m')}) if pnp else None,
                     ground_error=stats, unguided_stage1=dict(n=len(stage1), fitted=unguided_angles),
                     frames=[dict(file=r['file'], sha256=r['sha256'], detected=r['detected'], guided=r['guided']) for r in rows])
        postures.append(entry)
    calib = dict(schema='ugrp.camera_calib_measured.v1', option='measured_v1', date='2026-10-12',
                 frame='chassis_yaw_floor (same as servo_fk_v1: x forward, y left, z up above floor; rotation columns = camera right/down/forward)',
                 intrinsics=dict(K=K.tolist(), D=D.ravel().tolist(), note='measured fisheye K/D from sim.masterpi_camera_profile, kept fixed'),
                 board=board, placement_note='chassis x,y,yaw are lab-marked floor positions (fixture), not simulator readback',
                 fitter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), postures=postures)
    text = json.dumps(calib, indent=1)
    out.write_text(text)
    print('sha256', hashlib.sha256(text.encode()).hexdigest())
    for e in postures:
        print(e['posture'], 'detected', e['n_detected'], '/', e['n_frames'], 'rms_px', round(e['reprojection_rms_px'], 3))
        print('  fitted', {k: round(v, 4) for k, v in e['fitted'].items()}); print('  nominal', {k: round(v, 4) for k, v in e['nominal_fk'].items()})
        print('  sigma', e['param_sigma']); print('  pnp', e['per_frame_pnp'])
        for k, v in e['ground_error'].items(): print('  ', k, {a: round(b, 3) for a, b in v.items()})


if __name__ == '__main__':
    main()
