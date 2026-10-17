"""Default-off beamact5 round-2 search/approach controls.

Two independent opt-in modes. Both are recorded as profile values and are
``off`` in every historical bundle, so the pinned 26f84d0f behavior is
unchanged unless a new candidate selects them.

- ``search26_circles``: initial in-place search circles start with the lowest
  pitch instead of the highest. The existing reacquire order already uses the
  down-first order; this mode reuses that same tuple. Basis: wide-start r1
  gate worlds 10/20, where a close start was acquired only in the third
  circle (``SEARCH_V2_PITCHES[2]`` = (500,2500)) after two full up-first
  circles.
- ``search26_static_peer``: a peer that is still inside the existing peer-wait
  goal region and has not moved more than the existing 1 cm displacement for
  the existing 6 SIM s window is treated as a static stance obstruction, so
  the unchanged goal-set can choose an alternative stance instead of waiting
  out the 12 SIM s encounter budget. Basis: wide-start r1 gate world 6, where
  parked r3 overlapped r1's nominal stance (min_gap_m -0.056406) and every
  12 s retry re-entered the same wait.

No new distance, angle, time or clearance threshold is introduced here.
"""
MODES = {'search26_circles': 'search26_downfirst_circles_v1',
         'search26_static_peer': 'search26_static_peer_stance_v1'}


def enabled(t, key):
    return getattr(t, 'search15_modes', {}).get(key, 'off') != 'off'
