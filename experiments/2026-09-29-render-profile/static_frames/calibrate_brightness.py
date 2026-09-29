"""Static (no physics stepping) brightness calibration for ``noshadow_bright_v1`` at recorded A/B poses.

For each recorded probe state (mjSTATE_INTEGRATION checkpoint from the 2026-09-29 A/B raw) this rebuilds the
same scene, restores the state, runs ``mj_forward`` only, and renders the robots' own camera through the real
port pipeline (fisheye + JPEG q82, decoded) and the shared top camera. Lighting variants are applied in place on the
compiled model (castshadow / reflectance / light diffuse+ambient scale), so every variant sees the identical state.

Run from a worktree root with the sim venv:
  python experiments/2026-09-29-render-profile/static_frames/calibrate_brightness.py <ab_raw_root> <out.json> [--scales 1,1.2,...]
No controller, no PF, no stage stepping. Read-only on the raw.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

import cv2
import mujoco
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from harness.zone_own_team_host import OwnCamTeamHost  # noqa: E402
from scripts.run_pair_stage_probes import CALIBRATION, MAP_ID, ORDER  # noqa: E402
from scripts.zone_pair_dev_runtime import make_scene  # noqa: E402

# (label, run folder, case folder prefix, checkpoint)
STATES = [
    ('align_entry', 'st1-shadows-align-grasp', 'align_b-v6d_teacher_nominal_s911_pE2E', 'staged_before_submit'),
    ('align_stop', 'st1-shadows-align-grasp', 'align_b-v6d_teacher_nominal_s911_pE2E', 'stage_stop'),
    ('grasp_lift_entry', 'st1-shadows-align-grasp', 'grasp_lift_b-v6d_teacher_nominal_s911_pE2E', 'staged_before_submit'),
    ('grasp_lift_stop', 'st1-shadows-align-grasp', 'grasp_lift_b-v6d_teacher_nominal_s911_pE2E', 'stage_stop'),
    ('carry_entry', 'st1-shadows-carry-L0', 'carry_b-v6d_teacher_nominal_s911_pE2E', 'staged_before_submit'),
    ('carry_stop', 'st1-shadows-carry-L0', 'carry_b-v6d_teacher_nominal_s911_pE2E', 'stage_stop'),
    ('setdown_entry', 'st1-shadows-setdown-Lend', 'setdown_b-v6d_teacher_nominal_s911_pE2E_Lend', 'staged_before_submit'),
    ('setdown_stop_ns', 'st1-noshadow-setdown-Lend', 'setdown_b-v6d_teacher_nominal_s911_pE2E_Lend', 'stage_stop'),
]


def build_host(root, run, case_dir, frames_dir, render_profile=None):
    case = json.load(open(root / run / 'cases' / f'{case_dir}.case.json'))
    sheet = case['coarse_order_sheet']
    spec = {'map': MAP_ID, 'seed': case['seed'], 'goal': {'B': {'cyan': 1}}, 'pair_policy': case.get('pair_policy', 'v5h'),
            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': list(case['beam_xyyaw'])}],
            'pair_order_sheets': {'cargoX': sheet}, 'order_sheet': copy.deepcopy(ORDER),
            'contact_profile': 'cargo_noslip_v1', 'job_sim_limit_s': 900.}
    student = {'mode': 'm1', 'calibration': CALIBRATION,
               'skill_module': 'harness.wrist_zone_skill_v9', 'skill_class': 'WristZoneDeliveryV9'}
    scene = make_scene(spec)
    if render_profile:
        from sim import render_profile as rp
        rp.install(scene, render_profile)
    spawns = scene.config['setup_only']['spawns']
    z = spawns['r1'][2]
    for rid, (x, y, yaw) in case['placement_xyyaw'].items():
        spawns[rid] = [float(x), float(y), z, float(yaw)]
    host = OwnCamTeamHost.__new__(OwnCamTeamHost)
    OwnCamTeamHost.__init__(host, spec, student, root=ROOT, study_layer=lambda *a: None, frames_dir=frames_dir, scene=scene)
    return host


class Lighting:
    """In-place lighting variants on the compiled model; ``restore`` returns the authored values."""

    def __init__(self, model):
        self.m = model
        self.orig = {k: getattr(model, k).copy() for k in ('light_castshadow', 'mat_reflectance', 'light_diffuse',
                                                           'light_ambient', 'light_specular',
                                                           'light_cutoff', 'light_exponent')}
        self.head = {k: getattr(model.vis.headlight, k).copy() for k in ('ambient', 'diffuse', 'specular')}

    def set(self, shadow=True, reflect=True, scale=1., head_scale=1., spec_scale=1., cutoff=None):
        m, o = self.m, self.orig
        m.light_castshadow[:] = o['light_castshadow'] if shadow else 0
        m.mat_reflectance[:] = o['mat_reflectance'] if reflect else 0.
        m.light_diffuse[:] = o['light_diffuse'] * scale
        m.light_ambient[:] = o['light_ambient'] * scale
        m.light_specular[:] = o['light_specular'] * spec_scale
        m.light_cutoff[:] = o['light_cutoff'] if cutoff is None else cutoff
        for k, v in self.head.items():
            getattr(m.vis.headlight, k)[:] = v * head_scale


def stats(rgb):
    """Gate-equivalent numbers on the same rim mask ``valid_frame`` uses (harness/zone_pair_vision), HSV V."""
    from harness.zone_pair_vision import _valid
    v = cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2HSV)[..., 2][_valid()].astype(float)
    lo, hi = np.percentile(v, [1, 99])
    gate = bool((v < 8).mean() < .25 and hi - lo >= 15 and v.std() >= 3)
    return {'meanV': float(v.mean()), 'p10V': float(np.percentile(v, 10)), 'sat_frac': float((v >= 250).mean()),
            'dark_frac': float((v < 8).mean()), 'contrast_p1_p99': float(hi - lo), 'std': float(v.std()), 'gate_pass': gate}


def decode(jpeg):
    return cv2.cvtColor(cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def render_all(host):
    out = {}
    for rid in ('r1', 'r2'):
        out[rid] = decode(host.world.render_jpeg(robot_id=rid, camera='robot_cam'))
    out['top'] = decode(host.world.render_team_jpeg('cctv_top'))
    return out


def audit_black(root, scale, n, seed=0):
    """Random own-camera poses (base x, y, yaw) around the recorded region: count all-dark (mean V < 1) frames per variant.

    Purpose: the non-shadow path of MuJoCo's renderer returned all-black frames for the r2 setdown view (see README);
    this measures how common that is with ``noshadow_v1`` and whether ``omni`` lights avoid it. Poses may be unphysical
    (inside walls/objects); only the render is exercised, no stepping.
    """
    label, run, case_dir, ck = STATES[6]
    rng = np.random.default_rng(seed)
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        host = build_host(root, run, case_dir, Path(tmp))
        m, d = host.world.model, host.world.data
        arr = np.load(root / run / 'cases' / case_dir / 'checkpoints' / f'{ck}.npz')['mj_state_integration']
        mujoco.mj_setState(m, d, arr, mujoco.mjtState.mjSTATE_INTEGRATION)
        light = Lighting(m)
        joints = {rid: m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f'{rid}__base_free')] for rid in ('r1', 'r2')}
        poses = [(rng.uniform(0.3, 5.5), rng.uniform(-2.6, 0.4), rng.uniform(-np.pi, np.pi)) for _ in range(n)]
        variants = [('shadows_v1', dict()), ('noshadow_v1', dict(shadow=False, reflect=False)),
                    (f'omni_x{scale:g}', dict(shadow=False, reflect=False, scale=scale, spec_scale=scale, cutoff=180.))]
        for name, kw in variants:
            light.set(**kw)
            black = total = 0
            v_means = []
            for rid, adr in joints.items():
                for x, y, yaw in poses:
                    qs = d.qpos.copy()
                    d.qpos[adr:adr + 2] = (x, y)
                    d.qpos[adr + 3:adr + 7] = (np.cos(yaw / 2), 0, 0, np.sin(yaw / 2))
                    mujoco.mj_forward(m, d)
                    img = decode(host.world.render_jpeg(robot_id=rid, camera='robot_cam'))
                    v = float(stats(img)['meanV'])
                    v_means.append(v)
                    black += int(v < 1.)
                    total += 1
                    d.qpos[:] = qs
            out[name] = {'frames': total, 'all_dark_frames': black, 'meanV_median': float(np.median(v_means))}
        host.world.close()
    return out


def verify_and_time(root, scale, repeats=5):
    """The real XML profile must give the same frames as the in-place model edit; and time 640x480 own-camera renders.

    Timing is CPU time of this process (time.process_time) per rendered frame, interleaved across profiles; the host is
    loaded by other work, so read the ratios, not the absolute seconds.
    """
    import time
    out = {'state_checks': [], 'timing': {}}
    profiles = ['shadows_v1', 'noshadow_v1', 'noshadow_bright_v1']
    hosts = {}
    tmps = {name: tempfile.TemporaryDirectory() for name in profiles}
    label, run, case_dir, ck = STATES[0]
    arr = np.load(root / run / 'cases' / case_dir / 'checkpoints' / f'{ck}.npz')['mj_state_integration']
    try:
        for name in profiles:
            host = build_host(root, run, case_dir, Path(tmps[name].name), render_profile=name)
            mujoco.mj_setState(host.world.model, host.world.data, arr, mujoco.mjtState.mjSTATE_INTEGRATION)
            mujoco.mj_forward(host.world.model, host.world.data)
            hosts[name] = host
        for lab, run2, case2, ck2 in STATES:
            if (run2, case2) != (run, case_dir):
                continue
            a2 = np.load(root / run2 / 'cases' / case2 / 'checkpoints' / f'{ck2}.npz')['mj_state_integration']
            row = {'state': lab}
            for name, host in hosts.items():
                mujoco.mj_setState(host.world.model, host.world.data, a2, mujoco.mjtState.mjSTATE_INTEGRATION)
                mujoco.mj_forward(host.world.model, host.world.data)
                row[name] = {rid: stats(decode(host.world.render_jpeg(robot_id=rid, camera='robot_cam'))) for rid in ('r1', 'r2')}
            out['state_checks'].append(row)
        cpu = {name: [] for name in profiles}
        for _ in range(repeats):
            for name, host in hosts.items():            # interleaved
                t0 = time.process_time()
                for rid in ('r1', 'r2'):
                    for _k in range(3):
                        host.world.render_jpeg(robot_id=rid, camera='robot_cam')
                cpu[name].append((time.process_time() - t0) / 6)
        out['timing'] = {name: {'cpu_s_per_frame_median': float(np.median(v)), 'cpu_s_per_frame_all': [round(x, 4) for x in v]}
                         for name, v in cpu.items()}
        out['timing_ratio_to_shadows_v1'] = {name: out['timing'][name]['cpu_s_per_frame_median'] / out['timing']['shadows_v1']['cpu_s_per_frame_median']
                                             for name in profiles}
        out['loadavg_end'] = list(__import__('os').getloadavg())
    finally:
        for host in hosts.values():
            host.world.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('raw_root')
    ap.add_argument('out')
    ap.add_argument('--scales', default='1.0,1.3,1.6,2.0,2.5')
    ap.add_argument('--omni-scales', default='')
    ap.add_argument('--audit', type=int, default=0, help='random-pose all-dark audit with this many poses per robot')
    ap.add_argument('--audit-scale', type=float, default=0.3)
    ap.add_argument('--verify', action='store_true', help='XML profile vs in-place edit + per-frame render CPU time')
    ap.add_argument('--images', default=None, help='dir for side-by-side jpgs of the final variants')
    args = ap.parse_args()
    root = Path(args.raw_root)
    scales = [float(s) for s in args.scales.split(',') if s]
    omni_scales = [float(s) for s in args.omni_scales.split(',') if s]
    rows = []
    for label, run, case_dir, ck in STATES:
        with tempfile.TemporaryDirectory() as tmp:
            host = build_host(root, run, case_dir, Path(tmp))
            m, d = host.world.model, host.world.data
            arr = np.load(root / run / 'cases' / case_dir / 'checkpoints' / f'{ck}.npz')['mj_state_integration']
            mujoco.mj_setState(m, d, arr, mujoco.mjtState.mjSTATE_INTEGRATION)
            mujoco.mj_forward(m, d)
            light = Lighting(m)
            variants = [('shadows_v1', dict())] + [('noshadow_v1', dict(shadow=False, reflect=False))]
            variants += [(f'noshadow_x{s:g}', dict(shadow=False, reflect=False, scale=s)) for s in scales if s != 1.]
            variants += [(f'noshadow_x{s:g}_head', dict(shadow=False, reflect=False, scale=s, head_scale=s)) for s in scales if s != 1.]
            variants += [(f'omni_x{s:g}', dict(shadow=False, reflect=False, scale=s, spec_scale=s, cutoff=180.)) for s in omni_scales]
            for name, kw in variants:
                light.set(**kw)
                mujoco.mj_forward(m, d)
                imgs = render_all(host)
                for cam, img in imgs.items():
                    rows.append({'state': label, 'variant': name, 'cam': cam, **stats(img)})
                    if args.images:
                        Path(args.images).mkdir(parents=True, exist_ok=True)
                        cv2.imwrite(str(Path(args.images) / f'{label}__{cam}__{name}.jpg'), cv2.cvtColor(img, cv2.COLOR_RGB2BGR),
                                    [cv2.IMWRITE_JPEG_QUALITY, 90])
            light.set()
            host.world.close()
        print(label, 'done', flush=True)
    audit = audit_black(root, args.audit_scale, args.audit) if args.audit else None
    Path(args.out).write_text(json.dumps({'mujoco': mujoco.__version__, 'rows': rows, 'black_audit': audit, 'verify': verify_and_time(root, args.audit_scale) if args.verify else None}, indent=1))


if __name__ == '__main__':
    main()
