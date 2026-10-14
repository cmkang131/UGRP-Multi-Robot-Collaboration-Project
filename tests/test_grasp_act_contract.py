import copy
import pytest
from harness.grasp_act_contract import *

def issued(t=0.):
    return {'t':t,'wheels':[0.]*4,'duration_s':[0.]*4,'pwm':{str(s):1500 for s in SERVOS}}

def observation(t=0.):
    return {'schema':SCHEMA,'sample_id':f'episode:{t}:r1','robot_id':'r1','t':t,
        'skill':'grasp','object_kind':'long_beam','role':'teal','destination_zone':'none','skill_elapsed_s':t,'pwm_elapsed_s':t,
        'issued':[issued(t)]*HISTORY,'rgb':[{'path':'rgb/a.jpg','sha256':'a'*64,'robot_id':'r1','t':t} for _ in RGB_LAGS_S]}

def test_real_wheel_duty_roundtrip_expiry_and_dead_zone():
    from sim.grasp_act_port import duty_wheels,DutyActPort
    w,dt=duty_wheels([.07,.035,.01]);x=issued();x.update(wheels=w,duration_s=dt)
    assert set(map(abs,w))<={0.,.35} and len(set(dt))>1
    y=decode_action(encode_action(x));assert y['wheels']==w and y['duration_s']==pytest.approx(dt)
    x['wheels'][0]=.30
    with pytest.raises(ValueError,match='wheel range'):command(x)
    p=DutyActPort.__new__(DutyActPort);p._motor_commands=tuple(w);p._wheel_deadlines=[.01,.02,.03,.04]
    p._command_expires_at=None;p._drive_expires_at=None;p._advance_servos=lambda t:None
    p._set_motors=lambda v:setattr(p,'_motor_commands',tuple(v))
    p.tick(.015);assert p._motor_commands[0]==0 and p._motor_commands[1]!=0
    p.tick(.15);assert p._motor_commands==(0.,)*4

def test_owned_clocks_history_and_privileged_fields():
    x=observation();assert HISTORY>=16 and len(context(x))==CONTEXT_DIM
    clock=IssuedClock();c=issued();assert clock.observe('grasp',0.,c['pwm'])['pwm_elapsed_s']==0.
    assert clock.observe('grasp',1.,c['pwm'])=={'skill_elapsed_s':1.,'pwm_elapsed_s':1.}
    c['pwm']['1']=1600
    assert clock.observe('grasp',2.,c['pwm'])=={'skill_elapsed_s':2.,'pwm_elapsed_s':0.}
    for k in ('qpos','held','peer_state','pose'):
        y=copy.deepcopy(x);y[k]=0
        with pytest.raises(ValueError,match='whitelist'):validate_observation(y)
    refs=[{'t':i*.1} for i in range(61)]
    assert [round(6-r['t'],1) for r in image_history(refs,6)]==list(RGB_LAGS_S)

def test_chunks_do_not_bridge_excluded_navigation_or_wait_gaps():
    obs=[observation(t) for t in (0.,.1,2.)]
    labels=[{'sample_id':o['sample_id'],'skill':'grasp','object_kind':'long_beam',
             'done':i==2,'terminal_reason':'command_sequence_complete' if i==2 else None,
             'clean_teacher_command':issued(o['t'])} for i,o in enumerate(obs)]
    windows=training_windows(obs,labels,chunk=4)
    assert windows[0]['action_is_pad']==[False,False,True,True]
    assert windows[2]['action_is_pad']==[False,True,True,True]
    labels[2]['terminal_reason']='contact_confirmed'
    with pytest.raises(ValueError):training_windows(obs,labels)
