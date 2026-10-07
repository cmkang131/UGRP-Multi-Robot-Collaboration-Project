"""Opt-in GMapping processScan motion gate, ROS defaults; no truth inputs.

OpenSLAM gridfastslam/gridslamprocessor.cpp:338-366,446-449;
slam_gmapping.cpp:213-220. Existing N_eff<N/2 resampling remains unchanged.
"""
from types import MethodType
import math
import numpy as np
from harness.self_map_rbpf import RaoBlackwellizedGrid
from harness.self_map_prob import wrap

OPTION = 'gmapping_motion_v1'


def install(grid, *, rbpf_update='off'):
    if rbpf_update == 'off':
        return grid
    if rbpf_update != OPTION or not isinstance(grid, RaoBlackwellizedGrid):
        raise ValueError('RBPF_MOTION_GATE_OPTION_OR_GRID')
    if hasattr(grid, '_motion_gate'):
        raise ValueError('RBPF_GATE_ALREADY_INSTALLED')
    grid._motion_gate = dict(previous=list(grid.odom.driver.pose), linear=0., angular=0.,
                             processed=0, skipped=0)
    grid._observe = MethodType(_observe, grid)
    grid.export = MethodType(_export, grid)
    return grid


def _observe(self, rec, segments, *, camera_xy, robot_id):
    if robot_id != self.robot_id:
        raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
    key=(rec['t_sim'],rec['view_index'])
    if key in self.seen:
        return []
    camera=np.asarray(camera_xy,float)
    if camera.shape != (2,) or not np.isfinite(camera).all():
        raise ValueError('SELF_MAP_INVALID_CAMERA_ORIGIN')
    self.odom.advance(rec['t_sim'])
    state=self._motion_gate
    now=np.asarray(self.odom.driver.pose)
    delta=now-np.asarray(state['previous'])
    state['linear']+=float(np.linalg.norm(delta[:2]))
    state['angular']+=abs(float(wrap(delta[2])))
    state['previous']=now.tolist()
    unsettled=self.settle_s is not None and (not self.odom.has_servo or
        self.odom.t-self.odom.servo_since+1e-8 < self.settle_s[int(self.odom.loaded)])
    cutoff=min(4.,self.max_range_m if self.max_range_m is not None else 4.)
    near=any(np.linalg.norm(np.asarray(s)-camera,axis=1).max()<cutoff for s in segments)
    ready=not state['processed'] or state['linear']>=1. or state['angular']>=.5
    if not ready and not unsettled and near:
        self.seen.add(key)
        state['skipped']+=1
        self.decisions.append(dict(t=rec['t_sim'],frame_id=rec['view_index'],robot_id=robot_id,
            status='deferred',reason='gmapping_motion_gate',inserted=False,matching_attempted=False,
            resampled=False,neff=float(1/(self.weights@self.weights)),
            covariance=self.odom.covariance.tolist(),pose=list(self.odom.pose),
            motion_gate=dict(state)))
        return []
    # A motion-admitted scan gets the existing improved proposal, independent
    # of the old one-second attempt scheduler. No proposal/noise changes.
    if ready and not unsettled and near:
        self.last_attempt=-math.inf
    result=RaoBlackwellizedGrid._observe(self,rec,segments,camera_xy=camera_xy,robot_id=robot_id)
    if not unsettled and near:
        self.decisions[-1]['motion_gate']=dict(state)
        state['processed']+=1
        state['linear']=state['angular']=0.
    return result


def _export(self):
    out=RaoBlackwellizedGrid.export(self)
    out['rbpf_update']=OPTION
    out['motion_gate']={**self._motion_gate,'linear_update_m':1.,'angular_update_rad':.5,
                        'temporal_update_s':-1.,'resample_threshold':.5}
    return out
