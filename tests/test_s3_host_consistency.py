"""Consumer-boundary regressions for shared observation consistency."""
import copy
import functools
import json
from types import SimpleNamespace

import numpy as np
import pytest

from harness import pf_observation_consistency as c


def test_off_does_not_touch_consumers_or_arrays():
    invalid_consumer = object()
    score = np.array([-2., -8.])
    profiles = {'not_a_profile': object()}
    assert c.attach_s3(invalid_consumer) is invalid_consumer
    assert c.attach_ownmap(invalid_consumer) is invalid_consumer
    assert c.log_score(score, None) is score
    assert c.alpha_profiles(profiles) is profiles


def test_s3_actual_factory_binds_measurement_and_same_pulse_dictionary():
    from harness.zone_s3_sweep_contract import inputs, ROOT, hp
    from harness.zone_s3_sweep_contract import bundle
    from harness.zone_s3_consistent_runtime import Runtime
    b = bundle('0'*40)
    b['controller_config']['options']['observation_consistency'] = 'effective_sqrt_alpha_v1'
    rt = Runtime(hp.resolve(b['map_id'])[0], inputs()[2]['orders'], ROOT/b['calibration'],
        b['calibration_sha256'], seed=b['seed'], config=b['controller_config'])
    try:
        from harness.zone_solo_cyan_landmarks import Measurement
        for own in rt.localizers.values():
            pf = own.pose.provider.loc._pf
            selected = c._closure(pf.update_obs, 'selected').cell_contents
            score = selected.__globals__['likelihood']
            # Empty evidence remains exactly neutral, without fake precision.
            value = score(None, pf.px, Measurement(np.empty((0, 2)), []))
            assert np.array_equal(value, np.ones(pf.n))
            profiles = own.pulse_profiles
            pending = [pf.command]; found = False; seen = set()
            while pending:
                function = pending.pop()
                if id(function) in seen: continue
                seen.add(id(function))
                for cell in getattr(function, '__closure__', ()) or ():
                    value = cell.cell_contents
                    found |= value is profiles
                    if callable(value): pending.append(value)
            assert found, 'command predictor must consume the modified profile table'
            assert profiles is own.pulse_profiles
            assert own.observation_consistency_audit['scores'] == 1
            assert own.pulse_profiles['0:forward:0.35:0.10']['prediction_variance'][2] > 1e-6
            # Real slip factory has a second, authoritative pulse predictor.
            # Prove the final predictor consumes Q, not an obsolete dictionary.
            active = c._closure(pf.command, 'active').cell_contents
            start = np.tile([2., 0., 0.], (pf.n, 1))
            pf.initialized = True; pf.t = 0.; pf.px = start.copy()
            pf.logw = np.zeros(pf.n)
            pf.rng = SimpleNamespace(normal=lambda size: np.ones(size))
            original_profile = own.flow.profiles['0:forward:0.35:0.10']
            original_copy = copy.deepcopy(original_profile)
            own.pose.provider.on_command(dict(t=0.,kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.10))
            transformed = active.cell_contents[1]
            assert transformed is not original_profile
            assert transformed['mean_curve'] == original_copy['mean_curve']
            pf.predict_to(.05)
            changed = pf.px.copy()
            assert own.flow.profiles['0:forward:0.35:0.10'] == original_copy
            assert own.observation_consistency_audit['motion_noise_commands'] == 1
            pf.t=0.; pf.px=start.copy(); pf.logw=np.zeros(pf.n)
            active.cell_contents=(0.,original_profile)
            pf.predict_to(.05)
            assert not np.array_equal(changed,pf.px), 'alpha Q must change actual prediction'
    finally:
        rt.close()


def likelihood(field, points, poses, sigma, effective_points=12.):
    return np.full(len(np.atleast_2d(poses)), -len(points), float)


def proposal(field, points, camera, prior, covariance, rng, options, *, yaw_window_deg):
    # The real proposal uses the same function at all three boundaries.
    return tuple(likelihood(field, points, prior, 1.) for _ in range(3))


def test_ownmap_private_proposal_and_calibration_are_isolated():
    from harness.zone_s2_realism_contract_v122 import PULSE_MODEL
    from pathlib import Path
    profiles = json.loads(Path(PULSE_MODEL).read_text())['profiles']
    base = copy.deepcopy(profiles)
    original = functools.partial(proposal, yaw_window_deg=20.)
    grid = SimpleNamespace(_selective_proposal=original,
        odom=SimpleNamespace(driver=SimpleNamespace(profiles=profiles)))
    c.attach_ownmap(grid, observation_consistency='effective_sqrt_v1')
    args = (None, np.zeros((48, 2)), None, np.zeros((1, 3)), None, None, None)
    before, after = original(*args), grid._selective_proposal(*args)
    assert all(np.array_equal(x, [-48.]) for x in before)
    assert all(np.allclose(x, [-48/np.sqrt(12)]) for x in after)
    assert profiles == base
    assert grid.odom.driver.profiles is profiles
    for key, p in grid.odom.driver.profiles.items():
        assert p['mean_curve'] == base[key]['mean_curve']
        assert p['mean_delta'] == base[key]['mean_delta']
        assert np.all(np.asarray(p['prediction_variance']) >= base[key]['prediction_variance'])


def test_archived_replay_includes_controller_pose_feedback(tmp_path, monkeypatch):
    """The frontend alone misses GoalRoute._localize's whole-cloud correction."""
    import hashlib
    import importlib.util
    import sys
    import types
    from pathlib import Path
    from PIL import Image
    root = Path(__file__).resolve().parents[1]
    script = root/'experiments/2026-10-09-s3-no-prior/s3fix6/replay_ownmap.py'
    spec = importlib.util.spec_from_file_location('consistency_replay_test', script)
    replay = importlib.util.module_from_spec(spec); spec.loader.exec_module(replay)
    raw = tmp_path/'raw'; (raw/'robots/r3').mkdir(parents=True)
    Image.new('RGB', (2, 2)).save(raw/'frame.jpg')
    digest = hashlib.sha256((raw/'frame.jpg').read_bytes()).hexdigest()
    frames = [dict(sim_time=float(i), frame_id=i, path='frame.jpg', sha256=digest) for i in range(12)]
    ob = dict(segments=[])
    covariance = np.eye(3)
    odom = SimpleNamespace(pose=[0., 0., 0.], covariance=covariance)
    grid = SimpleNamespace(odom=odom, poses=np.zeros((1,3)), weights=np.ones(1), rng=np.random.default_rng(1))
    explorer = SimpleNamespace(memory=SimpleNamespace(self_map=grid))
    issued = []
    class Controller:
        def command(self, row): issued.append(row['t'])
        def receive(self, **kw):
            assert issued == ([] if kw['t'] == 10. else [10.])
            # Stand-in for the real causal route match, after frontend update.
            odom.pose[0] += 1.
            return dict(t=kw['t'],kind='hold'), {}
    controller = Controller()
    def module(name, **attributes):
        m=types.ModuleType(name);m.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules,name,m)
    import harness, scripts, sim
    for package in (harness,scripts,sim):
        monkeypatch.setattr(package,'__path__',list(package.__path__))
    module('harness.active_camera', SEARCH={})
    module('harness.active_wall_vision', observe=lambda *a,**k:ob)
    module('scripts.run_own_map_return_repeat', actor=lambda *a,**k:explorer)
    module('scripts.run_active_wall_rotleft', install_profile=lambda *a,**k:None)
    module('scripts.run_goal_route_continuous', controller=lambda *a,**k:controller)
    data={'bundle.json':dict(task=dict(seed=1)),
        'own-inputs.json':[dict(frame_id=i,own_range=None) for i in (10,11)]}
    line_data={'robots/r3/frames.jsonl':frames,
        'robots/r3/commands.jsonl':[dict(t=0.,kind='initial_servo_command',pulses={}),dict(t=10.,kind='hold'),dict(t=11.,kind='hold')],
        'own-contacts.jsonl':[dict(t=float(i),frame_id=i,**ob) for i in (10,11)],
        'own-controller.jsonl':[dict(command=dict(t=float(i),kind='hold')) for i in (10,11)],
        'frontend-covariances.jsonl':[dict(t=float(i),frame_id=i,pose=[float(i-9),0.,0.],covariance=covariance.tolist()) for i in (10,11)]}
    for name,value in data.items(): (raw/name).write_text(json.dumps(value))
    for name,value in line_data.items(): (raw/name).write_text(''.join(json.dumps(r)+'\n' for r in value))
    replay.replay(raw,tmp_path/'out',root,'off')
    result=json.loads((tmp_path/'out/result.json').read_text())
    assert result['frames']==2 and result['original_frontend_equal'] and result['original_proposals_equal']


def test_ownmap_alpha_reaches_actual_cloud_covariance():
    """Recorded consumer source: command -> callback -> own-scan GMapping Q."""
    import math
    from pathlib import Path
    from types import MethodType
    from harness.zone_s2_realism_contract_v122 import PULSE_MODEL
    asset = json.loads((Path(__file__).parent/'fixtures/ownmap_motion_consumer_5b330946.json').read_text())
    model = json.loads(Path(PULSE_MODEL).read_text())
    namespace = dict(np=np, math=math, AXES=('forward', 'left', 'turn'),
        wrap=lambda x: (x+np.pi)%(2*np.pi)-np.pi,
        model=lambda: copy.deepcopy(model),
        CSMOptions=lambda: SimpleNamespace(floor=lambda: np.eye(3)*1e-6))
    for row in asset['snippets']:
        exec(compile(row['source'], row['path']+':'+row['name'], 'exec'), namespace)
    namespace['RaoBlackwellizedGrid'] = SimpleNamespace(propagate=namespace['propagate'])

    def consumer(option):
        g = SimpleNamespace(poses=np.zeros((2, 3)), pending_cov=np.repeat((np.eye(3)*1e-6)[None], 2, 0),
            best=0, weights=np.full(2, .5), _selective_state=dict(previous=[0.,0.,0.], noise_frames=0),
            _selective_proposal=functools.partial(proposal, yaw_window_deg=20.))
        odom = object.__new__(namespace['CloudOdometry'])
        odom.owner=g; odom.driver=namespace['PulseOdometry'](); g.odom=odom
        odom.driver.step_callback=MethodType(namespace['_command_propagate'], g)
        odom.advance=MethodType(namespace['_advance'], odom)
        c.attach_ownmap(g, observation_consistency=option)
        return g

    for axis, u, loaded in [('forward', .35, False), ('turn', .35, False),
                             ('left', .65, False), ('forward', .35, True)]:
        pair=[consumer(option) for option in ('effective_sqrt_v1','effective_sqrt_alpha_v1')]
        for g in pair:
            g.odom.command(dict(t=0.,kind='initial_servo_command',pulses={'1':1400 if loaded else 2000}))
            g.odom.command(dict(t=0.,kind='mecanum',duration_s=.65 if axis=='left' else .10,**{axis:u}))
            g.odom.advance(.2)
        before,after=pair
        assert np.array_equal(before.poses,after.poses)
        assert before.odom.driver.profiles == after.odom.driver.profiles
        delta=after.pending_cov-before.pending_cov
        assert np.linalg.eigvalsh(delta).min() >= -1e-15
        if axis=='forward' and not loaded:
            assert np.any(delta>0), 'Q must reach the cloud, not only driver covariance'
            assert after.observation_consistency_audit['motion_noise_augmented'] == 1
        if loaded or axis=='left':
            assert np.array_equal(before.pending_cov,after.pending_cov)
        pending=after.pending_cov.copy()
        after.odom.advance(.2)
        assert np.array_equal(pending,after.pending_cov), 'do not double-count Q'
        assert namespace['_advance'].__globals__['motion_variance'] is namespace['motion_variance']
