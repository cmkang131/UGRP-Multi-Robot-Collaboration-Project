"""No physics/render: RGB counterexamples, epoch barrier and nominal motion."""
import copy
import math
from types import SimpleNamespace

import numpy as np
import pytest

from sim import release_regrasp as check
from sim import release_regrasp_recovery as recovery
from sim.grasp_act_release_teacher import ReleaseTeacher, PairReleaseCode
from sim.release_global_observation import pair_choice, margin_report
from sim.release_axis_correction import correction_angle, plans


def frame(*, edge=False, empty=False, fresh=0):
    out=np.full((240,320,3),60,np.uint8)
    if not empty:
        out[15:225, (245 if edge else 15):305]=[5,220,150]  # long-beam H=40
    out[0,0]=fresh
    return out


def commands():
    return [dict(t=0.,pwm={1:1500,3:800,4:1900,5:2180,6:1500},wheels=[0.]*4),
            dict(t=1.4,pwm={1:1500,3:600,4:1650,5:2220,6:1500},wheels=[0.]*4)]


def test_rgb_requires_fresh_centered_shaft_and_completed_own_lift():
    before,after,settled=frame(),frame(fresh=1),frame(fresh=2)
    assert check.lift_evidence(before,after,settled,commands())['answer']=='yes'
    for bad,reason in [(frame(empty=True),'own_grip_shaft_not_framed'),
                       (frame(edge=True),'own_grip_shaft_not_framed')]:
        result=check.lift_evidence(before,after,bad,commands())
        assert result['answer']=='no' and result['reason']==reason
    assert check.lift_evidence(before,before,before,commands())['answer']=='unknown'
    for change in ('wheel','open','no_arm','pan','short'):
        cmd=commands()
        if change=='wheel':cmd[-1]['wheels'][0]=.35
        if change=='open':cmd[-1]['pwm'][1]=2000
        if change=='no_arm':cmd[-1]['pwm']=copy.deepcopy(cmd[0]['pwm'])
        if change=='pan':cmd[-1]['pwm'][6]=1700
        if change=='short':cmd[-1]['t']=.2
        assert check.lift_evidence(before,after,settled,cmd)['answer']=='unknown'


def teachers():
    result={}
    for rid,end in [('r1','teal'),('r2','blue')]:
        t=ReleaseTeacher(rid,end,{1:1500,3:782,4:1795,5:2195,6:1500},
            handoff_pose_estimate=None,zone_rect=(4.6,.4,.3,.7),reach_mode='pad_window_v2',
            odometry_profile='native_yaw_v1')
        t.belief.observe('released_band',[.20,0.,0. if end=='teal' else math.pi],0.,source='own_command')
        t.holding=False
        result[rid]=t
    return result


def drive_barrier(*, failures=(), lose_at_barrier=False):
    ts=teachers();barrier=check.RegraspBarrier(ts,7,0.,wheel_commands=lambda r:[0.]*4)
    schedules={r:[] for r in ts}; issued=[];captures=[]
    def schedule(rid,seq,now):
        schedules[rid]=[(now+dt,p) for dt,p in seq]
        issued.append((now,rid,copy.deepcopy(seq)))
    def capture(rid,now,label):
        captures.append((rid,now,label))
        return frame(edge=(rid in failures or (lose_at_barrier and rid=='r1' and label=='barrier')),
                     fresh=1+len(captures)%250)
    for k in range(1600):
        now=k*.1
        for rid,seq in schedules.items():
            while seq and seq[0][0]<=now+1e-9:
                _,p=seq.pop(0);ts[rid].pwm.update(p)
        result=barrier.tick(now,capture,schedule)
        if result in ('ready','failed'):return barrier,issued,captures
    raise AssertionError('finite verification failed to terminate')


def test_sequential_confirmation_retries_only_failed_robot_and_caps():
    b,issued,_=drive_barrier(failures=('r2',))
    assert b.failure=='regrasp_attempt_cap:r2:own_grip_shaft_not_framed'
    assert b.attempts=={'r1':1,'r2':3}
    assert b.confirmed=={'r1':True,'r2':False}
    retries=[e for e in b.records if e['event']=='retry']
    assert [e['robot'] for e in retries]==['r2','r2']
    last_r1=max(t for t,r,_ in issued if r=='r1')
    first_r2=min(t for t,r,_ in issued if r=='r2')
    assert last_r1<first_r2   # no partner command during own challenge
    assert len([e for e in b.records if e['event']=='confirmed' and e['robot']=='r1'])==1


def test_epoch_ack_and_fresh_loss_do_not_authorize_motion():
    b,_,_=drive_barrier()
    assert b.state=='ready' and all(b.confirmed.values())
    code=PairReleaseCode(b.robots)
    for r in b.robots:code.post(r,dict(phase='regrasp_confirmed_6'),10.)
    code.deliver(10.2)
    assert not code.ready('regrasp_confirmed_7',10.)
    code.post('r1',dict(phase='regrasp_confirmed_7'),11.)
    code.deliver(11.2)
    assert not code.ready('regrasp_confirmed_7',11.)
    code.post('r2',dict(phase='regrasp_confirmed_7'),11.2)
    code.deliver(11.4)
    assert code.ready('regrasp_confirmed_7',11.)
    b.teachers['r2'].pwm[1]=2000
    assert b.fresh(12.,lambda *a:frame(fresh=20))==('r2','confirmed_command_changed')
    b,_,_=drive_barrier(lose_at_barrier=True)
    assert b.failure and b.attempts=={'r1':3,'r2':1}
    assert not b.confirmed['r1']


def test_actual_issued_wheel_or_partner_arm_change_invalidates_test():
    for change in ('wheel','partner'):
        ts=teachers();wheels={r:[0.]*4 for r in ts}
        b=check.RegraspBarrier(ts,1,0.,wheel_commands=lambda r:wheels[r])
        b.tick(0.,lambda *a:frame(),lambda *a:None)
        if change=='wheel':wheels['r1'][0]=.35
        else:ts['r2'].pwm[3]+=20
        assert b.tick(.1,lambda *a:frame(fresh=1),lambda *a:None)=='failed'
        assert 'command' in b.failure and not any(b.confirmed.values())


def stripe(center=288, slope=0., width=110):
    out=np.full((480,640,3),60,np.uint8)
    for y in range(20,460):
        x=round(center+slope*(y-240))
        out[y,max(0,x-width//2):min(640,x+width//2)]=[5,220,150]
    return out


def test_own_image_center_and_clipping_do_not_fake_orientation():
    f=recovery.shaft_features(stripe(450,.15))
    assert f['unclipped'] and f['center_error']>.19 and f['slope_error']>.04
    assert not recovery.shaft_features(stripe(630))['unclipped']
    assert not recovery.shaft_features(np.zeros((480,640,3),np.uint8))['valid']
    assert not recovery.shaft_features(np.zeros((240,320,3),np.uint8))['valid']
    ambiguous=stripe(200,width=60)
    other=stripe(420,width=60)
    ambiguous[(other[:,:,1]>200)]=other[(other[:,:,1]>200)]
    assert recovery.shaft_features(ambiguous)['reason']=='shaft_ambiguous'


def test_command_camera_interaction_sign_and_optical_target():
    from sim.lookaround_localization import Camera
    from harness.visual_arm_v3 import solve_grip_site_ik,MOUNT_X_M
    pwm={1:2000,**solve_grip_site_ik((MOUNT_X_M+.152,0.,.095))}
    j,target=recovery.image_jacobian(Camera(),pwm)
    assert j[0,0]>0 and j[0,1]>0  # body left/CCW sends static beam right
    assert target[0]==pytest.approx((287.68910608896766-319.5)/640)
    assert abs(target[1])<1e-10 and np.linalg.cond(j)<100
    # Independent finite pinhole projection of a right-offset parallel line.
    cam,_=Camera().pose(pwm);origin,rotation=cam;K=Camera().K
    pts=np.array([[.25,-.02,.032],[.45,-.02,.032]])
    q=(pts-origin)@rotation;pix=q@K.T;pix=pix[:,:2]/pix[:,2,None]
    slope=(pix[1,0]-pix[0,0])/(pix[1,1]-pix[0,1])
    center=pix[0,0]+slope*(239.5-pix[0,1])
    delta=-np.linalg.solve(j,np.array([(center-319.5)/640,slope*192/640])-target)
    assert delta[0]==pytest.approx(-.02,abs=.001) and abs(delta[1])<.001


@pytest.mark.parametrize('kind',('centered','missing','stalled','budget','command_changed'))
def test_recovery_open_back_align_return_and_bounded_failures(kind):
    from sim.lookaround_localization import Camera
    t=teachers()['r1'];issued=[];seq=[];captures=[]
    def wheels(r,w,d,now):
        assert t.pwm[1]==2000
        issued.append((now,w,d))
    r=recovery.RealignRecovery(t,0.,camera=Camera(),undistort=lambda f:f,wheel_command=wheels)
    def schedule(rid,s,now):seq[:]=[(now+dt,p) for dt,p in s]
    def capture(rid,now,label):
        captures.append(now)
        return np.zeros((480,640,3),np.uint8) if kind=='missing' else stripe(288 if kind in ('centered','command_changed') else (320 if kind=='stalled' else 450))
    for i in range(400):
        now=i*.1
        while seq and seq[0][0]<=now+1e-8:
            _,p=seq.pop(0);t.pwm.update(p)
        if kind=='budget' and r.state=='align':r.lateral=recovery.MAX_LATERAL_M;r.yaw=recovery.MAX_YAW_RAD
        if kind=='command_changed' and r.state=='align':t.pwm[1]=1500
        status=r.tick(now,capture,schedule)
        if status in ('ready','failed'):break
    assert now<recovery.RECOVERY_CAP_S+1
    if kind=='centered':
        assert status=='ready' and r.returned
        assert [e['event'] for e in r.records if e['event'] in ('open_then_hover','aligned_before_pick')]==['open_then_hover','aligned_before_pick']
        assert any(all(v<0 for v in w) for _,w,_ in issued)
        assert any(all(v>0 for v in w) for _,w,_ in issued)
        assert all(now>=2.6 for now,_,_ in issued)
    else:
        reason={'missing':'shaft_missing','stalled':'no_image_progress_3s','budget':'motion_cap','command_changed':'open_hover_command_changed'}[kind]
        assert r.failure=='regrasp_realign_'+reason
    assert r.axial<=.08 and r.lateral<=recovery.MAX_LATERAL_M and r.yaw<=recovery.MAX_YAW_RAD


def test_realign_invalidates_peer_confirmation_and_forbids_peer_motion():
    ts=teachers();wheels={r:[0.]*4 for r in ts}
    fake=SimpleNamespace(tick=lambda *a:'pending')
    b=check.RegraspBarrier(ts,1,0.,wheel_commands=lambda r:wheels[r],recovery_factory=lambda *a:fake)
    b.confirmed['r1']=True
    b.retry('r2','own_grip_shaft_not_framed',0.,lambda *a:None)
    assert b.state=='realign' and not any(b.confirmed.values())
    assert b.attempts=={'r1':1,'r2':2}
    wheels['r1']=[.35]*4
    assert b.tick(.1,lambda *a:None,lambda *a:None)=='failed'
    assert b.failure=='regrasp_partner_command_during_realign'


def test_axis_rejection_is_not_pose_unobserved_and_has_bounded_path():
    ts=teachers()
    locs={r:SimpleNamespace(own=SimpleNamespace(x=np.array([4.6,.4,a])),
        decision={'accepted':True,'sigma':[.05,.05,.05]},
        global_matcher=SimpleNamespace(free=lambda q,**kw:np.ones(len(q),bool)))
        for r,a in [('r1',-math.pi/2+.24),('r2',math.pi/2+.25)]}
    reports={r:margin_report(locs[r],t,0.,axis_recovery=True) for r,t in ts.items()}
    assert all(r['reason']=='release_axis_unaligned' for r in reports.values())
    assert pair_choice(reports,tuple(ts),0.)['reason']=='global_pose_unobserved'
    choice=pair_choice(reports,tuple(ts),0.,axis_recovery=True)
    assert choice['action']=='axis_correct' and choice['reason']=='release_axis_unaligned'
    angle=correction_angle(choice)
    assert angle==pytest.approx(-math.radians(5))
    with pytest.raises(ValueError,match='unconfirmed'):
        plans(locs,ts,angle,0.)
    for t in ts.values():t.holding=True
    moves=plans(locs,ts,angle,0.)
    assert moves.keys()==ts.keys() and all(moves.values())
    from sim.visible_belief import odometry
    for rid,steps in moves.items():
        nominal=np.zeros(3)
        for w,d in steps:
            assert all(v==0. or .04<=v<=.1 for v in d)
            nominal+=odometry([v*duration/.1 for v,duration in zip(w,d)],.1,'native_yaw_v1')
        assert nominal[2]==pytest.approx(angle)
        (x,y),(ox,oy),_=ts[rid].end_and_outward(0.)
        assert nominal[:2]==pytest.approx([(y-.3*oy)*angle,-(x-.3*ox)*angle])
    with pytest.raises(ValueError,match='disagreement'):
        correction_angle(dict(axis_errors_rad=[.01,.3]))
    with pytest.raises(ValueError,match='unobserved'):
        correction_angle(dict(axis_errors_rad=[None,.3]))
    locs['r1'].global_matcher.free=lambda q,**kw:np.zeros(len(q),bool)
    with pytest.raises(ValueError,match='clearance'):
        plans(locs,ts,angle,0.)


def test_default_off_and_aligned_margin_choices_unchanged():
    rows={r:dict(kind='localized_margin',margin_m=.4,lateral_clearance_m=.2,expected_slack_m=.8)
          for r in ('r1','r2')}
    assert pair_choice(rows,tuple(rows),1.)==pair_choice(rows,tuple(rows),1.,axis_recovery=True)
