"""pairact P1 cand-2b: align-phase bounded obstacle refresh keyed on the PULSE path.

Basis:
* beamact5 r13diag world 27 FAIL: from SIM 17.6 s 91 x ``alignment_axes_blocked``;
  the segment/pulse safety check replaced every align pulse with hold because the
  remembered red_1 cargo margin was stale.
* r14 (``search26_align_refresh_v1``, teacher f1cf1926) passed 2/3 standalone; the
  failing repeat logged 0 x ``align_refresh_begin``.  r14 asks
  ``remembered_blockers`` about ``goal_set_log[-1]['candidates']``, i.e. only the
  ``blocked_goal`` STANCE GOALS.  In align the selected stance is feasible, so the
  stale obstacle that rejects the pulse is near the current pose / pulse path, not
  near any rejected goal, and the blocker set can be empty.  (Alternative cause:
  the obstacle encounter budget was already spent before align; this module logs
  which of the two happened.  Which one fired in r14 rep3 is [확인 필요].)

This mode keeps the r14 trigger (align phase, no active reobserve, the issued
command has zero wheels) but additionally requires that the PROPOSED command had
non-zero wheels (a rejected pulse, not an intentional hold).  The predicate is the
unchanged ``remembered_blockers``; only its input changes: instead of rejected
stance goals it receives the current pose and the proposed pulse path sampled at
the existing 2 mm resolution, for both issued odometry models.  The refresh is the
existing bounded ``ActiveReobserve.begin('obstacle', ...)`` (VIEW_S, RETREAT_S,
LIMIT_S, MAX_ENCOUNTERS unchanged).  No new distance, margin, time or count
constant.  Default off.
"""
import math

MODE_KEY = 'search26_align_refresh2'
MODE = 'search26_align_refresh_v2'
STEP_M = .002   # existing pulse sweep resolution (grasp_act_align_guard / search19)


def enabled(teacher):
    return teacher.search15_modes.get(MODE_KEY, 'off') != 'off'


def _moving(value):
    return any(value.get('wheels') or [0., 0., 0., 0.])


def pulse_points(pose, value, *, modes=('off',), dt=.1):
    """Pure: current xy plus the issued pulse path (2 mm samples) for each odometry model."""
    from harness.grasp_act_visible_world import command_delta
    points = [tuple(pose[:2])]
    c, s = math.cos(pose[2]), math.sin(pose[2])
    for mode in dict.fromkeys(modes):
        dx, dy, _ = command_delta(value, dt, mode=mode)
        end = (pose[0]+c*dx-s*dy, pose[1]+s*dx+c*dy)
        n = max(1, math.ceil(math.dist(pose[:2], end)/STEP_M))
        points += [(pose[0]+(end[0]-pose[0])*i/n, pose[1]+(end[1]-pose[1])*i/n) for i in range(1, n+1)]
    return points


def pulse_blockers(world, rid, pose, value, folded, *, modes=('off',)):
    """Pure: stale cargo/walls whose padded footprint covers the pose or pulse path.

    Same predicate as ``remembered_blockers`` (stale only, beam_1 excluded, same
    radius/padding); the pulse samples stand in for the rejected goals.
    """
    from sim.grasp_act_reobserve import remembered_blockers
    rows = [{'reason': 'blocked_goal', 'goal': p} for p in pulse_points(pose, value, modes=modes)]
    return remembered_blockers(world, rid, rows, folded)


def maybe_begin(teacher, truth, proposed, value, now):
    """Teacher hook after all pulse checks.  Returns True if a refresh started."""
    if (not enabled(teacher) or teacher.phase != 'align' or teacher.reobserver.active is not None
            or _moving(value) or not _moving(proposed) or truth.get('beam') is None):
        return False
    pose = truth['robots'][teacher.rid]['pose']
    blockers = pulse_blockers(truth, teacher.rid, pose, proposed, teacher.folded_ready,
                              modes=('off', teacher.search15_modes['search17_odometry']))
    if blockers and teacher.reobserver.begin('obstacle', blockers, truth, teacher, now):
        teacher.recovery_log.append({'t': now, 'event': 'align_refresh2_begin', 'blockers': sorted(blockers),
                                     'encounter': teacher.reobserver.used['obstacle']})
        teacher.align_refresh2_skip = None
        return True
    # Diagnostic only: log when the reason a refresh did not start changes.
    reason = 'no_stale_blocker_on_pulse' if not blockers else 'obstacle_encounters_spent'
    if getattr(teacher, 'align_refresh2_skip', None) != reason:
        teacher.align_refresh2_skip = reason
        teacher.search20_log.append({'t': now, 'event': 'align_refresh2_skip', 'reason': reason,
                                     'blockers': sorted(blockers), 'used': teacher.reobserver.used['obstacle']})
    return False
