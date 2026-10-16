"""CPU-only state ownership regressions; no native model/physics/renderer."""
from types import SimpleNamespace as S
import sys
import numpy as np
import pytest
from scripts.warp10_control import port_state,apply_ports,mirror,restore,packet_exact,initial_proof,ADVANCED_FIELDS

def context():
    p=S(_servo_applied={1:1500.25},_servo_targets={1:1600},_servo_tick_time=2.,_servo_pulses={1:1600},
        _motor_commands=(.3,0,0,0),_wheel_deadlines=[2.1,None,None,None],_drive_expires_at=2.1,
        _busy_until=2.2,_command_expires_at=None,_frame_id=72)
    robot=S(servo_command_pulses={1:1500})
    data=S(qpos=np.array([1.,2.]),time=2.,contact=S(pos=np.array([[3.,4.,5.]])),ncon=1,nefc=2,nJ=4,nisland=0,nidof=0)
    return dict(ports={'r1':p},origin=2.,world=S(data=data,scene_xml='<mujoco/>',robot=lambda rid:robot))

def test_issued_state_roundtrip_does_not_reset_frame_history_or_alias_commands():
    parent,child=context(),context();parent['ports']['r1']._servo_applied[1]=1510.75
    snapshot=port_state(parent,ADVANCED_FIELDS);apply_ports(child,snapshot)
    assert child['ports']['r1']._servo_applied[1]==1510.75 and child['ports']['r1']._frame_id==72
    snapshot['r1']['values']['_servo_applied'][1]=999
    assert child['ports']['r1']._servo_applied[1]==1510.75
    bad=port_state(parent);bad['r1']['values']['measured_qpos']=np.ones(4)
    with pytest.raises(ValueError,match='unregistered'):apply_ports(child,bad)

def test_evaluation_mirror_copies_only_exported_fields_and_preserves_bytes(monkeypatch):
    monkeypatch.setitem(sys.modules,'mujoco',S())
    parent,child=context(),context();child['world'].data.qpos[:]=0
    packet=mirror(parent,[('qpos',),('time',),('contact','pos')]);restore(child,packet)
    assert packet_exact(child,packet)
    parent['world'].data.qpos[:]=99
    np.testing.assert_array_equal(child['world'].data.qpos,[1.,2.])
    assert set(packet['values'])=={('qpos',),('time',),('contact','pos')}

def test_initial_handshake_detects_changed_native_setup_or_scene():
    parent,child=context(),context();assert initial_proof(parent)==initial_proof(child)
    child['world'].data.qpos[0]+=.001
    assert initial_proof(parent)!=initial_proof(child)
