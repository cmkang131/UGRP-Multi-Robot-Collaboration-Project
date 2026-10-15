"""Opt-in conservative admission, continuous revalidation and bounded planning.

Only the visible/issued world enters this module. Evaluation error distributions
are produced by the offline replay, never consumed by the controller.
"""
import math
import time

from sim.grasp_act_search18 import body_clearance, exact_start_path
from sim.grasp_act_search19 import BodyNavigation as LegacyBodyNavigation

MODES = {'search20': 'search20_v1'}
ADMIT_MARGIN_M = .140  # Offline relative-body bound max135.87mm, rounded UP; see search20.md.
RETAIN_MARGIN_M = .002  # Sampling envelope near overlap, not an uncertainty guarantee.
MAX_CHECKS = 32768
MAX_PATH_NODES = 512
CACHE_SIZE = 4096
MAX_PLANNING_S = 1.0


class PlanningBudgetExceeded(RuntimeError):
    pass


def enabled(teacher):
    return teacher.search15_modes.get('search20', 'off') != 'off'


class PlanningBudget:
    def __init__(self, *, max_checks=MAX_CHECKS, max_s=MAX_PLANNING_S):
        self.max_checks=max_checks;self.max_s=max_s
        self.started = None
        self.checks = self.hits = 0
        self.exhausted = False

    def elapsed(self):
        return 0. if self.started is None else time.perf_counter()-self.started

    def check(self):
        if self.started is None:self.started=time.perf_counter()
        if self.checks >= self.max_checks or (self.max_s is not None and self.elapsed() >= self.max_s):
            self.exhausted = True
            raise PlanningBudgetExceeded('search20 planning budget')
        self.checks += 1


class BodyNavigation(LegacyBodyNavigation):
    def __init__(self, teacher, world, *, admission=False):
        super().__init__(teacher, world)
        self.margin = ADMIT_MARGIN_M if admission else RETAIN_MARGIN_M
        self.teacher = teacher
        self.scene_key = (tuple(self.discs), tuple(map(tuple, self.rects)), tuple(self.bounds))

    def check_budget(self):
        budget = self.teacher.search20_budget
        if budget is not None:
            budget.check()

    def free(self, p, discs, rects, radius, *, heading=None):
        yaw = self.heading(p) if heading is None else heading
        self.check_budget()
        key = (self.scene_key, tuple(p[:2]), yaw, self.margin)
        cache = self.teacher.search20_cache
        if key in cache:
            if self.teacher.search20_budget is not None:
                self.teacher.search20_budget.hits += 1
            cache.move_to_end(key)
            return cache[key]
        result = body_clearance((*p[:2], yaw), self.discs, self.rects,
                                bounds=self.bounds, need=self.margin) >= self.margin
        cache[key] = result
        if len(cache) > CACHE_SIZE:
            cache.popitem(last=False)
        return result

    def pose_segment(self, a, b):
        da = math.atan2(math.sin(b[2]-a[2]), math.cos(b[2]-a[2]))
        # <0.8mm movement of any footprint point per sample; the SAME 2mm
        # retention envelope is used for poses, retreat, routes and pulses.
        n = max(1, math.ceil(math.dist(a[:2], b[:2])/.0005), math.ceil(abs(da)/math.radians(.1)))
        return all(self.free((a[0]+(b[0]-a[0])*i/n, a[1]+(b[1]-a[1])*i/n),
                             (), (), 0., heading=a[2]+da*i/n) for i in range(n+1))

    def path_for_goal(self, start, goal, discs, rects, radius):
        old = self.teacher.path
        if not old:return self.plan_path(start, goal, self.bounds, discs, rects=rects, radius=radius)
        nearest = min(range(len(old)), key=lambda i:math.dist(start, old[i]))
        remaining = [tuple(start), *old[nearest:-1], tuple(goal)]
        if all(self.segment_free(a,b,discs,rects,radius) for a,b in zip(remaining,remaining[1:])):
            return remaining
        return self.plan_path(start, goal, self.bounds, discs, rects=rects, radius=radius)

    def plan_path(self, start, goal, bounds, discs, *, rects=(), radius=.13):
        return exact_start_path(start, goal, bounds,
            lambda p: self.free(p, discs, rects, radius),
            lambda a,b: self.segment_free(a, b, discs, rects, radius), budget=MAX_PATH_NODES)


def retain(teacher, world, now):
    """Revalidate the same end-relative family at its UPDATED visible goal.

    No 1mm endpoint identity gate. The current choice is fixed, but the target,
    full arm/retreat/visibility and every remaining connector are checked anew.
    """
    if not teacher.search19_body_active or not teacher.path:
        return None
    from sim.grasp_act_pregrasp import select_sampled_goal
    selected, checked = select_sampled_goal(world, teacher.rid, teacher.end, teacher.bounds,
        teacher.folded_ready, teacher.sink.pwm, current=teacher.approach_choice,
        navigation=teacher._navigation(world))
    if selected is not None:
        teacher.search20_log.append({'t': now, 'event': 'stance_family_retained',
            'choice': teacher.approach_choice, 'goal_shift_m': math.dist(selected['goal'], teacher.path_goal),
            'margin_m': RETAIN_MARGIN_M})
    return selected, checked


def alignment_alternative(teacher, world, value, before, now):
    """On a rejected alignment axis, try another active axis, not a new skill.

    The lateral-first law can point into the beam while backward motion is
    clear. Both issued models and the existing arm sweep must admit an axis;
    the visible goal/yaw squared error must decrease. READY/IK stay unchanged.
    """
    from sim.grasp_act_search19 import admitted
    from sim.grasp_act_teacher import local, wrap
    from harness.grasp_act_visible_world import command_delta
    if teacher.phase != 'align' or not any(value['wheels']) or admitted(teacher, world, value, before):
        return value
    pose, point, heading, goal = teacher._geometry(world)
    gx, gy = local(pose, point)
    errors = (gx-teacher.staging_distance, gy, wrap(heading-pose[2]))
    old_merit = math.dist(pose[:2], goal)**2 + (.1*errors[2])**2
    for axis in (2, 0, 1):
        if not teacher.align_active[axis]:
            continue
        effort = (.9, .9, .8)[axis]*errors[axis] + teacher.align_integral[axis]
        lo, hi = ((-.05, .08), (-.06, .06), (-.10, .10))[axis]
        drive = [0., 0., 0.]; drive[axis] = max(lo, min(hi, effort))
        candidate = teacher._continuous(now, *drive)
        progresses = True
        for mode in ('off', teacher.search15_modes['search17_odometry']):
            dx, dy, da = command_delta(candidate, .1, mode=mode)
            c, s = math.cos(pose[2]), math.sin(pose[2])
            xy = (pose[0]+c*dx-s*dy, pose[1]+s*dx+c*dy)
            merit = math.dist(xy, goal)**2 + (.1*wrap(heading-pose[2]-da))**2
            progresses &= merit < old_merit-1e-10
        if progresses and admitted(teacher, world, candidate, before):
            teacher.search20_log.append({'t': now, 'event': 'alignment_axis_admitted', 'axis': axis})
            return candidate
    teacher.search20_log.append({'t': now, 'event': 'alignment_axes_blocked'})
    return value


def plan_active(teacher, world, now):
    """Keep the admitted family first; every replacement uses admission padding."""
    nav=teacher._navigation(world)
    pose,point,heading,goal=teacher._geometry(world)
    radius,discs,rects=teacher._constraints(world)
    changed=teacher.path_goal is None or math.dist(goal,teacher.path_goal)>.025
    blocked=not nav.free(goal,discs,rects,radius)
    if teacher.approach_plan_valid and not changed and not blocked and now<teacher.next_plan:
        return True
    kept=retain(teacher,world,now)
    selected,checked=kept if kept is not None else (None,[])
    if selected is None:
        from sim.grasp_act_search19 import body_fallback
        selected,more=body_fallback(teacher,world,now)
        checked+=more
    teacher.planner_calls+=1;teacher.next_plan=now+1.
    teacher.blocked_goal_calls+=int(blocked)
    teacher.no_path_calls+=int(selected is None)
    teacher.approach_plan_valid=selected is not None
    row={'t':now,'candidates':checked,'selected':None}
    if selected is not None:
        teacher.approach_choice=selected['choice'];teacher.staging_distance=selected['choice'][1]
        teacher.path=selected['path'];teacher.path_goal=tuple(selected['goal'])
        teacher.approach_blocked_since=None
        row['selected']={k:v for k,v in selected.items() if k!='path'}
    else:
        # Keep the family/path as an INVALID proposal for the next fresh view.
        # _plan_approach returns False, so no motion uses it before revalidation.
        from collections import Counter
        teacher.search20_log.append({'t':now,'event':'retained_proposal_blocked',
            'reasons':dict(Counter(c['reason'] for c in checked))})
        if teacher.approach_blocked_since is None:teacher.approach_blocked_since=now
    teacher.goal_set_log.append(row)
    from sim.grasp_act_search21 import schedule
    if selected is None:schedule(teacher,world,now)
    if teacher.approach_blocked_since is not None and now-teacher.approach_blocked_since>=teacher.APPROACH_BLOCKED_LIMIT_S-1e-8:
        teacher._approach_handoff(now)
    return teacher.approach_plan_valid
