"""Crate18 pre-grasp command calibration + unmodified release20 pulse policy.

Offline eval-only fit: experiments/2026-10-15-crate18/calibration.json.
Runtime receives current visible errors and own commands only. Held calibration
is unavailable: this module MUST NOT be used during carrying/release.
"""
import math
from harness.grasp_act_contract import command
from sim.settle_pulse import PulseSettler, proportional_pulse
from sim.crate_alignment_v14 import INNER

MODE = 'crate18_v1'
# (issued duration, measured effect median), frozen offline on GCP n4-highcpu-64.
# The runtime treats these as an own-command model; no measured state is read.
KNOTS = (
    ((.025, .001321), (.040, .004561)),
    ((.025, .000824), (.040, .004697)),
    ((.018, .012432), (.028, .024868), (.040, .040170), (.046, .048492)),
)
MIN_DURATION = tuple(k[0][0] for k in KNOTS)
DELTA = tuple(k[0][1] for k in KNOTS)
INNER18 = tuple(max(b, .6*d) for b,d in zip(INNER, DELTA))

def settlers():
    return [PulseSettler(b) for b in INNER]

def duration_for(axis, effect):
    knots = KNOTS[axis]
    for (ta, ea), (tb, eb) in zip(knots, knots[1:]):
        if effect <= eb: break
    value = ta + (effect-ea)*(tb-ta)/(eb-ea)
    # One allocator, millisecond hardware resolution; round up to preserve floor.
    return min(.1, max(MIN_DURATION[axis], math.ceil((value-1e-12)*1000)/1000))

def pulse(hold, axis, error):
    effect = proportional_pulse(error, DELTA[axis], quantize=True)
    if not effect: return command(hold)
    width = duration_for(axis, abs(effect))
    pattern = ((1,1,1,1), (-1,1,1,-1), (-1,1,-1,1))[axis]
    return command({**hold, 'wheels':[math.copysign(.35,effect)*v for v in pattern], 'duration_s':[width]*4})
