"""Default-off lower-trajectory contract; own issued commands and existing GO only."""
import copy

OPTIONS=('off','canonical_floor_v1','slow_final_v1','settle_floor_v1')
PARAMS=dict(slow_final_s=2.4,floor_settle_s=1.2,reference='actual queued lower endpoint, not earlier pickup pan',runtime_gt=False)


def lower_path(path,option):
    if option not in OPTIONS:raise ValueError('unknown setdown option')
    out=copy.deepcopy(path)
    if option=='slow_final_v1':out[-1]=(out[-1][0],PARAMS['slow_final_s'],out[-1][2])
    if option=='settle_floor_v1':out[-1]=(out[-1][0],out[-1][1],PARAMS['floor_settle_s'])
    return out


def attach(ep,option='off'):
    if option=='off':return ep
    if option not in OPTIONS:raise ValueError('unknown setdown option')
    ctl=ep.controller;start,lower=ctl._start_transit,ctl._lower
    def start_transit(phase,path,now):
        if phase=='lower':
            path=lower_path(path,option)
            ctl.s3_lower_target=copy.deepcopy(path[-1][0])
            ctl.log(ctl.rid,'setdown_contract',now,option=option,target=ctl.s3_lower_target,
                pickup_reference=ctl.grasp_pose,path=path,source='queued own trajectory')
        return start(phase,path,now)
    def finish_lower(now,idle):
        # The original monitor/closed-epoch/peer/floor-release checks remain.
        # Only the stale pickup target is replaced for THIS lower assertion.
        target=getattr(ctl,'s3_lower_target',None)
        if target is None:return lower(now,idle)
        pickup=ctl.grasp_pose
        try:
            ctl.grasp_pose=target
            return lower(now,idle)
        finally:ctl.grasp_pose=pickup
    ctl._start_transit,ctl._lower=start_transit,finish_lower
    ctl.s3_setdown=dict(option=option,params=copy.deepcopy(PARAMS))
    return ep
