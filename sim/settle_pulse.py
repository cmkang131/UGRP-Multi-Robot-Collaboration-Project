"""Quantized pulse settling, using observed error and an own-command model only.

Units are chosen by the caller (radians, pixels, or normalized RGB features).
``delta`` is the predicted error change of ONE minimum issued pulse, never a
measured pose. A tolerance below half that quantum permits a two-cycle. The
0.6 margin and three-reversal fallback are engineering choices, not a general
stability theorem for a noisy, coupled plant. See release20.md for sources.
"""
from __future__ import annotations

import math


def proportional_pulse(error, delta, *, gain=.5, maximum=math.inf, quantize=True):
    """Signed correction; quantize once, here OR in a coupled wheel allocator.

    With ``quantize=False`` keep the continuous proportional direction. Raising
    its magnitude before an existing wheel deadband can change which wheels
    survive, so the allocator alone must enforce the minimum in that case.
    """
    if not all(math.isfinite(v) for v in (error, delta, gain)) or delta < 0 or (quantize and delta == 0) or gain <= 0 or maximum < delta:
        raise ValueError('invalid pulse model')
    return math.copysign(min(maximum, max(delta if quantize else 0., gain*abs(error))), error) if error else 0.


class PulseSettler:
    """Deadband with hysteresis and bounded consecutive command reversals.

    Call ``issued`` only when a pulse was actually sent; passive camera samples
    cannot accumulate reversals. A settled decision remains latched inside its
    recorded acceptance band, with a 25% exit margin for image noise. Missing
    features must reset this state in the caller. Large alternating errors do
    not certify alignment: reversal acceptance is limited to two quanta.
    """
    def __init__(self, tolerance, *, reversals=3):
        if not math.isfinite(tolerance) or tolerance < 0 or reversals < 1:
            raise ValueError('invalid settle policy')
        self.tolerance = tolerance
        self.limit = reversals
        self.previous = None
        self.pending = False
        self.reversals = 0
        self.total_reversals = 0
        self.pulses = 0
        self.band = None
        self.reason = None

    def issued(self, error):
        self.previous = error
        self.pending = True
        self.pulses += 1

    def observe(self, error, delta):
        if not math.isfinite(error) or not math.isfinite(delta) or delta < 0:
            raise ValueError('invalid observed error or command quantum')
        tolerance = max(self.tolerance, .6*delta)
        if self.pending:
            flipped = error*self.previous < 0
            self.total_reversals += int(flipped)
            self.reversals = self.reversals+1 if flipped and max(abs(error), abs(self.previous)) <= 2*max(delta, tolerance) else 0
            self.pending = False
        if self.band is not None and abs(error) > 1.25*self.band:
            self.band = self.reason = None
            self.reversals = 0
        if self.band is None:
            if abs(error) <= tolerance:
                self.band, self.reason = tolerance, 'quantum_deadband'
            elif self.reversals >= self.limit:
                self.band, self.reason = max(tolerance, abs(error), abs(self.previous)), 'consecutive_reversals'
        return dict(settled=self.band is not None, reason=self.reason, error=float(error),
                    delta=float(delta), tolerance=float(tolerance), acceptance_band=self.band,
                    consecutive_reversals=self.reversals, total_reversals=self.total_reversals,
                    pulses=self.pulses)
