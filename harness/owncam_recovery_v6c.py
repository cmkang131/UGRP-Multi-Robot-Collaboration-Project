"""v6c: the posterior-preserving PF with one clock for predictions and fixes.

Root cause (2026-09-28 stage probes, PR #260, Run A: 116 of 125 rejected v6
relook fixes failed only ``fix_age_valid``). Two SIM-time representations met:

* the fix time is the raw capture time of the own frame (``t`` passed to
  ``update``), itself an accumulated host time such as 1.5002500000000847;
* the PF clock ``self.t`` is a separate accumulator: ``predict_to`` adds
  ``min(STEP_S, t - self.t)`` per step and stops as soon as
  ``self.t >= t - 1e-9``. The float sum of steps lands up to 1e-9 s BEFORE
  ``t`` (observed -6.7e-14 ... -2.5e-13 s) and the loop ends without the last
  sub-nanosecond step.

``RecoveryLocalizer.estimate`` reports ``fix_age_s = self.t - last_fix_t``
unrounded, so a fix made at this very frame had a negative age and
``owncam_time.accepted_fix_checks`` (and ``relook_reason``) refused it. v5h
hid the same mismatch with ``round(age, 3)``.

The fix is in the clock, not in the age: after ``predict_to(t)`` the filter
state is stamped with the requested time, as a Bayes filter's state carries
the stamp of the measurement it was predicted to (robot_localization
``FilterBase::processMeasurement``: ``predict(measurement.time_, delta)`` then
``lastMeasurementTime_ = measurement.time_``). The skipped interval is below
the loop's own 1e-9 s tolerance, so no motion is dropped. A frame older than
the PF clock is never moved forward and keeps a positive age.
"""
from __future__ import annotations

from harness.owncam_recovery_v6 import RecoveryLocalizer, enable_provider as enable_v6

CLOCK_TOLERANCE_S = 1e-9   # the unchanged OwnCamLocalizer.predict_to stop tolerance


class ExactClockRecoveryLocalizer(RecoveryLocalizer):
    def predict_to(self, t):
        super().predict_to(t)
        if t - CLOCK_TOLERANCE_S <= self.t < t:
            self.t = t      # same instant within the loop tolerance: one clock, no age < 0


def enable_provider(provider):
    """v6 enable (posterior kept, same object identity) plus the exact clock."""
    enable_v6(provider)
    inner = provider
    while hasattr(inner, 'provider'):
        inner = inner.provider
    loc = getattr(inner, 'loc', None)
    if not isinstance(loc, RecoveryLocalizer):
        return  # a markerless provider owns its fix clock (v6 contract checked above)
    if not isinstance(loc, ExactClockRecoveryLocalizer):
        loc.__class__ = ExactClockRecoveryLocalizer  # same object: frozen drivers share this PF
    inner.exact_fix_clock_v6c = True   # the ':recovery_v6' source label stays the v6 contract's


def exact_clock_bound(provider):
    """True when this provider's PF was switched to the v6c clock (same object, reused)."""
    inner = provider
    while hasattr(inner, 'provider'):
        inner = inner.provider
    return isinstance(getattr(inner, 'loc', None), ExactClockRecoveryLocalizer)
