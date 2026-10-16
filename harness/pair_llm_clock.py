"""Integer nanoseconds at the pair hook boundary; public timestamps remain SIM seconds.

#363 owns its clock and raw records. Its legacy event stamp has 4 decimal places,
while its deadlines have 6. Decode that quantization once, without extending a
deadline or changing a controller. All subsequent interval/origin arithmetic is
integer arithmetic, also for host clock v2's round(k * .05, 9) seconds.
"""
import math

from harness.zone_study_contract import ContractViolation

UNITS = 1_000_000_000
WINDOW = 10 * UNITS
# Half a 4dp event unit plus half a 6dp deadline unit (not a runtime deadline grace).
LEGACY_QUANTIZATION = 50_500


def ticks(seconds):
    if type(seconds) not in (int, float) or not math.isfinite(seconds):
        raise ContractViolation('decision window needs finite controller-clock timestamps')
    return round(seconds * UNITS)


def seconds(value):
    return round(value / UNITS, 9)


def relative(value, origin):
    return seconds(ticks(value) - ticks(origin))


def hook_times(row):
    """Project legacy hook timestamps onto one precision; retain raw rows separately.

    A nominal full window's start can be rounded below end-10. Move only that
    start forward inside its known quantization cell. Never move end/cutoff,
    accept a genuinely longer interval, or turn a 9.9 s stop into a 10 s stop.
    """
    start = ticks(row['sim_s'])
    result = {k: seconds(ticks(row[k])) for k in
              ('decide_at_s', 'latch_until_s', 'window_until_s') if k in row}
    end = result.get('decide_at_s', result.get('window_until_s'))
    if end is not None:
        earliest = ticks(end) - WINDOW
        # Only the old 4dp serialization qualifies for this compatibility decode.
        if (start == ticks(round(row['sim_s'], 4)) and
                0 < earliest - start <= LEGACY_QUANTIZATION):
            start = earliest
    return seconds(start), result
