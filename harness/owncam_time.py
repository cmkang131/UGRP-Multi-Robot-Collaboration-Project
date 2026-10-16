"""Quantized PF report times versus raw own capture/command SIM times."""
import math

POSE_TIME_ROUNDING_S = 1e-4


def finite_time(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def pose_report_fresh(report, now, *, max_age_s=.3):
    # Both ends can round: a report can appear slightly future OR too old.
    return bool(report is not None and finite_time(now) and finite_time(report.t_est)
                and -POSE_TIME_ROUNDING_S <= now - report.t_est <= max_age_s + POSE_TIME_ROUNDING_S)


def report_at_or_after(report, raw_time):
    return bool(report is not None and finite_time(report.t_est) and finite_time(raw_time)
                and raw_time <= report.t_est + POSE_TIME_ROUNDING_S)


def accepted_fix_checks(report, now, start, *, strict_start=True):
    """Never reconstruct capture time by subtracting separately rounded age.

    The localizer's accepted-observation timestamp and start are raw times: keep that
    boundary exact, so even a fix just before the sweep cannot qualify.
    Only comparisons against the quantized report get rounding tolerance.
    """
    last_fix_t = None if report is None else report.last_fix_t
    fix_ok = finite_time(last_fix_t)
    start_ok = finite_time(start)
    return {
        'report_fresh': pose_report_fresh(report, now),
        'fix_age_valid': report is not None and finite_time(report.fix_age_s) and report.fix_age_s >= 0,
        'accepted_fix_present': fix_ok,
        'fix_in_sweep': fix_ok and start_ok and (last_fix_t > start if strict_start else last_fix_t >= start),
        'fix_not_future': fix_ok and finite_time(now) and last_fix_t <= now,
        'fix_in_report': fix_ok and report_at_or_after(report, last_fix_t),
    }
