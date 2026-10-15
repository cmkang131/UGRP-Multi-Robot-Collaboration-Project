"""Fixed saved-proposal replay, with GT opened only by separate scoring code.

No closed-loop, missing-RGB reconstruction, plant, render or network calls.
"""
import argparse
import copy
import json
import math
from pathlib import Path

import cv2
import numpy as np

from harness.natural_floor_slam import compose, wrap
from harness.selfmap4_geometry import inverse, observe
from harness.selfmap6_safety import CorrectionGate, release_due
from harness.own_map_amcl_vendor.landmarks import MapFeatures
from harness.self_map_landmark_sensor import Sensor
from scripts.offline_self_map import rows, read, dump, digest


def replay(trace, frames, rebuilds):
    """Controller-policy calculation: no evaluation arguments or file reads."""
    gate, admissions = CorrectionGate(), []
    for row, frame in zip(trace, frames):
        if row['frame_id'] != frame['frame_id']:
            raise ValueError('TRACE_FRAME_JOIN_REQUIRED')
        if row['pose_source'] not in ('visual_update', 'visual_relocalized'):
            continue
        test = row['revision_innovation']
        prior = np.asarray(row['pose'])-test['innovation']
        prior[2] = wrap(prior[2])
        P = np.asarray(test['predicted_covariance'])
        R = np.asarray(test['innovation_covariance'])-P
        # Saved proposals do not contain matched landmark IDs. Do not invent
        # independence or use post-rejection descendants as a rebuilt map.
        decision = gate.consider(prior, row['pose'], P, R, t=row['t'], frame_id=row['frame_id'],
            source='static' if row['visual_reason'] == 'selfmap4_static_lines' else 'visual',
            view=[*prior[:2], prior[2]], evidence_ids=[])
        admissions.append(dict(frame_id=row['frame_id'], t=row['t'], prior=prior.tolist(), **decision))
    trigger = next(r for r in admissions if r['frame_id'] == 254)
    # Separate forced legacy-quarantine branch. Recorded failed receipts are
    # replayed against the same release policy used by the live mapper.
    failures, release = 0, None
    for row in trace:
        if row['t'] < trigger['t']:
            continue
        failures = sum(not r['committed'] and r['t'] < row['t']-1e-8 for r in rebuilds)
        if release_due(trigger['t'], row['t'], failures):
            release = dict(t=row['t'], elapsed_sim_s=row['t']-trace[0]['t'],
                since_revision_s=row['t']-trigger['t'], failed_attempts=failures,
                reason='last_consistent_state_rollback', complete=False,
                scope='forced legacy quarantine; actual selfmap6 gate rejects initial correction')
            break
    return dict(proposals_N=len(admissions), proposals=admissions, trigger=trigger,
        rejected_N=sum(not r['accepted'] for r in admissions), forced_quarantine_release=release,
        causal_pose_replay=False, full_rgb_bank_replay=False)


def score(trace, truth):
    """Evaluation only; never passes truth or scores back into replay/gate."""
    by_t = {round(r['t'], 6): r for r in truth}
    first = by_t[round(trace[0]['t'], 6)]
    origin = [*first['robot_xyz_m'][:2], first['robot_yaw_rad']]
    output = []
    for row in trace:
        g = by_t[round(row['t'], 6)]
        world = np.array([*g['robot_xyz_m'][:2], g['robot_yaw_rad']])
        local = compose(inverse(origin), world)
        p = np.asarray(row['pose']); sr = row['static_registration']
        pf = np.asarray(sr['world_pose']); raw = np.asarray(sr['raw_covariance'])
        result = dict(frame_id=row['frame_id'], t=row['t'], truth_local=local.tolist(),
            pose_xy_error_m=float(np.linalg.norm(p[:2]-local[:2])),
            pose_yaw_error_deg=math.degrees(wrap(p[2]-local[2])),
            pf_xy_error_m=float(np.linalg.norm(pf[:2]-world[:2])),
            pf_yaw_error_deg=math.degrees(wrap(pf[2]-world[2])),
            pf_raw_sigma_xy_m=float(np.sqrt(np.linalg.eigvalsh(raw[:2, :2]).max())),
            pf_raw_sigma_yaw_deg=math.degrees(math.sqrt(raw[2, 2])))
        if row['frame_id'] == 254:
            prior = p-np.asarray(row['revision_innovation']['innovation'])
            result.update(prior_xy_error_m=float(np.linalg.norm(prior[:2]-local[:2])),
                          prior_yaw_error_deg=math.degrees(wrap(prior[2]-local[2])))
        output.append(result)
    return output


def recovered_lines(raw, images, trace, frames, truth):
    """Saved RGB re-extraction, then independent GT geometric scoring."""
    static = json.loads((raw/'inputs/static_map.json').read_text())
    mapped = MapFeatures(static); sensor = Sensor(mapped.hues)
    gt = {round(g['t'], 6): g for g in truth}
    output = []
    for row, f in zip(trace, frames):
        path = images/f['path']
        if not path.exists():
            continue
        if digest(path) != f['sha256']:
            raise ValueError('RGB_HASH_MISMATCH')
        servo = {int(k): v for k, v in f['commanded_servo'].items()}
        rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        obs = observe(rgb, servo, sensor)
        g = gt[round(row['t'], 6)]; pose = np.array([*g['robot_xyz_m'][:2], g['robot_yaw_rad']])
        c, s = math.cos(pose[2]), math.sin(pose[2]); R = np.array([[c, -s], [s, c]])
        errors = []
        for line in obs['features']:
            if line['kind'] != 'floor_line':
                continue
            ends = np.asarray(line['endpoints'])@R.T+pose[:2]; normal = np.asarray(line['normal'])@R.T
            matches = []
            for edge in mapped.edges:
                hd = abs(edge['hue']-line['hue'])
                if min(hd, 180-hd) > 12:
                    continue
                a, b = edge['a'], edge['b']; v = b-a
                residual = ends-a-np.clip((ends-a)@v/(v@v), 0, 1)[:, None]*v
                matches.append(dict(region=edge['region'], endpoint_max_error_m=float(np.linalg.norm(residual, axis=1).max()),
                    normal_error_deg=math.degrees(abs(wrap(math.atan2(normal[1], normal[0])-
                        math.atan2(edge['normal'][1], edge['normal'][0]))))))
            errors.append(dict(observation=copy.deepcopy(line),
                nearest_same_hue_eval_only=min(matches, key=lambda m:m['endpoint_max_error_m']) if matches else None))
        output.append(dict(frame_id=f['frame_id'], t=row['t'], elapsed_sim_s=row['t']-trace[0]['t'],
            path=str(path), sha256=f['sha256'], features=obs['features'], line_scores_eval_only=errors))
    return output


def analyze(raw, images):
    trace, ts = rows(raw/'trace.jsonl'); frames, fs = rows(raw/'robots/r3/frames.jsonl')
    saved, ms = read(raw/'map.json'); saved = json.loads(saved)
    policy = replay(trace, frames, saved['rebuilds'])
    # The policy result is complete before evaluation files are opened.
    truth, gs = rows(raw/'eval_only/trajectory.jsonl')
    scores = score(trace, truth)
    lines = recovered_lines(raw, images, trace, frames, truth)
    root = Path(__file__).resolve().parents[1]
    return dict(schema='ugrp.selfmap6_offline.v1', base_sha='cfbab2afed755777383c45347062b593175a7cc5',
        sources=[ts, fs, ms, gs], trace_N=len(trace), policy=policy,
        trigger_score_eval_only=next(s for s in scores if s['frame_id'] == 254),
        score_samples_eval_only=[scores[i] for i in [0, 115, 230, 252, 253, 345, 460, 575]],
        recovered_rgb_N=len(lines), trigger_rgb_recovered=any(r['frame_id'] == 254 for r in lines),
        recovered_lines=lines, registered_frames=sum(r['static_registration']['registered'] for r in trace),
        legacy_rebuilds=saved['rebuilds'],
        implementation_sha256={p: digest(root/p) for p in ['harness/selfmap6_safety.py', 'harness/self_map_integration.py',
            'harness/selfmap4_geometry.py', 'scripts/analyze_selfmap6.py']},
        limitations=['fixed saved proposals, not closed-loop map/navigation success',
            'matched IDs and most RGB absent; no independent outlier confirmations inferred',
            'forced legacy quarantine policy replay is separate from initial-correction rejection',
            'frame254 pixel/line correspondence unavailable; PF line features at that frame not saved'],
        physics_calls=0, render_calls=0, model_calls=0, pool_with_previous_results=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True); p.add_argument('--images', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    result = analyze(a.raw, a.images); a.output.parent.mkdir(parents=True, exist_ok=True); dump(a.output, result)
    print(json.dumps(dict(trace_N=result['trace_N'], recovered_rgb_N=result['recovered_rgb_N'],
        trigger=result['policy']['trigger'], score=result['trigger_score_eval_only'],
        release=result['policy']['forced_quarantine_release']), ensure_ascii=False))


if __name__ == '__main__':
    main()
