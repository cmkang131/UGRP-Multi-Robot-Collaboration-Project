"""VIS4 command-only motion regression and dev/test isolation (no MuJoCo)."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'experiments'/'2026-09-26-vision-loc'
sys.path.insert(0, str(HERE))

import vision_loc as vl
import vision_motion as vm
import vision_pf
import diagnose_v4 as diag


def pf(options=None):
    base = vl.mp.load_m1_localizer()
    params = copy.deepcopy(base.DEFAULT_PARAMS)
    params['particles'] = 8
    params['roughen'] = [0., 0., 0.]
    for key in ('motion', 'motion_loaded'):
        params[key] = dict(gain=np.eye(3).tolist(), tau_s=.2, tau_stop_s=.05,
                           noise_abs=[0., 0., 0.], noise_rel=[0., 0., 0.], scale_std=0., scale_walk=0.)
    params['motion_profiles'] = {'fine': copy.deepcopy(params['motion'])}
    static = json.loads((HERE/'maps/zone_wide_door_walls_v3_notags.json').read_text())
    result = vision_pf.make_robust_pf(base, static, params, {}, {}, {}, 1, motion_v4=options)
    result.init_gaussian([0., 0., 0.], [0., 0., 0.])
    return result


def command(t=0., duration=.073, **kwargs):
    return {'t': t, 'kind': 'mecanum', 'forward': 1., 'left': 0., 'turn': 0., 'duration_s': duration, **kwargs}


def test_exact_expiry_integrates_only_issued_duration_and_stop_tail():
    p = pf({'exact': True})
    p.command(command())
    p.predict_to(.073)
    v, d = vm.lag_integral(np.zeros(3), np.array([1., 0., 0.]), .073, .2)
    assert np.allclose(p.px[0], d, atol=1e-12)
    p.predict_to(.123)
    _, tail = vm.lag_integral(v, np.zeros(3), .05, .05)
    assert np.allclose(p.px[0], d + tail, atol=1e-12)


def test_exact_translation_is_independent_of_observation_partition():
    a, b = pf({'exact': True}), pf({'exact': True})
    for p in (a, b): p.command(command())
    a.predict_to(.4)
    for t in (.013, .07, .071, .084, .21, .4): b.predict_to(t)
    assert np.allclose(a.px, b.px, atol=1e-12)
    assert np.allclose(a.vel, b.vel, atol=1e-12)


def test_delay_is_causal_and_expiry_is_shifted_with_onset():
    p = pf({'exact': True, 'delay_s': {'unloaded': .1}})
    p.command(command())
    p.predict_to(.1)
    assert np.all(p.px == 0.)
    p.predict_to(.173)
    _, expected = vm.lag_integral(np.zeros(3), np.array([1., 0., 0.]), .073, .2)
    assert np.allclose(p.px[0], expected, atol=1e-12)
    assert p.cmd_expires == pytest.approx(.173)


def test_midpoint_heading_tracks_constant_body_twist():
    p=pf({'exact':True}); p.params['motion']['tau_s']=1e-6
    p.command(command(duration=1.,turn=1.)); p.predict_to(1.)
    assert p.px[0,0] == pytest.approx(math.sin(1.),abs=.0005)
    assert p.px[0,1] == pytest.approx(1.-math.cos(1.),abs=.0005)
    assert p.px[0,2] == pytest.approx(1.,abs=2e-6)


def test_delay_switch_preserves_command_order():
    p=pf({'exact':True,'delay_s':{'unloaded':.15,'loaded':0.}})
    p.command(command(duration=.3))
    p.load.loaded=True
    p.command({'t':.01,'kind':'hold'})
    assert [t for t,_ in p.pending_wheels] == [.15,.15]
    p.predict_to(.2)
    assert not p.pending_wheels and np.all(p.px==0.) and np.all(p.cmd==0.)


def test_stop_supersedes_pending_velocity_and_new_command_supersedes_old_expiry():
    p = pf({'exact': True, 'delay_s': {'unloaded': .1}})
    p.command(command(duration=.5))
    p.command({'t': .03, 'kind': 'hold'})
    p.predict_to(.13)
    assert np.all(p.cmd == 0.) and not p.pending_wheels
    q = pf({'exact': True})
    q.command(command(duration=.1))
    q.command(command(t=.05, duration=.3, forward=.5))
    q.predict_to(.2)
    assert q.cmd_expires == pytest.approx(.35) and q.cmd[0] == .5


def test_fine_profile_and_own_load_choose_delay_without_truth():
    p = pf({'exact': True, 'delay_s': {'unloaded': .1, 'loaded': .15}})
    p.load.loaded = True  # fixture representing own issued grasp history
    p.command(command())
    assert p.pending_wheels[0][0] == .15
    p.set_motion_profile(.2, 'fine')
    p.command(command(t=.2))
    assert not p.pending_wheels and p.cmd_expires == pytest.approx(.273)


def test_servo_command_keeps_issued_time_during_wheel_delay():
    p = pf({'exact': True, 'delay_s': {'unloaded': .1}})
    p.command(command())
    p.command({'t': .03, 'kind': 'look', 'pan_pulse': 1600})
    assert p.servo[6] == 1600 and p.own_servo_cmd_t == .03 and np.all(p.px == 0.)


@pytest.mark.parametrize('t', [float('nan'), float('inf'), -.1])
def test_bad_or_backwards_time_rejected(t):
    with pytest.raises(ValueError, match='time'): pf({'exact': True}).predict_to(t)


@pytest.mark.parametrize('options', [[], {'exact': 1}, {'extra': 0}, {'delay_s': []},
    {'exact': True, 'delay_s': {'unloaded': -.1}}, {'exact': True, 'delay_s': {'loaded': float('nan')}},
    {'exact': True, 'delay_s': {'loaded': True}}, {'delay_s': {'loaded': .1}}])
def test_motion_options_fail_closed(options):
    with pytest.raises(ValueError): vm.validate_motion(options)


def test_default_and_explicit_disabled_have_identical_rng_and_results():
    a, b = pf(), pf({'exact': False})
    for p in (a, b):
        p.command(command()); p.predict_to(.31); p._normalize_and_resample()
    assert np.array_equal(a.px, b.px)
    assert a.rng.bit_generator.state == b.rng.bit_generator.state


def test_fit_response_has_exact_expiry_and_delay():
    times = np.array([0., .1, .173, .223])
    v = diag.command_response(times, [command()], np.eye(3), .2, .05, .1)
    end, d = vm.lag_integral(np.zeros(3), np.array([1., 0., 0.]), .073, .2)
    _, tail = vm.lag_integral(end, np.zeros(3), .05, .05)
    assert np.allclose(v[0], 0.)
    assert np.allclose(v[1]*.073, d)
    assert np.allclose(v[2]*.05, tail)


def test_dev_guard_rejects_old_tests_and_train_before_io():
    for episodes in ([], ['vl3-test-s951'], ['vl-test-s917'], ['vl-train-s901'], ['vl-dev-s910']*2):
        with pytest.raises(ValueError): diag.require_dev(episodes)
    plan = json.loads(diag.PLAN.read_text())
    assert set(plan['fit_episodes']).isdisjoint(plan['validation_episodes'])
    diag.require_dev(plan['fit_episodes'] + plan['validation_episodes'])


def test_fitter_robust_scale_resists_outlier_and_has_bounds():
    x=np.ones(100); y=np.full(100,1.2); y[-1]=1000.
    scale,_=diag.robust_scale(x,y,np.ones(100),.03)
    assert scale == pytest.approx(1.2,abs=.001)
    assert diag.robust_scale(x,np.ones(100)*100,np.ones(100),.03)[0] == 1.5


def test_results_refuse_overwrite(tmp_path):
    path=tmp_path/'result.json'; diag.save(path,{'value':1})
    with pytest.raises(FileExistsError): diag.save(path,{'value':2})
    assert json.loads(path.read_text()) == {'value':1}


def test_new_suite_is_in_ci_collection():
    import fnmatch
    spec = importlib.util.spec_from_file_location('ci_v4', ROOT/'scripts'/'run_ci_tests.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert any(fnmatch.fnmatch('tests/test_vision_loc_v4.py', p) for p in module.TEST_PATTERNS)


def test_motion_diagnostics_do_not_change_particle_state_or_rng():
    p=pf({'exact':True}); p.command(command()); p.predict_to(.05)
    state=copy.deepcopy(p.rng.bit_generator.state); particles=p.px.copy()
    est=p.estimate()
    assert len(est['diag']['scale_mean']) == 3 and len(est['diag']['command_velocity']) == 3
    assert p.rng.bit_generator.state == state and np.array_equal(p.px,particles)


def test_draft_has_fresh_seed_and_both_route_pairs_and_stays_disabled():
    import design_v4
    table=json.loads((HERE/'episodes_v4_DRAFT.json').read_text())
    assert table == design_v4.design()
    pre=json.loads((HERE/'prereg_v4_DRAFT.json').read_text())
    assert pre['status']=='DRAFT' and pre['execution_enabled'] is False and pre['source_commit'] is None
    assert len(pre['episodes']['primary'])==8 and len(pre['episodes']['reserve_order'])==4
    old=[e for f in ('episodes.json','episodes_v3.json') for e in json.loads((HERE/f).read_text())['episodes']]
    seeds=set(); pairs=set(); slots=set()
    for e in old+table['episodes']:
        cell=tuple(e.get('cyan_cell',design_v4.cyan_cell(e['seed'],e['goal'])))
        a,b=(e['spawn_y'],cell),(cell,e['slot_id'])
        if e in table['episodes']:
            assert e['seed'] not in seeds and a not in pairs and b not in slots
        seeds.add(e['seed']); pairs.add(a); slots.add(b)


def test_geometry_gates_are_conservative_and_not_old_five_cm_path_claim():
    import gates_v4 as gates
    b=gates.budgets()
    assert b['door_lateral_remaining_m'] == pytest.approx(.054738378538)
    assert b['door_lateral_gate_m'] < b['door_lateral_remaining_m']
    assert b['slot_position_gate_m'] < min(b['slot_x_remaining_m'],b['slot_y_remaining_m'])
    assert b['path_position_gate_m'] < b['path_translation_remaining_at_3deg_m']
    assert gates.joint_path_error(0.,math.radians(3)) > b['existing_path_joint_budget_m']
    assert gates.joint_path_error(.03,math.radians(3)) < b['path_joint_gate_m']
    assert gates.joint_path_error(.03,math.radians(363)) == pytest.approx(gates.joint_path_error(.03,math.radians(3)))
    assert gates.joint_slot_extent(.01,.01,math.radians(3)) < .045
    assert gates.joint_slot_extent(.01,.03,math.radians(3)) > .045


def test_selection_requires_validation_improvement_and_guards_oracle():
    import compare_v4 as comparison
    def cohort(p=.06,l=.04,y=2.,oracle=.05):
        return {'pooled':{k:{'door_loaded':{'pos_p90_m':p if k=='vision' else oracle,'lat_abs_p99_m':l,
                                         'yaw_p90_deg':y},'all':{'pos_p90_m':.5,'n':1000}} for k in ('vision','oracle')},
                'recovery_pooled':{'vision':{'lost_frames':100}}}
    values={v:{c:cohort() for c in ('all_dev','validation')} for v in ('b0','x1','m1')}
    assert comparison.select(values)['selected']=='b0'
    for c in ('all_dev','validation'): values['x1'][c]=cohort(p=.056)
    assert comparison.select(values)['selected']=='x1'
    values['x1']['all_dev']=cohort(p=.056,oracle=.056)
    assert comparison.select(values)['selected']=='b0'
    values['x1']['all_dev']=cohort(p=.056)
    values['x1']['validation']=cohort(p=.061)
    assert comparison.select(values)['selected']=='b0'


def test_motion_phase_diagnostic_honors_command_expiry():
    import analyze_motion_v4 as analysis
    names,active=analysis.wheel_phases([command()],np.array([.02,.06,.08,.2]))
    assert active.tolist()==[True,True,False,False]
    assert names.tolist()==['start','start','stop','stop']


def test_signed_report_keeps_direction_and_excludes_unloaded(tmp_path,monkeypatch):
    import report_v4
    ep='vl-dev-s910'; ev=tmp_path/'render'/ep/'eval_only'; ev.mkdir(parents=True)
    ev.joinpath('frames_eval.jsonl').write_text(json.dumps({'frame':0,'gt':[2.,0.,0.]})+'\n')
    out=tmp_path/'estimates'; out.mkdir()
    row={'frame':0,'t':0.,'loaded':True,
         'vision':{'xyyaw':[2.03,0.,0.],'diag':{'scale_mean':[1.1,1.,1.]}},
         'oracle':{'xyyaw':[1.99,0.,0.],'diag':{}}}
    out.joinpath(ep+'.estimates.jsonl').write_text(json.dumps(row)+'\n')
    monkeypatch.setattr(report_v4.vio,'RENDER_ROOT',tmp_path/'render')
    result=report_v4.signed_metrics(out,[ep])
    assert result['vision']['dx_mean_m']==pytest.approx(.03)
    assert result['oracle']['dx_mean_m']==pytest.approx(-.01)
    assert result['vision']['particle_scale_mean']==[1.1,1.,1.]
    row['loaded']=False
    out.joinpath(ep+'.estimates.jsonl').write_text(json.dumps(row)+'\n')
    assert report_v4.signed_metrics(out,[ep])['vision']['n']==0


def test_camera_diagnostic_uses_correct_base_and_optical_frames():
    import analyze_camera_v4 as camera
    servo={1:1500,3:777,4:2053,5:1646,6:1500}
    o,r=vl.mp.camera_in_base(servo);yaw=.3;c,s=math.cos(yaw),math.sin(yaw)
    rz=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
    delta=np.array([.001,.002,-.003]);base=np.array([2.,-.1,0.])
    label={'base_gt':[2.,-.1,yaw],'cam_pos_m':(base+rz@(o+delta)).tolist(),
           'cam_xmat':(rz@r@np.diag([1.,-1.,-1.])).ravel().tolist()}
    sag={'loaded':{'s3':[777],'bias':[0.],'dz':[0.]}}
    assert camera.camera_residual(label,servo,True,sag)==pytest.approx([.001,.002,-.003,0.,0.],abs=1e-10)


def test_equal_timestamp_camera_precedes_new_command(tmp_path):
    import cv2
    folder=tmp_path/'episode'; inputs=folder/'inputs'; inputs.mkdir(parents=True)
    cv2.imwrite(str(folder/'frame.jpg'),np.zeros((8,8,3),np.uint8))
    commands=[{'t':0.,'kind':'initial_servo_command','pulses':{'6':1500}},
              {'t':1.,'kind':'look','pan_pulse':1600}]
    frames=[{'t':1.,'frame':0,'file':'frame.jpg'},{'t':1.1,'frame':1,'file':'frame.jpg'}]
    inputs.joinpath('commands.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in commands))
    inputs.joinpath('frames.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in frames))
    inputs.joinpath('motion_profile.jsonl').write_text('')
    seen=[]
    class Sink:
        pan=None
        def command(self,row):
            self.pan=row['pulses']['6'] if row['kind']=='initial_servo_command' else row['pan_pulse']
        def frame(self,t,bgr,row): seen.append(self.pan)
    assert vl.replay(folder,[Sink()])==2 and seen==[1500,1600]
