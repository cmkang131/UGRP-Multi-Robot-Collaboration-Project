"""Pure, offline D1 sampling. Execution never discovers deletion candidates."""
import math
import re
import statistics


def select_samples(items):
    """Return (kept paths, description, measured median SIM interval).

    The caller separates episodes, legs and camera streams, and unions these
    samples with all protected model/reference frames. items = (path, name, t).
    Unknown timing uses at most 10% (round down), except mandatory endpoints
    require two frames in streams shorter than 20. No wall-time inference.
    """
    if not items:
        return set(), 'empty stream', None
    items = sorted(items, key=lambda row: [int(x) if x.isdigit() else x
                                          for x in re.split(r'(\d+)', row[1])])
    timed = all(isinstance(x[2], (int, float)) and math.isfinite(x[2]) for x in items)
    chosen = {items[0][0], items[-1][0]}
    cadence = None
    if timed:
        items.sort(key=lambda x: (x[2], x[1]))
        last = -math.inf
        for path, name, t in items:
            if t - last >= 1. - 1e-7:
                chosen.add(path)
                last = t
        chosen.update([items[0][0], items[-1][0]])
        deltas = [b[2] - a[2] for a, b in zip(items, items[1:]) if b[2] - a[2] > 1e-8]
        cadence = statistics.median(deltas) if deltas else None
        rule = 'first + >=1 SIM second since last sample + last per stream/episode/leg'
    else:
        budget = max(2, math.floor(len(items) * .1))
        step = max(10, math.ceil((len(items) - 1) / max(1, budget - 1)))
        chosen.update(items[j][0] for j in range(0, len(items), step))
        rule = (f'unknown SIM timing: every {step}th numeric-sorted frame + first/last '
                '(mandatory endpoints may exceed 10% for n<20)')
    return chosen, rule, cadence


def bracket_indices(times, boundary):
    """Indices immediately before/at-or-after a logged SIM boundary."""
    import bisect
    if not times:
        return set()
    i = bisect.bisect_left(times, boundary)
    return {max(0, min(len(times) - 1, i - 1)), min(len(times) - 1, i)}
