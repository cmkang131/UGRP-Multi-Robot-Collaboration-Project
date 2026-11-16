import math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import pytest
from sim import servo_stiffness as s
from scripts import run_wall_servo_stiffness as run


def xml():
    return '<mujoco><option integrator="implicitfast"/><actuator>'+''.join(
        f'<position name="{robot}__servo_{name}" kp="4" joint="{robot}__{name}"/>'
        for robot in ('r1','r2','r3') for name in (*s.TORQUE_NM,'gripper_left','gripper_right'))+'</actuator></mujoco>'


def test_off_is_identity_without_parse_and_only_own_four_actuators_change():
    invalid='not XML\n  unchanged'
    assert s.transform_xml(invalid) is invalid
    before=ET.fromstring(xml())
    after=ET.fromstring(s.transform_xml(xml(),servo_stiffness='real_v1'))
    for a,b in zip(before.findall('actuator/position'),after.findall('actuator/position')):
        own=a.get('name').startswith('r3__') and 'gripper' not in a.get('name')
        if not own:assert a.attrib==b.attrib
        else:
            cap=float(b.get('forcerange').split()[1])
            assert float(b.get('kp'))*math.radians(.3)==pytest.approx(cap)
            assert b.get('dampratio')=='1' and b.get('forcelimited')=='true'
    with pytest.raises(ValueError):s.transform_xml(xml(),servo_stiffness='typo')


def test_compile_preserves_mass_contact_and_other_robots():
    mujoco=pytest.importorskip('mujoco')
    from sim.wall_servo_stiffness import make_scene
    from sim import wall_parallax_strafe as old
    # Build standard Scene XML without stepping/rendering.
    source=Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-texture-v1/tape-north/scene.xml')
    if not source.exists():pytest.skip('local old scene fixture')
    text=source.read_text()
    a=mujoco.MjModel.from_xml_string(text)
    b=mujoco.MjModel.from_xml_string(s.transform_xml(text,servo_stiffness='real_v1'))
    for field in ('body_mass','body_inertia','dof_damping','geom_friction','geom_contype','geom_conaffinity'):
        np.testing.assert_array_equal(getattr(a,field),getattr(b,field))
    for i in range(a.nu):
        name=a.actuator(i).name
        if not (name.startswith('r3__servo_') and name[10:] in s.TORQUE_NM):
            np.testing.assert_array_equal(a.actuator_gainprm[i],b.actuator_gainprm[i])
    assert b.opt.integrator==mujoco.mjtIntegrator.mjINT_IMPLICITFAST


def test_schedule_evaluation_return_cannot_change_actions(tmp_path):
    class Backend:
        now=1.3
        moves=[]
        def __init__(self,*a,**k):pass
        def reset(self,cap):pass
        def set_deadline(self,t):pass
        def issue(self,rid,action):self.moves.append(action)
        def capture(self):pass
        def eval_sample(self):return {'success':False,'pose':[999]*3}
        def advance_to(self,t):self.now=t
        def close(self):pass
    r=run.acquire_case('stiff-north',tmp_path/'north','test',Backend,servo_stiffness='real_v1')
    assert r['status']=='RECORDED' and r['frames']==181
    moves=[a for a in Backend.moves if a['kind']=='mecanum']
    assert len(moves)==8 and [a['left'] for a in moves]==[.65]*4+[-.65]*4
    assert len([a for i in range(551) for a in run.static_actions(i) if a['kind']=='mecanum'])==2


def test_default_scene_wrapper_bytes_and_frozen_explore_vocabulary():
    pytest.importorskip('mujoco')
    from sim import wall_parallax_strafe as old
    from sim import wall_servo_stiffness as new
    from harness.self_pulse_odom import model,profile_key
    bundle=dict(case='stiff-north',spawn=run.old.CASES['strafe-north']['spawn'],
        map_id='zone_wide_two_doors_final_v3',contact_profile='cargo_noslip_v1')
    a,b=old.make_scene(bundle,15101),new.make_scene(bundle,15101)
    assert a.config==b.config
    source=Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-strafe-v1/strafe-north-host-retry1/scene.xml')
    if source.exists():
        text=source.read_text()
        assert a.transform(text).encode()==b.transform(text).encode()
    moves=[r for i in range(301) for r in run.explore_actions(i) if r['kind']=='mecanum']
    assert len(moves)==12
    assert all(profile_key(action,False) in model()['profiles'] for action in moves)
