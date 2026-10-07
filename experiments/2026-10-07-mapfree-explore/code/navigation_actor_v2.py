"""Own-command-only v2 execution adapter shared by both 2D information conditions."""
import math
import numpy as np

from run_grid import Actor, NavigationOptions, Footprint, astar, motion_profiles, inverse, wrap
from harness.own_map_navigation_v2 import OwnMapNavigatorV2, polygon_clearance, segment_clear

OPTIONS_V2 = dict(exploration='own_frontier_v2',door_detection='own_gap_v1',partial_planning='own_astar_v2')


class ActorV2(Actor):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.grid.support.clear()
        self.navigator = OwnMapNavigatorV2('r1',NavigationOptions(**OPTIONS_V2))

    def plan(self):
        if self.condition!='static_map':
            return super().plan()
        pose = self.odom.pose
        grid = self.navigator.prepare_grid(self.grid,pose)
        _,clear,dist,lo = polygon_clearance(grid,Footprint(),.02,yaw=pose[2])
        start = tuple(np.asarray(grid.cell(pose[:2]))-lo)
        target = tuple(np.asarray(grid.cell(self.static_goal))-lo)
        path = astar(clear,start,target,.1,dist)
        return dict(status='static_map' if path else 'static_no_path',
            path_m=[grid.point(np.array(c)+lo).tolist() for c in path] if path else [],doors=[],
            heading_rad=math.atan2(self.static_goal[1]-pose[1],self.static_goal[0]-pose[0]) if path else wrap(pose[2]+math.radians(25)))

    def command(self,plan):
        pose = np.array(self.odom.pose)
        path = plan.get('path_m',[])
        gain = np.asarray(motion_profiles()['motion']['gain'])
        target = pose.copy()
        twist = np.zeros(3)
        if len(path)>1:
            delta = np.array(path[1])-pose[:2]
            delta *= min(1.,.12/max(1e-9,np.linalg.norm(delta)))
            target[:2] += delta
            twist[:2] = inverse([target[:2]],pose)[0]
        else:
            error = wrap(plan.get('heading_rad',pose[2]+math.radians(25))-pose[2])
            if abs(error)<.05:
                error = math.radians(25)
            twist[2] = float(np.clip(error,-.5*gain[2,2],.5*gain[2,2]))
            target[2] += twist[2]
        allowed = segment_clear(self.navigator.last_grid,pose,target)
        requested = np.linalg.solve(gain,twist) if allowed else np.zeros(3)
        # Scale the complete command together: clipping one axis would restore coupling.
        requested /= max(1.,abs(requested[0])/.25,abs(requested[1])/.25,abs(requested[2])/.5)
        if not allowed:
            self.counts['swept_footprint_unknown_or_occupied'] = self.counts.get('swept_footprint_unknown_or_occupied',0)+1
        self.steps += 1
        self.counts[plan['status']] = self.counts.get(plan['status'],0)+1
        return dict(t=self.t,kind='mecanum',forward=float(requested[0]),left=float(requested[1]),
                    turn=float(requested[2]),duration_s=1.)
