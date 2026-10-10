"""First boundary of the bottom-connected column, without a new appearance model.

Ulrich & Nourbakhsh (AAAI 2000), section 3: only the lowest obstacle pixels
are ground contacts. Here the existing strip discontinuities define connectivity;
they do NOT establish that a connected region is semantically floor.
"""
import numpy as np

OPTION = 'bottom_up_connected_v1'


def candidate_mask(run_top, rows, valid, self_top):
    """Keep only the first contiguous edge-response band reached from below.

``run_top`` is the existing surface_run_top output, ``valid`` is remap
support for the same column strips. No bridging masked gaps or lower edges
that fail the subsequent wall classifier. Adjacent edge-response rows come
from the existing smoothing window and are one boundary, not new tolerance.
"""
    height, columns = run_top.shape
    keep = np.zeros(rows.shape, bool)
    breaks = np.r_[np.zeros((1, columns), bool), np.diff(run_top, axis=0) != 0]
    for j in range(columns):
        support = np.flatnonzero(valid[:height - 1, j])
        if not len(support):
            continue
        bottom = int(support[-1])
        # A self occluder at the bottom cannot be treated as a floor seed.
        if bottom >= self_top[j]:
            continue
        v = bottom
        while v > 0 and valid[v, j] and not breaks[v, j]:
            v -= 1
        if v == 0 or not valid[v, j]:
            continue
        high = low = v
        while high > 0 and valid[high - 1, j] and breaks[high - 1, j]:
            high -= 1
        keep[:, j] = (rows[:, j] >= high) & (rows[:, j] <= low)
    return keep
