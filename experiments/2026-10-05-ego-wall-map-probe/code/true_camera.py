"""True rendered camera of a recorded frame, for SCORING and DIAGNOSIS only.

Refs #216. **No physics is stepped** (``mj_forward`` on the recorded ``qpos`` only).

The detector's camera model is forward kinematics of the *commanded* servo pulses plus a
fixed elevation bias (``harness.visual_arm.camera_extrinsics``). The pixels were rendered
from the *actual* MuJoCo camera, which differs from that model (position servos sag under
gravity, and the FK frame origin is the arm-base axis, not the chassis origin). Scoring the
detector against a ground truth built from the same FK model therefore inherits the model
error. This module rebuilds the per-column floor trace from the camera MuJoCo really
rendered from, so a ground truth row / range is independent of the detector's camera model.

Nothing here may be imported by a detector code path.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

import markerless_probe as mp  # noqa: E402
import wall_probe as wp  # noqa: E402


class PoseColumnModel(mp.ColumnModel):
    """``ColumnModel`` whose camera pose is given directly instead of computed from servos.

    ``servo`` carries ``(origin (3,), R_bc (3x3, columns = optical axes in the base frame))``.
    The per-column floor trace maths is the parent's, line for line (same K, same row model),
    so ``rows`` / ``t_of_row`` / ``floor_point`` mean exactly what they mean for the detector.
    """

    def __post_init__(self):  # noqa: D105 - mirrors ColumnModel.__post_init__
        o, r_bc = self.servo
        o = np.asarray(o, float)
        rot = np.asarray(r_bc, float) @ mp.bias_rotation(self.bias_rad).T
        self.origin = o
        self._rot = rot
        u = self.columns.astype(float)
        a = rot @ (mp.K_INV @ np.stack([u, np.zeros_like(u), np.ones_like(u)]))
        b = rot @ (mp.K_INV @ np.array([0., 1., 0.]))
        v_bottom = mp.HEIGHT - 1.
        v_h = -a[2]/b[2]
        v_far = np.minimum(v_bottom - 1., v_h + 25.)
        q = []
        for v in (np.full_like(u, v_bottom), v_far):
            ray = a + v[None, :]*b[:, None]
            if np.any(ray[2] >= 0):
                raise ValueError('bottom image row does not see the floor')
            q.append(o[:, None] + ray*(-o[2]/ray[2]))
        q0, q1 = q
        d = q1 - q0
        d /= np.linalg.norm(d[:2], axis=0, keepdims=True)
        self.q0 = q0[:2].T
        self.d = d[:2].T
        self.alpha = (rot.T @ (q0 - o[:, None])).T
        self.beta = (rot.T @ np.vstack([d[:2], np.zeros(len(u))])).T
        self.gamma = rot.T @ np.array([0., 0., 1.])
        self._traces = {}


def elevation_deg(r_bc) -> float:
    """Elevation of the optical (forward) axis above the horizontal, degrees."""
    z = np.asarray(r_bc, float)[:, 2]
    return math.degrees(math.asin(max(-1., min(1., float(z[2])))))


class TrueCamera:
    """Recorded scene + trajectory -> the camera that actually rendered each frame."""

    def __init__(self, ep_dir: Path, robot: str):
        self.ep_dir = Path(ep_dir)
        self.robot = robot
        self.traj = [json.loads(l) for l in (self.ep_dir/'eval_only'/'trajectory.jsonl').read_text().splitlines()
                     if l.strip()]
        self.qa, _ = wp.free_joint_qaddr(self.ep_dir/'scene.xml', f'{robot}__base_free')
        self.model = mujoco.MjModel.from_xml_path(str(self.ep_dir/'scene.xml'))
        self.data = mujoco.MjData(self.model)
        self.cam_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, f'{robot}__robot_cam')
        if self.cam_id < 0:
            raise ValueError(f'camera {robot}__robot_cam not in scene.xml')
        arm = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, f'{robot}__arm_base')
        self.arm_base_x_m = float(self.model.body_pos[arm][0])      # chassis -> arm-base axis (FK frame origin)

    def at(self, idx: int):
        """(origin, R_bc, pose) of frame ``idx`` in the chassis-yaw floor frame.

        ``pose`` = (chassis x, chassis y, yaw) in the map frame. Origin / axes are expressed in
        the floor frame the FK uses: +x forward, +y left, +z up, **origin under the chassis
        origin**. (FK's own origin is the arm-base axis, ``arm_base_x_m`` ahead of that.)
        """
        st = self.traj[idx]
        self.data.qpos[:] = np.asarray(st['qpos'], float)
        self.data.qvel[:] = np.asarray(st['qvel'], float)
        self.data.time = float(st['t'])
        mujoco.mj_forward(self.model, self.data)                     # no mj_step
        q = self.data.qpos[self.qa:self.qa + 7]
        yaw = wp.yaw_from_quat(q[3:7])
        c, s = math.cos(yaw), math.sin(yaw)
        rot = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
        mat = self.data.cam_xmat[self.cam_id].reshape(3, 3)
        axes_w = np.stack([mat[:, 0], -mat[:, 1], -mat[:, 2]], axis=1)   # MuJoCo (x right, y up, -z fwd) -> OpenCV
        origin = rot.T @ (self.data.cam_xpos[self.cam_id] - np.array([q[0], q[1], 0.]))
        return origin, rot.T @ axes_w, (float(q[0]), float(q[1]), yaw)

    def column_model(self, idx: int, columns):
        origin, r_bc, pose = self.at(idx)
        return PoseColumnModel((origin, r_bc), 0., np.asarray(columns)), pose
