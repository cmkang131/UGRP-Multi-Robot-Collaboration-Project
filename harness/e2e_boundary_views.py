"""Default-off candidate -> reachable stand-off view -> fresh RGB verification.

Yamauchi exploration completion is not target verification. This finite ring
sampler follows classical candidate-conditioned view planning; its score is a
travel/framing proxy, NOT a predicted full boundary or information gain. Only
own RGB memory, own grid and issued-command pose enter. No gate is relaxed.
References: experiments/2026-10-12-e2e-bboundary/REFERENCES.md.
"""
import math
from types import SimpleNamespace
import numpy as np
from harness.e2e_exploration import Navigator
from harness.public_navigation.follower import command_from_twist
from harness.public_navigation_persistent import raytrace_cells
from harness.public_navigation.costmap import Costmap
from harness.active_wall_mapping import inverse
from harness.e2e_own_inputs import scan
from harness.self_odom_grid import transform
from harness.zone_study_contract import ContractViolation

OPTION = 'candidate_views_v1'
STANDOFF_OPTION = 'standoff_fullquad_v1'  # whole-outline framing; live poses require an own-frame source
OPTIONS = (OPTION, STANDOFF_OPTION)
RADII_M = (.8, 1.2, 1.6, 2., 2.4)  # SAP-Nav AVV Eq. 4, same finite rings
N_ANGLES = 24
MAX_VIEWS = 3
VIEW_BUDGET_S = 30.
RETRY_OPTION = 'navigation_v1'
MAX_NAVIGATION_FAILURES = 6
COVERAGE_OPTION = 'native_v1'


def observed_sweep_clear(costmap, start, end):
    """Preserve native checks and additionally reject unknown filled footprints.

    Baseline v8 UnknownCostmap/NavFn intentionally permits tracking unknown.
    Confirmation views have a separate, stronger explored-space requirement.
    Reuse the existing filled polygon and sweep discretization without changing
    baseline costs, navigation policy or observation provenance.
    """
    known = SimpleNamespace(pose_clear=lambda pose:Costmap.pose_clear(costmap, pose))
    return costmap.sweep_clear(start, end) and Costmap.sweep_clear(known, start, end)


def observed_path_clear(costmap, pose, path, yaw, *, observed=True):
    if not path: return False
    sweep = (lambda a,b:observed_sweep_clear(costmap,a,b)) if observed else costmap.sweep_clear
    previous = np.asarray(pose, float)
    for point in path[1:]:
        point = np.asarray(point)
        # A repeated NavFn point has no direction; retain the actual heading.
        if np.array_equal(point, previous[:2]): continue
        heading = math.atan2(point[1]-previous[1], point[0]-previous[0])
        oriented = np.array([*previous[:2], heading])
        endpoint = np.array([*point, heading])
        if not sweep(previous, oriented) or not sweep(oriented, endpoint):
            return False
        previous = endpoint
    return sweep(previous, [*path[-1], yaw])


def request(candidate, boundary_remembered, *, option='off'):
    """Pure scheduling predicate, also replayable without a saved costmap."""
    if option == 'off': return False
    if option not in OPTIONS: raise ValueError('UNKNOWN_B_BOUNDARY_VIEWS')
    if candidate is None or boundary_remembered: return False
    scan(candidate)
    if candidate.get('source') != 'own' or candidate.get('kind') != 'B':
        raise ContractViolation('OWN_B_CANDIDATE_REQUIRED')
    center = np.asarray(candidate['center_m'], float)
    if center.shape != (2,) or not np.isfinite(center).all():
        raise ContractViolation('FINITE_OWN_B_CENTER_REQUIRED')
    return True


def choose_view(costmap, pose, center, plan_to, *, tried=(), coverage='off', standoff=None):
    """Sample free stand-off positions facing the observed partial candidate.

    Unknown cells are not approach positions. Require a complete collision-free
    swept footprint on every connector, including terminal in-place rotation.
    Failed views are separate from the frontier blacklist and the B hypothesis.
    """
    pose, center = np.asarray(pose, float), np.asarray(center, float)
    if pose.shape != (3,) or center.shape != (2,) or not np.isfinite(np.r_[pose, center]).all():
        raise ValueError('FINITE_OWN_VIEW_INPUTS_REQUIRED')
    views = []
    goal_cell = costmap.world_to_map(center)
    if goal_cell is None: return None
    # standoff: candidates already in the same self-map/odom frame; rings otherwise.
    samples = ([(math.hypot(*(np.asarray(p[:2])-center)), None, np.asarray(p[:2]), p[2]) for p in standoff] if standoff is not None else
               [(radius, angle, center + radius*np.array([math.cos(angle), math.sin(angle)]), None)
                for radius in RADII_M for angle in np.arange(N_ANGLES)*2*math.pi/N_ANGLES])
    for radius, _, xy, fixed_yaw in samples:
        if any(np.linalg.norm(xy-p) < .25 for p in tried): continue
        cell = costmap.world_to_map(xy)
        if cell is None or costmap.raw[cell[1], cell[0]] != 0: continue
        if costmap.costs[cell[1], cell[0]] >= 253: continue
        # Known occlusion disqualifies a view; unknown sight lines remain
        # hypotheses to inspect, never permission to traverse unknown cells.
        sight = list(raytrace_cells(cell, goal_cell))
        if any(costmap.raw[y,x] == 254 for x,y in sight): continue
        unknown_sight = sum(costmap.raw[y,x] == 255 for x,y in sight)
        yaw = math.atan2(center[1]-xy[1], center[0]-xy[0]) if fixed_yaw is None else fixed_yaw
        pose_clear = costmap.pose_clear if coverage == COVERAGE_OPTION else lambda p:Costmap.pose_clear(costmap,p)
        if not pose_clear([*xy, yaw]): continue
        path = plan_to(costmap, pose, xy)
        if not path: continue
        if not observed_path_clear(costmap, pose, path, yaw, observed=coverage != COVERAGE_OPTION): continue
        length = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
        views.append(dict(target=xy.tolist(), heading=yaw, path=path,
                          score=length+(0. if fixed_yaw is not None else abs(radius-1.2))+.05*unknown_sight,
                          stand_off_m=radius, unknown_sight_cells=int(unknown_sight)))
    return min(views, key=lambda v:v['score']) if views else None


class CandidateNavigator(Navigator):
    def __init__(self, driver, goal):
        super().__init__(driver)
        self.goal = goal
        self.option = OPTION
        self.view_active = False
        self.view_started = None
        self.view_target_own = None
        self.tried_own = []
        self.observe_frames = []
        self.last_view_reason = None
        self.last_view_search = -math.inf
        self.retry_option = 'off'
        self.completed_views = 0
        self.navigation_failures = 0
        self.coverage_option = 'off'
        self.boundary_frame = 'off'
        self.coverage_checks = None
        self.coverage_would_stops = 0
        self.coverage_by_stage = {}
        self.coverage_logged_stages = set()

    def record_coverage(self, strict, native, t, stage, **details):
        self.coverage_checks = dict(t=t, stage=stage, strict_clear=bool(strict),
                                    native_clear=bool(native), **details)
        # Arrival and rotation can occur in the same receive call. Preserve
        # each site's latest decision rather than overwriting one with another.
        self.coverage_by_stage[stage] = self.coverage_checks
        if not strict and native:
            self.coverage_would_stops += 1
            if stage not in self.coverage_logged_stages:
                self.coverage_logged_stages.add(stage)
                self.event(t,'B_view_would_stop_observed_coverage',dev_light=True,
                           **{k:v for k,v in self.coverage_checks.items() if k!='t'})
        return bool(native)

    def coverage_check(self, costmap, pose, path, yaw, t):
        strict = bool(path) and observed_path_clear(costmap, pose, path, yaw)
        native = strict or bool(path) and observed_path_clear(costmap, pose, path, yaw, observed=False)
        return self.record_coverage(strict, native, t, 'path', path_points=len(path),
            strict_start_clear=bool(Costmap.pose_clear(costmap,pose)), native_start_clear=bool(costmap.pose_clear(pose)))

    def can_attempt(self):
        if self.retry_option == 'off': return len(self.tried_own) < MAX_VIEWS
        return self.completed_views < MAX_VIEWS and self.navigation_failures < MAX_NAVIGATION_FAILURES

    def pending(self):
        return request(self.goal.entities.get('B'), 'B' in self.goal.e2e_gate.references, option=self.option)

    def end_view(self, t, reason):
        if self.view_target_own is not None: self.tried_own.append(self.view_target_own.copy())
        if reason == 'B_view_observed_still_unconfirmed': self.completed_views += 1
        elif reason != 'B_view_boundary_remembered': self.navigation_failures += 1
        self.event(t, reason, views_attempted=len(self.tried_own))
        self.view_active = False
        self.view_target_own = None
        self.observe_frames = []
        self.phase = None
        self.target = self.frontier = None
        self.path = []
        self.locked = self.finished = False
        self.goal_started = self.progress_time = None
        self.reset_action()

    def update(self, costmap, pose, t, static_goal=None):
        if self.view_active and not self.pending(): self.end_view(t, 'B_view_boundary_remembered')
        if self.view_active and t-self.view_started >= VIEW_BUDGET_S:
            self.end_view(t, 'B_view_timeout')
        if (not self.view_active and not self.phase and self.pending() and self.can_attempt()
                and t-self.last_view_search >= 1.-1e-8):
            self.last_view_search = t
            tf = self.goal.explorer.map_to_odom
            center = transform([self.goal.entities['B']['center_m']], tf)[0]
            tried = transform(self.tried_own, tf) if self.tried_own else ()
            own_standoff = None
            if self.option == STANDOFF_OPTION:
                from harness.e2e_boundary_frame import poses
                own_standoff = poses(center, pose)
            view = choose_view(costmap, pose, center, self.plan_to, tried=tried, coverage=self.coverage_option, standoff=own_standoff)
            if view:
                self.reset_action()
                self.target = np.asarray(view['target'])
                self.path, self.heading = view['path'], view['heading']
                self.frontier = None
                self.view_active = self.locked = True
                self.finished = self.failed = False
                self.view_started = self.goal_started = self.progress_time = t
                self.progress_xy = np.asarray(self.driver.pose[:2]).copy()
                self.view_target_own = transform([self.target], inverse(tf))[0]
                self.event(t, 'B_confirmation_view_selected', target=view['target'],
                           stand_off_m=view['stand_off_m'], score=view['score'])
                self.last_view_reason = None
            elif self.last_view_reason != 'no_reachable_view':
                self.event(t, 'B_candidate_unresolved_no_reachable_view')
                self.last_view_reason = 'no_reachable_view'
        if self.view_active:
            terminal_pose = [*self.target, self.heading]
            strict_terminal = Costmap.pose_clear(costmap, terminal_pose)
            terminal_clear = (self.record_coverage(strict_terminal, costmap.pose_clear(terminal_pose),
                t, 'terminal', terminal_pose=list(terminal_pose))
                if self.coverage_option == COVERAGE_OPTION else strict_terminal)
            if not terminal_clear:
                self.end_view(t, 'B_view_coverage_lost')
                return super().update(costmap, pose, t, static_goal)
            if np.linalg.norm(self.target-np.asarray(pose)[:2]) <= .05:
                self.phase = 'B_candidate_observe'
                return self.idle(pose, 'B_candidate_observe')
            self.path = self.plan_to(costmap, pose, self.target)
            clear = (self.coverage_check(costmap,pose,self.path,self.heading,t) if self.coverage_option == COVERAGE_OPTION else
                     bool(self.path) and observed_path_clear(costmap, pose, self.path, self.heading))
            if not clear:
                self.end_view(t, 'B_view_path_lost')
            else:
                self.last_plan_t = t
                return dict(status='public_frontier', path_m=self.path, heading_rad=self.heading, doors=[])
        return super().update(costmap, pose, t, static_goal)

    def arrival(self, pose, t):
        if not self.view_active: return super().arrival(pose, t)

    def action_failed(self, t, reason):
        if self.view_active: self.end_view(t, 'B_view_action_failed')
        else: super().action_failed(t, reason)

    def command(self, costmap, pose, plan, t):
        if self.phase != 'B_candidate_observe': return super().command(costmap, pose, plan, t)
        if not self.pending() or t-self.view_started >= VIEW_BUDGET_S:
            self.end_view(t, 'B_view_boundary_remembered' if not self.pending() else 'B_view_timeout')
            return command_from_twist(np.zeros(3), t)
        error = math.atan2(math.sin(self.heading-pose[2]), math.cos(self.heading-pose[2]))
        if abs(error) > .06:
            self.observe_frames = []
            turn = math.copysign(.35, error)
            # Check the actual terminal spin even in dev_light.
            end = [*pose[:2], pose[2]+math.copysign(.1, error)]
            strict_turn = observed_sweep_clear(costmap, pose, end)
            turn_clear = (self.record_coverage(strict_turn, costmap.sweep_clear(pose, end), t, 'rotation',
                start_pose=np.asarray(pose).tolist(), end_pose=list(end))
                if self.coverage_option == COVERAGE_OPTION else strict_turn)
            if not turn_clear:
                self.end_view(t, 'B_view_rotation_blocked'); turn = 0.
            return command_from_twist(np.array([0.,0.,turn]), t)
        row = self.goal.e2e_gate.current
        if row and 0 <= t-row['ref']['t_sim'] <= .25:
            ref = row['ref']
            if not self.observe_frames or ref['frame_id'] != self.observe_frames[-1]['frame_id']:
                if self.observe_frames and ref['t_sim']-self.observe_frames[-1]['t_sim'] > .5:
                    self.observe_frames = []
                self.observe_frames.append(dict(ref))
            if len(self.observe_frames) >= 3 and ref['t_sim']-self.observe_frames[0]['t_sim'] >= .2-1e-8:
                self.end_view(t, 'B_view_observed_still_unconfirmed')
        return command_from_twist(np.zeros(3), t)


def install(goal, option='off', *, retry='off', coverage='off', frame='off'):
    from harness.e2e_boundary_frame import OPTION as FRAME
    if frame not in ('off', FRAME): raise ValueError('UNKNOWN_BOUNDARY_FRAME')
    if frame != 'off' and option != STANDOFF_OPTION: raise ValueError('STANDOFF_REQUIRED_FOR_OWN_FRAME')
    if option == STANDOFF_OPTION and frame != FRAME:
        raise ValueError('STATIC_MAP_TO_OWN_RGB_REGISTRATION_REQUIRED')
    if retry not in ('off', RETRY_OPTION): raise ValueError('UNKNOWN_BOUNDARY_RETRY')
    if retry != 'off' and option == 'off': raise ValueError('BOUNDARY_VIEWS_REQUIRED_BEFORE_RETRY')
    if coverage not in ('off',COVERAGE_OPTION): raise ValueError('UNKNOWN_BOUNDARY_COVERAGE')
    if coverage != 'off' and (option == 'off' or not goal.dev_light): raise ValueError('DEV_BOUNDARY_VIEWS_REQUIRED_BEFORE_NATIVE_COVERAGE')
    if option == 'off': return goal
    if option not in OPTIONS: raise ValueError('UNKNOWN_B_BOUNDARY_VIEWS')
    old = goal.explorer.navigator
    if type(old) is not Navigator: raise ValueError('FRONTIER_PROGRESS_V1_REQUIRED_BEFORE_VIEWS')
    goal.explorer.navigator = CandidateNavigator(old.driver, goal)
    goal.explorer.navigator.option = option
    goal.explorer.navigator.boundary_frame = frame
    goal.explorer.navigator.retry_option = retry
    goal.explorer.navigator.coverage_option = coverage
    goal.e2e_gate.diagnostics_enabled = True
    receive = goal.receive
    def with_diagnostics(**kwargs):
        command, trace = receive(**kwargs)
        n = goal.explorer.navigator
        trace['boundary_view'] = dict(option=option, frame=frame, pending=n.pending(), active=n.view_active,
            attempted=len(n.tried_own), max_views=MAX_VIEWS, phase=n.phase)
        trace['boundary_diagnostics'] = goal.e2e_gate.current.get('boundary_diagnostics')
        if retry != 'off':
            trace['boundary_view'].update(retry=retry, completed_views=n.completed_views,
                navigation_failures=n.navigation_failures, max_navigation_failures=MAX_NAVIGATION_FAILURES)
        if coverage != 'off':
            trace['boundary_view'].update(coverage=coverage, checks=n.coverage_checks,
                checks_by_stage=dict(n.coverage_by_stage), would_stops=n.coverage_would_stops)
        return command, trace
    goal.receive = with_diagnostics
    return goal
