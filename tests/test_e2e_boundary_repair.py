"""Partial geometry association and navigation-vs-observation retry contracts."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from harness.e2e_boundary_association import Association, overlap, install
from harness.e2e_boundary_views import CandidateNavigator


def fixture():
    candidate = dict(kind='B', source='own', center_m=[1., 0.],
                     observation=dict(partial_extent=True, bounds_m=[[0.,-.5],[2.,.5]]))
    boundary = dict(complete=True, white_markers=3, center=[1.,-.6],
                    polygon=[[.5,-1.1],[1.5,-1.1],[1.5,-.1],[.5,-.1]])
    gate = SimpleNamespace(current=None, references={})
    gate.remember_B = lambda: gate.references.setdefault('B', copy.deepcopy(gate.current))
    goal = SimpleNamespace(entities={'B':candidate}, e2e_gate=gate, event=lambda *a, **k:None)
    return goal, boundary


def receive(a, boundary, i, t):
    a.goal.e2e_gate.current = dict(boundary=boundary, ref=dict(frame_id=i,t_sim=t))
    a.observe()


def test_complete_boundary_replaces_partial_centroid_only_after_fresh_stable_overlap():
    g,b=fixture();a=Association(g)
    assert overlap(g.entities['B'], b) == pytest.approx(.4)
    for i in range(2):
        receive(a,b,i,i*.2);assert not g.e2e_gate.references
    receive(a,b,2,.4)
    assert g.e2e_gate.references['B']['boundary']==b
    assert g.entities['B']['center_m']==[1.,-.6] and a.last['accepted']
    # Existing GoalRoute must not overwrite the anchored full-region endpoint.
    g.entities['B']['center_m']=[1.,0.]
    receive(a,None,3,.6)
    assert g.entities['B']['center_m']==[1.,-.6]


@pytest.mark.parametrize('change', ['partial','markers','disjoint','peer','replay','gap','unstable'])
def test_association_rejects_incomplete_unrelated_replayed_or_unstable_evidence(change):
    g,b=fixture();a=Association(g)
    if change=='partial':b['complete']=False
    if change=='markers':b['white_markers']=2
    if change=='disjoint':b['polygon']=[[10,10],[11,10],[11,11],[10,11]]
    if change=='peer':g.entities['B']['source']='peer'
    for i in range(3):
        if change=='unstable':b['center']=[1.+i,-.6]
        receive(a,b,0 if change=='replay' else i,i*(1. if change=='gap' else .2))
    assert not g.e2e_gate.references


def test_navigation_failures_have_finite_separate_budget_and_off_preserves_three_attempts():
    g,_=fixture();g.explorer=SimpleNamespace(map_to_odom=np.zeros(3))
    n=CandidateNavigator(SimpleNamespace(pose=np.zeros(3)),g)
    for i in range(3):
        n.view_target_own=np.array([i,0.]);n.end_view(i,'B_view_path_lost')
    assert not n.can_attempt()
    n.retry_option='navigation_v1'
    assert n.can_attempt() and n.completed_views==0
    for i in range(3,6):n.end_view(i,'B_view_action_failed')
    assert not n.can_attempt() and n.navigation_failures==6
    n=CandidateNavigator(SimpleNamespace(pose=np.zeros(3)),g);n.retry_option='navigation_v1'
    for i in range(3):n.end_view(i,'B_view_observed_still_unconfirmed')
    assert not n.can_attempt() and n.navigation_failures==0


def test_bundle_default_identity_three_candidates_relay_and_real_wiring():
    from scripts.run_e2e_ownmap_live import bundle
    from scripts.s4_proxy_relay import accepted_call_id
    from harness.e2e_live_mapping import Robot
    from harness.s4_event_policy import Options
    x=object();assert install(x) is x
    kw=dict(enabled=True,stall_odometry='rgb_vo_us_v1',ultrasonic_front='on_v1',
        exploration_progress='frontier_progress_v1',boundary_views='candidate_views_v1',b_marker_detect='contrast_v1',
        vo_floor_mask='homography_v1',vo_rotation_policy='no_ransac_v1',explore_deadlock='replan_v1')
    old=bundle('sha',61001,'study_gemma4_31b_v1',**kw)
    assert old==bundle('sha',61001,'study_gemma4_31b_v1',**kw,boundary_association='off',boundary_retry='off')
    for association,retry in [('extent_v1','off'),('off','navigation_v1'),('extent_v1','navigation_v1')]:
        b=bundle('sha',61001,'study_gemma4_31b_v1',**kw,boundary_association=association,boundary_retry=retry)
        assert b['execution_bundle_id']=='e2e-boundary-repair-v212'
        assert b['e2e_options']['boundary_association']==association
        assert b['e2e_options']['boundary_retry']==retry
    for name in ['e2e-idle-a-s61001-r2','e2e-idle-b-s61003-r3']:
        assert accepted_call_id(name+':call-0001-r1:1')
    assert not accepted_call_id('e2e-idle-a-s61010-r2:call-0001-r1:1')
    cov=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    r=Robot('r1',61001,cov,Options(),exploration_progress='frontier_progress_v1',
        boundary_views='candidate_views_v1',boundary_association='extent_v1',boundary_retry='navigation_v1')
    assert isinstance(r.goal.boundary_association,Association)
    assert r.goal.explorer.navigator.retry_option=='navigation_v1'


def test_recorded_full_boundary_replay_overcomes_partial_centroid_rejection():
    replay=json.loads(Path('experiments/2026-10-12-e2e-idle/boundary-repair-replay.json').read_text())
    g,_=fixture();a=Association(g)
    for r in replay['rows']:
        g.entities['B']=copy.deepcopy(r['candidate'])
        g.e2e_gate.current=copy.deepcopy(r)
        assert np.linalg.norm(np.asarray(r['boundary']['center'])-r['candidate']['center_m'])>.20
        a.observe()
    assert g.e2e_gate.references and a.last['accepted']


def test_native_coverage_distinguishes_unknown_from_obstacles_without_making_free_cells():
    from harness import e2e_boundary_views as v
    from harness.public_navigation_unknown import UnknownCostmap
    g,_=fixture();g.explorer=SimpleNamespace(map_to_odom=np.zeros(3))
    n=CandidateNavigator(SimpleNamespace(pose=np.zeros(3)),g)
    n.coverage_option=v.COVERAGE_OPTION
    c=UnknownCostmap(np.full((100,100),255,np.uint8),[-2.5,-2.5],.05)
    before=c.raw.copy();path=[[0.,0.],[.5,0.]]
    assert not v.observed_path_clear(c,[0,0,0],path,0)
    assert n.coverage_check(c,[0,0,0],path,0,1.)
    assert n.coverage_would_stops==1 and np.array_equal(before,c.raw)
    # Known occupied perimeter remains rejected by the native planner.
    c.raw[:]=254;c.costs=c.inflate()
    assert not n.coverage_check(c,[0,0,0],path,0,2.)
    assert not n.coverage_check(c,[0,0,0],[],0,3.)


def test_native_coverage_bundle_is_dev_only_and_off_is_identical():
    from scripts.run_e2e_ownmap_live import bundle
    kw=dict(enabled=True,stall_odometry='rgb_vo_us_v1',ultrasonic_front='on_v1',
        exploration_progress='frontier_progress_v1',boundary_views='candidate_views_v1',b_marker_detect='contrast_v1',
        vo_floor_mask='homography_v1',vo_rotation_policy='no_ransac_v1',explore_deadlock='replan_v1',
        boundary_association='extent_v1')
    old=bundle('sha',61001,'study_gemma4_31b_v1',**kw)
    assert old==bundle('sha',61001,'study_gemma4_31b_v1',**kw,boundary_coverage='off')
    with pytest.raises(ValueError,match='DEV_V211'):
        bundle('sha',61001,'study_gemma4_31b_v1',**kw,boundary_coverage='native_v1')
    for retry in ('off','navigation_v1'):
        new=bundle('sha',61001,'study_gemma4_31b_v1',**kw,boundary_coverage='native_v1',boundary_retry=retry,dev_light=True)
        assert new['execution_bundle_id']=='e2e-boundary-native-v213'
        assert new['e2e_options']['boundary_coverage']=='native_v1'
        from harness.e2e_runtime_registration import require_current
        from scripts.run_e2e_ownmap_live import ROOT
        require_current(new,ROOT)
        new['e2e_options']['dev_light']=False
        with pytest.raises(ValueError,match='DEV_BOUNDARY_NATIVE'):
            require_current(new,ROOT)


def test_renumbered_cli_and_historical_registration_preserved(capsys):
    import hashlib
    from scripts.run_e2e_ownmap_live import main
    from scripts.run_e2e_reviewed import main as reviewed
    args = ['--expected-source-sha', 'x', '--output', '/tmp/unused', '--seed', '61001',
            '--driver-profile', 'study_gemma4_31b_v1', '--relay-receipt', '/tmp/receipt.json',
            '--exploration-progress', 'frontier_progress_v1', '--stall-odometry', 'rgb_vo_us_v1',
            '--ultrasonic-front', 'on_v1', '--boundary-views', 'candidate_views_v1',
            '--b-marker-detect', 'contrast_v1', '--vo-floor-mask', 'homography_v1',
            '--vo-rotation-policy', 'no_ransac_v1', '--explore-deadlock', 'replan_v1',
            '--boundary-association', 'extent_v1', '--boundary-retry', 'navigation_v1']
    main([*args, '--expected-workflow-id', 'e2e-boundary-repair-v212'])
    b = json.loads(capsys.readouterr().out)
    assert b['execution_bundle_id'] == 'e2e-boundary-repair-v212'
    assert b['e2e_options']['boundary_association'] == 'extent_v1'
    assert b['e2e_options']['boundary_retry'] == 'navigation_v1'
    reviewed([*args, '--expected-workflow-id', 'e2e-reviewed-runtime-v210'])
    b = json.loads(capsys.readouterr().out)
    assert b['parent_execution_bundle_id'] == 'e2e-boundary-repair-v212'
    assert b['inherited_results'] is False
    record = json.loads(Path('experiments/2026-10-12-merge-train/pr453/retired-bundles.json').read_text())
    for item in record['retired'][0]['blobs']:
        assert hashlib.sha256(Path(item['preserved']).read_bytes()).hexdigest() == item['sha256']


def test_unstable_association_is_preserved_in_actual_ownmap_record():
    from scripts.run_e2e_ownmap_live import ownmap_record
    g, boundary = fixture(); association = Association(g)
    for i, x in enumerate((1., 1., 1.2)):
        boundary['center'] = [x, -.6]
        receive(association, boundary, i, i*.2)
    assert not g.e2e_gate.references
    g.explorer = SimpleNamespace(local_pose=np.zeros(3)); g.stage = 'explore'
    robot = SimpleNamespace(goal=g, nav_command={'kind':'hold'})
    obs = {'frame_id':2, 'sha256':'own-frame'}
    record = ownmap_record(robot, obs, {'boundary_association':association.last}, .4)
    saved = json.loads(json.dumps(record))['boundary_association']
    assert saved == association.last
    assert saved['overlap_fraction'] == pytest.approx(.4)
    assert saved['frames'] == 1 and saved['accepted'] is False
    assert 'boundary_association' not in ownmap_record(robot, obs, {}, .4)


def test_native_arrival_and_rotation_keep_both_would_stop_records():
    from harness import e2e_boundary_views as v
    from harness.e2e_exploration import Navigator
    from harness.public_navigation_unknown import UnknownCostmap
    g, _ = fixture(); driver = SimpleNamespace(pose=np.zeros(3))
    g.explorer = SimpleNamespace(map_to_odom=np.zeros(3), navigator=Navigator(driver))
    g.dev_light = True; g.e2e_gate.current = {}
    g.receive = lambda **kw: ({'kind':'hold'}, {})
    v.install(g, v.OPTION, coverage=v.COVERAGE_OPTION)
    n = g.explorer.navigator
    n.view_active = True; n.view_started = 0.
    n.target = np.zeros(2); n.view_target_own = np.zeros(2); n.heading = .5
    c = UnknownCostmap(np.full((100,100),255,np.uint8), [-2.5,-2.5], .05)
    before = c.raw.copy(); pose = np.zeros(3)
    plan = n.update(c, pose, .2)
    assert n.phase == 'B_candidate_observe' and n.view_active
    action = n.command(c, pose, plan, .2)
    assert action['turn'] != 0
    _, trace = g.receive()
    saved = json.loads(json.dumps(trace))['boundary_view']
    assert saved['would_stops'] == 2
    assert set(saved['checks_by_stage']) == {'terminal','rotation'}
    for row in saved['checks_by_stage'].values():
        assert row['strict_clear'] is False and row['native_clear'] is True
    assert {e['stage'] for e in n.events if e['reason']=='B_view_would_stop_observed_coverage'} == {'terminal','rotation'}
    np.testing.assert_array_equal(before, c.raw)


def test_saved_view_probe_forwards_observed_keyword_and_restores_hook(monkeypatch, tmp_path):
    import hashlib
    import importlib.util
    from harness import e2e_boundary_views as v
    from harness.public_navigation_unknown import UnknownCostmap
    path = Path('experiments/2026-10-12-e2e-idle/probe_view_path.py')
    spec = importlib.util.spec_from_file_location('_merge_train_view_probe', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    data = b'synthetic frame bytes'; (tmp_path/'frame.bin').write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    records = {
        'bundle.json':[{'seed':61001,'e2e_options':{},'study_options':{}}],
        'frames.jsonl':[{'frame_id':1,'sim_time':0.,'path':'frame.bin','sha256':digest}],
        'ownmap.jsonl':[{'frame_id':1,'t':0.,'sha256':digest,'pose_own_m':[0.,0.,0.],'command':{'kind':'hold'}}],
        'commands.jsonl':[], 'range.jsonl':[{}]}
    monkeypatch.setattr(module, 'rows', lambda p:records[p.name])
    monkeypatch.setattr(module.Image, 'open', lambda f:SimpleNamespace(convert=lambda mode:np.zeros((2,2,3),np.uint8)))
    c = UnknownCostmap(np.full((100,100),255,np.uint8), [-2.5,-2.5], .05)
    outcomes = []
    class Robot:
        def __init__(self, *args, **kwargs):
            self.goal=SimpleNamespace(explorer=SimpleNamespace(local_pose=np.zeros(3),navigator=SimpleNamespace(view_active=True)))
            self.nav_command={'kind':'hold'}
        def receive(self, *args):
            for observed in (True, False):
                outcomes.append(v.observed_path_clear(c,[0.,0.,0.],[[0.,0.],[.5,0.]],0.,observed=observed))
            return {}
    monkeypatch.setattr(module, 'Robot', Robot)
    original = v.observed_path_clear
    result = module.probe(tmp_path, 1)
    assert outcomes == [False, True]
    assert result['path_checks'][0]['native_path_clear'] is True
    assert result['navigation_command_differences'] == 0
    assert v.observed_path_clear is original


def test_native_artifact_correction_preserves_original_manifest_and_verifies_entries():
    import hashlib
    import subprocess
    correction = json.loads(Path('experiments/2026-10-12-merge-train/pr453/native-artifact-correction.json').read_text())
    manifest = Path(correction['original_manifest']).read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == correction['original_manifest_sha256']
    source_sha = correction['source_sha']
    assert len(source_sha) == 40 and all(c in '0123456789abcdef' for c in source_sha)
    repo = Path(__file__).resolve().parents[1]
    def archived_bytes(name):
        return subprocess.check_output(['git', 'show', f'{source_sha}:{name}'], cwd=repo)
    assert archived_bytes(correction['original_manifest']) == manifest
    entries = json.loads(manifest)
    assert len(entries) == correction['unchanged_entries_verified'] + len(correction['corrections'])
    for name, recorded in entries.items():
        if name in correction['corrections']:
            item = correction['corrections'][name]
            assert recorded == item['recorded']
            recorded = item['corrected']
        # This correction describes a fixed historical snapshot. Later run
        # summaries and README updates must not rewrite its recorded hashes.
        data = archived_bytes(name)
        assert len(data) == recorded['bytes']
        assert hashlib.sha256(data).hexdigest() == recorded['sha256']
