"""Per-frame issued-command increments/covariance; no observation or truth input."""
import numpy as np
from harness.self_pulse_odom import PulseOdometry
from harness.e2e_rgb_vo import between,compose


def increments(frames, commands):
    result={}
    for name in dict.fromkeys(r['sequence'] for r in frames):
        rows=[r for r in frames if r['sequence']==name]
        odom=PulseOdometry();odom.command(dict(kind='initial_servo_command',t=0,pulses=rows[0]['servo']))
        pending=[];odom.step_callback=lambda delta,variance:pending.append((np.asarray(delta).copy(),np.asarray(variance).copy()))
        index=0;previous=np.zeros(3)
        for row in rows:
            while index<len(commands) and commands[index]['t']<=row['t']:
                command=commands[index]
                odom.command(dict(kind='mecanum',t=command['t'],duration_s=command['duration_s'],
                    **{command['axis']:command['value']}));index+=1
            pose=np.asarray(odom.advance(row['t']));delta=between(previous,pose);previous=pose.copy()
            # Same SE(2) Jacobian propagation as self_pulse_odom, reset at each
            # frame. v122's callback supplies independent per-tick variance;
            # the accumulated pose covariance is NOT an increment covariance.
            relative=np.zeros(3);covariance=np.zeros((3,3))
            for d,variance in pending:
                c,s=np.cos(relative[2]),np.sin(relative[2]);rotation=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
                world_delta=rotation@d;jacobian=np.eye(3);jacobian[:2,2]=[-world_delta[1],world_delta[0]]
                covariance=jacobian@covariance@jacobian.T+rotation@np.diag(variance)@rotation.T
                relative=compose(relative,d)
            pending.clear()
            result[name,row['frame_id']]=dict(command_delta=delta.tolist(),command_covariance=covariance.tolist())
    return result
