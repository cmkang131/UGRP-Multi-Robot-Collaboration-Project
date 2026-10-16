import copy,json
from types import SimpleNamespace as NS
import cv2,numpy as np,pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision,rt
from harness.zone_solo_cyan_visual_fix import Runtime,Previous,install,flow_pair,FLOW
from harness import zone_s2_realism_contract_v123 as c


def test_default_and_explicit_off_bytes(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)
        for cls,kw in [(Previous,{}),(Runtime,{}),(Runtime,dict(visual_update='off',visual_stall='off'))]]
    try:
        for r in rs:
            r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}});r.last_report=r.pose.report(1.);r.state='carry';r.receipt=True
        for t in (1.,1.05,1.1,1.2,1.65,1.8):
            actions=[r.step(t) for r in rs]
            assert len(set(json.dumps(x).encode() for x in actions))==1
            for r,rows in zip(rs,actions):
                for rid,a in rows:r.on_command(rid,t,a)
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def make_provider():
    from harness.zone_solo_cyan_camera_v3 import build_provider
    from harness import vision_loc_protocol as vp
    src=build_provider(c.old.hp.resolve(c.old.MAP_ID)[0],c.ROOT/c.old.CALIBRATION,c.old.CALIBRATION_SHA,7)
    p=src.provider;p.servo={1:1500,**rt.high.HIGH};p.high_since=-10
    pf=p.loc._pf;pf.init_gaussian((1.6,0.,0.),(.02,.02,.03));pf.load.loaded=True
    return src,pf,vp.load_vis3()[0]


def test_rejected_scan_is_prediction_only_on_real_pf_and_unloaded_delegates():
    sources=[make_provider() for _ in range(3)]
    try:
        a,b,legacy=[x[1] for x in sources];vl=sources[0][2]
        stats=install(a,vl);n=len(a.columns)
        # An image edge at row 450 is inconsistent with the loaded HIGH wall
        # geometry at this prior. It must not change weights or imply a fix.
        obs=vl.ColumnObs(a.columns.copy(),np.ones(n,int)*vl.EDGE,np.full(n,450.),np.full(n,450.),np.zeros(n,int),np.full(n,np.nan),np.full(n,np.nan))
        out=a.update_obs(2.,obs,rt.high.HIGH);b.update_obs(2.,None,rt.high.HIGH)
        assert stats['rejected']==1 and not out['measured']
        np.testing.assert_array_equal(a.px,b.px);np.testing.assert_array_equal(a.logw,b.logw)
        assert a.last_scan_t==b.last_scan_t and a.stats['scan_updates']==0
        # Loaded gate is not installed into another instance or shared source.
        legacy.update_obs(2.,obs,rt.high.HIGH);assert legacy.stats['scan_updates']==1
    finally:
        for src,_,_ in sources:src.close()


def test_good_scan_still_updates_real_pf():
    src,pf,vl=make_provider()
    try:
        stats=install(pf,vl);pf.init_gaussian((1.6,1.,0.),(.005,.005,.005));pf.t=2.
        vb,vt=pf.expected(np.array([[1.6,1.,0.]]),rt.high.HIGH)
        n=len(pf.columns);valid=(vb[0]>4)&(vb[0]<470)
        obs=vl.ColumnObs(pf.columns.copy(),np.where(valid,vl.EDGE,vl.NONE),vb[0],vb[0],np.zeros(n,int),np.full(n,np.nan),np.full(n,np.nan))
        pf.update_obs(2.,obs,rt.high.HIGH)
        assert stats['accepted']==1 and pf.stats['scan_updates']==1
    finally:src.close()


def textured():
    a=np.full((480,640,3),170,np.uint8)
    for x in range(100,560,50):
        for y in range(70,370,50):cv2.rectangle(a,(x,y),(x+12,y+12),(90,90,90),-1)
    return a


def test_flow_stationary_changed_texture_and_cargo_unknown():
    a=textured();same=flow_pair(a,a);assert same['status']=='stationary_view' and same['tracks']>=6
    moved=cv2.warpAffine(a,np.float32([[1,0,5],[0,1,0]]),(640,480),borderValue=(170,170,170))
    changed=flow_pair(a,moved);assert changed['status']=='changed_view' and changed['median_px']==pytest.approx(5,abs=.1)
    uniform=np.full_like(a,170);assert flow_pair(uniform,uniform)['status']=='unknown_texture'
    cyan=a.copy();cyan[:]=(20,200,220);assert flow_pair(cyan,cyan)['status']=='unknown_texture'


def test_stall_is_log_only_and_servo_change_cancels(monkeypatch):
    monkeypatch.setattr(Previous,'on_frames',lambda *a:None)
    monkeypatch.setattr(Previous,'on_command',lambda *a:None)
    r=object.__new__(Runtime);r.robot_id='r3';r.visual_stall='lk_pulse_v1';r.flow_frame=None;r.flow_pending=None;r.flow_streak=0;r.flow_rows=[];r.state='carry';r.servo={1:1500,**rt.high.HIGH}
    soft=[];r.soft=lambda code,t:soft.append((code,t))
    r.robot_id='r3';a=textured()
    for i in range(3):
        r.flow_pending=dict(t=i,end=i+.2,before=a,before_t=i,servo=dict(r.servo),commands=[dict(kind='mecanum',forward=.35)],expected_delta=[.06,0,0])
        r.on_frames(i+.2,{'r3':(dict(frame_id=i),a)})
    assert len(soft)==3 and r.flow_rows[-1]['would_stop'] and r.state=='carry'
    r.flow_pending=dict(t=4);r.on_command('r3',4,dict(kind='arm',servo_id=5,pulse=1800))
    assert r.flow_pending is None and r.flow_streak==0 and r.flow_frame is None


def test_admission_defaults_fresh_seed_and_result_reporting(tmp_path):
    from scripts.run_s2_realism_v123 import parser,run
    args=parser().parse_args(['--expected-source-sha','a'*40,'--output',str(tmp_path)])
    assert args.visual_update==args.visual_stall=='off'
    b=c.bundle('a'*40,seed=1047,**c.NEW_OPTIONS);c.require_execution(b)
    for seed in (1045,1046,1029):
        bad=copy.deepcopy(b);bad['task']['seed']=seed
        with pytest.raises(ValueError,match='unregistered'):c.require_execution(bad)
    for field,value in [('scenario','S3'),('research_result',True),('confirmation_sample',True)]:
        bad=copy.deepcopy(b);bad[field]=value
        with pytest.raises(ValueError):c.require_execution(bad)
    def no_world(*a,**kw):raise RuntimeError('synthetic preflight error')
    result=run(b,tmp_path/'no-sim',backend_factory=no_world)
    assert result['status']=='HOST_ERROR' and result['options']['visual_stall']=='lk_pulse_v1'


def test_flow_window_accumulates_net_motion_and_does_not_count_reversals(monkeypatch):
    monkeypatch.setattr(Previous,'on_frames',lambda *a:None)
    monkeypatch.setattr(Previous,'on_command',lambda *a:None)
    r=object.__new__(Runtime);r.robot_id='r3';r.visual_stall='lk_pulse_v1';r.flow_frame=textured();r.flow_frame_t=0.;r.flow_pending=None
    r.flow_streak=0;r.flow_rows=[];r.state='carry';r.servo={1:1500,**rt.high.HIGH};r.soft=lambda *a:None
    m=json.loads((c.ROOT/c.PULSE_MODEL).read_text());r.pulse_profiles=m['profiles']
    pos=dict(kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1)
    for i in range(5):
        r.on_command('r3',float(i),pos)
        r.on_frames(i+.3,{'r3':(dict(frame_id=i),textured())})
    assert len(r.flow_rows)==1 and len(r.flow_rows[0]['commands'])>=4
    assert r.flow_rows[0]['would_stop']
