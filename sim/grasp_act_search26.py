"""Default-off beamact5 search/approach controls.

Independent opt-in modes. All are recorded as profile values and are ``off`` in
every historical bundle, so the pinned 26f84d0f behavior is unchanged unless a
new candidate selects them.

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
- ``search26_peer_memory``: the same still-peer witness survives ticks where the
  peer is only remembered (``world['robots']`` from visible-history memory,
  ``PEER_TTL_S``), instead of being reset by every non-fresh tick; the witness
  is removed only when the remembered peer disappears. Basis: wide-start r2
  validation world 6, where the static-peer goal set engaged at 56.1 SIM s
  (barely before the 60 s cap) because the 6 s window restarted on visibility
  flicker.
- ``search26_reobserve``: a retreat-first obstacle reobserve continues into the
  existing camera/body view attempts after its 0.6 s retreat boundary instead
  of finishing there. Basis: wide-start r2 validation world 27, where the
  retreat-first reobserve ended at ``retreat_bounded_replan`` at exactly the
  boundary and never ran a view attempt.
- ``search26_circles_farfirst``: conditional circle order for the r4 arm:
  far pitch first (the dominant layer band), close pitch second, mid pitch
  third, i.e. ``(SEARCH_V2_PITCHES[2], SEARCH_V2_PITCHES[0],
  SEARCH_V2_PITCHES[1])``.  The r2 down-first order delayed the far pitch by
  two circles and the r3 gate showed 2.47-3.19x longer initial searches in 12
  previously passing worlds (hypothesis, not proven); the pure r1 revert
  (r4-a ablation) instead lost the close-start benefit (world 10 regressed to
  cap_end).  This candidate keeps the far pitch at circle 1 and moves the
  low-pitch close fallback to circle 2.  Separate opt-in; never pooled.
- ``search26_wide_stance``: a NEW teacher candidate (never pooled with the
  other modes' results) whose certified stance map samples jaw-allowed angles
  on a 1-degree grid inside the existing calibrated radial envelope, instead of
  the 5-degree grid whose maximum offset is +/-15 deg. Basis: wide-start r2
  validation world 37, where the best sampled +/-15 deg stance left 4.87 mm,
  below the runtime measurement floor of 11.07 mm, while the geometric jaw
  bound at that target height is 17.88 deg.

No new distance, angle, time or clearance threshold is introduced here; the
new stance candidate uses only the existing calibrated envelope, the existing
jaw predicate, and the existing margins.
"""
MODES = {'search26_circles': 'search26_downfirst_circles_v1',
         'search26_circles_farfirst': 'search26_circles_farfirst_v1',
         'search26_static_peer': 'search26_static_peer_stance_v1',
         'search26_peer_memory': 'search26_peer_memory_v1',
         'search26_reobserve': 'search26_reobserve_views_v1',
         'search26_wide_stance': 'search26_wide_stance_v1'}


def enabled(t, key):
    return getattr(t, 'search15_modes', {}).get(key, 'off') != 'off'
