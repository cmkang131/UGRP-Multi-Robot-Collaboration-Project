"""Own-input pair admission receipt. Private audit data, never STATUS/actor input."""
from dataclasses import asdict

from harness.zone_own_contract import finite_number, pose_report_fresh


def readiness_snapshot(ex, now, item_ref=None, target_zone=None):
    """Use the original admission ordering/thresholds; expose the predicates for audit.

    Values retain full precision. Non-finite numbers are null with a separate
    failed predicate so the receipt can be written with allow_nan=False.
    Tag age is explanatory only; it is NOT an additional admission threshold.
    """
    number = lambda v: float(v) if finite_number(v) else None
    rep, obs, gate = ex.last_report, ex.last_obs, ex.gate
    p = gate.profile
    report_age = now - rep.t_est if rep is not None else None
    obs_time = obs.get('sim_time') if obs is not None else None
    obs_age = now - obs_time if finite_number(obs_time) else None
    checks = {'not_stopped': ex.stopped is None, 'idle': ex.job is None}
    out = {'schema': 'ugrp.zone_pair_admission.v1', 'source': 'own_inputs_only',
           'sim_s': number(now), 'robot_id': ex.robot_id, 'checks': checks,
           'gate': {**gate.as_dict(), 'thresholds': asdict(p),
                    'candidate_since_sim_s': number(gate._candidate_since),
                    'last_update_sim_s': number(gate._last_t)},
           'report': None if rep is None else {
               'initialized': bool(rep.initialized), 't_est': number(rep.t_est),
               'age_s': number(report_age), 'std_xy_m': number(rep.std_xy_m),
               'std_yaw_rad': number(rep.std_yaw_rad), 'since_tag_s': number(rep.since_tag_s),
               'source': rep.source,
               'classification': gate.classify(rep.initialized, rep.std_xy_m, rep.std_yaw_rad)},
           'observation': None if obs is None else {
               'sim_time': number(obs_time), 'age_s': number(obs_age),
               'frame_id': obs.get('frame_id'), 'sha256': obs.get('sha256'), 'camera': obs.get('camera')},
           'servo_ids': sorted(ex.servo), 'missing_servo_ids': sorted({1, 3, 4, 5, 6} - set(ex.servo))}

    def finish(state):
        out.update(state=state, failed_checks=[key for key, passed in checks.items() if not passed])
        return out

    if not checks['not_stopped']:
        return finish('stopped')
    if not checks['idle']:
        return finish('busy')
    if item_ref is not None:
        order = ex.orders.get(item_ref) if isinstance(item_ref, str) else None
        checks['order_compatible'] = bool(order is not None and order.get('kind') == 'long_beam'
            and order.get('count') == 1 and order.get('required_robots') == 2
            and order.get('destination_zone') == target_zone)
        if not checks['order_compatible']:
            return finish('incompatible')
    checks.update(mode_m1=ex.mode == 'm1', gate_ok=gate.ok, report_present=rep is not None,
                  report_initialized=rep is not None and bool(rep.initialized),
                  report_fresh=pose_report_fresh(rep, now),
                  std_xy_finite=rep is not None and finite_number(rep.std_xy_m),
                  std_yaw_finite=rep is not None and finite_number(rep.std_yaw_rad),
                  observation_present=obs is not None,
                  observation_fresh=obs_age is not None and 0 <= obs_age <= .3,
                  servo_complete=not out['missing_servo_ids'])
    if not all(checks.values()):
        return finish('uncertain')
    from harness.zone_pair_vision import valid_frame
    checks['image_valid'] = valid_frame(obs, ex.robot_id, now)
    if not checks['image_valid']:
        return finish('invalid_image')
    out['holding_answer'] = ex.holding()['answer']
    checks['empty_handed'] = out['holding_answer'] == 'no'
    return finish('available' if checks['empty_handed'] else 'occupied')
