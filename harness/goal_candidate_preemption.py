"""Nav2 GoalUpdated preempts an old action; own candidate is NOT confirmed B.

Default off leaves object/output untouched. See egomap63 for upstream code.
"""
from types import MethodType
import numpy as np

OPTION='nav2_goal_updated_v1'


def install(navigator, *, goal_preemption='off'):
    if goal_preemption=='off':return navigator
    if goal_preemption!=OPTION:raise ValueError('UNKNOWN_GOAL_PREEMPTION')
    if hasattr(navigator,'_goal_update_base'):raise ValueError('GOAL_PREEMPTION_ALREADY_INSTALLED')
    navigator._goal_update_base=navigator.update
    navigator._candidate_active=False
    navigator.update=MethodType(_update,navigator)
    return navigator


def _update(self,costmap,pose,t,static_goal=None):
    if static_goal is not None:
        target=np.asarray(static_goal,float)
        changed=self.requested_goal is None or not np.array_equal(self.requested_goal,target)
        if changed:
            self.event(t,'goal_updated_preempt',old_phase=self.phase,target=target.tolist())
            self.reset_action()
            self.failed=self.finished=False
        # Cycle arrival must not start a panorama for an active RGB waypoint.
        self.sweep_pending=None;self.sweep_last_yaw=None;self.locked=False
        self.target=target.copy();self.frontier=None
        self._candidate_active=True
    elif self._candidate_active:
        self.target=self.frontier=self.requested_goal=None
        self.locked=False;self._candidate_active=False
        self.reset_action();self.failed=self.finished=False
    return self._goal_update_base(costmap,pose,t,static_goal)
