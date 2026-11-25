#!/usr/bin/env python3
"""Per-robot Sim2Real calibration helper for MasterPi profiles (`configs/real_robot/<robot>.json`).

Subcommands:
  1. `trim-straight` : Automatically tune per-wheel mecanum diagonal speed trim on a live Pi
                       using short paired forward/backward pulses while tracking a 30 mm red cube.
                       Fixes forward-right / forward-left drift so the robot drives dead straight
                       like the MuJoCo simulator, and writes the trimmed wheel points back to the
                       robot's calibration JSON.
  2. `verify-motions`: Run short paired forward/backward, rotate-left/right, and strafe-left/right
                       pulses through the robot's live `Executor` + calibration JSON and report
                       how closely physical displacement/yaw matches simulator contract targets.
  3. `set-profile`   : Offline helper to update `camera`, `vision`, `pulse_scale`, `servos`, or
                       `diagonal_trim` fields in a calibration JSON and validate via `calibration.parse`.

Safety:
  - Always stops `ugrp-camera.service` cleanly before opening `/dev/video0`.
  - Always executes paired `+dir` / `-dir` pulses (`<= 0.25 s`) and stops all 4 motors in `finally`.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from real_robot import calibration as cal_mod  # noqa: E402


def apply_wheel_trim(
    data: dict,
    *,
    diag_delta: float = 0.0,
    yaw_delta: float = 0.0,
    min_speed: float = 35.0,
    max_speed: float = 100.0,
) -> dict:
    """Return a copy of calibration JSON with idempotent per-wheel mecanum diagonal & yaw trim.

    - `diag_delta > 0` boosts `front_right` & `rear_left` (counters forward-right lateral drift).
      `diag_delta < 0` boosts `front_left` & `rear_right` (counters forward-left lateral drift).
    - `yaw_delta > 0` boosts `front_right` & `rear_right` (counters right/CW heading drift).
      `yaw_delta < 0` boosts `front_left` & `rear_left` (counters left/CCW heading drift).
    All 4 wheel boosts are shifted so min(boost) == 0, preserving the symmetric base speed curve.
    """
    out = json.loads(json.dumps(data))
    wheels = out['wheels']
    names = ('front_left', 'front_right', 'rear_left', 'rear_right')
    n_pts = len(wheels['front_left']['points'])
    if any(len(wheels[w]['points']) != n_pts for w in names):
        raise ValueError('all four wheels must have the same number of calibration points to apply wheel trim')

    base_points = []
    for idx in range(n_pts):
        sim_v = float(wheels['front_left']['points'][idx][0])
        base_b = min(float(wheels[w]['points'][idx][1]) for w in names)
        base_points.append((sim_v, base_b))

    raw_offsets = {
        'front_left': -0.5 * float(diag_delta) - 0.5 * float(yaw_delta),
        'front_right': +0.5 * float(diag_delta) + 0.5 * float(yaw_delta),
        'rear_left': +0.5 * float(diag_delta) - 0.5 * float(yaw_delta),
        'rear_right': -0.5 * float(diag_delta) + 0.5 * float(yaw_delta),
    }
    floor = min(raw_offsets.values())
    boosts = {w: round(raw_offsets[w] - floor, 2) for w in names}

    for w in names:
        boost = boosts[w]
        new_pts = []
        for sim_v, base_b in base_points:
            b_val = round(max(min_speed, min(max_speed, base_b + boost)), 1)
            new_pts.append([sim_v, b_val])
        wheels[w]['points'] = new_pts

    src = out.get('source')
    if isinstance(src, dict):
        src['wheel_trim'] = {
            'diag_delta': round(float(diag_delta), 2),
            'yaw_delta': round(float(yaw_delta), 2),
            'per_wheel_boost': boosts,
        }
    cal_mod.parse(out)
    return out


def apply_diagonal_trim(data: dict, delta_fr_rl: float, *, min_speed: float = 35.0, max_speed: float = 100.0) -> dict:
    """Backward-compatible wrapper applying symmetric mecanum diagonal trim (`diag_delta=delta_fr_rl`)."""
    return apply_wheel_trim(data, diag_delta=delta_fr_rl, yaw_delta=0.0, min_speed=min_speed, max_speed=max_speed)


def fit_camera_from_cube_samples(
    samples: list[dict],
    *,
    cube_size_mm: float = 30.0,
    cx_real: float = 320.0,
    cy_real: float = 240.0,
    posture: dict | None = None,
) -> dict:
    """Estimate `SimCameraWarp` parameters (`f_real`, `pitch_offset_deg`, `yaw_offset_deg`) from cube frames.

    Each sample dict requires:
      - `distance_m`: measured floor distance from robot base to cube front/center (m, > 0)
      - `cx`, `cy`: detected cube centroid (px) in the unwarped 640x480 real frame
      - `area_px`: detected cube pixel area in the unwarped 640x480 real frame
      - `y1` (optional): bottom pixel row of the cube blob (used for ground projection; falls back to `cy + 0.5*sqrt(area_px)`)
    """
    import importlib.util
    if not samples:
        raise ValueError('at least one cube sample is required')
    if cube_size_mm <= 0.0:
        raise ValueError(f'cube_size_mm must be > 0, got {cube_size_mm}')

    gp_path = ROOT / 'solo_pipeline' / 'harness' / 'approach_survey_v1_parts' / 'ground_projection.py'
    ac_path = ROOT / 'solo_pipeline' / 'harness' / 'approach_survey_v1_parts' / 'approach_core.py'
    gp_spec = importlib.util.spec_from_file_location('ugrp_cal_gp', gp_path)
    gp = importlib.util.module_from_spec(gp_spec)
    gp_spec.loader.exec_module(gp)
    ac_spec = importlib.util.spec_from_file_location('ugrp_cal_ac', ac_path)
    ac = importlib.util.module_from_spec(ac_spec)
    ac_spec.loader.exec_module(ac)

    use_posture = dict(ac.FAR_POSTURE) if posture is None else {int(k): int(v) for k, v in posture.items()}
    f_sim = math.sqrt(float(gp.K[0, 0]) * float(gp.K[1, 1]))
    cube_m = cube_size_mm / 1000.0

    f_geom_list = []
    f_sim_match_list = []
    yaw_list = []
    pitch_list = []
    for s in samples:
        d = float(s['distance_m'])
        area = float(s['area_px'])
        cx = float(s['cx'])
        cy = float(s['cy'])
        if d <= 0.0 or area <= 0.0:
            raise ValueError(f'invalid sample {s!r}')
        side_px = math.sqrt(area)
        f_geom = side_px * d / cube_m
        f_geom_list.append(f_geom)
        # Match apparent cube area in warped sim image to A_REF_PX at D_STOP_M (0.20 m):
        # A_real * (f_sim / f_real)^2 == A_REF_PX * (D_STOP_M / d)^2
        f_match = f_sim * (d / ac.D_STOP_M) * math.sqrt(area / ac.A_REF_PX)
        f_sim_match_list.append(f_match)
        yaw_list.append(-math.degrees(math.atan2(cx - cx_real, f_geom)))

        # Solve pitch_offset_deg by bisection so ground_projection of cube bottom edge matches d
        y_bot = float(s['y1']) if s.get('y1') is not None else min(479.0, cy + 0.5 * side_px)
        lo, hi = -30.0, 45.0
        for _ in range(32):
            mid = 0.5 * (lo + hi)
            gp.set_camera_pitch_offset_deg(mid)
            hit = gp.project_pixels([[cx, y_bot]], use_posture)[0]
            r_est = float(hit[0]) if math.isfinite(hit[0]) and hit[0] > 0 else 99.0
            # Larger +pitch (steeper downward) -> shorter projected distance r_est
            if r_est > d:
                lo = mid
            else:
                hi = mid
        pitch_list.append(0.5 * (lo + hi))
    gp.set_camera_pitch_offset_deg(None)

    return {
        'f_real_geom': round(float(median(f_geom_list)), 1),
        'f_real': round(float(median(f_sim_match_list)), 1),
        'pitch_offset_deg': round(float(median(pitch_list)), 1),
        'yaw_offset_deg': round(float(median(yaw_list)), 1),
        'n_samples': len(samples),
    }


def solve_zero_drift_delta(samples: list[tuple[float, float]]) -> float:
    """Given [(delta_fr_rl, median_dcx_px), ...], find delta where forward dcx_px == 0.

    Note: when the robot drifts forward-RIGHT, the stationary cube ahead moves LEFT in the image
    (`dcx < 0`). Increasing `delta_fr_rl` pushes the robot forward-LEFT, making `dcx` more positive.
    """
    if not samples:
        raise ValueError('no trim samples provided')
    pts = sorted(samples, key=lambda x: x[0])
    # First look for a sign change (bracketed root)
    for (d0, x0), (d1, x1) in zip(pts, pts[1:]):
        if x0 == 0.0:
            return float(d0)
        if x1 == 0.0:
            return float(d1)
        if (x0 < 0.0 < x1) or (x1 < 0.0 < x0):
            return float(d0 + (0.0 - x0) * (d1 - d0) / (x1 - x0))
    # Fallback: linear least-squares fit clamped to tested range + 4
    if len(pts) >= 2:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        denom = sum((x - mx) ** 2 for x in xs)
        if denom > 1e-9:
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
            if abs(slope) > 0.2:
                est = mx - my / slope
                lo, hi = min(xs) - 4.0, max(xs) + 4.0
                return float(max(lo, min(hi, est)))
    # Otherwise pick the tested delta with smallest |dcx|
    return float(min(pts, key=lambda p: abs(p[1]))[0])


_PI_TRIM_SCRIPT = r"""
import json, sys, time, cv2, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path.home() / 'ugrp_sim2real'))
from real_robot.boards import I2CBoard
from real_robot.camera import OpenCVSource

cfg = json.loads(sys.stdin.read())
wheels = cfg['wheels']
deltas = cfg['deltas']
reps = int(cfg['reps'])
pulse_s = float(cfg['pulse_s'])
base_speed = float(cfg['base_speed'])
red_hue_max = int(cfg['red_hue_max'])
red_sat_min = int(cfg['red_sat_min'])
settle_s = float(cfg['settle_s'])

FAR_POSTURE = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}

def detect_red(src):
    for _ in range(3):
        _, jpeg, _, _ = src.grab()
        time.sleep(0.03)
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = (((h <= red_hue_max) | (h >= 172)) & (s > red_sat_min) & (v > 90)).astype(np.uint8)
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    best = None
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 150:
            continue
        if best is None or area > best['A']:
            best = {'A': area, 'cx': float(cents[i][0]), 'cy': float(cents[i][1])}
    return best

def stop_all(board):
    for w in wheels.values():
        board.write_motor(w['motor'], 0)

def drive_pulse(board, sign_dir, delta, dur_s):
    boost_fr_rl = max(0.0, delta)
    boost_fl_rr = max(0.0, -delta)
    for name, w in wheels.items():
        boost = boost_fr_rl if name in ('front_right', 'rear_left') else boost_fl_rr
        spd = int(round(max(35.0, min(100.0, base_speed + boost))))
        board.write_motor(w['motor'], w['sign'] * sign_dir * spd)
    time.sleep(dur_s)
    stop_all(board)

board = I2CBoard()
src = OpenCVSource()
results = []
try:
    for sid, pwm in FAR_POSTURE.items():
        board.write_servo(sid, pwm, 0.8)
    time.sleep(1.0)
    pre = detect_red(src)
    if pre is None:
        print(json.dumps({'ok': False, 'error': 'red cube not visible in FAR_POSTURE', 'pre': None}))
        sys.exit(0)
    for delta in deltas:
        trials = []
        for rep in range(reps):
            b0 = detect_red(src)
            drive_pulse(board, +1, delta, pulse_s)
            time.sleep(settle_s)
            b1 = detect_red(src)
            drive_pulse(board, -1, delta, pulse_s)
            time.sleep(settle_s)
            b2 = detect_red(src)
            row = {'rep': rep, 'b0': b0, 'b1': b1, 'b2': b2}
            if b0 and b1:
                row['dcx_fwd'] = round(b1['cx'] - b0['cx'], 2)
                row['dcy_fwd'] = round(b1['cy'] - b0['cy'], 2)
                row['area_ratio'] = round(b1['A'] / max(1, b0['A']), 4)
            trials.append(row)
        results.append({'delta': delta, 'trials': trials})
    print(json.dumps({'ok': True, 'pre': pre, 'results': results}))
finally:
    stop_all(board)
    src.close()
    board.close()
"""


_PI_VERIFY_SCRIPT = r"""
import json, sys, time, cv2, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path.home() / 'ugrp_sim2real'))
from real_robot import calibration as cal_mod
from real_robot.boards import I2CBoard
from real_robot.camera import OpenCVSource
from real_robot.executor import Executor

cfg = json.loads(sys.stdin.read())
cal = cal_mod.load(cfg['remote_cal'])
red_hue_max = cal.vision.red_hue_max
red_sat_min = cal.vision.red_sat_min
FAR_POSTURE = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}

def detect_red(src):
    for _ in range(3):
        _, jpeg, _, _ = src.grab()
        time.sleep(0.03)
    img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = (((h <= red_hue_max) | (h >= 172)) & (s > red_sat_min) & (v > 90)).astype(np.uint8)
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    best = None
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 150:
            continue
        if best is None or area > best['A']:
            best = {'A': area, 'cx': float(cents[i][0]), 'cy': float(cents[i][1])}
    return best

board = I2CBoard()
src = OpenCVSource()
ex = Executor(board, cal)
seq = 0
def run_pulse(wheels, dur_s):
    global seq
    seq += 1
    t0 = time.monotonic()
    ev = ex.apply(seq, {'t': seq * 0.1, 'wheels': wheels, 'duration_s': [dur_s] * 4, 'pwm': FAR_POSTURE}, t0)
    while ex.next_deadline() is not None:
        time.sleep(0.002)
        ex.poll(time.monotonic())
    time.sleep(0.35)
    return ev

out = {'ok': True, 'robot_id': cal.robot_id, 'motions': {}}
try:
    ex.initialize_servos(FAR_POSTURE, 0.8, time.monotonic())
    time.sleep(1.0)
    out['pre'] = detect_red(src)
    if out['pre'] is None:
        out['ok'] = False
        out['error'] = 'red cube not visible'
        print(json.dumps(out))
        sys.exit(0)
    patterns = [
        ('forward', [0.35, 0.35, 0.35, 0.35], [-0.35, -0.35, -0.35, -0.35], 0.10, 3),
        ('rotate_left', [-0.35, 0.35, -0.35, 0.35], [0.35, -0.35, 0.35, -0.35], 0.10, 2),
        ('strafe_left', [-0.35, 0.35, 0.35, -0.35], [0.35, -0.35, -0.35, 0.35], 0.10, 2),
    ]
    for name, w_pos, w_neg, dur, n_pulses in patterns:
        b0 = detect_red(src)
        for _ in range(n_pulses):
            run_pulse(w_pos, dur)
        b1 = detect_red(src)
        for _ in range(n_pulses):
            run_pulse(w_neg, dur)
        b2 = detect_red(src)
        entry = {'n_pulses': n_pulses, 'dur_s': dur, 'b0': b0, 'b1': b1, 'b2': b2}
        if b0 and b1:
            entry['dcx_total'] = round(b1['cx'] - b0['cx'], 2)
            entry['dcx_per_pulse'] = round((b1['cx'] - b0['cx']) / n_pulses, 2)
            entry['dcy_total'] = round(b1['cy'] - b0['cy'], 2)
            entry['area_ratio'] = round(b1['A'] / max(1, b0['A']), 4)
        out['motions'][name] = entry
    print(json.dumps(out))
finally:
    ex.stop_all('verify end')
    src.close()
    board.close()
"""


def _ssh_run_python(host: str, script: str, payload: dict, timeout_s: int = 90) -> dict:
    cmd = [
        'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host,
        'systemctl --user stop ugrp-camera.service 2>/dev/null || true; '
        'pkill -9 -f "[m]asterpi_robot_server.py" 2>/dev/null || true; '
        'python3 -c ' + json.dumps(script),
    ]
    res = subprocess.run(cmd, input=json.dumps(payload), capture_output=True, text=True, timeout=timeout_s)
    if res.returncode != 0:
        raise RuntimeError(f'ssh {host} failed (rc={res.returncode}): {res.stderr.strip() or res.stdout.strip()}')
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError(f'ssh {host} produced no output: {res.stderr.strip()}')
    return json.loads(lines[-1])


def _sync_calibration(host: str, local_path: Path, remote_dir: str = '~/ugrp_sim2real/configs/real_robot') -> None:
    subprocess.run(['scp', '-o', 'BatchMode=yes', str(local_path), f'{host}:{remote_dir}/{local_path.name}'], check=True)


def cmd_sync_runtime(args) -> int:
    """Copy Pi-side runtime modules + robot calibration JSON to `<host>:~/ugrp_sim2real/`."""
    host = args.host
    files = [
        ROOT / 'real_robot' / 'calibration.py',
        ROOT / 'real_robot' / 'executor.py',
        ROOT / 'real_robot' / 'camera.py',
        ROOT / 'real_robot' / 'camera_warp.py',
        ROOT / 'real_robot' / 'adapter.py',
        ROOT / 'real_robot' / 'skill_io.py',
    ]
    subprocess.run(
        ['scp', '-o', 'BatchMode=yes', *[str(f) for f in files], f'{host}:~/ugrp_sim2real/real_robot/'],
        check=True,
    )
    if args.calibration:
        cal_path = Path(args.calibration)
        cal_mod.load(cal_path)
        _sync_calibration(host, cal_path)
        print(f'Synced runtime + {cal_path.name} to {host}:~/ugrp_sim2real/')
    else:
        print(f'Synced runtime to {host}:~/ugrp_sim2real/real_robot/')
    return 0


def cmd_trim_straight(args) -> int:
    cal_path = Path(args.calibration)
    data = json.loads(cal_path.read_text())
    cal = cal_mod.parse(data)
    # Use base board speed at sim=0.35 (minimum across wheels so re-running starts from symmetric base)
    base_35 = min(
        cal_mod.parse(apply_diagonal_trim(data, 0.0)).board_speed(i, 0.35) * cal.wheels[w].sign
        for i, w in enumerate(cal_mod.SIM_WHEELS)
    )
    deltas = [float(x) for x in args.deltas.split(',')]
    payload = {
        'wheels': {w: {'motor': cal.wheels[w].motor, 'sign': cal.wheels[w].sign} for w in cal_mod.SIM_WHEELS},
        'deltas': deltas,
        'reps': args.reps,
        'pulse_s': args.pulse_s,
        'base_speed': float(base_35),
        'red_hue_max': cal.vision.red_hue_max,
        'red_sat_min': cal.vision.red_sat_min,
        'settle_s': args.settle_s,
    }
    report = _ssh_run_python(args.host, _PI_TRIM_SCRIPT, payload)
    if not report.get('ok'):
        print(json.dumps(report, indent=2))
        return 1

    samples = []
    summary_rows = []
    for item in report['results']:
        dcxs = [t['dcx_fwd'] for t in item['trials'] if 'dcx_fwd' in t]
        if dcxs:
            med_dcx = float(median(dcxs))
            samples.append((float(item['delta']), med_dcx))
            summary_rows.append({'delta': item['delta'], 'dcx_fwd_values': dcxs, 'dcx_fwd_median': round(med_dcx, 2)})
        else:
            summary_rows.append({'delta': item['delta'], 'dcx_fwd_values': [], 'dcx_fwd_median': None})

    best_delta = round(solve_zero_drift_delta(samples), 1)
    print(json.dumps({'pre': report['pre'], 'sweep': summary_rows, 'solved_delta_fr_rl': best_delta}, indent=2))

    if args.apply:
        updated = apply_diagonal_trim(data, best_delta)
        if isinstance(updated.get('source'), dict):
            updated['source']['straight_trim_sweep'] = summary_rows
        cal_path.write_text(json.dumps(updated, indent=1) + '\n')
        print(f'Updated {cal_path} with delta_fr_rl={best_delta}')
        if args.sync:
            _sync_calibration(args.host, cal_path)
            print(f'Synced {cal_path.name} to {args.host}:~/ugrp_sim2real/configs/real_robot/')
    return 0


def cmd_verify_motions(args) -> int:
    cal_path = Path(args.calibration)
    cal_mod.load(cal_path)
    if args.sync:
        _sync_calibration(args.host, cal_path)
    remote_cal = f'~/ugrp_sim2real/configs/real_robot/{cal_path.name}'
    report = _ssh_run_python(args.host, _PI_VERIFY_SCRIPT, {'remote_cal': remote_cal})
    print(json.dumps(report, indent=2))
    return 0 if report.get('ok') else 1


def cmd_fit_camera(args) -> int:
    import importlib.util
    cal_path = Path(args.calibration)
    data = json.loads(cal_path.read_text())
    cal = cal_mod.parse(data)

    ac_path = ROOT / 'solo_pipeline' / 'harness' / 'approach_survey_v1_parts' / 'approach_core.py'
    ac_spec = importlib.util.spec_from_file_location('ugrp_fitcam_ac', ac_path)
    ac = importlib.util.module_from_spec(ac_spec)
    ac_spec.loader.exec_module(ac)
    ac.set_red_hue_max(cal.vision.red_hue_max)
    ac.set_red_sat_min(cal.vision.red_sat_min)

    samples = []
    for item in args.sample:
        if ':' not in item:
            raise SystemExit(f'--sample must be DIST_M:IMAGE_PATH, got {item!r}')
        dist_str, img_path = item.split(':', 1)
        d_m = float(dist_str)
        comps = ac.components(Path(img_path).read_bytes(), args.kind)
        if not comps:
            raise SystemExit(f'no {args.kind} cube detected in {img_path}')
        b = comps[0]
        samples.append({'distance_m': d_m, 'cx': b['cx'], 'cy': b['cy'], 'area_px': b['A'], 'y1': b['y1']})

    fitted = fit_camera_from_cube_samples(samples, cube_size_mm=args.cube_size_mm)
    print(json.dumps({'samples': samples, 'fitted': fitted}, indent=2))
    if args.apply:
        cam = dict(data.get('camera') or {})
        cam.update(
            enabled=True,
            f_real=fitted['f_real'],
            pitch_offset_deg=fitted['pitch_offset_deg'],
            yaw_offset_deg=fitted['yaw_offset_deg'] if args.apply_yaw else cam.get('yaw_offset_deg', 0.0),
        )
        data['camera'] = cam
        if isinstance(data.get('source'), dict):
            data['source']['camera_fit'] = fitted
        cal_mod.parse(data)
        cal_path.write_text(json.dumps(data, indent=1) + '\n')
        print(f'Updated {cal_path} camera section')
        if args.sync and args.host:
            _sync_calibration(args.host, cal_path)
            print(f'Synced {cal_path.name} to {args.host}:~/ugrp_sim2real/configs/real_robot/')
    return 0


def cmd_set_profile(args) -> int:
    cal_path = Path(args.calibration)
    data = json.loads(cal_path.read_text())
    if args.diagonal_trim is not None or args.yaw_trim is not None:
        data = apply_wheel_trim(
            data,
            diag_delta=args.diagonal_trim or 0.0,
            yaw_delta=args.yaw_trim or 0.0,
        )
    if args.camera_f_real is not None or args.camera_pitch_deg is not None or args.camera_enabled is not None:
        cam = dict(data.get('camera') or {})
        if args.camera_enabled is not None:
            cam['enabled'] = args.camera_enabled == 'true'
        if args.camera_f_real is not None:
            cam['f_real'] = args.camera_f_real
        if args.camera_pitch_deg is not None:
            cam['pitch_offset_deg'] = args.camera_pitch_deg
        data['camera'] = cam
    if args.red_hue_max is not None or args.red_sat_min is not None:
        vis = dict(data.get('vision') or {})
        if args.red_hue_max is not None:
            vis['red_hue_max'] = args.red_hue_max
        if args.red_sat_min is not None:
            vis['red_sat_min'] = args.red_sat_min
        data['vision'] = vis
    if any(v is not None for v in (args.drive_scale, args.rotate_scale, args.strafe_scale)):
        ps = dict(data.get('pulse_scale') or {'drive': 1.0, 'rotate': 1.0, 'strafe': 1.0})
        if args.drive_scale is not None:
            ps['drive'] = args.drive_scale
        if args.rotate_scale is not None:
            ps['rotate'] = args.rotate_scale
        if args.strafe_scale is not None:
            ps['strafe'] = args.strafe_scale
        data['pulse_scale'] = ps
    cal_mod.parse(data)
    cal_path.write_text(json.dumps(data, indent=1) + '\n')
    print(f'Validated and saved {cal_path}')
    if args.sync and args.host:
        _sync_calibration(args.host, cal_path)
        print(f'Synced {cal_path.name} to {args.host}:~/ugrp_sim2real/configs/real_robot/')
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)

    t = sub.add_parser('trim-straight', help='Tune per-wheel diagonal trim on live robot for straight driving')
    t.add_argument('--host', required=True, help='SSH host (e.g. ras2, ugrp1)')
    t.add_argument('--calibration', required=True, help='Local robot calibration JSON path')
    t.add_argument('--deltas', default='0,4,8,12', help='Comma-separated FR+RL trim deltas to sweep')
    t.add_argument('--reps', type=int, default=2, help='Paired forward/back reps per delta')
    t.add_argument('--pulse-s', type=float, default=0.20, help='Pulse duration per leg (<= 0.25 s)')
    t.add_argument('--settle-s', type=float, default=0.35, help='Settle wait between pulses')
    t.add_argument('--apply', action='store_true', help='Write solved trim into --calibration')
    t.add_argument('--sync', action='store_true', help='Also scp updated JSON to Pi')

    v = sub.add_parser('verify-motions', help='Verify forward/rotate/strafe through live Executor')
    v.add_argument('--host', required=True)
    v.add_argument('--calibration', required=True)
    v.add_argument('--sync', action='store_true', help='scp JSON to Pi before verifying')

    s = sub.add_parser('set-profile', help='Update and validate profile fields offline')
    s.add_argument('--calibration', required=True)
    s.add_argument('--diagonal-trim', type=float, default=None)
    s.add_argument('--yaw-trim', type=float, default=None)
    s.add_argument('--camera-enabled', choices=('true', 'false'), default=None)
    s.add_argument('--camera-f-real', type=float, default=None)
    s.add_argument('--camera-pitch-deg', type=float, default=None)
    s.add_argument('--red-hue-max', type=int, default=None)
    s.add_argument('--red-sat-min', type=int, default=None)
    s.add_argument('--drive-scale', type=float, default=None)
    s.add_argument('--rotate-scale', type=float, default=None)
    s.add_argument('--strafe-scale', type=float, default=None)
    s.add_argument('--host', default=None)
    s.add_argument('--sync', action='store_true')

    f = sub.add_parser('fit-camera', help='Fit camera f_real/pitch/yaw from cube frames at known distances')
    f.add_argument('--calibration', required=True)
    f.add_argument('--sample', action='append', required=True, help='DIST_M:IMAGE_PATH (repeatable, e.g. 0.45:far.jpg)')
    f.add_argument('--kind', choices=('red', 'cyan'), default='red')
    f.add_argument('--cube-size-mm', type=float, default=30.0)
    f.add_argument('--apply', action='store_true')
    f.add_argument('--apply-yaw', action='store_true', help='Also write fitted yaw_offset_deg into camera config')
    f.add_argument('--host', default=None)
    f.add_argument('--sync', action='store_true')

    r = sub.add_parser('sync-runtime', help='Copy updated real_robot/ runtime and optional calibration JSON to Pi')
    r.add_argument('--host', required=True)
    r.add_argument('--calibration', default=None)
    return p


def main(argv=None) -> int:
    p = build_parser()
    a = p.parse_args(argv)
    if a.cmd == 'trim-straight':
        if not 0.05 <= a.pulse_s <= 0.25:
            p.error('--pulse-s must be in [0.05, 0.25]')
        return cmd_trim_straight(a)
    if a.cmd == 'verify-motions':
        return cmd_verify_motions(a)
    if a.cmd == 'fit-camera':
        return cmd_fit_camera(a)
    if a.cmd == 'sync-runtime':
        return cmd_sync_runtime(a)
    return cmd_set_profile(a)


if __name__ == '__main__':
    raise SystemExit(main())
