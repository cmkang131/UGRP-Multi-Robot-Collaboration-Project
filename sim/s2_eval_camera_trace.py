"""Opt-in write-only camera/body geometry for evaluation; no forward/step/action."""
import numpy as np
from sim.masterpi_camera_review_v1 import quat_matrix


def camera_row(world,rid,t):
    m,d=world.model,world.data
    cid=world.robot(rid).robot_cam_cid;bid=int(m.cam_bodyid[cid])
    body_r=np.asarray(d.xmat[bid]).reshape(3,3)
    fk_r=body_r@quat_matrix(m.cam_quat[cid])
    cached_r=np.asarray(d.cam_xmat[cid]).reshape(3,3)
    tree=int(m.body_treeid[bid])
    return dict(t=t,controller_feedback=False,
        camera_cached_xyz_m=d.cam_xpos[cid].tolist(),camera_cached_optical_rotation=(cached_r@np.diag([1,-1,-1])).tolist(),
        camera_from_body_xyz_m=(d.xpos[bid]+body_r@m.cam_pos[cid]).tolist(),
        camera_from_body_optical_rotation=(fk_r@np.diag([1,-1,-1])).tolist(),
        gripper_xyz_m=d.xpos[bid].tolist(),gripper_rotation=body_r.tolist(),
        camera_local_position_m=m.cam_pos[cid].tolist(),camera_local_quaternion=m.cam_quat[cid].tolist(),
        robot_tree_asleep=int(d.tree_asleep[tree]),
        cached_pitch_deg=float(np.degrees(np.arcsin(np.clip(-cached_r[2,2],-1,1)))),
        body_derived_pitch_deg=float(np.degrees(np.arcsin(np.clip(-fk_r[2,2],-1,1)))))


def backend_class(base=None):
    if base is None:
        from sim.s2_idle_contacts import backend_class as previous
        base=previous()
    class Backend(base):
        def __init__(self,bundle,*a,**kw):
            self.eval_camera_trace=bundle['options'].get('eval_camera_trace','off')
            if self.eval_camera_trace not in ('off','pose_v1'):raise ValueError('unsupported eval_camera_trace')
            super().__init__(bundle,*a,**kw)
        def capture(self):
            out=super().capture()
            if self.eval_camera_trace=='pose_v1':
                self._append('eval_only/camera-pose.jsonl',camera_row(self.world,self.rid,self.now))
            return out
    return Backend
