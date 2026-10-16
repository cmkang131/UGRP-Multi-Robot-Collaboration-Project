"""v102 loaded pair gain calibration: static plan, command tables, bundle and registration (no physics)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import final_pair_loaded_gain_v102 as env  # noqa: E402
from harness import zone_final_pair_loaded_schedule as v92  # noqa: E402


def test_plan_is_registered_generator_output_and_admitted():
    plan = env.protocol()
    assert plan == env.build_plan()
    report = env.validate(plan, for_execution=True)
    assert set(report) == {'latA', 'latB', 'fwdA', 'fwdB'}
    assert all(v['admitted'] and v['start_pose_check']['admitted'] for v in report.values())
    assert [r['axis'] for r in plan['runs']] == ['left', 'left', 'forward', 'forward']
    assert not set(r['seed'] for r in plan['runs']) & set(env.RESERVED_SEEDS)


def test_config_bytes_equal_canonical_generator_output():
    text = (ROOT / env.CONFIG).read_text()
    assert text == json.dumps(env.build_plan(), ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def test_changed_plan_is_rejected():
    plan = json.loads(json.dumps(env.protocol()))
    plan['runs'][0]['segments'][0]['value'] = .13
    with pytest.raises(ValueError, match='contract changed'):
        env.validate(plan, for_execution=False)


def test_starts_and_seeds_do_not_reuse_v92_or_probe_values():
    plan = env.protocol()
    assert all(r['beam_xy_yaw'][:2] != [3.55, -.85] for r in plan['runs'])
    assert all(r['seed'] not in (911, *range(1101, 1107)) for r in plan['runs'])
    assert len({tuple(r['beam_xy_yaw']) for r in plan['runs']}) == 4


def test_levels_cover_registered_sets_with_both_signs_and_heldout_roles():
    plan = env.protocol()
    for run in plan['runs']:
        steps = [s for s in run['segments'] if s['phase'] == 'step']
        fit = {round(abs(s['value']), 6) for s in steps if s['role'] == 'fit'}
        held = {round(abs(s['value']), 6) for s in steps if s['role'] == 'heldout'}
        want_fit, want_held = ((env.LEFT_FIT, env.LEFT_HELD) if run['axis'] == 'left'
                               else (env.FORWARD_FIT, env.FORWARD_HELD))
        assert fit == {round(v, 6) for v in want_fit} and held == {round(v, 6) for v in want_held}
        assert not fit & held                                           # held-out levels are never fit levels
        for role in ('fit', 'heldout', 'fit_duration', 'heldout_leg'):
            signs = {s['value'] > 0 for s in steps if s['role'] == role}
            assert signs == {True, False}, role
        legs = [s for s in steps if s['role'] == 'heldout_leg']
        assert {round(abs(s['value']), 6) for s in legs} == {env.LEG[run['axis']]['value']}
        assert {s['duration_s'] for s in legs} == {env.LEG[run['axis']]['duration_s']}
        assert max(abs(s['value']) for s in steps) == (.1 if run['axis'] == 'left' else .05)


def test_recorded_fcc5215f_legs_are_replicated_tick_for_tick():
    # recorded 0.1 s cadence trains: left -0.0622 x128 ticks (12.8 s), forward +0.0443 x133 ticks (13.3 s)
    assert round(env.LEG['left']['duration_s'] / env.CONTROL_PERIOD_S) == 128
    assert round(env.LEG['forward']['duration_s'] / env.CONTROL_PERIOD_S) == 133
    plan = env.protocol()
    run = [r for r in plan['runs'] if r['id'] == 'latB'][0]                   # sign_first -1: -0.0622 first
    train = [e for e in env.events(run) if e['robot_id'] == 'r1' and e['action'].get('left') == -.0622]
    assert len(train) == 128 and {e['action']['duration_s'] for e in train} == {.15}


def test_event_table_follows_live_cadence_convention_and_port_limits():
    from sim.camera_robot_port import validate_raw_action
    plan = env.protocol()
    for run in plan['runs']:
        ev = env.events(run)
        assert [e['t'] for e in ev] == sorted(e['t'] for e in ev)
        motion = [e for e in ev if e['action']['kind'] == 'mecanum']
        assert len(motion) == 2 * round(sum(s['duration_s'] for s in run['segments']) / .1)
        assert motion[0]['t'] == env.PREP_END_S and motion[-1]['t'] < env.PREP_END_S + run['motion_s']
        by_t = {}
        for e in motion:
            by_t.setdefault(e['t'], {})[e['robot_id']] = e['action']
            validate_raw_action(e['action'], allow_reverse=True, allow_mecanum=True)
        for t, pair in by_t.items():
            a, b = pair['r1'], pair['r2']
            assert a['duration_s'] == b['duration_s'] == .15
            assert a['turn'] == b['turn'] == 0 and (a['forward'], a['left']) == (-b['forward'], -b['left'])
            assert (a['forward'] == 0) == (run['axis'] == 'left') or a['left'] == 0
        assert run['sim_cap_s'] == env.PREP_END_S + run['motion_s'] + env.END_HOLD_S
        assert round(run['sim_cap_s'] / .05) * .05 == pytest.approx(run['sim_cap_s'])


def test_every_step_is_preceded_by_a_zero_command_coast_so_it_starts_from_rest():
    for run in env.protocol()['runs']:
        segs = run['segments']
        assert segs[0]['phase'] == 'step' and env.PREP_END_S >= 40.      # preparation settles before the first step
        for a, b in zip(segs, segs[1:]):
            assert (a['phase'] == 'step') != (b['phase'] == 'step')      # strictly alternating step / coast
            if b['phase'] == 'coast':
                assert b['value'] == 0 and b['duration_s'] == env.COAST_S


def test_preparation_is_the_v92_servo_schedule():
    prep = env.prep_events()
    old = [e for e in v92.schedule() if e['t'] <= 24.]
    assert prep == sorted(old, key=lambda e: e['t']) or sorted(map(json.dumps, prep)) == sorted(map(json.dumps, old))


def test_stations_match_v92_for_yaw_zero_and_rotate_with_the_beam():
    from harness.zone_final_pair_calibration import teacher_stations
    from harness import zone_final_pair_contract as pair
    static = pair.resolve(env.MAP_ID)[0]
    old = teacher_stations(static)
    new = env.stations([3.55, -.85, 0.])
    for rid in ('r1', 'r2'):
        assert new[rid] == pytest.approx(old[rid])
    rot = env.stations([3.8, -1.05, env.HALF_PI])
    assert rot['r1'] == pytest.approx([3.8, -1.05 - .4732, env.HALF_PI], abs=1e-3)
    assert rot['r2'] == pytest.approx([3.8, -1.05 + .4732, 3 * env.HALF_PI], abs=1e-3)


def test_bundle_is_runnable_and_registered():
    b = env.bundle('fwdA')
    assert b['execution_bundle_id'] == env.BUNDLE_ID == 'zone-final-pair-loaded-gaincal-v102'
    assert b['check'] == 'calibration-loaded' and b['runnable'] and b['seed'] == 1203
    assert b['contact_profile'] == 'cargo_noslip_v1' and b['render_profile'] == 'floor_light_v1' and b['weld'] == 'off'
    assert b['controller_inputs'] == [] and b['teacher_only'] is True
    for p in (env.CONFIG, env.WORKFLOW, 'harness/final_pair_loaded_gain_v102.py',
              'scripts/run_final_pair_loaded_gain_v102.py', 'sim/final_pair_loaded_gain_v102.py'):
        assert p in b['source_sha256']
    with pytest.raises(ValueError):
        env.bundle('nope')


def test_workflow_catalog_entry():
    catalog = json.loads((ROOT / env.WORKFLOW).read_text())
    (wf,) = catalog['workflows']
    assert wf['id'] == env.WORKFLOW_ID and wf['version'] == env.WORKFLOW_VERSION
    assert wf['runner'] == 'scripts.run_final_pair_loaded_gain_v102'
    assert (ROOT / wf['entry']).is_file()


def test_runner_plan_only_prints_without_executing(capsys):
    from scripts import run_final_pair_loaded_gain_v102 as runner
    code = runner.main(['--check', 'calibration-loaded', '--run-id', 'latA', '--seed', '1201',
                        '--expected-source-sha', '0' * 40, '--output', '/tmp/never-created-v102'])
    assert code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['execution_started'] is False and plan['runnable'] is True and plan['seed'] == 1201
    assert not Path('/tmp/never-created-v102').exists()
    with pytest.raises(ValueError, match='seed'):
        runner.main(['--check', 'calibration-loaded', '--run-id', 'latA', '--seed', '911',
                     '--expected-source-sha', '0' * 40, '--output', '/tmp/never-created-v102'])
