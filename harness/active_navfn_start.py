"""Default-off NavFn clearRobotCell + Nav2 recover-before-abort adapter.

Apache/BSD source mapping and adaptations: egomap47 README. The global planner
does not test a raster connector's footprint. Local collision checks stay live.
"""
import math
import numpy as np
from harness.active_wall_recovery import RecoveryMapper,ExplorationRecoveryNavigator
from harness.active_frontier_cycle import CycleNavigator,VisibilityMapper,make_mapper as legacy_mapper,OPTION as CYCLE

OPTION='navfn_recovery_v1'
RECOVERY=('clear','spin','wait','backup')  # pinned Nav2 BT XML


def make_mapper(*args,navigation_start='off',frontier_observation='off',map_acceleration='off',**kwargs):
    if map_acceleration!='off':
        from harness.grid_acceleration import install
        return install(make_mapper(*args,navigation_start=navigation_start,frontier_observation=frontier_observation,**kwargs),map_acceleration=map_acceleration)
    if navigation_start=='off':return legacy_mapper(*args,frontier_observation=frontier_observation,**kwargs)
    if navigation_start!=OPTION:raise ValueError('UNKNOWN_NAVIGATION_START')
    if kwargs.pop('active_recovery','off')!='nav2_frontier_v1':raise ValueError('START_REQUIRES_FROZEN_RECOVERY')
    if frontier_observation not in ('off',CYCLE):raise ValueError('UNKNOWN_FRONTIER_OBSERVATION')
    return (StartCycleMapper if frontier_observation==CYCLE else StartRecoveryMapper)(*args,**kwargs)


class StartRecoveryNavigator(ExplorationRecoveryNavigator):
    def plan_to(self,costmap,pose,target):
        start,goal=costmap.world_to_map(pose[:2]),costmap.world_to_map(target)
        if start is None or goal is None:return []
        if goal!=start and costmap.costs[goal[1],goal[0]] in (253,254):return []
        # NavfnPlanner::clearRobotCell. Only a planning copy is changed: the
        # sensor map and local controller must keep every measured obstacle.
        costs=costmap.costs.copy();costs[start[1],start[0]]=0
        if start==goal:return [list(pose[:2]),list(target)]
        cells=self.core.plan(costs,start,goal)
        if not len(cells):return []
        # Source getPlanFromPotential has no footprint/sweep rejection here.
        # Existing coordinate conversion and path follower remain unchanged.
        return np.vstack([pose[:2],costmap.map_to_world(cells),target]).tolist()

    def select_frontier(self,costmap,pose,t):
        if self.phase:return  # Nav2 recovery retains the current navigation action.
        now=round(t*1e9)
        if self.frontier is not None and now<self.next_frontier_ns:return
        self.next_frontier_ns=now+round(1e9/.33)
        for f in self.core.frontiers(costmap.raw,costmap.origin,costmap.resolution,pose[:2]):
            centre=f[:2]
            if self.blocked(centre,costmap.resolution):continue
            same=self.frontier is not None and np.linalg.norm(centre-self.frontier)<.01
            if not same or self.best_distance>f[4]:self.best_distance,self.last_progress=f[4],t
            if t-self.last_progress>30.:
                self.blacklist.append(centre.copy())
                self.event(t,'progress_timeout_blacklist',target=centre.tolist())
                self.target=self.frontier=None;self.reset_action();continue
            if same:return
            path=self.plan_to(costmap,pose,centre)
            self.reset_action()
            self.target,self.path,self.frontier=centre.copy(),path,centre.copy()
            self.heading=0.
            self.event(t,'frontier_selected' if path else 'frontier_navigation_action',target=centre.tolist())
            # explore_lite submits an action; ComputePath/FollowPath failures
            # get contextual/general recovery before action_failed blacklists.
            return
        self.target=self.frontier=None;self.finished=True
        self.event(t,'exploration_finished_no_frontier')

    def failure(self,t,reason,context='controller'):
        if self.phase or self.failed:return
        self.event(t,reason)
        if context not in self.context_used:
            self.context_used.add(context);self.begin_phase('context_clear',t)
            self.event(t,'context_clear_'+context)
        elif self.retry>=6:self.action_failed(t,'recovery_exhausted')
        else:self.begin_phase(RECOVERY[self.round_index],t)

    def phase_result(self,t,success):
        if self.phase in ('context_clear','contact_backup'):return super().phase_result(t,success)
        phase=self.phase;self.event(t,'recovery_success' if success else 'recovery_failure',action=phase)
        self.phase=None;self.round_index=(self.round_index+1)%len(RECOVERY)
        if success:
            self.round_failures=0;self.retry+=1;self.context_used.clear();self.restart_follow()
        else:
            self.round_failures+=1
            if self.round_failures>=len(RECOVERY):self.action_failed(t,'all_recoveries_failed')
            else:self.begin_phase(RECOVERY[self.round_index],t)


class StartCycleNavigator(CycleNavigator,StartRecoveryNavigator):
    """Keep the frozen arrival/progress sensor sweep, with the new planner port."""


class StartRecoveryMapper(RecoveryMapper):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.navigator=StartRecoveryNavigator()


class StartCycleMapper(VisibilityMapper):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.navigator=StartCycleNavigator()
