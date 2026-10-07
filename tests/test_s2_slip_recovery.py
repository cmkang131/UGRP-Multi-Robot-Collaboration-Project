import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from test_solo_cyan_v106 import static, cal, FakePose, FakeVision
from harness import zone_solo_cyan_slip_recovery as m


def profiles():
    return json.loads(Path('configs/s2_motion_v7_pulse_cal_v1.json').read_text())['profiles']


def slip(t, status='slip_replaced'):
    return dict(t=t, end=t+.75, direction=[0,.65], visual_delta=[0,.001,0],
                status=status, complete_visual=status!='unknown_preserved')


def runtime_stub(rows):
    r=m.Runtime.__new__(m.Runtime)
    r.slip_recovery=m.OPTION; r.state='carry'
    r.last_report=NS(x_m=0.,y_m=0.,yaw_rad=0.)
    r.flow=NS(audit=dict(rows=rows),measure_small=False)
    r.slip_progress=m.SlipProgress();r.slip_cursor=0;r.slip_backup=None
    r.slip_blocks=[];r.slip_recovery_rows=[];r.slip_replan=False;r.slip_exhausted_logged=False
    r.pulse_profiles=profiles();r.path=[];r.path_goal=None;r.map={};r.cal_rows=[]
    r.soft=lambda *args:None
    return r


def test_default_off_command_record_bytes(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),
            vision_factory=FakeVision,**kw)
        for cls,kw in [(m.Previous,{}),(m.Runtime,{}),(m.Runtime,dict(slip_recovery='off'))]]
    try:
        a=[r.initial_commands(0.,{'r3':{1:2000,3:600,4:2200,5:1400,6:1500}}) for r in rs]
        assert len(set(json.dumps(x).encode() for x in a))==1
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_nav2_strict_time_radius_and_no_count_threshold():
    p=m.SlipProgress()
    for t in range(10):assert p.observe(slip(t)) is None
    hit=p.observe(slip(10));assert hit['n']==11 and hit['t']==10.75
    p=m.SlipProgress()
    # A fixed N cannot trigger at high frame/pulse frequency.
    for i in range(50):assert p.observe(slip(i*.1)) is None
    p=m.SlipProgress()
    for i in range(40):
        x=slip(i);x['visual_delta']=[0,.2,0]
        assert p.observe(x) is None


def test_unknown_normal_turn_and_unmeasured_pulse_break_streak():
    for status in ('unknown_preserved','normal_preserved','interrupted'):
        p=m.SlipProgress()
        for i in range(10):p.observe(slip(i))
        assert p.observe(slip(10,status)) is None and p.start is None
    for key in ('1:turn:0.35:0.10','1:left:0.35:0.06','1:left:-0.65:0.65'):
        p=m.SlipProgress();p.observe(slip(0));p.issued(m.action_of(profiles()[key]),profiles())
        assert p.start is None


def test_runtime_stop_backup_timeout_replan_and_direction_filter(monkeypatch):
    r=runtime_stub([slip(t) for t in range(11)])
    monkeypatch.setattr(m,'plan_path',lambda *a,**k:dict(waypoints_m=[[0,0],[.5,0]]))
    def base(self,*a,**k):
        proposed=m.action_of(profiles()['1:left:0.65:0.65'])
        if '1:left:0.65:0.65' not in self.pulse_profiles:proposed=m.action_of(profiles()['1:forward:0.35:0.10'])
        return [proposed],False
    monkeypatch.setattr(m.Previous,'drive',base)
    assert r.drive([.5,0],11)==([dict(kind='hold')],False)
    a,done=r.drive([.5,0],11.05)
    assert not done and a[0]['left']==-.35 and a[0]['turn']==0 and a[0]['duration_s']==.06
    assert not any(x['kind']=='arm' for x in a)
    assert r.flow.measure_small
    a,done=r.drive([.5,0],21.1)
    assert not r.flow.measure_small and r.slip_backup is None and not done
    assert a[0]['forward']==.35 and a[0]['left']==0
    assert any(x['event']=='replan' for x in r.slip_recovery_rows)
    end=next(x for x in r.slip_recovery_rows if x['event']=='backup_end')
    assert end['timeout'] and not end['measured_success'] and end['progress_m']==0


def test_unknown_backup_never_invents_distance_and_complete_rgb_can_finish(monkeypatch):
    r=runtime_stub([slip(t) for t in range(11)])
    monkeypatch.setattr(m,'plan_path',lambda *a,**k:dict(waypoints_m=[[0,0],[.5,0]]))
    monkeypatch.setattr(m.Previous,'drive',lambda *a,**k:([dict(kind='hold')],False))
    r.drive([.5,0],11)
    x=slip(12,'unknown_preserved');x['direction']=[0,-.35]
    r.flow.audit['rows'].append(x);r.drive([.5,0],13)
    assert np.array_equal(r.slip_backup['delta'],np.zeros(3))
    x=slip(14,'normal_preserved');x['direction']=[0,-.35];x['visual_delta']=[0,-.31,0]
    r.flow.audit['rows'].append(x);r.drive([.5,0],15)
    assert r.slip_backup is None
    end=next(x for x in r.slip_recovery_rows if x['event']=='backup_end')
    assert end['measured_success'] and end['progress_m']==pytest.approx(.31)


def test_inverse_profile_is_calibrated_loaded_bounded_and_registration_fixed(static):
    for d in ([1.,0.],[-1.,0.],[0.,1.],[0.,-1.]):
        p=m.inverse_profile(profiles(),np.array(d),0.)
        assert p and p['loaded'] and abs(p['u'])==.35
        assert np.dot(m.direction(m.action_of(p)),d)<0
        assert np.linalg.norm(p['mean_delta'][:2])/p['duration_s']<=.15
    c=json.loads(Path('experiments/2026-10-06-s2-realism/slip-recovery-criteria.json').read_text())
    assert all(c['parameters'][k]==v for k,v in m.PARAMS.items())
    for kw in (dict(slip_recovery='bad'),dict(slip_recovery=m.OPTION)):
        with pytest.raises(ValueError):m.Runtime(static,None,None,**kw)
