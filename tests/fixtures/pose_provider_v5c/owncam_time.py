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


def accepted_tag_checks(report, now, last_tag_t, start, *, strict_start=True):
    """Never reconstruct capture time by subtracting separately rounded age.

    The localizer's accepted-tag timestamp and start are raw times: keep that
    boundary exact, so even a tag just before the sweep cannot qualify.
    Only comparisons against the quantized report get rounding tolerance.
    """
    tag_ok = finite_time(last_tag_t)
    start_ok = finite_time(start)
    return {
        'report_fresh': pose_report_fresh(report, now),
        'tag_age_valid': report is not None and finite_time(report.since_tag_s) and report.since_tag_s >= 0,
        'accepted_tag_present': tag_ok,
        'tag_in_sweep': tag_ok and start_ok and (last_tag_t > start if strict_start else last_tag_t >= start),
        'tag_not_future': tag_ok and finite_time(now) and last_tag_t <= now,
        'tag_in_report': tag_ok and report_at_or_after(report, last_tag_t),
    }
