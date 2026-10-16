"""E2E-only residual pulse budget; the frozen S3 scheduler stays unchanged.

Duration interpolation is a command-space prediction, not a measured response
of a short pulse. Both robots use S3's shared conservative calibration/clock.
"""
import math

from harness.zone_s3_synchronized_carry import pulse_schedule as legacy_schedule
from harness.zone_s3_integer_carry import TICKS_PER_SECOND, tick

OPTIONS = ('off', 'fractional_duration_v1', 'tick_duration_v1')


def pulse_schedule(ctl, t0, profiles, *, option='off'):
    if option not in OPTIONS:
        raise ValueError('UNKNOWN_E2E_PULSE_BUDGET')
    schedule, duration = legacy_schedule(ctl, t0, profiles)
    if option == 'off':
        return schedule, duration
    row = ctl.claims['segments'][-1]
    count, step, distance = row['pulses'], row['calibrated_step_m'], row['distance_m']
    fraction = min(1., max(0., distance / step - (count - 1)))
    last_duration = duration * fraction
    if option == 'tick_duration_v1':
        last_duration = min(duration, max(1 / TICKS_PER_SECOND,
                            round(last_duration * TICKS_PER_SECOND) / TICKS_PER_SECOND))
    if not 0 < last_duration <= duration:
        raise ValueError('POSITIVE_FINAL_PULSE_REQUIRED')
    # These windows only dispatch ONCE on the 20Hz control clock. The port's
    # actual motor expiration uses last_duration, including its fractional tail.
    start, _, command = schedule[count - 1]
    dispatch_end = start + max(1, math.ceil(last_duration * TICKS_PER_SECOND - 1e-10)) / TICKS_PER_SECOND
    schedule[count - 1] = (start, dispatch_end, command)
    durations = [duration] * (count - 1) + [last_duration]
    ctl.e2e_pulse_durations = {tick(s[0]): d for s, d in zip(schedule[:count], durations)}
    ctl.e2e_pulse_commands = {tick(s[0]): dict(s[2]) for s in schedule[:count]}
    prediction = step * sum(d / duration for d in durations)
    row.update(pulse_budget=option, pulse_durations_s=durations,
               old_nominal_distance_m=count * step, nominal_distance_m=prediction,
               residual_prediction_m=prediction - distance,
               response_model='linear duration interpolation; short-pulse physics unmeasured')
    ctl.log(ctl.rid, 'e2e_residual_pulse', t0, seg=ctl.seg, option=option,
            last_duration_s=last_duration, predicted_distance_m=prediction, runtime_gt=False)
    return schedule, duration


def attach(ep, *, option='off'):
    """Attach AFTER synchronized_carry and BEFORE integer_carry.

    Set the duration consumed by the existing synchronized port wrapper at each
    dispatch. Merely shortening the scheduling window would still issue .65s.
    """
    if option == 'off':
        return ep
    if option not in OPTIONS:
        raise ValueError('UNKNOWN_E2E_PULSE_BUDGET')
    ctl = ep.controller
    if not hasattr(ctl, 's3_synchronized_carry') or hasattr(ctl, 's3_integer_carry'):
        raise ValueError('ATTACH_AFTER_SYNC_BEFORE_INTEGER_CARRY')
    profiles, apply = ep.own.pose.localizer.pulse_profiles, ctl.port.apply

    def build(now):
        result, ctl.s3_carry_pulse_s = pulse_schedule(ctl, now, profiles, option=option)
        return result

    def issue(action, now):
        if ctl.state == 'carry' and action.get('kind') == 'mecanum' and any(
                action.get(k, 0.) for k in ('forward', 'left', 'turn')):
            durations = getattr(ctl, 'e2e_pulse_durations', {})
            if tick(now) not in durations:
                raise ValueError('UNSCHEDULED_E2E_CARRY_PULSE')
            ctl.s3_carry_pulse_s = durations[tick(now)]
        return apply(action, now)

    ctl.door_schedule, ctl.port.apply = build, issue
    ctl.e2e_pulse_budget = option
    return ep


def pulse_authorizer(ep, agreement, context):
    """Port permission from current agreement and the exact generated command."""
    used = set()
    def authorize(action, now):
        ctl = ep.controller
        value = context()
        if value is None: return False
        key = tuple(value)
        n = tick(now)
        identity = (key, n)
        if (len(key) != 4 or key[0] != 'order-5' or key[1] != ctl.v3_plan.get('agreement_route_hash') or
                key[3] != ctl.seg or ctl.state != 'carry' or not agreement.ready or agreement.key != key or identity in used):
            return False
        expected = getattr(ctl, 'e2e_pulse_commands', {}).get(n)
        duration = getattr(ctl, 'e2e_pulse_durations', {}).get(n)
        if expected is None or duration is None or action.get('duration_s') != duration:
            return False
        if any(action.get(k) != expected[k] for k in ('forward', 'left', 'turn')): return False
        used.add(identity)
        return True
    return authorize
