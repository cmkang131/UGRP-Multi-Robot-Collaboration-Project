"""Nonphysical input boundaries, carry kinematics and global degeneracy."""
import ast
from pathlib import Path
import numpy as np
import pytest
from harness.servo_camera_fk import transform_from_commands,CARRY_OPTION
from harness.mapbuild_static_registration import StaticRegistration,OPTION

POSE={1:2000,3:807,4:1897,5:2187,6:1500}


def test_carry_is_explicit_and_grip_is_not_camera_ancestor():
    opened,_=transform_from_commands(POSE,camera_pose='servo_fk_v1')
    assert transform_from_commands({**POSE,1:1500},camera_pose='servo_fk_v1')[0] is None
    for grip in (500,1500,1600,2000,2500):
        value,reason=transform_from_commands({**POSE,1:grip},camera_pose=CARRY_OPTION)
        np.testing.assert_array_equal(value[0],opened[0]);np.testing.assert_array_equal(value[1],opened[1])
    assert transform_from_commands(None)==(None,'off')
    with pytest.raises(ValueError):transform_from_commands({**POSE,'qpos':[]},camera_pose=CARRY_OPTION)
    assert transform_from_commands({**POSE,3:2500},camera_pose=CARRY_OPTION)[0] is None


def test_carry_adapter_has_no_global_mutation_and_supports_closed_floor():
    from harness.mapbuild_camera import adapters
    from harness import e2e_rgb_vo as vo
    from harness.mapbuild_rbpf import virtual_scan
    from harness.active_camera import transform
    old=(vo.ground,vo.floor_mask,vo.image_mask,transform)
    assert adapters()==(vo.ground_pair,virtual_scan)
    pair,scan=adapters(CARRY_OPTION)
    rng=np.random.default_rng(0);im=np.repeat(rng.integers(30,120,(480,640,1),dtype=np.uint8),3,axis=2)
    result=pair(im,im.copy(),{**POSE,1:1500})
    assert result['status']=='unknown_identical_rgb'
    assert (vo.ground,vo.floor_mask,vo.image_mask,transform)==old


def test_static_off_and_no_unseen_geometry():
    static=dict(bounds_m=[-1,1,-1,1],obstacles=[dict(id='wall_north',center_m=[0,1],half_extents_m=[1,.02])])
    assert StaticRegistration(static).register([[[0,0],[1,0]]])['static_from_own'] is None
    reg=StaticRegistration(static,option=OPTION)
    assert reg.register([])['reason']=='no_observed_wall_segments'
    assert reg.register([[[0,0],[.1,0]]])['reason']=='insufficient_near_points'
    with pytest.raises(ValueError):reg.register([[[float('nan'),0],[1,0]]])


def test_runtime_modules_no_truth_or_host_imports():
    for name in ('mapbuild_camera.py','mapbuild_static_registration.py','servo_camera_fk.py'):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'harness'/name).read_text())
        imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
        assert not any(any(s in name for s in ('mujoco','evaluate','audit','platform','subprocess')) for name in imports)
