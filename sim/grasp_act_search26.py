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
- ``search26_reobserve_refresh``: allow a bounded extra obstacle reobserve
  (at most two beyond the existing two encounters) only when the previous
  obstacle encounter ended in ``fresh_measurements_replan`` and the same stale
  cargo re-blocks.  Basis: gcp6 case 27 in r1/r2/r3/r4b consumed both obstacle
  encounters by SIM 15.2 s and still re-blocked at ~21-27 s (92/92 stances
  blocked while the remembered cargo is stale), handing off at ~25-30 s.  The
  extra refreshes are the next bounded attempts; default off and no new
  distance/angle/time threshold.
- ``search26_reobserve_refresh_open``: the same conditional refresher chain as
  ``search26_reobserve_refresh`` but with no fixed extra-encounter count: as
  long as the last obstacle encounter ended in ``fresh_measurements_replan``
  (i.e. it produced a fresh measurement) the next re-blocked plan may refresh
  again.  Bounded only by the existing 60 SIM cap and the existing approach
  deadline.  Basis: gcp6 r5b case 27 used all four bounded refreshes between
  SIM 15.8-17.4 s, each fresh window allowing only ~0.1 m of movement before
  the stale-margin blocked the plan again, and handed off at 20.4 s; the
  bounded count, not the refresh mechanism, ended the attempt.
- ``search26_wide_rescue``: when the normal sampled stance family returns no
  selection, retry the selection against the separate 1-degree wide-angle
  certified family (search26_wide_stance's map) as a bounded rescue.  Basis:
  r4c/r5/r6/r7 world 27 has 92/92 stances blocked whenever the remembered
  red_1 cargo is stale (sampled family best gap 46.7 mm vs stale margin up to
  52.1 mm), and r1/r2 world 37's sampled +/-15 deg family best gap is 4.87 mm
  below the runtime floor 11.07 mm; a wider family may contain clearance poses
  in both.  Used only when the normal family fails, so the normal planning
  cost is unchanged.  Default off; separate never-pooled family.
- ``search26_commit_plan``: keep driving a feasible committed approach plan
  until its existing 1 s replan boundary instead of re-planning on every
  blocked tick caused by stale-memory margins.  Basis: gcp6 r5c case 27 spent
  SIM 15-60 s cycling reobserve->feasible selection->blocked on the very next
  tick (92/92 stances blocked whenever the remembered red_1 cargo is stale),
  so the robot never drove; the refresh produced fresh evidence but every
  refresh window lasted one control tick.  The commit window reuses the
  already existing ``next_plan = now + 1 s`` cadence: no new time constant.
  Default off; path/target/geometry failures still replan immediately.
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
         'search26_wide_rescue': 'search26_wide_rescue_v1',
         'search26_commit_plan': 'search26_commit_plan_v1',
         'search26_reobserve_refresh_open': 'search26_reobserve_refresh_open_v1',
         'search26_reobserve_refresh': 'search26_reobserve_refresh_v1',
         'search26_circles_farfirst': 'search26_circles_farfirst_v1',
         'search26_static_peer': 'search26_static_peer_stance_v1',
         'search26_peer_memory': 'search26_peer_memory_v1',
         'search26_reobserve': 'search26_reobserve_views_v1',
         'search26_wide_stance': 'search26_wide_stance_v1'}


def enabled(t, key):
    return getattr(t, 'search15_modes', {}).get(key, 'off') != 'off'
