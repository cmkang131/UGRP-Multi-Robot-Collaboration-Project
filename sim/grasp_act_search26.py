"""Default-off observed replanning and shared quantized alignment.

Only current own visible measurements and issued commands enter this module.
See search26.md for baseline distributions, provenance and Nav2 references.
"""
import json
import math

from sim.settle_pulse import PulseSettler, proportional_pulse

MODES = {'search26_alignment': 'search26_pulse_v1',
         'search26_observation': 'search26_observed_v1'}


def enabled(t, key):
    return t.search15_modes.get(key, 'off') != 'off'


def observed_band(nav):
    """Existing sensor admission, not a lowered 5/15 prediction threshold.

    A new observation replans the next command; future view predictions must
    not overrule a currently admitted band. Body/arm sweeps remain mandatory.
    Missing or stale observations use the legacy prediction unchanged.
    """
    if not hasattr(nav, 'teacher') or not enabled(nav.teacher, 'search26_observation'):
        return None
    vis = nav.world['visibility'][nav.rid]
    m = vis.get('observations', {}).get('band_'+nav.end)
    if (nav.world.get('beam') is not None and m is not None
            and m['seen_t'] >= nav.world['t']-1e-8 and vis.get('visible_probes', 0) >= 5):
        return vis['visible_probes']
    return None


def connector_cache(t, world):
    """Reuse successes AND failures only within the identical input snapshot.

    No coordinate rounding or age tolerance: new sensor/command geometry or
    observation freshness invalidates all entries. Cache lifetime is one
    snapshot, bounded by the existing logical check budget (98304).
    """
    if not enabled(t, 'search26_observation'):
        return {}
    key = json.dumps(world, sort_keys=True, separators=(',', ':'))
    if getattr(t, 'search26_cache_key', None) != key:
        t.search26_cache_key = key
        t.search26_connector_cache = {}
    return t.search26_connector_cache


def pulse(t, now, axis, correction):
    """Use the SAME speed35/40ms floor already present in this teacher.

    PulseSettler/proportional_pulse are copied unchanged from release20
    097e53da. Delta is command-model displacement, not a measured response or
    a new hardware specification. Quantization occurs in the wheel allocator.
    """
    drive = [0., 0., 0.]
    drive[axis] = correction
    return t._continuous(now, *drive, restore_ik=True)


def alignment(t, world, now):
    from harness.grasp_act_visible_world import command_delta
    from sim.grasp_act_teacher import local, wrap, grasp_poses
    from sim.grasp_act_search19 import admitted
    pose, point, heading, goal = t._geometry(world)
    gx, gy = local(pose, point)
    ex, ey = local(pose, goal)
    errors = (ex, ey, wrap(heading-pose[2]))
    # Preserve existing inner bands; readiness still calls unmodified IK,
    # jaw/arm checks and XY_TOL_M / YAW_TOL_RAD (60mrad).
    inner = (.002, .012, .02)
    if t.search26_settlers is None:
        t.search26_settlers = [PulseSettler(v) for v in inner]
    t.search26_errors = errors
    merit = max(abs(e)/b for e, b in zip(errors, inner))
    if t.align_best is None or merit < t.align_best-.25:
        t.align_best = merit
        t.align_progress_t = now
    elif now-t.align_progress_t >= 3.:
        return t._begin_relook(now, 'no_visible_error_progress_3s')[0]
    try:
        grasp_poses((gx, gy, point[2]))
        reachable = True
    except ValueError:
        reachable = False
    old_merit = math.dist(pose[:2], goal)**2 + (.1*errors[2])**2
    before = dict(t.sink.pwm)
    candidates = []
    for axis in (2, 1, 0):
        minimum = pulse(t, now, axis, 1e-9)
        quantum = abs(command_delta(minimum, .1, mode=t.search15_modes['search17_odometry'])[axis])
        state = t.search26_settlers[axis].observe(errors[axis], quantum)
        # A settled axis may clear a blocked yaw pulse. Evaluate its minimum
        # motion against the same geometric merit; do not silently disable it.
        error = gx-t.staging_distance if axis == 0 and not reachable else errors[axis]
        amount = proportional_pulse(error, quantum, quantize=False)
        factor = (3., 3., .65)[axis]
        # Convert model displacement back to the allocator's body effort.
        unit = abs(command_delta(pulse(t, now, axis, 1./factor), .1,
                                 mode=t.search15_modes['search17_odometry'])[axis])
        candidate = pulse(t, now, axis, amount*.35/(unit*factor))
        checks = []
        safe = admitted(t, world, candidate, before, audit=checks)
        merits = []
        for mode in ('off', t.search15_modes['search17_odometry']):
            dx, dy, da = command_delta(candidate, .1, mode=mode)
            c, s = math.cos(pose[2]), math.sin(pose[2])
            xy = (pose[0]+c*dx-s*dy, pose[1]+s*dx+c*dy)
            merits.append(math.dist(xy, goal)**2 + (.1*wrap(errors[2]-da))**2)
        improves = max(merits) < old_merit
        restore = axis == 0 and not reachable
        accepted = safe and any(candidate['wheels']) and (improves or restore)
        geometric=[d for c in checks for d in c.get('blockers',[]) if d.get('gap_m') is not None]
        nearest=min(geometric,key=lambda d:d['gap_m']) if geometric else None
        t.search20_log.append({'t': now, 'event': 'alignment_pulse_check', 'axis': axis,
            'reason': 'admitted' if accepted else 'safety_reject' if not safe else 'no_merit_progress',
            'category': 'alignment', 'blocked_object': nearest['id'] if nearest else 'none:alignment_merit',
            'min_gap_m': nearest['gap_m'] if nearest else None,
            'gap_scope': nearest.get('gap_scope','sampled body sweep') if nearest else 'no geometric blocker; alignment merit',
            'errors': errors, 'settler': state, 'checks': checks,
            'merit_before': old_merit, 'merit_after': merits})
        if accepted:
            candidates.append((state['settled'] and not restore, max(merits), candidate))
    # Settled axes are clearance alternatives only while a required axis is
    # blocked; never keep pulsing an already settled quantized error.
    required=not reachable or any(z.band is None for z in t.search26_settlers) or abs(errors[2]) > .06
    if candidates and required:
        return min(candidates, key=lambda c: c[:2])[2]
    return t._hold(now)


def remember_issued(t, value):
    """Reversal counts require an actual command after every safety filter."""
    if not enabled(t, 'search26_alignment') or t.phase != 'align' or t.search26_errors is None:
        return
    from harness.grasp_act_visible_world import command_delta
    delta = command_delta(value, .1, mode=t.search15_modes['search17_odometry'])
    for i, d in enumerate(delta):
        if d:
            t.search26_settlers[i].issued(t.search26_errors[i])


def record_rejection(t, now, check, reason, audit):
    if not enabled(t,'search26_alignment'):
        return
    rows=[d for a in audit for d in a.get('blockers',[a]) if d.get('gap_m') is not None]
    nearest=min(rows,key=lambda d:d['gap_m']) if rows else None
    t.search20_log.append({'t':now,'event':'final_command_reject','check':check,
        'reason':reason,'category':'command_safety',
        'blocked_object':nearest['id'] if nearest else 'none:'+reason,
        'min_gap_m':nearest['gap_m'] if nearest else None,
        'gap_scope':nearest.get('gap_scope','sampled command clearance') if nearest else 'no geometric blocker; '+reason,
        'checks':audit})
