"""Own-map host for the shared v145 selector; no duplicate heading law.

Own pose/path only. Preserve the existing ego rotL calibration and the v145
finite pulse/coast/fresh observation contract. Global S2 PF/maps are not used.
"""
import copy
import numpy as np
from harness import own_map_heading as shared
from harness.path_heading_policy import DEFAULT
from harness.self_pulse_rotation import selected_model
from harness.zone_solo_cyan_pulse_cal import profile_key, response
from harness.active_wall_mapping import compose

OPTION='shared_v145'


class Host:
    def __init__(self,robot_id,motion_model):
        self.robot_id=robot_id;self.profiles=selected_model(motion_model)['profiles']
        self.ready=-float('inf');self.rows=[]

    def command(self,*,t,pose,path,goal,costmap,core,points,map_pose,dev_light):
        if t<self.ready-1e-8:
            return dict(t=float(t),kind='hold'),dict(reason='heading_coast_wait',predicted_delta=[0.,0.,0.])
        # Last point is the mission goal, not a dense teach waypoint: the
        # shared selector permits lateral trim only at the final goal.
        plan=dict(coordinate_frame=f'{self.robot_id}/own_odom',status='goal_approach',
                  path_m=[list(pose[:2]),*map(list,path),list(goal)],heading_rad=float(pose[2]))
        action=shared.command(plan,pose,self.profiles,robot_id=self.robot_id,heading_mode=DEFAULT)
        info=dict(reason='shared_v145',predicted_delta=[0.,0.,0.],blocked=False)
        if action['kind']!='hold':
            p=self.profiles[profile_key(action,False)]
            end=response(p,p['times'][-1]);info['predicted_delta']=end.tolist()
            clear=all(costmap.pose_clear(compose(map_pose,response(p,s))) for s in np.arange(0,p['times'][-1]+1e-8,.025))
            ttc=core.collision_time(points,end/p['times'][-1])
            info['blocked']=not clear or 0<=ttc<1.2
            if info['blocked'] and not dev_light:action=dict(kind='hold')
            else:self.ready=t+p['times'][-1]
        self.rows.append(dict(t=t,plan=plan,action=copy.deepcopy(action),**info))
        return dict(t=float(t),**action),info
