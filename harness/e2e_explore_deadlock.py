"""Default-off retry of an exhausted local exploration action, not mission success.

explore_lite abort/reselection and Nav2 replan-before-spin, adapted to the
continuing own-camera beam mission. Only issued commands and local navigator
state are inspected. No pose reset, map clearing, GT or new motion primitive.
"""
import math

OPTION = 'replan_v1'
PARAMS = dict(idle_s=30., issued_gap_s=.4, sweep_limit_s=30.)


class DeadlockRecovery:
    def __init__(self, goal):
        self.goal = goal
        self.last_issued = self.idle_since = None
        self.cycles = 0
        self.last_recovery = None
        self.search = None

    def commanded(self, row):
        if row['kind'] not in ('hold', 'mecanum'):
            return
        t = float(row['t'])
        if self.last_issued is None or not 0 <= t-self.last_issued <= PARAMS['issued_gap_s']+1e-8:
            self.idle_since = t
        if row['kind'] == 'mecanum' and any(row.get(k, 0) for k in ('forward', 'left', 'turn')):
            # Count ALL commanded motion, not just translation. An issued
            # command is not evidence of physical movement or localization.
            self.idle_since = t
        self.last_issued = t

    def before_receive(self, t):
        g = self.goal
        n = g.explorer.navigator
        if (g.robot_id not in ('r1', 'r2') or g.done or g.stage != 'explore'
                or n.failed or n.phase or n.sweep_pending or getattr(n, 'view_active', False)):
            self.idle_since = t
            return
        # Mapping owns locomotion only while it is issuing commands. No
        # recovery when transport/another owner has stopped issuing them.
        if self.last_issued is None or not 0 <= t-self.last_issued <= PARAMS['issued_gap_s']+1e-8:
            self.idle_since = t
            return
        if self.idle_since is None or t-self.idle_since < PARAMS['idle_s']-1e-8:
            return
        self.last_recovery = dict(t=float(t), idle_s=t-self.idle_since,
            finished=n.finished, target=None if n.target is None else n.target.tolist(),
            expired_blacklist=len(n.blacklist), expired_visited=len(n.visited))
        # These lists suppress action targets, not measured obstacles. Expire
        # the suppression epoch only after 30s of issued zero-motion commands.
        n.blacklist.clear()
        n.visited.clear()
        n.reset_action()
        n.target = n.frontier = n.requested_goal = None
        n.path = []
        n.locked = n.finished = n.static_mode = False
        n.goal_started = n.progress_time = n.progress_xy = None
        n.best_distance = math.inf
        n.next_frontier_ns = 0
        # Fresh costmap/frontier selection first; if none can be reached,
        # reuse the existing bounded own-command-yaw sensor sweep and retry.
        n.initial_scan_used = False
        g.explorer.plan = None
        g.explorer.last_plan_t = -math.inf
        self.cycles += 1
        self.idle_since = t
        n.event(t, 'explore_deadlock_replan', cycle=self.cycles, **{
            k: v for k, v in self.last_recovery.items() if k != 't'})

    def snapshot(self, t):
        n = self.goal.explorer.navigator
        return dict(option=OPTION, idle_s=None if self.idle_since is None else max(0., t-self.idle_since),
            last_issued_s=self.last_issued, cycles=self.cycles, last_recovery=self.last_recovery,
            finished=n.finished, failed=n.failed, phase=n.phase, sweep_pending=n.sweep_pending,
            blacklist_count=len(n.blacklist), visited_count=len(n.visited), search=self.search)


def install(goal, option='off'):
    if option == 'off':
        return goal
    if option != OPTION:
        raise ValueError('UNKNOWN_EXPLORE_DEADLOCK')
    from harness.e2e_exploration import Navigator
    n = goal.explorer.navigator
    if not isinstance(n, Navigator):
        raise ValueError('FRONTIER_PROGRESS_V1_REQUIRED_BEFORE_DEADLOCK')
    recovery = DeadlockRecovery(goal)
    goal.explore_deadlock = recovery
    command, receive = goal.command, goal.receive
    frontiers, plan_to = n.core.frontiers, n.plan_to

    def frontier_search(*args, **kwargs):
        result = frontiers(*args, **kwargs)
        recovery.search = dict(frontier_count=len(result), plan_attempts=0, reachable=0,
                              blacklist_count=len(n.blacklist), visited_count=len(n.visited))
        return result

    def plan(*args, **kwargs):
        result = plan_to(*args, **kwargs)
        if recovery.search is not None:
            recovery.search['plan_attempts'] += 1
            recovery.search['reachable'] += bool(result)
        return result

    def commanded(row):
        result = command(row)
        recovery.commanded(row)
        return result

    def received(**kwargs):
        if kwargs['robot_id'] != goal.robot_id:
            raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
        recovery.before_receive(kwargs['t'])
        action, trace = receive(**kwargs)
        trace['explore_deadlock'] = recovery.snapshot(kwargs['t'])
        return action, trace

    n.core.frontiers, n.plan_to = frontier_search, plan
    goal.command, goal.receive = commanded, received
    return goal
