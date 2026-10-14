"""Bounded next-best-view after the legacy release panorama is exhausted.

Static map, own RGB hypotheses and issued commands only. The Gaussian
entropy reduction is 0.5 log det(I + P J), averaged over the retained own
hypotheses (uniform, since consensus scores are not posterior probabilities).
See release6.md for Fox 1998 and Zhang/Scaramuzza 2019 and the approximation.
This planner never changes localization acceptance or authorizes a release.
"""
from __future__ import annotations

import math
import numpy as np

from sim.active_lookaround import OwnPose, gain, information, wrap, MOTION_COST_PER_RAD, MIN_GAIN
from sim.lookaround_localization import (LOOK_ARM, LOOK_ARM_V2, look_servo,
                                         visible_fn_for, rotate_plan, pan_pulse)

MODES = ('off', 'map_nbv_v1')
MAX_ROUNDS = 3
VIEW_BUDGET = 3
BACKSTEP_M = .10
YAW_DEG = (0., -45., 45., -90., 90., 180.)
PANS_DEG = tuple(range(-90, 91, 15))


def view_key(command_pose, arm, pan):
    """Command-frame view identity, including arm elevation, not map truth."""
    x, y, a = command_pose
    return (round(x/.01), round(y/.01), round(wrap(a)/math.radians(5)),
            tuple(sorted(arm.items())), pan_pulse(pan))


def plan(localizer, *, used=()):
    decision = localizer.decision or {}
    # Keep ALL exposed alternatives, even when the best consensus is accepted
    # but cannot produce a release-axis margin. Never use a partner's fix.
    hypotheses = decision.get('alternatives') or decision.get('credible_hypotheses', [])
    poses = np.asarray([h['pose'] for h in hypotheses], float).reshape(-1, 3)
    if not len(poses) or not np.isfinite(poses).all():
        return None
    command = np.asarray(localizer.command_own.x, float)
    visited = {(k[0], k[1], k[2], tuple(tuple(p) for p in k[3]), k[4]) for k in used}
    for v in localizer.views:
        servo = v.get('servo')
        if servo and 'command_pose' in v:
            servo = {int(k): value for k, value in servo.items()}
            arm = {k: servo[k] for k in (3, 4, 5)}
            visited.add(view_key(v['command_pose'], arm, (servo[6]-1500)*.09))
    # Two extremal visible samples per physical line, not hundreds of
    # correlated wall points; doors are excluded (not used by this matcher).
    landmarks = [l for l in localizer.landmarks if l['type'] in ('wall', 'zone_edge')]
    sigma = np.asarray(decision.get('sigma', [.05, .05, math.radians(3)]), float)
    P = np.diag(sigma**2)
    visibility = {name: visible_fn_for(localizer.static, localizer.camera, arm, wall_range=2.5)
                  for name, arm in (('surroundings', LOOK_ARM_V2), ('floor', LOOK_ARM))}
    best = None
    for back in (0., BACKSTEP_M):
        moved = poses.copy()
        moved[:, :2] -= back*np.c_[np.cos(poses[:, 2]), np.sin(poses[:, 2])]
        cmd = command.copy()
        cmd[:2] -= back*np.array([math.cos(command[2]), math.sin(command[2])])
        for yaw in YAW_DEG:
            # Static swept clearance over every alternative with the existing
            # 18 cm radius + 15 cm halo. Unknown/unsafe motion is not issued;
            # stationary camera views remain available.
            motion = bool(back or yaw)
            safe = all(localizer.global_matcher.free(
                poses + np.c_[-d*np.cos(poses[:, 2]), -d*np.sin(poses[:, 2]), np.zeros(len(poses))],
                extra_clearance=.15).all() for d in np.linspace(0., back, 6))
            if motion and not safe:
                continue
            target = moved.copy(); target[:, 2] += math.radians(yaw)
            target_command = cmd.copy(); target_command[2] += math.radians(yaw)
            predicted_covariances = []
            for pose in poses:
                predicted = OwnPose(pose); predicted.P = P.copy()
                predicted.propagate(-back, 0., math.radians(yaw))
                predicted_covariances.append(predicted.P)
            # Fox's utility includes the uncertainty introduced by motion,
            # rather than assuming the issued translation/turn was exact.
            motion_entropy = float(np.mean([.5*(np.linalg.slogdet(Q)[1]-np.linalg.slogdet(P)[1])
                                             for Q in predicted_covariances]))
            candidates = []
            for name, arm in (('surroundings', LOOK_ARM_V2), ('floor', LOOK_ARM)):
                for pan in PANS_DEG:
                    key = view_key(target_command, arm, pan)
                    if key in visited:
                        continue
                    Js = []; groups = []; ranks = []
                    for pose in target:
                        seen = {}
                        for lm in landmarks:
                            if visibility[name](pose, 0., pan, lm):
                                seen.setdefault(lm['group'], []).append(lm)
                        points = []
                        for samples in seen.values():
                            if len(samples) >= 2 and math.dist(samples[0]['xy'], samples[-1]['xy']) >= .12:
                                points.extend((samples[0], samples[-1]))
                        Js.append(information(pose, points))
                        groups.append(sorted({l['group'] for l in points}))
                        normals = [l['normal'] for l in points]
                        ranks.append(int(np.linalg.matrix_rank(normals)) if normals else 0)
                    candidates.append(dict(arm=name, pan_deg=pan, key=key, Js=Js,
                                           groups=groups, normal_ranks=ranks))
            chosen = []; total = [np.zeros((3, 3)) for _ in poses]; last = 0.
            pan_cost = 0.
            for _ in range(VIEW_BUDGET):
                scored = []
                for i, candidate in enumerate(candidates):
                    if i in chosen:
                        continue
                    delta = float(np.mean([.5*(gain(Q, J+K)-gain(Q, J))
                                           for Q, J, K in zip(predicted_covariances, total, candidate['Js'])]))
                    cost = MOTION_COST_PER_RAD*math.radians(abs(candidate['pan_deg']-last))
                    scored.append((delta-cost, delta, -i, cost))
                if not scored:
                    break
                score, delta, neg_i, cost = max(scored)
                if delta < MIN_GAIN:
                    break
                i = -neg_i; chosen.append(i); last = candidates[i]['pan_deg']; pan_cost += cost
                total = [J+K for J, K in zip(total, candidates[i]['Js'])]
            measurement_gain = float(np.mean([.5*gain(Q, J) for Q, J in zip(predicted_covariances, total)]))
            expected = measurement_gain-motion_entropy
            utility = expected-pan_cost-MOTION_COST_PER_RAD*2*abs(math.radians(yaw))-.5*back
            if chosen and expected >= MIN_GAIN and (best is None or utility > best['utility_nats']+1e-12):
                best = dict(backstep_m=back, body_yaw_deg=yaw, expected_gain_nats=expected,
                            measurement_gain_nats=measurement_gain, motion_entropy_nats=motion_entropy,
                            utility_nats=utility, hypothesis_count=len(poses),
                            hypothesis_weighting='uniform_over_exposed_own_alternatives',
                            all_retained_hypotheses_clear=bool(safe),
                            views=[{k: v for k, v in candidates[i].items() if k != 'Js'} for i in chosen])
    return best


def script(localizer, teacher, now, *, used=()):
    if teacher.holding:
        return [], dict(action='nbv_unavailable', reason='cargo_not_set_down', t=now)
    selected = plan(localizer, used=used)
    if selected is None:
        return [], dict(action='nbv_unavailable', reason='no_new_informative_safe_view', t=now)
    restore = {k: teacher.pwm[k] for k in (3, 4, 5, 6)}
    steps = [dict(servo=look_servo(0., LOOK_ARM_V2), wait=1., capture=False, label='nbv_fold')]
    if selected['backstep_m']:
        steps.append(dict(wheels=teacher.shift_plan(selected['backstep_m'], -1.),
                          wait=.3, capture=False, label='nbv_backstep'))
    yaw = math.radians(selected['body_yaw_deg'])
    if yaw:
        steps.append(dict(wheels=rotate_plan(yaw), wait=.3, capture=False, label='nbv_turn'))
    last_pan = 0.
    for v in selected['views']:
        arm = LOOK_ARM_V2 if v['arm'] == 'surroundings' else LOOK_ARM
        # 2000 PWM/s pan slew plus .3 s settle, and >=1 s for arm elevation.
        dwell = max(1., abs(v['pan_deg']-last_pan)/180.+.3)
        steps.append(dict(servo=look_servo(v['pan_deg'], arm), wait=dwell, capture=True,
                          label=f"nbv_{v['arm']}_{v['pan_deg']:+.0f}"))
        last_pan = v['pan_deg']
    if yaw:
        steps.append(dict(wheels=rotate_plan(-yaw), wait=.3, capture=False, label='nbv_turn_return'))
    steps.append(dict(servo=restore, wait=1., capture=False, label='restore_arm'))
    return steps, dict(action='map_nbv', t=now, **selected)
