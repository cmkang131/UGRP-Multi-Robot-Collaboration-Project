"""Continuous ACT actuator port; no measured state, geometry or teacher access.

The old zone port used body-wrench units. Native v7 accepts normalized wheel
commands and has an input relay. This driver uses issued command signs only
for a one-tick breakaway command, then the fixed kinetic feedforward. Both
teacher and student use this exact driver; physics/contact settings are intact.
"""
import math
from sim.camera_robot_port import CameraRobotPort
from harness.grasp_act_contract import wheel_mix


def native_wheels(drive, previous):
    # Same constants as the fixed v7 drive profile, not inferred robot motion.
    desired = wheel_mix(drive)
    result = []
    for value, old in zip(desired, previous):
        if abs(value) < 1e-8:
            result.append(0.)
            continue
        level = min(1., abs(value)+1./12.)
        if old*value <= 0:
            level = max(.35, level)
        result.append(math.copysign(level, value))
    return tuple(result)


class ContinuousActPort(CameraRobotPort):
    def validate_action(self, action):
        if action.get('kind') != 'mecanum':
            return super().validate_action(action)
        if set(action) != {'kind','forward','left','turn','duration_s'}:
            raise ValueError('exact continuous mecanum fields required')
        drive = [float(action[k]) for k in ('forward','left','turn')]
        if not all(map(math.isfinite, drive)) or max(map(abs,wheel_mix(drive))) > 1.+1e-9:
            raise ValueError('normalized continuous wheel range required')
        if action['duration_s'] != .15:
            raise ValueError('continuous ACT lease is 150 ms')

    def apply(self, action, sim_time):
        if action['kind'] != 'mecanum':
            return super().apply(action, sim_time)
        self.validate_action(action)
        if not math.isfinite(sim_time):
            raise ValueError('finite command time required')
        self._command_expires_at = None
        self._set_motors(native_wheels([action[k] for k in ('forward','left','turn')],self._motor_commands))
        self._drive_expires_at = float(sim_time)+.15
        self._busy_until = self._drive_expires_at
        return dict(ok=True,robot_id=self.robot_id,kind='mecanum',sim_time=float(sim_time),
                    busy_until=self._busy_until,actuator_state=self._actuator_state())


def duty_wheels(drive, period=.1):
    """Pulse-width modulation above the real dead zone, on the 10 Hz clock.

    Desired body effort is converted with the existing wheel mixing matrix.
    0.35 means Board.py speed 35 (the board accepts signed percent, -100..100).
    Independent pulse widths preserve diagonal/yaw ratios without commanding
    a wheel in 1..30. This changes commands, never the physics profile.
    """
    desired=wheel_mix(drive);scale=max(.35,max(map(abs,desired)))
    wheels=[];durations=[]
    for v in desired:
        dt=period*abs(v)/scale
        if dt<.001: wheels.append(0.);durations.append(0.)
        else: wheels.append(math.copysign(.35,v));durations.append(dt)
    return wheels,durations


class DutyActPort(CameraRobotPort):
    """Same per-wheel pulse contract for teacher and independently running ACT."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._wheel_deadlines=[None]*4

    def validate_action(self,action):
        if action.get('kind')!='wheel_pulse':return super().validate_action(action)
        if set(action)!={'kind','wheels','duration_s'}:raise ValueError('exact wheel pulse fields required')
        from harness.grasp_act_contract import command,SERVOS
        command({'t':0.,'wheels':action['wheels'],'duration_s':action['duration_s'],
                 'pwm':{str(s):1500 for s in SERVOS}})

    def apply(self,action,sim_time):
        if action.get('kind')!='wheel_pulse':return super().apply(action,sim_time)
        self.validate_action(action)
        if not math.isfinite(sim_time):raise ValueError('finite command time required')
        self._command_expires_at=None
        self._wheel_deadlines=[sim_time+d if d else None for d in action['duration_s']]
        self._set_motors(tuple(action['wheels']))
        self._drive_expires_at=None
        self._busy_until=sim_time+max(action['duration_s'])
        return {'ok':True,'robot_id':self.robot_id,'kind':'wheel_pulse','sim_time':sim_time}

    def tick(self,sim_time):
        super().tick(sim_time)
        current=list(self._motor_commands)
        for i,deadline in enumerate(self._wheel_deadlines):
            if deadline is not None and sim_time>=deadline:
                current[i]=0.;self._wheel_deadlines[i]=None
        if tuple(current)!=tuple(self._motor_commands):self._set_motors(tuple(current))

    def stop(self):
        self._wheel_deadlines=[None]*4
        super().stop()
