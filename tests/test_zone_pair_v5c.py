"""Saved dev09/10 decisions and semantic blockage regression; no physics/models."""
import base64
import copy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
from types import SimpleNamespace

import cv2
import pytest

from harness.owncam_time import POSE_TIME_ROUNDING_S, accepted_fix_checks, pose_report_fresh
from harness.zone_pair_obstruction import target_context
from harness.zone_own_perception import judge_route_blockage
from tests.test_zone_pair_grasp import real_pair, fresh
from tests.test_zone_pair_v5 import report

FIX = Path(__file__).parent / 'fixtures/zone_pair_v5c'
DATA = json.loads((FIX / 'manifest.json').read_text())


def install(row):
    _, _, eps = real_pair()
    ep = eps[row['robot_id']]
    ep.own.last_report = report(ep, row['report'])
    ep.own.gate.state = 'ok' if row['gate_ok'] else 'uncertain'
    ep.own.pose.loc.last_tag_t = row['accepted_tag_t']
    ep.own.last_report = replace(ep.own.last_report, last_fix_t=row['accepted_tag_t'])
    ep.controller.align_look_started_at = row['start']
    ep.controller.pregrasp_started_at = row['start']
    return ep


def test_saved_ten_decisions_old_zero_fixed_nine_and_sigma_still_rejected():
    # Load only the old predicate source, preserving the pre-fix failure proof.
    import harness.zone_pair_align as align
    source = (FIX / DATA['frozen_predicate_fixture']['file']).read_bytes()
    assert hashlib.sha256(source).hexdigest() == DATA['frozen_predicate_fixture']['sha256']
    scope = dict(vars(align)); exec(compile(source, '<frozen v5b>', 'exec'), scope)
    old = scope['_align_fix_ready']
    outcomes = []
    for row in DATA['decisions']:
        ep = install(row); ctl = ep.controller; now = row['observation']['sim_time']
        assert not old(ctl, now)
        checks = ctl._align_fix_checks(now)
        outcomes.append(ctl._align_fix_ready(now))
        if not outcomes[-1]:
            assert row['run'] == 'dev10' and row['robot_id'] == 'r1'
            assert row['report']['std_xy_m'] == .05601
            assert {k for k, v in checks.items() if not v} == {'std_xy', 'sigma_reserve', 'gate_ok'}
    assert len(outcomes) == 10 and sum(outcomes) == 9


@pytest.mark.parametrize('sign', [-1, 1])
@pytest.mark.parametrize('offset,ok', [(2.5e-9, True), (.000099, True), (.000101, False)])
def test_both_rounding_directions_in_align_and_pregrasp(sign, offset, ok):
    _, _, eps = real_pair(); ep = eps['r1']; fresh(ep, 2.)
    ep.controller.align_look_started_at = ep.controller.pregrasp_started_at = 1.
    ep.own.last_report = replace(ep.own.last_report, t_est=2. + sign * offset)
    assert ep.controller._align_fix_ready(2.) is ok
    assert ep.controller._grasp_pose_ready(2.) is ok


@pytest.mark.parametrize('tag', [1. - 1e-9, 1., None, 2.000001, float('nan')])
def test_raw_capture_boundary_never_accepts_prelook_or_future_tags(tag):
    _, _, eps = real_pair(); ep = eps['r1']; fresh(ep, 2.)
    ep.controller.align_look_started_at = 1.
    ep.own.pose.loc.last_tag_t = tag
    ep.own.last_report = replace(ep.own.last_report, last_fix_t=tag)
    assert not ep.controller._align_fix_ready(2.)


@pytest.mark.parametrize('age,ok', [(.3, True), (.300099, True), (.300101, False),
                                   (-.000099, True), (-.000101, False)])
def test_freshness_admission_guard_and_limits_share_both_bounds(age, ok):
    from harness.owncam_pose_source import check_limits, PoseLimits
    from harness.zone_pair_admission import readiness_snapshot
    _, _, eps = real_pair(); ep = eps['r1']; fresh(ep, 0.)
    ep.own.last_report = replace(ep.own.last_report, t_est=-age)
    rep = ep.own.last_report
    assert pose_report_fresh(rep, 0.) is ok
    assert (not check_limits(rep, 0., PoseLimits(.05, math.radians(3)))) is ok
    assert (ep.command_guard._pose(0.) is not None) is ok
    ep.own.job = None
    assert readiness_snapshot(ep.own, 0.)['checks']['report_fresh'] is ok


@pytest.mark.parametrize('delta,ok', [(-.000099, True), (-.000101, False), (2.5e-9, True)])
def test_stop_cache_uses_same_report_tolerance(delta, ok):
    _, _, eps = real_pair(); ep=eps['r1']; fresh(ep, 1.1)
    ep.command_guard.motion_until = 1.
    ep.command_guard.stationary_pose = None
    ep.own.last_report = replace(ep.own.last_report, t_est=1. + delta)
    assert ep.command_guard.align_stop_ready(1.1, 1.) is ok


def test_separately_rounded_age_is_not_used_as_capture_timestamp():
    _, _, eps = real_pair(); ep = eps['r1']; fresh(ep, 1.10004)
    ep.controller.align_look_started_at = 1.
    # Rounded subtraction gives a pre-start tag, authoritative capture is new.
    ep.own.last_report = replace(ep.own.last_report, t_est=1.1, since_tag_s=.1, fix_age_s=.1)
    ep.own.pose.loc.last_tag_t = 1.00004
    ep.own.last_report = replace(ep.own.last_report, last_fix_t=1.00004)
    assert ep.controller._align_fix_ready(1.10004)
    ep.own.pose.loc.last_tag_t = .99999
    ep.own.last_report = replace(ep.own.last_report, last_fix_t=.99999)
    assert not ep.controller._align_fix_ready(1.10004)


def test_rejection_event_names_every_failed_conjunct():
    _, _, eps=real_pair();ep=eps['r1'];fresh(ep, 2.)
    ctl=ep.controller;ctl.align_look_started_at=1.;ctl.align_pans=[];ctl.arm.until=2.
    ep.own.pose.loc.last_tag_t=0.
    ep.own.last_report = replace(ep.own.last_report, last_fix_t=0.)
    ep.own.last_report=replace(ep.own.last_report,std_xy_m=.05601)
    ctl._align_relook(2.,True)
    row=next(x for x in ep.events if x['event']=='align_relook_fix_rejected')
    assert {'fix_in_sweep','std_xy','sigma_reserve'} <= set(row['failed_checks'])
    assert ctl.failure == 'ALIGN_RELOOK_NO_FIX'


def blockage_setup(row):
    ep = install(row); now = row['observation']['sim_time']
    ep.plan['sheet'] = row['sheet']; ep.controller.seg = 0
    ep.own.now=now
    ep.own.last_obs=copy.deepcopy(row['observation'])
    jpeg=(FIX/row['file']).read_bytes()
    assert hashlib.sha256(jpeg).hexdigest()==row['observation']['sha256']
    ep.own.last_obs['image']=base64.b64encode(jpeg).decode()
    ep.own.servo={int(k):v for k,v in row['observation']['actuator_state']['servo_pulses'].items()}
    belief=dict(zip(('x_m','y_m','yaw_rad'),row['report']['xyyaw']));belief['confidence']='high'
    return ep, now, jpeg, belief


@pytest.mark.parametrize('row', DATA['blockages'], ids=lambda r:r['run'])
def test_saved_target_beam_excluded_but_other_objects_stay_blocked(row):
    ep,now,jpeg,belief=blockage_setup(row)
    kw=dict(static_map=ep.own.map,pose_belief=belief)
    old=judge_route_blockage(jpeg,ep.own.servo,**kw)
    target=target_context(ep.own,ep.own.last_report,now)
    assert target
    new=judge_route_blockage(jpeg,ep.own.servo,expected_target=target,**kw)
    assert len(new['expected_target_occupancy'])==1
    assert new['expected_target_occupancy'][0]['pixel_bbox']==old['nearest']['pixel_bbox']
    assert new['answer']=='yes' and new['reason']=='UNMAPPED_OBSTRUCTION_IN_LANE'
    assert old['nearest']['pixel_bbox'] not in [c['pixel_bbox'] for c in new['candidates']]
    assert new['candidates']==[c for c in old['candidates'] if c!=old['nearest']]
    # Actual caller takes encoded own JPEG (canonical BGR decode), not its RGB array.
    import numpy as np
    ep.own._judge(now,ep.own.last_obs,np.zeros((480,640,3),dtype=np.uint8),ep.own.last_report)
    assert ep.own.judgment_log[-1]['expected_target_occupancy']


@pytest.mark.parametrize('fault', ['no_job','wrong_order','terminal','later_segment','wrong_sheet','merged_red','wrong_colour','nan_pose','high_pose'])
def test_unknown_other_or_merged_objects_are_never_target_exclusions(fault):
    ep,now,jpeg,belief=blockage_setup(DATA['blockages'][1])
    if fault=='no_job':ep.own.job=None
    elif fault=='wrong_order':ep.own.job.args['order_id']='unknown'
    elif fault=='terminal':ep.terminal=True
    elif fault=='later_segment':ep.controller.seg=1
    elif fault=='wrong_sheet':ep.plan['sheet']['beam_xyyaw'][1]+=.6
    elif fault=='nan_pose':ep.own.last_report=replace(ep.own.last_report,x_m=float('nan'))
    elif fault=='high_pose':ep.own.last_report=replace(ep.own.last_report,std_xy_m=.070001)
    else:
        import numpy as np
        frame=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR)
        if fault=='merged_red':cv2.rectangle(frame,(330,250),(380,360),(0,0,255),-1)
        else:
            hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV);mask=(hsv[...,0]>=27)&(hsv[...,0]<=54)&(hsv[...,1]>=60)
            frame[mask]=(0,0,255)
        jpeg=cv2.imencode('.jpg',frame)[1].tobytes()
    target=target_context(ep.own,ep.own.last_report,now)
    r=judge_route_blockage(jpeg,ep.own.servo,static_map=ep.own.map,pose_belief=belief,expected_target=target)
    assert not r['expected_target_occupancy'] and r['answer']=='yes'


@pytest.mark.parametrize('run', ['dev13','dev14'])
def test_v5c_prepare_is_source_bound_and_has_no_physics_or_model_calls(tmp_path, run):
    import sys
    from scripts import run_zone_pair_dev as dev
    out=tmp_path/run
    result=subprocess.run([sys.executable,str(dev.ROOT/'scripts/run_zone_pair_dev.py'),
                           '--prereg',str(dev.PREREG_V5H),'--run-id',run,'--output',str(out)],
                          capture_output=True,text=True)
    # The old registration is preserved, so this changed v6 source must reject
    # it before constructing a world or creating an output directory.
    assert result.returncode!=0 and 'scene contract' in result.stderr
    assert not out.exists()


@pytest.mark.parametrize('fault,reason', [('seed','fixes'),('criteria','preserve v2 criteria'),
    ('source','grasp contract/hash'),('supersedes','previous prereg hash'),('scene','scene contract/hash')])
def test_v5c_rejects_changed_registration(tmp_path,fault,reason):
    from scripts import run_zone_pair_dev as dev
    p=json.loads(dev.PREREG_V5H.read_text())
    # Bind the test copy to this source to isolate each structural mutation;
    # the actual archived file remains byte-identical and non-executable.
    from scripts.zone_pair_grasp_contract import grasp_contract
    p['scene_contract']=dev.scene_contract()
    p['grasp_contract']=grasp_contract()
    if fault=='seed':p['runs'][0]['seed']=905
    elif fault=='criteria':p['criteria']['lift_bottom_m']=.01
    elif fault=='source':p['grasp_contract']['source_sha256']['harness/owncam_time.py']='0'*64
    elif fault=='scene':p['scene_contract']['sha256']='0'*64
    else:p['supersedes']['sha256']='0'*64
    # Reseal only to isolate structural/source checks; separate tests cover seal tampering.
    from scripts.zone_pair_authorization import registration_payload
    p['registration_sha256'] = dev.digest(registration_payload(p))
    path=tmp_path/'bad.json';path.write_text(json.dumps(p))
    args=dev.parser().parse_args(['--prereg',str(path),'--run-id','dev13','--output',str(tmp_path/'out')])
    with pytest.raises(ValueError,match=reason):dev.load_config(args)


@pytest.mark.parametrize('row', [r for r in DATA['decisions']+DATA['blockages'] if 'file' in r], ids=lambda r:r['file'])
def test_saved_small_jpegs_reproduce_recorded_own_tag_ids(row):
    import numpy as np
    from harness.wall_tags import TagDetector
    data=(FIX/row['file']).read_bytes()
    assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['observation']['sha256']
    static=json.loads(Path('maps/zones/zone_wide_door_tags_v2_dock_v3.json').read_text())
    rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
    ids=sorted(d['id'] for d in TagDetector.for_map(static).detect(rgb))
    assert ids==row['report']['last_valid_obs']['tag_ids']


@pytest.mark.parametrize('fault', [None,'expired','high_sigma','wrong_segment','moved'])
def test_own_anchor_context_is_segment_bound_and_does_not_mutate_track(fault):
    from harness.owncam_pair_beam_v2 import observe_beam
    ep,now,jpeg,belief=blockage_setup(DATA['blockages'][0])
    ep.controller.seg=1;track=ep.command_guard.beam_track;track.segment=1;track.t=now-.1
    beam=observe_beam(jpeg,ep.own.servo)
    track.beam={**beam,'std_xy_m':.049,'std_yaw_rad':.02,'anchor_time_s':now-.1,'prediction_time_s':now-.1}
    if fault=='expired':track.beam['anchor_time_s']=now-31
    elif fault=='high_sigma':track.beam['std_xy_m']=.051
    elif fault=='wrong_segment':track.segment=0
    elif fault=='moved':track.beam['grip_base_m'][1]+=.6
    before=copy.deepcopy(track.beam)
    target=target_context(ep.own,ep.own.last_report,now)
    assert track.beam==before and track.t==now-.1
    result=judge_route_blockage(jpeg,ep.own.servo,static_map=ep.own.map,pose_belief=belief,expected_target=target)
    assert bool(result['expected_target_occupancy']) is (fault is None)


def test_new_runtime_has_no_simulator_or_evaluation_inputs():
    import ast
    files=['harness/owncam_time.py','harness/zone_pair_obstruction.py','harness/zone_pair_align.py',
           'harness/zone_pair_grasp.py','harness/zone_own_status.py']
    forbidden={'mujoco','xpos','xquat','qpos','qvel','MjData','GtStubPoseSource','eval_only','cctv_top','nav_cam'}
    for file in files:
        tree=ast.parse(Path(file).read_text())
        names={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}|{n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
        assert not names&forbidden,file


def test_two_disconnected_matching_components_are_ambiguous(monkeypatch):
    # Negative association injection: even if both candidates independently
    # match, one ordered cargo must not hide multiple disconnected objects.
    import harness.zone_pair_obstruction as obstruction
    ep,now,jpeg,belief=blockage_setup(DATA['blockages'][1])
    target=target_context(ep.own,ep.own.last_report,now)
    monkeypatch.setattr(obstruction,'target_component',lambda *a: {'classification':'expected_target_occupancy'})
    r=judge_route_blockage(jpeg,ep.own.servo,static_map=ep.own.map,pose_belief=belief,expected_target=target)
    assert r['answer']=='yes' and not r['expected_target_occupancy']


@pytest.mark.parametrize('max_age',[.25,.3])
@pytest.mark.parametrize('shift,valid', [(-.000099,True),(.000099,True),(-.000101,False),(.000101,False)])
def test_common_time_quantization_at_exact_freshness_boundaries(max_age,shift,valid):
    # Quantize toward either end of an otherwise boundary-valid report.
    t=shift if shift>0 else -max_age+shift
    assert pose_report_fresh(SimpleNamespace(t_est=t),0.,max_age_s=max_age) is valid
