"""Opt-in route pulse admission and blocked-goal body geometry.

Velocity-space admission follows the DWA principle, but uses issued-command
kinematics, not measured dynamics or a braking-distance safety guarantee.
The body fallback has its own 5mm diagnostic margin. Jaw, visibility and arm
checks remain intact; the legacy path still uses the search18 margins.
"""
import math
from copy import deepcopy

from harness.grasp_act_contract import command
from harness.grasp_act_visible_world import SEARCH17_GAINS, command_delta
from sim.grasp_act_port import duty_wheels
from sim.grasp_act_search17 import pulse_free
from sim.grasp_act_search18 import Navigation, body_clearance

MODES = {'search19_motion': 'search19_motion_v1',
         'search19_footprint': 'search19_footprint_v1'}
BODY_MARGIN_M = .005  # Diagnostic geometric padding, NOT the 65mm odometry p90.


class BodyNavigation(Navigation):
    """Search19 fallback only. Search18's 65mm profile is never changed."""
    def __init__(self, teacher, world):
        super().__init__(world, teacher.rid, teacher.end, teacher.sink.pwm,
                         teacher.bounds, rectangle=True, true_start=True)

    def free(self, p, discs, rects, radius, *, heading=None):
        yaw = self.heading(p) if heading is None else heading
        return body_clearance((*p[:2], yaw), self.discs, self.rects,
                              bounds=self.bounds, need=BODY_MARGIN_M) >= BODY_MARGIN_M

    def pose_segment(self, a, b):
        da = math.atan2(math.sin(b[2]-a[2]), math.cos(b[2]-a[2]))
        n = max(1, math.ceil(math.dist(a[:2], b[:2])/.002), math.ceil(abs(da)/math.radians(.5)))
        # At most 2mm motion of any body point between samples.
        margin = BODY_MARGIN_M+.002
        return all(body_clearance((a[0]+(b[0]-a[0])*i/n, a[1]+(b[1]-a[1])*i/n, a[2]+da*i/n),
                                  self.discs, self.rects, bounds=self.bounds, need=margin) >= margin
                   for i in range(n+1))


def body_pulse_free(teacher, world, value, *, audit=None):
    from sim.grasp_act_search27 import enabled as search27,command_check
    if search27(teacher):
        before=getattr(teacher,'search27_before_pwm',dict(teacher.sink.pwm))
        ok,checks=command_check(teacher,world,value,before,after=dict(teacher.sink.pwm))
        if audit is not None:audit.extend(checks)
        return ok
    from sim.grasp_act_search20 import enabled, BodyNavigation as Search20Navigation
    nav = Search20Navigation(teacher, world) if enabled(teacher) else BodyNavigation(teacher, world)
    from sim.grasp_act_search22 import enabled as search22, BodyNavigation as Search22Navigation
    if search22(teacher):nav=Search22Navigation(teacher,world)
    from sim.grasp_act_search23 import enabled as search23, BodyNavigation as Search23Navigation
    if search23(teacher):nav=Search23Navigation(teacher,world)
    for mode in ('off', teacher.search15_modes['search17_odometry']):
        pose = tuple(nav.pose)
        times = sorted({0., .1, *(max(0., min(.1, d)) for d in value['duration_s'])})
        for t0, t1 in zip(times, times[1:]):
            a, b = (command_delta(value, tt, mode=mode) for tt in (t0, t1))
            dx, dy, da = (y-x for x, y in zip(a, b))
            si = math.sin(da)/da if abs(da)>1e-10 else 1.
            co = (1-math.cos(da))/da if abs(da)>1e-10 else 0.
            x, y = si*dx-co*dy, co*dx+si*dy
            c, s = math.cos(pose[2]), math.sin(pose[2])
            end = (pose[0]+c*x-s*y, pose[1]+s*x+c*y, pose[2]+da)
            if not nav.pose_segment(pose, end):
                if audit is not None:
                    audit.append({'check':'body_pose_segment','mode':mode,'from':pose,'to':end,
                        'reason':'body_sweep_reject','category':'body_sweep',
                        'blockers':list(getattr(nav,'last_blockers',[])),
                        'min_gap_m':getattr(nav,'last_segment_gap',None),
                        'gap_scope':'sampled body sweep',
                        'blocked_object':','.join(d['id'] for d in getattr(nav,'last_blockers',[])) or 'none:body_sweep'})
                return False
            pose = end
    return True


def body_fallback(teacher, world, now):
    from sim.grasp_act_pregrasp import select_sampled_goal
    from sim.grasp_act_goal_set import ANGLES_DEG
    from sim.grasp_act_recovery import AXIAL_CHOICES
    from sim.grasp_act_search17 import expanded_choices
    choices = [(math.radians(a), d) for a in ANGLES_DEG for _, d in AXIAL_CHOICES]
    from sim.grasp_act_search21 import enabled as search21, fallback
    if search21(teacher):return fallback(teacher,world,now,list(dict.fromkeys([*choices,*expanded_choices()])))
    selected, checked = select_sampled_goal(
        world, teacher.rid, teacher.end, teacher.bounds, teacher.folded_ready,
        teacher.sink.pwm, choices=_fallback_choices(teacher, [*choices, *expanded_choices()]),
        navigation=_fallback_navigation(teacher, world))
    from sim.grasp_act_search20 import enabled, ADMIT_MARGIN_M
    teacher.search19_log.append({'t': now, 'event': 'body_fallback', 'margin_m': ADMIT_MARGIN_M if enabled(teacher) else BODY_MARGIN_M,
                                 'tested': len(checked), 'feasible': sum(c['reason']=='feasible' for c in checked)})
    if selected is not None:
        teacher.search19_body_active = True
        teacher.sampled_stance = True
    return selected, checked


def admitted(teacher, world, value, before, *, audit=None):
    radius, discs, rects = teacher._constraints(world)
    pose = world['robots'][teacher.rid]['pose']
    if teacher.search19_body_active:
        clear = body_pulse_free(teacher, world, value, audit=audit)
    else:
        clear = all(pulse_free(pose, value, discs, rects, radius, mode=m)
                    for m in ('off', teacher.search15_modes['search17_odometry']))
    if not clear:
        return False
    if teacher.sampled_stance:
        from sim.grasp_act_pregrasp import issued_sweep_reason
        arm=[] if audit is not None else None
        reason=issued_sweep_reason(world, teacher.rid, pose, before, teacher.sink.pwm,
                               command_delta(value, .1),audit=arm)
        if reason:
            if audit is not None:
                audit.append({'check':'issued_arm_sweep','reason':reason,'category':'arm_sweep',
                    'blockers':arm,'blocked_object':','.join(d['id'] for d in arm) or 'none:'+reason,
                    'min_gap_m':min((d['gap_m'] for d in arm if d.get('gap_m') is not None),default=None),
                    'gap_scope':'issued arm sweep'})
            return False
    return True


def project_motion(teacher, world, value, before, now):
    """Replace only a rejected route pulse; leave every admitted pulse identical.

    Never alters alignment/pick, PWM, obstacle geometry or readiness. A finite
    velocity fan must advance toward a checked waypoint under BOTH existing
    odometry models, and pass their full wheel-deadline segment checks.
    """
    from sim.grasp_act_teacher import STATION_M
    guarded = (teacher.search19_body_active or teacher.sampled_stance or teacher.priority is not None
               or (teacher.approach_plan_valid and teacher.approach_choice != (0., STATION_M)))
    if (not guarded or teacher.phase != 'approach' or world['beam'] is None
            or not any(value['wheels']) or admitted(teacher, world, value, before)):
        return value
    nav = teacher._navigation(world)
    radius, discs, rects = teacher._constraints(world)
    pose = world['robots'][teacher.rid]['pose']
    route = teacher.peer_route if teacher.peer_wait_since is not None else teacher.path
    target = nav.waypoint(pose[:2], route, discs, rects, radius)
    if target is None:
        return value  # Existing escape/hold policy remains responsible.
    bearing = math.atan2(target[1]-pose[1], target[0]-pose[0])-pose[2]
    turn = command_delta(value, .1, mode=teacher.search15_modes['search17_odometry'])[2]
    # The route law's gains differ on x/y. Invert only the fixed command model;
    # every candidate is then checked in both calibrated and legacy models.
    gains = SEARCH17_GAINS if teacher.search15_modes['search17_odometry'] != 'off' else (1., 1., 1.)
    for offset in (0, -15, 15, -30, 30, -45, 45, -60, 60, -75, 75):
        a = bearing+math.radians(offset)
        for speed in (.05, .025):
            for yaw in (turn/.1, 0.):
                wheels, widths = duty_wheels([3*speed*math.cos(a)/gains[0],
                                              3*speed*math.sin(a)/gains[1], yaw/gains[2]])
                candidate = command({**deepcopy(value), 'wheels': wheels, 'duration_s': widths})
                advance = True
                for mode in ('off', teacher.search15_modes['search17_odometry']):
                    dx, dy, da = command_delta(candidate, .1, mode=mode)
                    si = math.sin(da)/da if abs(da)>1e-10 else 1.
                    co = (1-math.cos(da))/da if abs(da)>1e-10 else 0.
                    dx, dy = si*dx-co*dy, co*dx+si*dy
                    c, s = math.cos(pose[2]), math.sin(pose[2])
                    endpoint = (pose[0]+c*dx-s*dy, pose[1]+s*dx+c*dy)
                    if math.dist(endpoint, target) >= math.dist(pose[:2], target)-1e-6:
                        advance = False
                if advance and admitted(teacher, world, candidate, before):
                    teacher.search19_log.append({'t': now, 'event': 'route_pulse_projected',
                                                 'offset_deg': offset, 'speed': speed,
                                                 'waypoint': target})
                    return candidate
    return value


def _fallback_navigation(teacher, world):
    from sim.grasp_act_search21 import enabled as search21, BodyNavigation as Search21Navigation
    if search21(teacher):return Search21Navigation(teacher,world,admission=True)
    from sim.grasp_act_search20 import enabled, BodyNavigation as Search20Navigation
    return Search20Navigation(teacher, world, admission=True) if enabled(teacher) else BodyNavigation(teacher, world)


def _fallback_choices(teacher, choices):
    from sim.grasp_act_search20 import enabled
    return list(dict.fromkeys(choices)) if enabled(teacher) else choices
