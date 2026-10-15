"""Command/port integration counterexample, no physics or renderer."""
from types import SimpleNamespace
import pytest
from harness.reloc17_servo_wait import ServoWait
from sim.camera_robot_port import CameraRobotPort


class Robot:
    def __init__(self):
        self.servo_command_pulses={1:2000,3:740,4:2320,5:1320,6:1500}
        self.motors=[]
    def set_motor_commands(self,x):self.motors=list(x)
    def set_servo_pulses(self,x):self.servo_command_pulses.update(x)
    def __getattr__(self,k):raise AssertionError('privileged read:'+k)


def execute(candidate,terminal=False):
    r=Robot();world=SimpleNamespace(robot=lambda rid:r,data=SimpleNamespace(time=0.))
    p=CameraRobotPort(world,'r3',allow_mecanum=True);wait=ServoWait()
    look=dict(t=0.,kind='look',pan_pulse=2000);wait.issued(look,r.servo_command_pulses.copy())
    p.apply({k:v for k,v in look.items() if k!='t'},0.)
    for tick in range(400):p.tick(tick*.0005)
    hold=dict(t=.2,kind='hold')
    command=wait.command(hold,t=.2,terminal=terminal) if candidate else hold
    if command['kind']=='hold':p.hold(.2)
    else:p.apply({k:v for k,v in command.items() if k!='t'},.2)
    for tick in range(400,1201):p.tick(tick*.0005)
    return r,p,command


def test_wait_completes_pan_instead_of_freezing_1899_pwm():
    old,_,_=execute(False);new,p,c=execute(True)
    assert old.servo_command_pulses[6]==1899  # saved-run 35.91deg counterexample
    assert new.servo_command_pulses[6]==2000
    assert new.motors==[0.]*4
    assert c['kind']=='mecanum' and not p._servo_targets


def test_terminal_hold_still_revokes_trajectory():
    r,p,c=execute(True,terminal=True)
    assert c['kind']=='hold' and r.servo_command_pulses[6]==1899
    assert not p._servo_targets and r.motors==[0.]*4


def test_default_off_bundle_is_identical_and_on_is_explicit():
    from scripts.run_self_map_diagnostic import bundle
    a=bundle('a'*40,93584,60)
    assert a==bundle('a'*40,93584,60,reloc17_servo_wait_v1=False)
    assert bundle('a'*40,93584,60,reloc17_servo_wait_v1=True)['options']['reloc17_servo_wait_v1'] is True
    with pytest.raises(ValueError):bundle('a'*40,93584,60,reloc17_servo_wait_v1=1)
