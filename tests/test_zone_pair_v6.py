"""No physics or models: production guards, own RGB and fake providers only."""
import base64
import copy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness.owncam_pose_source import OwnCamPoseSource, PoseReport
from harness.owncam_recovery_v6 import enable_provider, likelihood_quality
from harness.zone_pair_global import GlobalEnvelope, GlobalPairSweepGuard
from harness.zone_pair_relative import RelativeBeamTrack, BeamRelativeReport
from harness.zone_pair_v6_policy import pair_policy, informative_fix
from tests.test_zone_pair_grasp import real_pair

FIX = Path(__file__).parent/'fixtures/zone_pair_v6'
DATA = json.loads((FIX/'reports.json').read_text())


def source():
    p = OwnCamPoseSource(DATA['map'],DATA['params'],seed=628)
    enable_provider(p)
    return p


def good(t=0., **kw):
    return PoseReport(t,True,x_m=.6,y_m=0.,yaw_rad=0.,std_xy_m=.01,std_yaw_rad=.01,
                      last_fix_t=t,fix_age_s=0.,observation_quality={
                          'accepted':True,'informative':True,'settled':True,'ambiguous':False},**kw)


def obs(record):
    o = copy.deepcopy(record['observation'])
    data = (FIX/record['image']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==o['sha256']
    o['image'] = base64.b64encode(data).decode()
    return o


def saved_report(record):
    r = record['report']
    return PoseReport(t_est=r['t_est'],initialized=True,x_m=r['xyyaw'][0],y_m=r['xyyaw'][1],yaw_rad=r['xyyaw'][2],
                      **{k:r[k] for k in ('std_xy_m','std_yaw_rad','last_fix_t','fix_age_s','observation_quality')})


@pytest.mark.parametrize('record',DATA['records'],ids=lambda r:f"{r['run']}-{r['observation']['frame_id']}")
def test_saved_saturated_and_outlier_majority_are_not_fixes(record):
    p = source(); loc = p.loc
    r = record['report']; t = record['observation']['sim_time']
    servo = {int(k):v for k,v in record['observation']['actuator_state']['servo_pulses'].items()}
    loc.initialized=True;loc.t=t;loc.px[:]=r['xyyaw'];loc.servo=servo
    loc.last_tag_t=loc.last_informative_t=t-10
    ll = [float(loc._loglik(loc.px[:1],[d],servo)[0]) for d in record['detections']]
    assert ll == pytest.approx(record['per_feature_loglik'])
    before = loc.px.copy()
    loc.update(t,record['detections'],servo)
    assert loc.quality['accepted'] and not loc.quality['informative']
    assert loc.last_informative_t==t-10 and not informative_fix(p.report(t))
    assert np.array_equal(loc.px,before)
    if record['run']=='dev14':
        assert r['std_xy_m']==pytest.approx(.01896,abs=.00001)
        assert loc.quality['inlier_fraction']==pytest.approx(1/3)
    else:
        assert loc.quality['saturated']


def test_routine_look_preserves_posterior_rng_and_absolute_fix():
    p=source(); loc=p.loc; loc.initialized=True;loc.px[:]=[.6,0.,0.]
    loc.last_informative_t=loc.last_tag_t=0.
    before=(loc.px.copy(),loc.logw.copy(),copy.deepcopy(loc.rng.bit_generator.state))
    assert p.begin_observation(0.,{})
    p.begin_relocalization(0.,{})  # old driver API also means routine in v6
    assert p.loc is loc and np.array_equal(loc.px,before[0]) and np.array_equal(loc.logw,before[1])
    assert loc.rng.bit_generator.state==before[2] and loc.last_informative_t==0.
    assert not p.begin_observation(0.,{},lost=True)
    loc.inconsistent_frames=3
    assert p.begin_observation(0.,{},lost=True)
    assert p.begin_observation(0.,{},lost=True)
    assert not p.begin_observation(0.,{},lost=True)
    assert loc.recovery_frames==3 and loc.recovery_requests==2


def test_geometry_information_not_detector_acceptance_or_low_sigma():
    flat=np.full((20,4),math.log(.05)-6)
    assert not likelihood_quality(flat,np.zeros(20),floor=flat[0,0],curvature=100)['informative']
    valid=np.full((20,4),-.5)
    assert not likelihood_quality(valid,np.zeros(20),floor=-9,curvature=0)['informative']
    assert likelihood_quality(valid,np.zeros(20),floor=-9,curvature=100)['informative']


def test_delayed_routine_look_preserves_queued_inputs_and_capture_clock():
    from harness.zone_study_pose_delay import DelayedPoseSource
    p=source(); p.loc.t=0.
    delayed=DelayedPoseSource(p)
    delayed.on_command({'kind':'hold','t':1.})
    delayed.begin_observation(1.1,{},lost=False)
    assert len(delayed.pending)==2 and p.loc.t==0.
    delayed.report(1.2)
    assert len(delayed.pending)==1 and p.loc.t==pytest.approx(1.04)
    delayed.report(1.3)
    assert not delayed.pending and p.loc.t==pytest.approx(1.14)


def test_global_envelope_grows_without_fix_and_cannot_be_reset_by_relative_report():
    env=GlobalEnvelope();r=good();p0=env.pose(r,0.)
    env.command(dict(t=0.,kind='drive',forward=.05,turn=0.,duration_s=1.))
    p1=env.pose(replace(r,t_est=1.,fix_age_s=1.,x_m=.7),1.)
    assert p1.std_xy>p0.std_xy and env.fix_t==0.
    relative=BeamRelativeReport(1,'a',1.,0,(),grip_base_m=(.162,0.),std_xy_m=.001)
    assert relative.std_xy_m==.001 and env.fix_t==0.
    # dev14's compact jump cannot establish a new global anchor.
    jump=replace(good(1.1),x_m=1.5,std_xy_m=.019)
    assert env.pose(jump,1.1) is None and env.fix_t==0.


def test_global_uncertainty_monotonic_no_cap_false_safe():
    _,_,eps=real_pair();ep=eps['r1']
    g=GlobalPairSweepGuard(ep.own.guard,ep.plan['beam_geometry'],ep.arguments['role'])
    from harness.zone_own_guards import OwnPose
    values=[g.chassis_clearance(OwnPose(.6,0.,0.,s,.01))[0] for s in (.01,.06,.10,.15,.151,.82)]
    assert all(b<=a for a,b in zip(values,values[1:]))
    assert values[-1]==-math.inf and values[-2]==-math.inf


def test_relative_align_relooks_while_global_reserve_is_still_safe(monkeypatch):
    _,_,eps=real_pair();ep=eps['r1'];ep.policy=pair_policy('a+b');ctl=ep.controller
    ctl.state='align';seen=[]
    monkeypatch.setattr(ctl,'global_certificate',lambda now:{'clear':True,'relook_reserve_low':True})
    monkeypatch.setattr(ctl,'_begin_align_relook',lambda now,reason:seen.append((now,reason)))
    ctl.tick(1.)
    assert seen==[(1.,'global_safety_reserve')]


def shape_observation(fid=1,t=0.,digest='shape'):
    return dict(frame_id=fid,sha256=digest,sim_time=t,image=b'fake',
                actuator_state={'servo_pulses':{1:2000,3:800,4:2380,5:1380,6:1500}})


def fit(x=.162):
    return dict(grip_base_m=[x,0.],axis_heading_rad=0.,std_xy_m=.015,std_yaw_rad=.02,bias_bound_m=.01)


def test_relative_report_gauge_independence_partial_duplicate_movement_and_loaded(monkeypatch):
    from harness import zone_pair_relative as rel
    monkeypatch.setattr(rel,'shape_fit',lambda *a:(fit(),()))
    track=RelativeBeamTrack();o=shape_observation();servo=o['actuator_state']['servo_pulses']
    r=track.observe(o,servo,0,now=0.)
    assert r.ready(0.) and not r.marker_dependency
    repeated=track.observe(o,servo,0,now=.1)
    assert repeated.ready(.1) and repeated.captured_at_s==r.captured_at_s
    assert repeated.grip_base_m==r.grip_base_m and repeated.std_xy_m>r.std_xy_m
    assert repeated.std_xy_m==track.beam['std_xy_m']
    monkeypatch.setattr(rel,'shape_fit',lambda *a:(None,('END_CLIPPED',)))
    monkeypatch.setattr(rel,'shape_points',lambda *a:(np.array([[.2,0.],[.21,0.]]),None,None,None))
    r2=track.observe(shape_observation(2,.2,'partial'),servo,0,now=.2)
    assert r2.ready(.2) and r2.anchor_time_s==0. and r2.std_xy_m>=r.std_xy_m
    assert r2.grip_base_m==r.grip_base_m
    monkeypatch.setattr(rel,'shape_fit',lambda *a:(fit(.7),()))
    r3=track.observe(shape_observation(3,.3,'moved'),servo,0,now=.3)
    assert not r3.ready(.3) and 'BEAM_MOVED_OR_ASSOCIATION_LOST' in r3.reasons
    r4=track.observe(shape_observation(4,.4,'loaded'),servo,0,now=.4,mode='attached_hypothesis')
    assert not r4.ready(.4) and r4.reasons==('LOADED_DEPTH_UNKNOWN',)


@pytest.mark.parametrize('reason',['END_CLIPPED','BAND_CLIPPED','END_ID_AMBIGUOUS','MONOCULAR_DEPTH_AMBIGUOUS'])
def test_partial_and_ambiguous_views_cannot_initialize_metric_pose(monkeypatch,reason):
    from harness import zone_pair_relative as rel
    monkeypatch.setattr(rel,'shape_fit',lambda *a:(None,(reason,)))
    o=shape_observation();r=RelativeBeamTrack().observe(o,o['actuator_state']['servo_pulses'],0,now=0.)
    assert r.grip_base_m is None and not r.ready(0.) and r.observable_axes==()


def test_dev14_real_guard_cancels_blocked_pan_queue():
    _,_,eps=real_pair();ep=eps['r2'];record=DATA['records'][-1]
    ep.policy=pair_policy('b-only');ctl=ep.controller;own=ep.own
    own.last_obs=obs(record);own.servo={int(k):v for k,v in own.last_obs['actuator_state']['servo_pulses'].items()}
    own.last_report=saved_report(record);now=own.last_obs['sim_time']
    ctl.state='align_relook';ctl.align_look_started_at=now-1.6;ctl.align_look_total_s=0.
    ctl.active_relook_pan=970;ctl.arm.commanded=dict(own.servo)
    ctl.arm.queue({6:970},now,duration=.4,settle=.6)
    for e in eps.values():
        e.own.job.deadline=now+20;e.status.tick('aligning',now)
    result=ep.arm_step(now+.05)
    assert result==[{'kind':'hold'}] and not ep.terminal
    assert not ctl.arm.events and ep.arm_wait_at is None
    assert ctl.arm.commanded==own.servo and ctl.relook_cancelled and ctl.relook_excluded=={970}


def test_dwell_only_wait_does_not_queue_another_pan(monkeypatch):
    _,_,eps=real_pair();ep=eps['r1'];ep.policy=pair_policy('b-only');ctl=ep.controller
    ctl.state='align_relook';ctl.align_look_started_at=0.;ctl.align_pans=[970,1230]
    ctl.arm.until=0.;ep.own.last_obs['sim_time']=1.
    monkeypatch.setattr(ctl,'_align_fix_checks',lambda t:{'gate_ok':False})
    ctl._align_relook(1.,True)
    assert not ctl.arm.events and ctl.align_pans==[970,1230]


@pytest.mark.parametrize('ready,directions',[(False,3),(True,1)])
def test_pregrasp_cancel_cannot_refill_direction_budget_or_override_fix(monkeypatch,ready,directions):
    _,_,eps=real_pair();ep=eps['r1'];ep.policy=pair_policy('b-only');ctl=ep.controller
    ctl.state='pregrasp_look';ctl.pregrasp_look_started_at=0.;ctl.pregrasp_sweeps=1
    ctl.pg_pans=[970];ctl.active_relook_pan=700;ctl.relook_cancelled=True
    ctl.relook_directions_used=directions
    monkeypatch.setattr(ctl,'_grasp_pose_checks',lambda t:{'informative_fix':ready})
    monkeypatch.setattr(ctl,'_grasp_pose_ready',lambda t:ready)
    monkeypatch.setattr(ctl,'align_look_choices',lambda:pytest.fail('unexpected direction refill'))
    retry=[];monkeypatch.setattr(ctl,'_queue_grasp',lambda t:retry.append(t))
    ctl._pregrasp_look(1.,True)
    if ready:
        assert ctl.pregrasp_done and ctl.state=='pregrasp_standoff' and not retry
    else:
        assert retry==[1.] and not ctl.arm.events


def test_markerless_fake_provider_contract_and_geometry_ranking(monkeypatch):
    from harness.zone_pair_align import ranked_look_pans
    from harness.owncam_recovery_v6 import begin_observation
    _,_,eps=real_pair();ep=eps['r1']
    calls=[]
    class Markerless:
        source='owncam_markerless_fake'
        def begin_observation(self,now,servo,*,lost=False):calls.append((now,lost))
        def expected_observability(self,pose,pan,static_map):return 1.+pan/2500.
    p=Markerless();enable_provider(p);begin_observation(p,1.,ep.own.servo)
    assert calls==[(1.,False)]
    no_tags=copy.deepcopy(ep.own.map);no_tags['landmarks'].pop('tags',None)
    g=GlobalPairSweepGuard(ep.own.guard,ep.plan['beam_geometry'],ep.arguments['role'])
    a=ranked_look_pans(no_tags,good(),ep.own.servo,g,p,recovery_v6=True)
    assert a and all(row['observability_score']>0 for row in a)


def test_ablation_flags_are_independent_and_unknown_flag_rejected():
    assert not pair_policy().posterior_relook
    assert pair_policy('b-only').posterior_relook and not pair_policy('b-only').beam_relative
    assert pair_policy('a+b').beam_relative
    with pytest.raises(ValueError):pair_policy('a-only')


def test_actual_shape_detector_works_without_black_grip_bands():
    from harness.owncam_view import base_rays
    from harness.owncam_pair_beam_v2 import pose_of
    from harness.zone_pair_relative import shape_fit
    servo=pose_of('search');o,r,x,y,valid=base_rays(servo,1)
    distance=(.032-o[2])/np.where(abs(r[:,2])>1e-8,r[:,2],1.)
    pts=o+distance[:,None]*r
    hit=valid&(distance>0)&(r[:,2]<-1e-6)&(pts[:,0]>=.3)&(pts[:,0]<=.9)&(abs(pts[:,1])<=.02)
    im=np.full((480,640,3),100,np.uint8)
    im[y[hit].astype(int),x[hit].astype(int)]=[0,220,120]
    no_marker,_=shape_fit(im,servo)
    # Top-only raster (no end face): the mid-height end-face estimate lies
    # within its reported bound of the true .33 m grip (review 3).
    assert no_marker is not None
    assert abs(no_marker['grip_base_m'][0]-.33) <= no_marker['std_xy_m']+no_marker['bias_bound_m']
    band=hit&(pts[:,0]>.312)&(pts[:,0]<.348)
    im[y[band].astype(int),x[band].astype(int)]=0
    with_marker,_=shape_fit(im,servo)
    assert with_marker is not None
    assert with_marker['grip_base_m']==pytest.approx(no_marker['grip_base_m'],abs=.005)
    im[np.all(im==100,axis=2)]=0  # band indistinguishable from a floor gap
    ambiguous,reasons=shape_fit(im,servo)
    assert ambiguous is None and 'DISCONNECTED_SHAPE_OR_OCCLUSION' in reasons


def test_command_invalidates_cached_relative_image_but_finger_does_not(monkeypatch):
    from harness import zone_pair_relative as rel
    monkeypatch.setattr(rel,'shape_fit',lambda *a:(fit(),()))
    track=RelativeBeamTrack();o=shape_observation();servo=o['actuator_state']['servo_pulses']
    assert track.observe(o,servo,0,now=0.).ready(0.)
    track.command(dict(kind='arm',t=0.,servo_id=1,pulse=1990),servo)
    assert track.observe(o,servo,0,now=0.).ready(0.)
    track.command(dict(kind='drive',t=0.,forward=.03,turn=0.,duration_s=.3),servo)
    assert not track.observe(o,servo,0,now=.1).ready(.1)


def test_relative_dual_ready_same_go_abort_and_stale_guards(monkeypatch):
    from tests.test_zone_pair_grasp import ready_to_close,fresh
    _,_,eps=real_pair()
    for ep in eps.values():
        ep.policy=pair_policy('a+b');ready_to_close(ep,1.);ep.status.tick('aligning',1.)
        ep.own.last_report=good(1.)
        def observed(o,servo,segment,*,now,mode, _ep=ep):
            return BeamRelativeReport(o['frame_id'],o['sha256'],o['sim_time'],segment,(),
                grip_base_m=(.162,0.),axis_heading_rad=0.,std_xy_m=.015,std_yaw_rad=.02,bias_bound_m=.01,
                observable_axes=('forward','left','yaw'),endpoint_hypotheses=('nearest_end',),
                anchor_time_s=1.,anchor_sha256='synthetic-shape-receipt')
        monkeypatch.setattr(ep.command_guard.relative_track,'observe',observed)
    a,b=eps.values()
    a.controller._wait_close(1.,True)
    assert not a.controller.arm.events and not b.controller.arm.events
    b.controller._wait_close(1.,True)
    for t in (1.1,1.2):
        for ep in eps.values():
            fresh(ep,t,grip=True);ep.own.last_report=replace(good(t),std_xy_m=.08)
            ep.controller._wait_close(t,True)
    assert a.controller.state==b.controller.state=='grasp'
    assert a.controller.arm.events==b.controller.arm.events
    assert a.own.last_report.std_xy_m==.08  # relative confidence never shrank global sigma
    a.abort(1.21,'TEST_ABORT');b.check(1.21)
    assert a.terminal and b.terminal and not a.controller.arm.events and not b.controller.arm.events


def test_return_sweep_cancel_cannot_resume_alignment():
    _,_,eps=real_pair();ctl=eps['r1'].controller
    ctl.state='align_relook_return'
    ctl.cancel_relook_pan(1.)
    assert ctl.state=='failed' and ctl.failure=='ALIGN_RETURN_VIEW_BLOCKED'


def test_replay_stops_consuming_at_first_new_branch():
    from scripts.replay_zone_pair_v6 import ReplayBoundary,Reader
    replay=ReplayBoundary();assert replay.compare(0.,'hold','hold')
    assert not replay.compare(1.,'pan700','pan970')
    assert replay.divergence['after_branch']=='unknown'
    with pytest.raises(RuntimeError):replay.compare(2.,'old JPEG','new JPEG')
    with pytest.raises(ValueError):Reader().bytes(Path('/forbidden/eval_only/trace.jsonl'))


@pytest.mark.parametrize('policy,run',[('v5h','v6b-s911-v5h'),('b-boot','v6b-s911-bboot'),('a+b-boot','v6b-s911-abboot')])
def test_v6_draft_prepare_and_execution_refusal(tmp_path,policy,run):
    # v6b is the current v6-family revision; v6 is historical (PR #259 cohort).
    from scripts import run_zone_pair_dev as dev
    from scripts.zone_pair_v6_contract import PREREG_V6B as PREREG
    args=dev.parser().parse_args(['--prereg',str(PREREG),'--run-id',run,'--pair-policy',policy,
                                  '--output',str(tmp_path/'draft')])
    p,case=dev.load_config(args)
    assert case['pair_policy']==policy and p['execution_source_sha'] is None and p['approval'] is None
    assert dev.main(['--prereg',str(PREREG),'--run-id',run,'--pair-policy',policy,
                     '--output',str(tmp_path/'prepared')])==0
    manifest=json.loads((tmp_path/'prepared/manifest.json').read_text())
    assert manifest['pair_policy']==policy and manifest['applied'] is None and manifest['physical_success'] is None
    args.execute=True
    with pytest.raises(ValueError,match='prepare-only'):dev.load_config(args)


@pytest.mark.parametrize('execute', [False, True])
def test_v6_registration_is_historical_and_never_loaded_from_the_current_tree(tmp_path, execute):
    from scripts import run_zone_pair_dev as dev
    from scripts.zone_pair_v6_contract import PREREG
    argv = ['--prereg', str(PREREG), '--run-id', 'v6-s912-b', '--output', str(tmp_path/'never')]
    if execute:
        argv += ['--execute', '--lock-owner', 'claude', '--expected-source-sha', 'a'*40]
    with pytest.raises(ValueError, match='historical'):
        dev.load_config(dev.parser().parse_args(argv))
    assert not (tmp_path/'never').exists()


def test_v6_historical_audit_uses_registration_commit_blobs(monkeypatch):
    from scripts import zone_pair_v6_contract as c
    # Literal pins (not the module constant): PR #259 REGISTERED conversion and its registration hash.
    assert c.V6_REGISTRATION_COMMIT == '3c26acddec066adcd9164e6d2a6f51c1261c5f66'
    assert json.loads(c.PREREG.read_text())['registration_sha256'] == \
        '379ffe42baddab81554a007bd4cef5d3668c255e33d0342286dede49d77368fa'
    receipt = c.verify_v6_historical()
    assert receipt['commit'] == '3c26acddec066adcd9164e6d2a6f51c1261c5f66' and receipt['status'] == 'REGISTERED'
    assert receipt['execution_bundle_id'] == 'zone-pair-v70-beam-relative-multiturn' and receipt['sources'] == 72
    with pytest.raises(ValueError, match='differ from their registration commit'):   # an earlier commit
        c.verify_v6_historical(commit='c6feb21dcc4b8213ced1cde9419de5aa5e5efd18')
    with pytest.raises(ValueError, match='not in this history'):
        c.verify_v6_historical(commit='f'*40)
    read = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes',                            # reformatting alone is a byte change
                        lambda self: json.dumps(json.loads(read(self)), indent=1, sort_keys=True).encode()
                        if self == c.PREREG else read(self))
    with pytest.raises(ValueError, match='differ from their registration commit'):
        c.verify_v6_historical()


def _v6_variant(tmp_path, name, mutate):
    from scripts.zone_pair_authorization import digest, registration_payload
    from scripts.zone_pair_v6_contract import PREREG_V6B
    p = json.loads(PREREG_V6B.read_text())
    mutate(p)
    p['registration_sha256'] = digest(registration_payload(p))
    path = tmp_path/name
    path.write_text(json.dumps(p))
    return path, p


def test_v6_draft_status_still_refuses_execution(tmp_path):
    from scripts import run_zone_pair_dev as dev
    def to_draft(p):
        assert p['status'] == 'DRAFT' and 'draft_registration' not in p
    path, _ = _v6_variant(tmp_path, 'draft.json', to_draft)
    args = dev.parser().parse_args(['--prereg', str(path), '--run-id', 'v6b-s911-abboot', '--output',
                                    str(tmp_path/'never'), '--execute'])
    with pytest.raises(ValueError, match='v6 DRAFT is prepare-only'):
        dev.load_config(args)
    assert not args.output.exists()


def test_v6b_registered_execution_needs_bound_envelope(tmp_path):
    """PR #259's REGISTERED admission path, kept for the current revision (v6b)."""
    from scripts import run_zone_pair_dev as dev
    from scripts.zone_pair_authorization import digest
    from scripts.zone_pair_v6_contract import PREREG
    assert json.loads(PREREG.read_text())['status'] == 'REGISTERED'         # v6 ran; now historical
    sha = 'a'*40
    def register(p):
        p.update(status='REGISTERED', runnable=True, draft_registration={
            'path': 'experiments/2026-09-28-zone-pair-v6b-boot/prereg_v6b.json',
            'commit': 'c'*40, 'sha256': 'd'*64, 'registration_sha256': 'e'*64})
    path, p = _v6_variant(tmp_path, 'registered.json', register)
    def envelope(p, run='v6b-s912-bboot'):
        auth = {'by': 'coordinator', 'source_sha': sha, 'registration_sha256': p['registration_sha256'],
                'run_id': run,
                'ref': 'https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/221#issuecomment-1'}
        auth['sha256'] = digest(auth)
        p['execution_authorization'] = auth
    envelope(p)
    path.write_text(json.dumps(p))
    out = dev.primary_root()/'outputs/never-created-v6b-registration-test'
    base = ['--prereg', str(path), '--run-id', 'v6b-s912-bboot', '--execute', '--lock-owner', 'claude']
    ok = dev.parser().parse_args([*base, '--output', str(out), '--expected-source-sha', sha])
    _, case = dev.load_config(ok)
    assert case['pair_policy'] == 'b-boot' and not out.exists()
    for bad, match in ((['--output', str(out), '--expected-source-sha', 'b'*40], 'source_sha differs'),
                       (['--output', 'rel/out', '--expected-source-sha', sha], 'absolute under primary'),
                       (['--output', str(tmp_path/'x'), '--expected-source-sha', sha], 'absolute under primary')):
        with pytest.raises(ValueError, match=match):
            dev.load_config(dev.parser().parse_args([*base, *bad]))
    other = dev.parser().parse_args(['--prereg', str(path), '--run-id', 'v6b-s912-abboot', '--execute',
                                     '--lock-owner', 'claude', '--output', str(out), '--expected-source-sha', sha])
    with pytest.raises(ValueError, match='run_id differs'):
        dev.load_config(other)
    p.pop('draft_registration')
    path.write_text(json.dumps(p))
    with pytest.raises(ValueError, match='registered contract changed'):
        dev.load_config(ok)
