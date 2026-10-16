"""Default-off Yamauchi (1997) arrival/timeout -> sensor sweep -> next goal.

Only own pose/RGB navigation inputs. Frozen PR409 planning and RBPF are reused.
Camera/temporal adaptations and original sources: egomap45 REFERENCES.md.
"""
import math
import numpy as np
from harness.active_wall_recovery import RecoveryMapper,ExplorationRecoveryNavigator,make_mapper as legacy_mapper
from harness.active_wall_mapping import compose,inverse
from harness.public_navigation.follower import command_from_twist
from harness.public_navigation_recovery import projection_clear
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap

OPTION='yamauchi_cycle_v1'
SWEEP_LIMIT_S=30.  # existing explore_lite progress_timeout, no outcome tuning
SWEEP_RAD=2*math.pi-.02


def make_mapper(*args,frontier_observation='off',**kwargs):
    if frontier_observation=='off':return legacy_mapper(*args,**kwargs)
    if frontier_observation!=OPTION:raise ValueError('UNKNOWN_FRONTIER_OBSERVATION')
    if kwargs.pop('active_recovery','off')!='nav2_frontier_v1':raise ValueError('CYCLE_REQUIRES_FROZEN_RECOVERY')
    return VisibilityMapper(*args,**kwargs)


class CycleNavigator(ExplorationRecoveryNavigator):
    def __init__(self):
        super().__init__()
        self.sweep_pending='initial_view'
        self.sweep_last_yaw=None
        self.sweep_rotation=0.
        self.locked=False
        self.visited=[]

    def blocked(self,goal,resolution):
        return super().blocked(goal,resolution) or any(
            np.all(np.abs(np.asarray(goal)-p)<5*resolution) for p in self.visited)

    def request_sweep(self,t,reason):
        self.target=self.frontier=self.requested_goal=None
        self.path=[]
        self.reset_action()
        self.failed=self.finished=self.static_mode=False
        self.locked=False
        self.sweep_pending=reason
        self.next_frontier_ns=0
        self.event(t,'sensor_sweep_requested',cause=reason)

    def start_sweep(self,pose,t):
        reason=self.sweep_pending
        self.sweep_pending=None
        self.phase='sensor_sweep';self.phase_start=t;self.phase_pose=np.array(pose,float)
        self.sweep_last_yaw=float(pose[2]);self.sweep_rotation=0.
        self.event(t,'sensor_sweep_started',cause=reason)

    def action_failed(self,t,reason):
        super().action_failed(t,reason)  # original inaccessible-goal blacklist
        self.request_sweep(t,reason)

    def failure(self,t,reason,context='controller'):
        if reason=='controller_no_progress' and not self.phase:
            self.event(t,reason)
            self.action_failed(t,'progress_timeout_sensor_sweep')
        else:super().failure(t,reason,context)

    def select_frontier(self,costmap,pose,t):
        if self.locked or self.sweep_pending or self.phase=='sensor_sweep':return
        super().select_frontier(costmap,pose,t)
        if self.target is not None:
            self.locked=True
            self.event(t,'frontier_cycle_committed',target=self.target.tolist())

    def arrival(self,pose,t):
        if self.locked and self.target is not None and not self.phase and np.linalg.norm(self.target-pose[:2])<=.05:
            self.visited.append(self.target.copy())
            self.event(t,'frontier_cycle_visited',target=self.target.tolist())
            self.request_sweep(t,'arrival')

    def update(self,costmap,pose,t,static_goal=None):
        self.arrival(pose,t)
        if self.sweep_pending:self.start_sweep(pose,t)
        if self.phase=='sensor_sweep':return self.idle(pose,'sensor_sweep')
        result=super().update(costmap,pose,t,static_goal)
        if self.target is not None:self.locked=True
        return result

    def command(self,costmap,pose,plan,t):
        self.arrival(pose,t)
        if self.sweep_pending:self.start_sweep(pose,t)
        if self.phase=='sensor_sweep':
            self.sweep_rotation+=float(wrap(pose[2]-self.sweep_last_yaw))
            self.sweep_last_yaw=float(pose[2])
            completed=self.sweep_rotation>=SWEEP_RAD
            if completed or t-self.phase_start>=SWEEP_LIMIT_S:
                self.event(t,'sensor_sweep_completed' if completed else 'sensor_sweep_incomplete',
                    rotation_rad=self.sweep_rotation,duration_s=t-self.phase_start)
                self.phase=None;self.sweep_last_yaw=None
                self.reset_action();self.next_frontier_ns=0
                return command_from_twist(np.zeros(3),t)
            twist=np.array([0.,0.,.5])  # frozen Nav2 recovery spin request
            if not projection_clear(costmap,pose,twist,horizon=2.):
                self.event(t,'sensor_sweep_collision_hold')
                twist[:]=0.
            return command_from_twist(twist,t)
        command=super().command(costmap,pose,plan,t)
        # A progress failure can request the sweep inside the parent command.
        # Never leak that aborted action's old velocity into this boundary tick.
        if self.sweep_pending:return command_from_twist(np.zeros(3),t)
        return command


class VisibilityMapper(RecoveryMapper):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.navigator=CycleNavigator()

    def choose_information(self,t,costmap):
        n=self.navigator
        if n.locked or n.sweep_pending or n.phase=='sensor_sweep':return
        super().choose_information(t,costmap)
        if n.target is not None:
            n.locked=True
            n.event(t,'information_cycle_committed',target=n.target.tolist())

    def graph(self,t):
        old=self.map_to_odom.copy()
        super().graph(t)
        delta=compose(self.map_to_odom,inverse(old));n=self.navigator
        n.visited=[transform([p],delta)[0] for p in n.visited]
        if n.sweep_last_yaw is not None:n.sweep_last_yaw=float(wrap(n.sweep_last_yaw+delta[2]))
