"""Replay saved carry ledgers numerically. No scene, renderer, remote or LLM."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import numpy as np
from harness.drive_model import CommandDriveModel
from sim.active_lookaround import information, wrap
from sim.lookaround_localization import Camera, map_landmarks, plan_views, visible_fn_for
from sim.solo_carry6 import rank_aware_plan, MARGIN_PX, calibrated_trim_delta, partial_posterior

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'experiments/2026-10-15-map-carry-zone'
BASE = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
CAL = BASE/'solo-carry-93220-870c0c59/raw'
VALID = BASE/'solo-carry-93240-c6d2f5a4/raw'


def ledger(path):
    return [json.loads(x) for x in subprocess.check_output(['zstd', '-dc', str(path)]).splitlines()]


def angular_rows(raw, end):
    commands = ledger(raw/'teacher-commands.jsonl.zst')
    evaluation = {round(r['t'], 1): r for r in ledger(raw/'eval-only.jsonl.zst')}
    model = CommandDriveModel(); rows = []
    for previous, current in zip(commands, commands[1:]):
        if current['t'] > end+1e-6:
            break
        delta = model.delta(previous['command']['wheels'], previous['command']['duration_s'], current['t']-previous['t'])
        def truth(r):
            return r['map_pose']['pose_estimate'][2]-evaluation[round(r['t'], 1)]['map_pose_error_yaw_rad']
        mixed = calibrated_trim_delta(previous['command'], delta, {'trim_yaw_scale': 0.})[2] != delta[2]
        rows.append(dict(t=current['t'], delta=delta, command=previous['command'], mixed=mixed,
                         truth_yaw_delta=wrap(truth(current)-truth(previous))))
    return rows


def calibration():
    # Fit uses ONLY 93220. 93240 is a separate retrospective validation run.
    rows = angular_rows(CAL, 18.4)
    trim = sum(r['delta'][2] for r in rows if r['mixed'])
    pure = sum(r['delta'][2] for r in rows if not r['mixed'])
    truth = sum(r['truth_yaw_delta'] for r in rows)
    scale = max(-1., min(1., (truth-pure)/trim))
    return dict(schema='ugrp.carry6_trim_calibration.v1', trim_yaw_scale=scale,
        drive_model_source='01703ed2790dadad666e53d1b276b97f2b510bda',
        drive_model_sha256=hashlib.sha256((ROOT/'harness/drive_model.py').read_bytes()).hexdigest(),
        calibration_ids=['solo-carry-93220-870c0c59:t1.3-18.4'],
        validation_ids=['solo-carry-93240-c6d2f5a4:t1.3-18.4'],
        fit_method='aggregate yaw minus non-trim yaw / mixed-duration trim yaw',
        calibration_raw=str(CAL), validation_raw=str(VALID),
        gt_usage='offline fit and scoring only; no runtime GT',
        validation_scope='retrospective separate run, same map/task; not prospective generalization',
        contact_loss_model_7b223e30=False)


def score_yaw(raw, constant):
    rows = angular_rows(raw, 18.4)
    old = sum(r['delta'][2] for r in rows)
    new = sum(calibrated_trim_delta(r['command'], r['delta'], constant)[2] for r in rows)
    truth = sum(r['truth_yaw_delta'] for r in rows)
    return dict(ticks=len(rows), baseline_yaw_deg=math.degrees(old), calibrated_yaw_deg=math.degrees(new),
        truth_yaw_change_deg=math.degrees(truth), baseline_error_deg=math.degrees(wrap(old-truth)),
        calibrated_error_deg=math.degrees(wrap(new-truth)))


def geometry():
    result = json.loads((VALID/'result.json').read_text())
    static = json.loads((VALID/'carry-static-map.json').read_text())
    state = result['teacher']['carry']['recovery_events'][0]['pose']
    pose = state['pose_estimate']; P = np.diag(np.square(state['sigma_m_m_rad']))
    camera = Camera(); lms = map_landmarks(static)
    visible = visible_fn_for(static, camera, margin_px=MARGIN_PX)
    baseline = plan_views(pose, P, lms, visible_fn_for(static, camera), start_pan=-48.6)
    candidate = rank_aware_plan(pose, P, lms, visible, start_pan=-48.6)
    truth = result['lookaround']['evaluation']['views'][0]['truth']
    # Actual saved floor detection, not a fabricated observation. No new image.
    from sim.lookaround_localization import LookaroundLocalizer
    saved = result['lookaround']['localizer']['localizer']['views'][0]
    loc = LookaroundLocalizer(static, pose); loc.rank_aware_v1 = True
    loc.own.P = P.copy(); prior = loc.own.x.copy()
    loc._grid_update([], saved['features'], {})
    receipt = loc.fix_acceptance([], saved['features'], [], prior, P)
    partial = partial_posterior(prior, P, loc.own.x, loc.own.P, loc._acceptance_rows, receipt)
    def score(plan):
        J = np.zeros((3, 3)); views = []
        for v in plan['views']:
            seen = [l for l in lms if visible(truth, v['body_yaw_deg'], v['pan_deg'], l)]
            J += information(truth, seen)
            views.append(dict(body_yaw_deg=v['body_yaw_deg'], pan_deg=v['pan_deg'],
                truth_groups_margin100=sorted({l['group'] for l in seen}),
                truth_x_normal_groups=sorted({l['group'] for l in seen if l.get('normal', [0])[0] != 0})))
        return dict(views=views, truth_minimum_eigenvalue_margin100=float(np.linalg.eigvalsh(J)[0]),
                    truth_x_normal_visible_views=sum(bool(v['truth_x_normal_groups']) for v in views))
    return dict(estimate_input=pose, sigma_input=state['sigma_m_m_rad'],
        baseline=score(baseline), candidate={**score(candidate), 'planning': candidate['rank_aware']},
        saved_first_view_partial=dict(full_fix_accepted=receipt['accepted'],
            shift=(partial[0]-prior).tolist(), sigma=np.sqrt(np.diag(partial[1])).tolist(), receipt=partial[2]),
        truth_usage='scoring AFTER planning only; pinhole geometry, no new pixels or detection claims')


def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, default=OUT/'carry6-replay.json')
    args = p.parse_args()
    constant = calibration()
    (OUT/'carry6-trim-calibration.json').write_text(json.dumps(constant, indent=2)+'\n')
    inputs = [raw/name for raw in (CAL, VALID) for name in ('teacher-commands.jsonl.zst', 'eval-only.jsonl.zst', 'result.json')]
    inputs += [VALID/'carry-static-map.json']
    report = dict(schema='ugrp.carry6_offline.v1', research_result=False, physical_runs=0,
        calibration=constant, calibration_score=score_yaw(CAL, constant),
        validation_score=score_yaw(VALID, constant), C1=geometry(),
        inputs=[dict(path=str(f), sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in inputs])
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('calibration_score','validation_score','C1')}, indent=2))

if __name__ == '__main__':
    main()
