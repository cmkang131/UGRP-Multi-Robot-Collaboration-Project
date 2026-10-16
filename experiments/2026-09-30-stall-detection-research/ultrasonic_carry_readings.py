#!/usr/bin/env python3
"""What would the front ultrasonic read while a facing pair carries the beam?  Kinematics + ray casts only, NO physics step.

Restores recorded MuJoCo states (mjSTATE_INTEGRATION checkpoints of stage-probe cases: `staged_before_submit` = beam just
lifted, before the leg; `stage_stop` = end of the leg / end of the stall) into the standard scene, runs `sim/ultrasonic_range.py`
(noise-free first echo + what it hit, evaluation diagnostic) for r1 and r2, and reports:
  * first echo range and geom at the leg start and at the leg end,
  * range change vs. the commanded forward displacement (own command history, x measured carry gain),
  * GT base displacement between the two states (label only),
  * which geoms fill the wrist camera's valid pixels (ray cast through the pinhole/fisheye model, step 8).
Nothing here reaches a controller.  Usage: ultrasonic_carry_readings.py [--max-moving N]
"""
import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from common import OUT, cmd_series, load_case  # noqa: E402
from harness import owncam_view  # noqa: E402
from harness.ultrasonic_model import DEFAULT_SPEC, sensor_seed  # noqa: E402
from harness.visual_arm import camera_extrinsics  # noqa: E402
from harness.zone_own_team_host import OwnCamTeamHost  # noqa: E402
from scripts.run_pair_stage_probes import CALIBRATION, MAP_ID, order_for  # noqa: E402
from scripts.zone_pair_dev_runtime import make_scene  # noqa: E402
from sim.ultrasonic_range import MujocoUltrasonic  # noqa: E402

GAIN = 1.328


def build(case, tmp):
    spec = {'map': case.get('map', MAP_ID), 'seed': case['seed'], 'goal': {'B': {'cyan': 1}}, 'pair_policy': case.get('pair_policy', 'v5h'),
            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': list(case['beam_xyyaw'])}],
            'pair_order_sheets': {'cargoX': case['coarse_order_sheet']}, 'order_sheet': order_for('B'),
            'contact_profile': 'cargo_noslip_v1', 'job_sim_limit_s': 900.}
    student = {'mode': 'm1', 'calibration': CALIBRATION, 'skill_module': 'harness.wrist_zone_skill_v9', 'skill_class': 'WristZoneDeliveryV9'}
    scene = make_scene(spec)
    host = OwnCamTeamHost.__new__(OwnCamTeamHost)
    OwnCamTeamHost.__init__(host, spec, student, root=ROOT, study_layer=lambda *a: None, frames_dir=Path(tmp) / 'frames', scene=scene)
    return host


def restore(host, ckpt):
    m, d = host.world.model, host.world.data
    state = np.load(ckpt)['mj_state_integration']
    spec = mujoco.mjtState.mjSTATE_INTEGRATION
    assert state.size == mujoco.mj_stateSize(m, spec), 'state size differs'
    mujoco.mj_setState(m, d, state, spec)
    mujoco.mj_forward(m, d)


def base_xy(host, rid):
    x = host.world.robot(rid).base_xyz()
    return float(x[0]), float(x[1])


def camera_geoms(host, rid, servo, step=8):
    """Fraction of the SIM-valid wrist pixels whose ray first hits each geom (ray cast, camera pose from issued servo pulses)."""
    m, d = host.world.model, host.world.data
    origin, rays, xs, ys, valid = owncam_view.base_rays(servo, step=step)
    body = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f'{rid}__robot')
    R = d.xmat[body].reshape(3, 3)
    o = d.xpos[body] + R @ origin
    dirs = np.ascontiguousarray(rays[valid] @ R.T)
    n = len(dirs)
    geom = np.full(n, -1, np.int32)
    dist = np.full(n, -1.)
    normal = np.zeros(3 * n)
    mujoco.mj_multiRay(m, d, o, dirs.ravel(), np.array([1, 1, 1, 1, 0, 1], np.uint8), 1, -1, geom, dist, normal, n, 6.0)
    names = []
    for g in geom:
        names.append('none' if g < 0 else (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, int(g)) or f'geom{int(g)}'))
    c = Counter()
    for nm in names:
        key = nm
        for pfx in ('r1__', 'r2__'):
            if key.startswith(pfx):
                key = 'own_or_partner_robot:' + key[len(pfx):]
        c[key] += 1
    return {k: round(v / n, 4) for k, v in c.most_common(8)}


def reading(host, rid, t):
    m, d = host.world.model, host.world.data
    sensor = MujocoUltrasonic(m, d, rid, seed=sensor_seed(911, rid), spec=DEFAULT_SPEC)
    rd, diag = sensor.measure_diagnostic(t)
    return {'range_m': rd.range_m, 'status': rd.status, 'true_first_echo_m': diag['true_first_echo_m'], 'echo_geom': diag['echo_geom'],
            'echo_is_own_arm': diag['echo_is_own_arm'], 'n_hit_geoms': len(diag['hit_geoms'])}


def commanded_forward_m(cmds, rid, t0, t1):
    """Commanded forward displacement (own command history) x measured gain, integrating 10 Hz commands (0.15 s hold)."""
    t, v, dur, holds = cmd_series(cmds, rid)
    tot = 0.0
    for ti, vi, di in zip(t, v, dur):
        a, b = max(ti, t0), min(ti + min(di, 0.1), t1)
        if b > a:
            tot += vi[0] * (b - a)
    return GAIN * tot


def analyse_case(host, d, label):
    case = json.loads((d / 'case.json').read_text())
    robots, cmds, trace = load_case(d)
    out = {'case': d.name, 'label': label, 'robots': {}}
    ck0, ck1 = d / 'checkpoints/staged_before_submit.npz', d / 'checkpoints/stage_stop.npz'
    t0 = json.loads((d / 'checkpoints/staged_before_submit.json').read_text())['sim_s']
    t1 = json.loads((d / 'checkpoints/stage_stop.json').read_text())['sim_s']
    st = {}
    for name, ck, tt in (('start', ck0, t0), ('end', ck1, t1)):
        restore(host, ck)
        st[name] = {rid: {'xy': base_xy(host, rid), 'us': reading(host, rid, tt)} for rid in ('r1', 'r2')}
        if name == 'start':
            servo = robots['r1']['frames'][-1]['commanded_servo']
            st['camera_geoms_start'] = {rid: camera_geoms(host, rid, {int(k): v for k, v in robots[rid]['frames'][-1]['commanded_servo'].items()}) for rid in ('r1', 'r2')}
    for rid in ('r1', 'r2'):
        s, e = st['start'][rid], st['end'][rid]
        disp = float(np.hypot(e['xy'][0] - s['xy'][0], e['xy'][1] - s['xy'][1]))
        cmd_m = abs(commanded_forward_m(cmds, rid, t0, t1))
        r0, r1 = s['us']['true_first_echo_m'], e['us']['true_first_echo_m']
        out['robots'][rid] = {'gt_base_displacement_m': disp, 'commanded_forward_m': cmd_m, 'gt_over_commanded': disp / cmd_m if cmd_m > 1e-3 else None,
                              'echo_start_m': r0, 'echo_end_m': r1, 'echo_start_geom': s['us']['echo_geom'], 'echo_end_geom': e['us']['echo_geom'],
                              'range_change_m': None if r0 is None or r1 is None else r1 - r0}
    out['camera_geoms_start'] = st['camera_geoms_start']
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-moving', type=int, default=8)
    a = ap.parse_args()
    stalled = []
    for tag in ('4194d34c-posAdv2R', '4194d34c-posAdv2L'):
        stalled += sorted((OUT / f'door-relax-envelope-{tag}/cases').glob('carry_*_VENV'))
    stalled.append(OUT / 'door-relax-envelope-4194d34c-posAdvM/cases/carry_b-v6h.adv_teacher_E_y-0.100_h+0.0_b+0.250_+0.0_s911_pPOST_L1_VENV')
    moving = sorted((OUT / 'door-relax-envelope-fdd35cee-envK1gL1/cases').glob('carry_*_s911_*VENV'))
    moving = [p for p in moving if json.loads((p / 'result.json').read_text())['evaluation'].get('passed')][:a.max_moving]
    case0 = json.loads((stalled[0] / 'case.json').read_text())
    res = []
    with tempfile.TemporaryDirectory() as tmp:
        host = build(case0, tmp)
        t_build = float(host.world.data.time)
        for d in stalled:
            res.append(analyse_case(host, d, 'stalled_by_contact'))
            print('done', d.name, flush=True)
        for d in moving:
            res.append(analyse_case(host, d, 'moving_passed'))
            print('done', d.name, flush=True)
        host.world.close()
    (HERE / 'results/ultrasonic_carry_readings.json').write_text(json.dumps({'world_time_after_build_s': t_build, 'cases': res}, indent=1, default=float))
    for lab in ('stalled_by_contact', 'moving_passed'):
        rr = [(c['case'], rid, v) for c in res if c['label'] == lab for rid, v in c['robots'].items()]
        print('==', lab, 'cases', len([c for c in res if c['label'] == lab]))
        for rid in ('r1', 'r2'):
            vs = [v for (_, r, v) in rr if r == rid]
            print(rid, 'GT disp m: %s' % [round(v['gt_base_displacement_m'], 3) for v in vs])
            print(rid, 'cmd fwd m: %s' % [round(v['commanded_forward_m'], 3) for v in vs])
            print(rid, 'echo start:', sorted({(round(v['echo_start_m'], 3) if v['echo_start_m'] is not None else None, v['echo_start_geom']) for v in vs}, key=str))
            print(rid, 'echo end  :', sorted({(round(v['echo_end_m'], 3) if v['echo_end_m'] is not None else None, v['echo_end_geom']) for v in vs}, key=str))
            print(rid, 'range change max |.|: %.4f' % max(abs(v['range_change_m']) for v in vs if v['range_change_m'] is not None))
    print('camera geoms (first case):', json.dumps(res[0]['camera_geoms_start']))


if __name__ == '__main__':
    main()
