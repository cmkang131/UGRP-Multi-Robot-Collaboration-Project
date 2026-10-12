"""Opt-in explore_lite goal lifecycle over the existing own-RGB costmap.

Yamauchi frontiers and the vendored gain/distance ranking are unchanged. A
reachable frontier starts navigation immediately; a full camera spin is only
needed when no reachable frontier exists. Goal commitment supplies hysteresis.
Progress uses the existing Nav2 checker and SIM time, never evaluator poses.
"""
import math
import numpy as np
from harness.active_navfn_start import StartCycleNavigator
from harness.public_navigation.follower import command_from_twist

OPTION = 'frontier_progress_v1'


class Navigator(StartCycleNavigator):
    def __init__(self, driver):
        super().__init__()
        self.driver = driver
        self.sweep_pending = None
        self.initial_scan_used = False
        self.goal_started = None
        self.progress_xy = None
        self.progress_time = None

    def select_frontier(self, costmap, pose, t):
        if self.phase or self.sweep_pending or self.locked:
            return
        # The native core returns explore_lite's distance/gain cost order.
        for row in self.core.frontiers(costmap.raw, costmap.origin, costmap.resolution, pose[:2]):
            target = row[:2]
            if self.blocked(target, costmap.resolution):
                continue
            path = self.plan_to(costmap, pose, target)
            if not path:
                self.blacklist.append(target.copy())
                self.event(t, 'frontier_unreachable_blacklisted', target=target.tolist())
                continue
            self.reset_action()
            self.target = self.frontier = target.copy()
            self.path, self.heading = path, 0.
            self.locked = True
            self.finished = False
            self.goal_started = self.progress_time = t
            self.progress_xy = np.asarray(self.driver.pose[:2]).copy()
            self.event(t, 'frontier_selected', target=target.tolist(), cost=float(row[6]),
                       path_length_m=float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum()))
            return
        self.target = self.frontier = None
        self.path = []
        if not self.initial_scan_used:
            self.initial_scan_used = True
            self.request_sweep(t, 'no_reachable_frontier')
        else:
            self.finished = True
            self.event(t, 'exploration_finished_no_frontier')

    def action_failed(self, t, reason):
        # explore_lite ABORTED -> blacklist -> select another goal. Do not
        # insert another unconditional full spin at every failed action.
        from harness.active_wall_recovery import ExplorationRecoveryNavigator
        ExplorationRecoveryNavigator.action_failed(self, t, reason)
        self.locked = False
        self.sweep_pending = None
        self.goal_started = self.progress_time = None
        self.progress_xy = None

    def failure(self, t, reason, context='controller'):
        if reason == 'controller_collision':
            self.event(t, 'would_stop_collision_guard', dev_light=True)
            return
        return super().failure(t, reason, context)

    def arrival(self, pose, t):
        if self.locked and self.target is not None and not self.phase and np.linalg.norm(self.target-pose[:2]) <= .05:
            self.visited.append(self.target.copy())
            self.event(t, 'frontier_cycle_visited', target=self.target.tolist())
            self.target = self.frontier = None
            self.path = []
            self.reset_action()
            self.locked = False
            self.goal_started = self.progress_time = None

    def update(self, costmap, pose, t, static_goal=None):
        # B candidates are recorded by GoalRoute; they must not replace the
        # committed frontier on each image and reset its progress deadline.
        self.arrival(pose, t)
        return super().update(costmap, pose, t, static_goal=None)

    def start_sweep(self, pose, t):
        super().start_sweep(pose, t)
        self.sweep_last_yaw = float(self.driver.pose[2])

    def command(self, costmap, pose, plan, t):
        if self.locked and self.progress_time is not None:
            xy = np.asarray(self.driver.pose[:2])
            if np.linalg.norm(xy-self.progress_xy) > .5:
                self.progress_xy, self.progress_time = xy.copy(), t
            elif t-self.progress_time > 10.:
                self.event(t, 'controller_no_progress', elapsed_s=t-self.progress_time,
                           source='own_issued_command_odometry')
                self.action_failed(t, 'progress_timeout_blacklist')
                return command_from_twist(np.zeros(3), t)
        # Spin progress must not include global localization yaw corrections.
        spin_pose = np.array(pose, float)
        if self.sweep_pending or self.phase == 'sensor_sweep':
            spin_pose[2] = self.driver.pose[2]
        command = super().command(costmap, spin_pose, plan, t)
        if self.phase == 'sensor_sweep' and not any(command.get(k, 0) for k in ('forward','left','turn')):
            self.event(t, 'would_stop_collision_guard', phase='sensor_sweep', dev_light=True)
            command = command_from_twist(np.array([0.,0.,.5]), t)
        return command


def install(controller, option='off'):
    if option == 'off':
        return controller
    if option != OPTION:
        raise ValueError('UNKNOWN_EXPLORATION_PROGRESS')
    explorer = controller.explorer
    odom = explorer.memory.self_map.odom
    driver = getattr(odom, 'base', odom).driver
    explorer.navigator = Navigator(driver)
    explorer.choose_information = lambda t, costmap: None
    explorer.bootstrap_turn = 2*math.pi
    graph = explorer.graph
    def graph_progress(t):
        n = explorer.navigator
        last_yaw = n.sweep_last_yaw
        graph(t)
        n.sweep_last_yaw = last_yaw  # command odom does not move with map TF
    explorer.graph = graph_progress
    receive = controller.receive
    event_cursor = 0
    def receive_progress(**kwargs):
        nonlocal event_cursor
        command, trace = receive(**kwargs)
        n = explorer.navigator
        trace['exploration'] = dict(option=option, phase=n.phase, locked=n.locked,
            target=None if n.target is None else n.target.tolist(),
            sweep_rotation_rad=n.sweep_rotation, goal_started_s=n.goal_started,
            events=list(n.events[event_cursor:]))
        event_cursor = len(n.events)
        return command, trace
    controller.receive = receive_progress
    return controller
