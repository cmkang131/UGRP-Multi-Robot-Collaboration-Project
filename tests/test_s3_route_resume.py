import json
from types import SimpleNamespace
import pytest
from harness import zone_s3_route_resume as resume
from scripts.run_s3_integer_carry import release_completes_probe, attach_endpoint
from scripts.run_s3_stage_origin import previous


def test_default_off_leaves_methods_and_objects_unchanged():
    marker = object()
    assert resume.attach(marker) is marker
    with pytest.raises(ValueError): resume.Options(final_release_only=1)


@pytest.mark.parametrize('segments', (2,3))
def test_real_checkpoint_increment_precedes_completion_predicate(segments):
    from harness.zone_final_pair_skill import V3Controller
    from scripts.run_s3_integer_carry import release_completes_probe as old
    c = SimpleNamespace(seg=0,segments=list(range(segments)),rid='r1',claims={},
        log=lambda *a,**k:None,set=lambda *a,**k:None)
    b = dict(registered_route=list(range(segments+1)))
    for completed_segment in range(segments-1):
        V3Controller._cp_open(c,1.,False)
        assert c.seg==completed_segment
        V3Controller._cp_open(c,1.,True)
        assert c.seg==completed_segment+1
        assert not resume.release_completes_probe(c,b)
    assert old(c,b)  # saved premature-stop counterexample
    assert resume.release_completes_probe(c,{})  # old single-stage semantics


def test_final_release_requires_last_segment_idle_open_floor_contract():
    calls=[]
    c=SimpleNamespace(seg=0,segments=[1,2,3],failure=None,floor_return_verified=True,
        _released=lambda *a:calls.append(a),_issued=lambda:{1:2000},
        port=SimpleNamespace(hold=lambda t:calls.append(('hold',t))))
    ep=SimpleNamespace(controller=c)
    resume.attach(ep,resume.CANDIDATES['completion'])
    c._released(1.,True)
    assert not getattr(c,'s3_first_release_complete',False)
    c.seg=2;c._released(2.,False)
    assert not getattr(c,'s3_first_release_complete',False)
    c.floor_return_verified=False;c._released(3.,True)
    assert not getattr(c,'s3_first_release_complete',False)
    c.floor_return_verified=True;c._released(4.,True)
    assert c.s3_first_release_complete and calls[-1]==('hold',4.)


def test_saved_floor_pose_through_outer_tick_restores_before_look_and_waits_fresh_frame(tmp_path,monkeypatch):
    from tests import s3_stage_probe as probe
    from harness import zone_s3_recovery_contract as contract
    from harness.zone_s3_recovery_runtime import Runtime
    from harness import zone_s3_coarse_fine as cf
    from harness.zone_s3_alignment_ownership import ALL
    monkeypatch.setattr(probe,'contract',contract);monkeypatch.setattr(probe,'Runtime',Runtime)
    p=probe.Probe(tmp_path,monkeypatch)
    try:
        ep=p.eps['r1'];ctl=ep.controller
        cf.attach_endpoint(ep,cf.OPTION,refinements=ALL)
        resume.attach(ep,resume.CANDIDATES['combined'])
        # Exact last-issued camera posture from three-leg c5 failure.
        for k,v in {1:2000,3:807,4:1897,5:2187,6:1568}.items():
            p.issue('r1',dict(kind='look',pan_pulse=v) if k==6 else dict(kind='arm',servo_id=k,pulse=v),1.)
        ctl.arm.events.clear();ctl.arm.until=0.;ctl.arm.commanded=dict(ep.own.servo)
        ctl.state='align';ctl.seg=1;ctl.next_look=0.;ctl.beam_grasp_receipt=None
        looked=[]
        expected={**cf.pose_of('inspect'),6:1568}
        def look(now):
            assert all(ep.own.servo[k]==v for k,v in expected.items())
            looked.append(now)
            return ep.own.last_obs
        ctl.look=look
        monkeypatch.setattr('harness.zone_pair_highpose_frame_gate.controller_gate',lambda c:lambda *a:True)
        class Vision:
            def __init__(self,*a):pass
            def observe_beam(self,*a):return dict(visible=False,end_visible=False,reason='not_visible')
        monkeypatch.setattr(cf,'PairVision',Vision)
        monkeypatch.setattr(cf,'band_vision',lambda v:v)
        p.refresh(1.1);ctl.tick(1.1)
        assert not looked and ctl.arm.events
        deadline=ctl.arm.until
        p.arm(ep,deadline+.05)
        assert all(ep.own.servo[k]==v for k,v in expected.items())
        ep.own.last_obs['sim_time']=1.1
        ctl.tick(deadline+.05)
        assert not looked  # old frame at settled posture still forbidden
        p.refresh(deadline+.2);ctl.tick(deadline+.2)
        assert looked==[deadline+.2] and ep.own.servo[6]==1568
        assert not ctl.failure
    finally:p.runtime.close()


def test_frozen_24_candidates_two_seeds_and_parent_run_binding(monkeypatch,tmp_path):
    from scripts import run_s3_route_resume as runner
    from scripts.run_s3_route_resume_cohort import commands
    plan=json.loads((runner.ROOT/runner.PLAN).read_text())
    cc=commands(plan,'0'*40)
    assert len(cc)==len({c['name'] for c,_ in cc})==24
    for candidate in resume.CANDIDATES:
        cases=[c for c,_ in cc if c['candidate']==candidate]
        assert len(cases)==6 and len({(c['route_case'],c['seed']) for c in cases})==6
    b=runner.bundle('0'*40,0,'multi-left',15201)
    assert b['route_resume']['candidate']=='baseline' and b['seed']==15201
    assert b['provider_seeds']==dict(r1=15201,r2=15202,r3=15203)
    assert b['cap_sim_s']==60.
    assert b['controller_config']['options']['heading_mode']=='path_tangent_v1'
    assert 'coupled_beam_carry' in b['heading_exceptions']
    with pytest.raises(ValueError):runner.bundle('0'*40,0,'multi-left',999)
    # This spy executes the runner's two private globals rebindings; no physics.
    def middle(b,out):return previous.run(b,out)
    monkeypatch.setattr(runner.previous,'run',middle)
    write=runner.previous.previous.previous.stage.previous
    monkeypatch.setattr(write,'write',lambda *a:None)
    monkeypatch.setattr(write,'artifact_manifest',lambda *a:None)
    # bind requires a referenced attach_endpoint name even in this test spy.
    def inherited(b,out):
        assert callable(attach_endpoint)
        return dict(status='DEV_STAGE_FINISHED',legacy_stop=release_completes_probe(SimpleNamespace(seg=1,segments=[1,2]),b))
    monkeypatch.setattr(runner.previous.previous,'run',inherited)
    saved=runner.previous.previous.run
    b['route_resume']['candidate']='combined'
    result=runner.run(b,tmp_path)
    assert result['legacy_stop'] is False and runner.previous.previous.run is saved
