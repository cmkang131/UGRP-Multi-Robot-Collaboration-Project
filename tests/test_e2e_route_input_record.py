"""Private planner recording/replay and exact geometry; no simulator/provider."""
import copy
import hashlib
import json
import subprocess
import numpy as np
import pytest
from harness import e2e_route_input_record as rec
from harness import e2e_route_stage_probe as sp
from harness import e2e_route_footprint as fp
from tests.test_e2e_route_recovery import scene,state,ref,pulse_fixture


def attempt(c):
    return c.route_to_B(dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=pulse_fixture()[1]['profiles'])


@pytest.mark.parametrize('kind', ['free','goal','unknown'])
def test_record_real_planner_success_failure_and_paired_replay(tmp_path,kind):
    from scripts.run_e2e_route_stage_probe import recordings_manifest,run,read
    c=scene(kind);root=tmp_path/'inputs';rec.install(c,rec.OPTION,root=root,metadata={'seed':61009})
    try:attempt(c)
    except Exception as exc:assert str(exc)=='OWN_GRID_ROUTE_UNAVAILABLE'
    summary=json.loads((root/'summary.json').read_text());assert summary['saved']==1
    row=json.loads((root/'index.jsonl').read_text());record,sha=read(root/row['file'])
    assert sha==row['sha256']
    raw=subprocess.check_output(['zstd','-dc',str(root/row['file'])])
    assert hashlib.sha256(raw).hexdigest()==row['uncompressed_sha256']
    assert record['snapshot']['odds'] and record['geometry']['pair_dimensions_m']==[1.25,.4]
    result=run(recordings_manifest([root]))
    assert len(result['rows'])==3 and result['rows'][0]['recorded_result_reproduced']
    assert result['metrics']['all']['off']['attempted_N']==1
    assert result['metrics']['all']['off']['compute_s_max']>=0
    assert result['metrics']['all']['off']['physical_evaluated_N']==0


def test_off_and_budget_are_observable_and_bounded(tmp_path):
    c=scene();assert rec.install(c,root=tmp_path/'off') is None
    assert not (tmp_path/'off').exists()
    limits={**rec.PARAMETERS,'max_attempts':1,'max_index_rows':2}
    recorder=rec.Recorder(tmp_path/'on',{},limits=limits)
    beam=dict(rgb=ref(3),pose_own_m=[0.,0.,0.]);kwargs=dict(now=1.3,profiles=pulse_fixture()[1]['profiles'])
    for i in range(4):recorder.attempt(c,c.route_to_B,beam,kwargs)
    summary=json.loads((tmp_path/'on'/'summary.json').read_text())
    assert (summary['attempts'],summary['saved'],summary['dropped'],summary['index_rows'])==(4,1,3,2)
    assert len(list((tmp_path/'on').glob('*.zst')))==1


def test_record_too_large_does_not_disable_planner(tmp_path):
    c=scene();r=rec.Recorder(tmp_path/'on',{},limits={**rec.PARAMETERS,'max_record_bytes':1})
    packet=r.attempt(c,c.route_to_B,dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),dict(now=1.3,profiles=pulse_fixture()[1]['profiles']))
    assert packet and r.saved==0 and r.dropped==1


def test_current_endpoint_identity_and_legacy_snapshot():
    c=scene();s=sp.capture(c,dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=pulse_fixture()[1]['profiles'],endpoint=c.e2e_gate.current['boundary'],endpoint_sources=[ref(3)])
    assert sp.replay(s)['generated']
    legacy=state();legacy['schema']=sp.LEGACY_SCHEMA
    for key in ('B_boundary','route_call','grid_flags'):legacy.pop(key)
    assert sp.replay(legacy)['generated']


def test_filled_footprint_removes_false_start_rejection_and_swept_eval():
    c=scene();c.explorer.grid.odds[(7,0)]=1.;c.explorer.grid.wall_frames[(7,0)]={3}
    s=sp.capture(c,dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=pulse_fixture()[1]['profiles'])
    old=sp.replay(s,'frontier_v1');new=sp.replay(s,fp.OPTION)
    assert not old['generated'] and new['generated']
    assert new['diagnostics']['sweep_validated']
    ev=dict(schema='ugrp.route_eval_rectangles.v1',input_sha256=new['input_sha256'],own_to_world=[0,0,0],bounds_xyxy=[-5,-5,5,5],obstacles_xyxy=[[.7,0,.8,.1]])
    assert sp.evaluate(new,s,ev)['collision_free']
    # A wall actually touching the carrier is still rejected.
    c.explorer.grid.odds[(6,0)]=1.;c.explorer.grid.wall_frames[(6,0)]={3}
    s=sp.capture(c,dict(rgb=ref(3),pose_own_m=[0.,0.,0.]),now=1.3,profiles=pulse_fixture()[1]['profiles'])
    assert not sp.replay(s,fp.OPTION)['generated']


def test_nearest_goal_cargo_must_fit_observed_boundary():
    s=state('snap');assert sp.replay(s,fp.OPTION)['generated']
    s['B_boundary']['polygon']=[[1.9,-.05],[2.1,-.05],[2.1,.05],[1.9,.05]]
    assert not sp.replay(s,fp.OPTION)['generated']
    assert not fp.goal_filter(None,0)([2,0])
    # The yaw changes which extent must fit; dimensions come from fixed beam_1.
    b=dict(complete=True,polygon=[[-.1,-.4],[.1,-.4],[.1,.4],[-.1,.4]])
    assert not fp.goal_filter(b,0)([0,0])
    assert fp.goal_filter(b,np.pi/2)([0,0])


def test_continuous_sweep_rejects_midsegment_obstacle():
    a=np.full((60,60),-1);a[30,30]=1
    clear=fp.sweep_checker(a,np.array([-30,-30]),.1,0,.02)
    assert not clear(np.array([-1.,0]),np.array([1.,0]))
    assert clear(np.array([-1.,1]),np.array([1.,1]))


def test_registration_all_new_bundles(monkeypatch):
    from tests import test_e2e_route_recovery as parent
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    # Reuse the exact admitted v375 constructor, not invented defaults.
    from tests import test_e2e_camera_hold as p
    captured=[]
    original=p.bundle
    def save(*a,**kw):captured.append((a,kw.copy()));return original(*a,**kw)
    monkeypatch.setattr(p,'bundle',save)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    args,kw=captured[-1]
    kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1',boundary_lifecycle='abort_v1',dialogue_call_policy='event_v1',call_snapshot='prepared_v1',speech_context='recent4_v1',post_relook='carry_nominal_v1',perception_fast='shadow_axes_v1',controller_timing='phase_v1',llm_memory='v1_commands',dialogue_decider='code_v1',explore_idle='idle5_v1',admission_clock='tick_v1')
    for option,record,v in [('off','on_v1',387),('frontier_v1','on_v1',388),('footprint_v2','off',389),('footprint_v2','on_v1',390)]:
        b=bundle(*args,**kw,route_recovery=option,route_input_record=record)
        assert b['execution_bundle_id']==f'e2e18-v{v}'
        require_current(b,ROOT)
        if record=='on_v1':
            bad=copy.deepcopy(b);bad['route_record_parameters']['max_attempts']=100000
            with pytest.raises(ValueError):require_current(bad,ROOT)
