"""Default-off Nav2 recovery lifecycle for own-camera frontier SLAM.

Pinned sources/line mapping: experiments/2026-10-08-active-recovery/REFERENCES.md.
Nav2 wrap-around control semantics, explore_lite per-goal abort/blacklist.
User-requested clear/spin/backup/wait order differs from the upstream XML default.
No simulator, GT, peer map, static scene or new estimator parameters.
"""
import copy
import math
import numpy as np
from harness.active_wall_mapping import ActiveMapper,compose,inverse,pulse_command
from harness.public_navigation_monitor import MonitorNavigator
from harness.public_navigation_recovery import issued_twist
from harness.public_navigation_unknown import from_observed_grid
from harness.own_map_navigation import ObservedGrid
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap

OPTION='nav2_frontier_v1'
RECOVERY=('clear','spin','backup','wait')


def make_mapper(*args,active_recovery='off',**kwargs):
    if active_recovery=='off':return ActiveMapper(*args,**kwargs)
    if active_recovery!=OPTION:raise ValueError('UNKNOWN_ACTIVE_RECOVERY')
    return RecoveryMapper(*args,**kwargs)


class ExplorationRecoveryNavigator(MonitorNavigator):
    def __init__(self):
        super().__init__()
        self.round_failures=0
        self.requested_goal=None
        self.resolution=.1

    def reset_action(self):
        super().reset_action()
        self.round_failures=0

    def action_failed(self,t,reason):
        self.event(t,'navigation_action_aborted',cause=reason)
        # A temporary own-RGB goal is also one exploration action, not a mission abort.
        targets=[self.frontier,self.target,self.requested_goal]
        for target in targets:
            if target is not None and not self.blocked(target,self.resolution):
                self.blacklist.append(np.asarray(target).copy())
                self.event(t,'ABORTED_goal_blacklisted',target=np.asarray(target).tolist())
        self.target=self.frontier=None
        self.path=[]
        self.best_distance=math.inf
        self.reset_action()
        self.failed=self.finished=self.static_mode=False
        self.requested_goal=None
        self.next_frontier_ns=0
        self.event(t,'next_frontier_requested')

    def failure(self,t,reason,context='controller'):
        if self.phase or self.failed:return
        self.event(t,reason)
        if context not in self.context_used:
            self.context_used.add(context)
            self.begin_phase('context_clear',t)
            self.event(t,'context_clear_'+context)
        elif self.retry>=6:
            self.action_failed(t,'recovery_exhausted')
        else:
            self.begin_phase(RECOVERY[self.round_index],t)

    def phase_result(self,t,success):
        if self.phase in ('context_clear','contact_backup'):
            return super().phase_result(t,success)
        phase=self.phase
        self.event(t,'recovery_success' if success else 'recovery_failure',action=phase)
        self.phase=None
        self.round_index=(self.round_index+1)%len(RECOVERY)
        if success:
            self.round_failures=0
            self.retry+=1  # Nav2 RecoveryNode: only successful recoveries count.
            self.context_used.clear()
            self.restart_follow()
        else:
            self.round_failures+=1
            if self.round_failures>=len(RECOVERY):
                self.action_failed(t,'all_recoveries_failed')
            else:self.begin_phase(RECOVERY[self.round_index],t)

    def update(self,costmap,pose,t,static_goal=None):
        self.resolution=costmap.resolution
        self.requested_goal=None if static_goal is None else np.asarray(static_goal).copy()
        if static_goal is not None and self.blocked(static_goal,self.resolution):
            static_goal=None
        return super().update(costmap,pose,t,static_goal)


class RecoveryMapper(ActiveMapper):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.navigator=ExplorationRecoveryNavigator()
        self.navigation_epoch=-math.inf

    def _rays(self,record,pose):
        if record['t']<self.navigation_epoch:
            return np.empty((0,2))
        return super()._rays(record,pose)

    def clear_navigation(self,t):
        before=sum(self.latest.values())
        self.navigation_epoch=t
        self.grid=ObservedGrid(self.robot_id,.1)
        self.latest={}
        if self.frames:self._rays(self.frames[-1],self.pose)
        self.navigator.clear_requested=False
        self.navigator.event(t,'navigation_layer_reset',old_hits=before,current_hits=sum(self.latest.values()),
            epoch=t,slam_reset=False)

    def choose_information(self,t,costmap):
        # Do not overwrite the goal of a running recovery with a periodic forecast.
        if self.navigator.phase:return
        return super().choose_information(t,costmap)

    def graph(self,t):
        if len(self.memory.self_map.ledger)<2:return
        n=self.navigator
        keys=('target','frontier','path','heading','phase','phase_pose','phase_start',
              'retry','round_index','round_failures','context_used','clear_requested',
              'failed','finished','active_t','last_progress','best_distance','checker','requested_goal')
        saved={k:copy.deepcopy(getattr(n,k)) for k in keys}
        old_tf=self.map_to_odom.copy();old_revisit=copy.deepcopy(self.revisit)
        super().graph(t)  # original SLAM/TF/blacklist; _rays excludes reset obstacle history
        delta=compose(self.map_to_odom,inverse(old_tf))
        for k,v in saved.items():setattr(n,k,v)
        for k in ('target','frontier','requested_goal'):
            if getattr(n,k) is not None:setattr(n,k,transform([getattr(n,k)],delta)[0])
        if n.path:n.path=transform(n.path,delta).tolist()
        if n.heading is not None:n.heading=float(wrap(n.heading+delta[2]))
        if n.phase_pose is not None:n.phase_pose=compose(delta,n.phase_pose)
        if n.checker.baseline is not None:n.checker.baseline=transform([n.checker.baseline],delta)[0]
        self.revisit=None if old_revisit is None else transform([old_revisit],delta)[0]
        n.last_plan_t=-math.inf
        # Same action remains live across map/odom TF updates; new path is replanned.
        n.event(t,'graph_preserved_recovery',phase=n.phase,retry=n.retry,navigation_epoch=None if not math.isfinite(self.navigation_epoch) else self.navigation_epoch)

    def receive(self,*,robot_id,t,frame_id,rgb,servo,observation):
        if robot_id!=self.robot_id:raise ValueError('ACTIVE_PEER_INPUT_FORBIDDEN')
        grid=self.memory.self_map
        grid.odom.advance(t)
        if observation['segments']:
            grid.observe_contacts_confident(t=t,frame_id=frame_id,segments=observation['segments'],features=observation['features'],
                camera_xy=observation['camera'],robot_id=robot_id)
        self.poses.append(dict(robot_id=robot_id,t=float(t),pose=self.local_pose.tolist()))
        row=dict(t=float(t),frame_id=frame_id,**observation)
        self.frames.append(row)
        wall=self._rays(row,self.pose)
        patches,_,diagnostics=self.goal.observe(rgb,robot_id=robot_id,frame_id=frame_id,t=t,pose=self.local_pose,servo=servo,profile='camera_v3',settled=t-self.started>=.25)
        if t>=self.next_graph:
            self.graph(t)
            self.next_graph=t+10.
        pose=self.pose
        if self.navigator.clear_requested:self.clear_navigation(t)
        costmap=from_observed_grid(self.grid,pose,self.latest,set())
        self.choose_information(t,costmap)
        goal=None
        if patches:
            # Observed candidate: approach in .12m increments for v3 temporal confirmation.
            target=compose(self.map_to_odom,[*patches[-1]['center_odom_m'],0.])[:2]
            delta=target-pose[:2]
            goal=target if patches[-1]['confirmed_t'] is not None else pose[:2]+.12*delta/max(np.linalg.norm(delta),1e-9)
        if self.revisit is not None:
            if np.linalg.norm(self.revisit-pose[:2])<.1:
                self.events.append(dict(t=t,reason='active_revisit_reached'))
                self.revisit=None
                self.navigator.target=None
            elif goal is None:goal=self.revisit
        if self.plan is None or t-self.last_plan_t>=1.-1e-8 or goal is not None:
            self.plan=self.navigator.update(costmap,pose,t,static_goal=goal)
            self.last_plan_t=t
        # Frozen v8 increments progress active time by .1 per command. Our
        # calibrated pulse cycle is .2s, so account for the other .1 explicitly.
        if not self.navigator.phase and not self.navigator.failed and not self.navigator.finished:
            self.navigator.active_t+=.1
        command=self.navigator.command(costmap,pose,self.plan,t)
        twist=issued_twist(command)
        # Only initial narrow-FOV acquisition may turn to uncover a frontier.
        if self.navigator.finished and t-self.started<20 and self.bootstrap_turn<2*math.pi:
            twist=np.array([0.,0.,.5])
            self.navigator.finished=False
            self.plan=None
        cmd,pulse=pulse_command(twist,t,costmap=costmap,pose=pose,core=self.navigator.core,points=wall)
        if self.navigator.target is None:self.bootstrap_turn+=abs(pulse['predicted_delta'][2])
        doors=self.doors.update(self.grid,pose)
        trace=dict(t=t,frame_id=frame_id,pose=pose.tolist(),local_pose=self.local_pose.tolist(),
            map_cells=len(self.grid.odds),wall_segments=len(observation['segments']),floor_points=len(observation['floor_xy']),
            status=(self.plan or {}).get('status','initial_camera_scan'),path=(self.plan or {}).get('path_m',[]),
            command=cmd,pulse=pulse,doors=doors,goal=self.goal.snapshot(),goal_diagnostics=diagnostics,
            sigma_xy=math.sqrt(float(np.linalg.eigvalsh(grid.odom.covariance[:2,:2]).max())))
        return cmd,trace
