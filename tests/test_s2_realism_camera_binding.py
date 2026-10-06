from types import SimpleNamespace as NS
import numpy as np
import pytest
from sim.s2_realism_camera_binding import bind_camera
from sim import masterpi_camera_review_v3 as camera


def test_runtime_camera_refresh_and_reconfigure_cannot_restore_old_mount(monkeypatch):
    import mujoco
    from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
    from sim import masterpi_camera_profile as archived
    m=NS(cam_pos=np.zeros((1,3)),cam_quat=np.zeros((1,4)),cam_resolution=np.zeros((1,2)),
         cam_sensorsize=np.zeros((1,2)),cam_intrinsic=np.zeros((1,4)))
    c=NS(model=m,data=None,robot_cam_cid=0,width=640,height=480,renderer=None)
    c._configure_measured_robot_camera=lambda:MasterPiDynamicsV2._configure_measured_robot_camera(c)
    monkeypatch.setattr(mujoco,'mj_forward',lambda *a:None)
    c._configure_measured_robot_camera()
    assert m.cam_pos[0] == pytest.approx(archived.CAMERA_LOCAL_POS_M)
    bind_camera(c)
    for callback in (c._sync_real_camera_mount,c._configure_measured_robot_camera):
        callback()
        assert m.cam_pos[0] == pytest.approx(camera.POSITION_M)
        assert m.cam_quat[0] == pytest.approx(camera.QUAT_WXYZ)
        assert m.cam_intrinsic[0] == pytest.approx(archived.mujoco_pixel_intrinsic(640,480))


def test_new_bundle_keeps_startup_failure_source_and_uses_fresh_probe():
    from harness import zone_s2_realism_contract_v110 as c
    b=c.bundle('a'*40,seed=1033,stage_probe='pick',pickup_slot='P1-2')
    assert b['execution_bundle_id']=='zone-s2-realism-v110'
    assert 'sim/s2_realism_camera_binding.py' in b['source_sha256']
    assert 'sim/s2_realism.py' in b['source_sha256']
    with pytest.raises(ValueError):
        c.bundle('a'*40,seed=1032,stage_probe='pick',pickup_slot='P1-2')
