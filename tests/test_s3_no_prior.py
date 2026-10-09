import copy
import json
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_s3_no_prior as m
from harness import zone_s3_no_prior_contract as c


def test_new_scenario_and_source_contract():
    b = c.bundle('a'*40)
    c.verify(b)
    assert b['weld'] == 'off' and b['known_start_information'] is False
    assert b['seed'] == 14201 and b['preregistration']['run_limit'] == 1
    assert b['controller_inputs'] == ['own_rgb', 'static_map', 'own_command_history']
    assert b['idle_robot_contacts'] == 'off'
    assert all(o['destination_zone'] == 'B' for o in c.inputs()[2]['orders'])
    bad = copy.deepcopy(b)
    bad['controller_config']['options']['start_prior'] = 'off'
    with pytest.raises(ValueError):
        c.verify(bad)


def test_three_real_localizers_never_call_dock_prior(monkeypatch):
    from sim import zone_model_conventions
    def forbidden(*a, **k):
        raise AssertionError('dock prior forbidden')
    monkeypatch.setattr(zone_model_conventions, 'spawn_layout', forbidden)
    static = c.hp.resolve(c.old.solo.MAP_ID)[0]
    runtime = m.Runtime(static, c.inputs()[2]['orders'], c.ROOT/c.old.solo.CALIBRATION,
        c.old.solo.CALIBRATION_SHA, seed=14201, config=c.controller_config())
    try:
        commands = {r: {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500} for r in m.ROBOTS}
        runtime.initial_commands(0., commands)
        clouds = []
        for rid, own in runtime.localizers.items():
            pf = own.pose.provider.loc._pf
            clouds.append(pf.px)
            assert pf.n == 100000 and np.ptp(pf.px[:, 2]) > 6.2
            assert own.pose.provider.prior['known_own_dock'] is False
            assert own.record()['start_prior']['dock_prior_calls'] == 0
            assert own.destination == 'B'
            assert len(own.commands) == 1
        assert not any(np.shares_memory(clouds[i], clouds[j]) for i in range(3) for j in range(i))
        for rid in ('r1', 'r2'):
            assert runtime.pair.actors[rid].pose.localizer is runtime.localizers[rid]
            runtime.on_command(rid, .05, dict(kind='mecanum', forward=.35, left=0., turn=0., duration_s=.1))
            assert runtime.localizers[rid].pose.provider.loc._pf.n == 2000
            assert len(runtime.localizers[rid].commands) == 2
        assert runtime.localizers['r3'].pose.provider.loc._pf.n == 100000
        # Exercise the real own-frame path on both sides of the startup handoff.
        # Synthetic pixels test transport/filter ownership, not localization accuracy.
        from tests.test_solo_cyan_v106 import observation
        runtime.on_frames(.2, {r: observation(.2, 1, rid=r) for r in m.ROBOTS})
        for rid, action in runtime.step(.2):
            runtime.on_command(rid, .2, action)
        assert all(v == 0 for v in runtime.wait_robot_s.values())
        runtime.boot_finished_at = .2
        runtime.on_frames(.4, {r: observation(.4, 2, rid=r) for r in m.ROBOTS})
        for rid in ('r1', 'r2'):
            assert runtime.pair.actors[rid].last_report.t_est == runtime.localizers[rid].last_report.t_est
            assert len(runtime.localizers[rid].pose_log) == 2
    finally:
        runtime.close()


def test_pose_port_refuses_prior_and_cross_robot_frame():
    own = SimpleNamespace(robot_id='r1')
    port = m.OwnPosePort(own)
    with pytest.raises(AssertionError):
        port.init_prior((0, 0, 0), (1, 1, 1))
    port.frame = (dict(robot_id='r2', sim_time=0.), None)
    with pytest.raises(ValueError):
        port.on_frame(0., np.zeros((2, 2, 3)))


def test_prior_present_frozen_runtime_and_config_bytes_unchanged():
    paths = ['harness/zone_s3_host.py', 'harness/zone_s3_door_yield.py', 'scripts/run_s3_host.py',
        'sim/zone_s3_host.py', 'configs/zone_study_dev/dev_s1lite.json', 'configs/simulation_workflows.json']
    for p in paths:
        frozen = subprocess.check_output(['git', 'show', 'd3393847f763a9b67db2789de434d47ec7ae1fdc:'+p], cwd=c.ROOT)
        assert (c.ROOT/p).read_bytes() == frozen, p


def test_default_cli_does_not_construct_or_execute(monkeypatch, capsys):
    from scripts import run_s3_no_prior as runner
    monkeypatch.setattr(runner, 'run', lambda *a, **k: pytest.fail('plan started runtime'))
    assert runner.main(['--expected-source-sha', 'a'*40, '--output', '/nonexistent/s3-plan']) == 0
    assert json.loads(capsys.readouterr().out)['no_prior'] == 'off'
    with pytest.raises(ValueError, match='explicit'):
        runner.main(['--expected-source-sha', 'a'*40, '--output', '/nonexistent/s3-plan', '--execute'])


def test_posthoc_does_not_accept_wrong_mode_or_unfinished_commands(tmp_path):
    from scripts.evaluate_s3_no_prior import metrics
    result = dict(status='DEV_NOT_DELIVERED', evaluation={'orders': {
        'order-1': {'complete': True}, 'order-5': {'complete': True}}}, wall_s=10, check_sim_s=1)
    student = dict(localizers={}, pair={'robots': {}})
    for rid in m.ROBOTS:
        path = tmp_path/f'eval_only/{rid}'
        path.mkdir(parents=True)
        (path/'trajectory.jsonl').write_text('\n'.join(json.dumps(dict(t=t, robot_xyz_m=[0, 0, 0],
            robot_yaw_rad=0)) for t in (0., 1.))+'\n')
        student['localizers'][rid] = dict(state='search' if rid == 'r3' else 'done', poses=[
            dict(t=.5, t_est=.34, x=1. if rid == 'r1' else 0., y=0., yaw=0., std_xy_m=.04)])
        student['pair']['robots'][rid] = {'jobs': [dict(kind='pair_carry', confirmation='unconfirmed')]}
    (tmp_path/'result.json').write_text(json.dumps(result))
    (tmp_path/'student_record.json').write_text(json.dumps(student))
    q = metrics(tmp_path)
    assert q['robots']['r1']['first_convergence']['wrong_mode'] is True
    assert q['robots']['r1']['success'] is False
    assert q['robots']['r2']['success'] is True
    assert q['robots']['r3']['delivery_complete'] is True
    assert q['robots']['r3']['success'] is False
    assert q['door_deadlocks'] == []
