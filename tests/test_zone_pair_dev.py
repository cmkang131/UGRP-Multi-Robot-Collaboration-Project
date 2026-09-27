"""Dev admission/provenance/evaluation without physical steps or model calls.

The frozen M2 controller import requires MuJoCo; its fake-world integration
case explicitly skips without it. No test constructs a MuJoCo world.
"""
from __future__ import annotations

import copy
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

from scripts import run_zone_pair_dev as dev
from scripts import evaluate_zone_pair_dev as ev
from scripts.zone_pair_dev_runtime import endpoint, make_scene, queue_snapshot


def config():
    return json.loads(dev.PREREG.read_text())


def arguments(tmp_path, *extra):
    return dev.parser().parse_args(['--run-id', 'dev03', '--output', str(tmp_path / 'new'), *extra])


@pytest.mark.parametrize('run_id,seed', [('dev03', 901), ('dev04', 902)])
def test_prereg_admission(tmp_path, run_id, seed):
    args = arguments(tmp_path, '--run-id', run_id)
    p, case = dev.load_config(args)
    assert case['seed'] == seed
    assert p['planned_run_count'] == 2
    assert p['limits']['model_calls'] == 0


@pytest.mark.parametrize('run_id', ['dev05', 'dev06'])
def test_v3_draft_prepares_but_cannot_execute_before_startup_decision(tmp_path, run_id):
    draft = dev.PREREG.with_name('prereg_v3_DRAFT.json')
    args = arguments(tmp_path, '--prereg', str(draft), '--run-id', run_id)
    p, case = dev.load_config(args)
    assert p['supersedes']['sha256'] == dev.sha_file(dev.PREREG)
    assert case['id'] == run_id and p['execution_readiness']['coordinator_decision'] is None
    assert p['criteria'] == config()['criteria'] and p['limits'] == config()['limits']
    assert p['execution_readiness']['spawn_change_applied'] is False
    args.execute = True
    with pytest.raises(ValueError, match='prepare-only'):
        dev.load_config(args)
    assert not args.output.exists()


def test_v2_freezes_profile_hashes_and_recalculates_budgets():
    p = config()
    old = json.loads(dev.PREVIOUS_PREREG.read_text())
    assert dev.sha_file(dev.PREVIOUS_PREREG) == '85334a68bae0d35c197c612cd610c84307c0eba268a34247e71f4e233a0fe0f3'
    assert [r['id'] for r in old['runs']] == ['dev01', 'dev02']
    receipt = dev.profile_contract()
    assert receipt == p['contact_profile_contract']
    assert receipt['sha256'] == dev.digest({k: v for k, v in receipt.items() if k != 'sha256'})
    assert receipt['timestep_s'] == .00025
    assert receipt['noslip_iterations'] == 10
    assert receipt['base_profile'] == 'local_contact_fine'
    assert p['timing']['gt_sample_steps'] == 200
    assert p['criteria']['gt_sample_period_s'] == .05
    assert p['criteria']['max_sample_gap_s'] == .05035
    assert p['timing']['max_physics_steps'] == 3_600_000
    assert p['timing']['physics_step_multiplier'] == 8
    assert p['limits']['sim_s'] == 900
    assert p['limits']['wall_s'] == 57_600
    assert p['limits']['outer_wall_timeout_s'] == 57_660


def test_profile_probe_derives_options_instead_of_repeating_a_timestep(monkeypatch):
    from sim import dispatch_contact_profile as base
    from sim import zone_cargo_contact as cargo
    original = base.contact_profile
    def changed_profile(xml, profile):
        return original(xml, profile).replace('timestep=".00025"', 'timestep=".000125"')
    monkeypatch.setattr(base, 'contact_profile', changed_profile)
    monkeypatch.setitem(cargo.CARGO_PROFILES['cargo_noslip_v1']['option'], 'noslip_iterations', '11')
    receipt = dev.profile_contract()
    assert receipt['timestep_s'] == .000125 and receipt['noslip_iterations'] == 11
    assert receipt['sha256'] != config()['contact_profile_contract']['sha256']
    timing, limits = dev.timing_contract(json.loads(dev.PREVIOUS_PREREG.read_text()), receipt['timestep_s'])
    assert timing['gt_sample_steps'] == 400 and timing['max_physics_steps'] == 7_200_000
    assert limits['wall_s'] == 115_200


@pytest.mark.parametrize('fault', ['old_prereg', 'profile_hash', 'profile_source_hash', 'timestep', 'sampling',
                                   'contact_steps', 'wall', 'outer_wall', 'old_run_ids', 'profile_drift'])
def test_v2_refuses_stale_or_altered_contract_before_prepare(tmp_path, monkeypatch, fault):
    p = config()
    args = arguments(tmp_path)
    if fault == 'old_prereg':
        p = json.loads(dev.PREVIOUS_PREREG.read_text())
    elif fault == 'profile_hash':
        p['contact_profile_contract']['sha256'] = '0' * 64
    elif fault == 'profile_source_hash':
        p['contact_profile_contract']['source_sha256']['sim/dispatch_contact_profile.py'] = '0' * 64
    elif fault == 'timestep':
        p['environment']['timestep_s'] = .002
    elif fault == 'sampling':
        p['criteria']['max_sample_gap_s'] = .0521
    elif fault == 'contact_steps':
        p['timing']['max_physics_steps'] = 450_000
    elif fault == 'wall':
        p['limits']['wall_s'] = 7200
    elif fault == 'outer_wall':
        p['limits']['outer_wall_timeout_s'] = 7260
    elif fault == 'old_run_ids':
        p['runs'][0]['id'] = args.run_id = 'dev01'
    else:
        changed = copy.deepcopy(p['contact_profile_contract'])
        changed['timestep_s'] /= 2
        monkeypatch.setattr(dev, 'profile_contract', lambda: changed)
    args.prereg = tmp_path / 'altered.json'
    dev.write_json(args.prereg, p)
    with pytest.raises(ValueError):
        dev.load_config(args)
    assert not args.output.exists()


@pytest.mark.parametrize('fault', ['before_start', 'enospc', 'missing_prereg', 'bad_prereg_hash', 'state_only', 'late_failure'])
def test_host_error_keeps_original_cause_without_route_trace_or_video(tmp_path, fault):
    run = tmp_path / 'host-error'
    run.mkdir()
    p = config()
    m = dev.build_manifest(p, p['runs'][0], source={}, environment={}, prereg_path=dev.PREREG)
    message = 'ENOSPC: no space left on device' if fault == 'enospc' else 'actual model settings differ: timestep_s=0.00025'
    cause = {'classification': 'HOST_ERROR', 'type': 'OSError' if fault == 'enospc' else 'ValueError',
             'message': message, 'enospc': fault == 'enospc'}
    m.update(state='host_error', host_error=cause)
    if fault == 'state_only':
        del m['host_error']
    if fault == 'late_failure':
        m.update(state='completed', simulator_start_s=1.3, sim_end_s=10.)
    if fault == 'bad_prereg_hash':
        m['prereg']['sha256'] = '0' * 64
    if fault != 'missing_prereg':
        (run / 'prereg.json').write_bytes(dev.PREREG.read_bytes())
    dev.write_json(run / 'manifest.json', m)
    dev.write_json(run / 'pair_records.json', [])  # dev01's exact route-failure trigger
    result = ev.evaluate_run(run)
    assert result['verdict'] == 'HOST_ERROR' and not result['physical_success']
    assert result['physical_scoring'] == 'not_performed_host_error'
    assert 'eval_only/trace.jsonl' in result['missing_evidence']
    assert result['prereg_integrity']['verified'] is (fault not in ('missing_prereg', 'bad_prereg_hash'))
    if fault != 'state_only':
        assert result['host_error'] == cause and result['error'] == message
    output = run / 'eval_only/review.json'
    assert ev.main([str(run), '--output', str(output)]) == 1
    assert json.loads(output.read_text())['verdict'] == 'HOST_ERROR'
    assert ev.evaluation_failure(m, OSError('missing trace'))['verdict'] == 'HOST_ERROR'
    assert ev.score(m, {}, [], {}, {})['verdict'] == 'HOST_ERROR'


def test_missing_evidence_without_explicit_host_error_stays_incomplete(tmp_path):
    run = tmp_path / 'incomplete'
    dev.write_json(run / 'manifest.json', {'state': 'interrupted'})
    out = run / 'eval_only/result.json'
    assert ev.main([str(run), '--output', str(out)]) == 1
    assert json.loads(out.read_text())['verdict'] == 'EVIDENCE_INCOMPLETE'


@pytest.mark.parametrize('change', ['unknown_run', 'negative_seed', 'nan_budget', 'infinite_budget', 'wrong_map',
                                    'bad_hash', 'bad_sheet', 'unsupported_fault', 'existing_output'])
def test_invalid_inputs_refused_before_import_or_output(tmp_path, change):
    p = config()
    args = arguments(tmp_path)
    if change == 'unknown_run':
        args.run_id = 'test01'
    elif change == 'negative_seed':
        p['runs'][0]['seed'] = -1
    elif change == 'nan_budget':
        p['limits']['sim_s'] = float('nan')
    elif change == 'infinite_budget':
        p['limits']['wall_s'] = float('inf')
    elif change == 'wrong_map':
        p['environment']['map'] = 'other'
    elif change == 'bad_hash':
        p['inputs']['calibration']['sha256'] = '0' * 64
    elif change == 'bad_sheet':
        p['runs'][0]['coarse_order_sheet']['beam_xyyaw'][0] += .01
    elif change == 'unsupported_fault':
        p['runs'][0]['intervention'] = 'teleport'
    elif change == 'existing_output':
        args.output.mkdir()
    path = tmp_path / 'prereg.json'
    path.write_text(json.dumps(p))
    args.prereg = path
    with pytest.raises(ValueError):
        dev.load_config(args)
    assert not list(args.output.glob('*'))


def test_execution_needs_explicit_full_sha_and_lock(tmp_path):
    args = arguments(tmp_path, '--execute')
    with pytest.raises(ValueError, match='expected-source-sha'):
        dev.load_config(args)
    args.expected_source_sha = 'a' * 40
    with pytest.raises(ValueError, match='lock-owner'):
        dev.load_config(args)
    args.lock_owner = 'codex'
    with pytest.raises(ValueError, match='primary checkout'):
        dev.load_config(args)


def test_prepare_and_help_with_mujoco_import_forbidden(tmp_path):
    # A successful subprocess is stronger than simply mocking the run function:
    # the complete default CLI, source receipt and static inputs must work.
    code = '''
import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "mujoco" or name.startswith("mujoco."):
        raise AssertionError("nonphysical command imported MuJoCo")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from scripts.run_zone_pair_dev import main
raise SystemExit(main(sys.argv[1:]))
'''
    out = tmp_path / 'prepared'
    result = subprocess.run([sys.executable, '-c', code, '--run-id', 'dev03', '--output', str(out)],
                            cwd=dev.ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    m = json.loads((out / 'manifest.json').read_text())
    assert m['applied'] is None and m['state'] == 'prepared_not_executed'
    assert m['physical_success'] is None and m['model_calls'] == 0
    assert not (out / 'eval_only/trace.jsonl').exists()
    assert (out / 'inputs/static.json').is_file()
    result = subprocess.run([sys.executable, '-c', code, '--help'], cwd=dev.ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_applied_manifest_reads_actual_model_and_rejects_mismatch():
    from harness.zone_pair_executor import PairTeam
    host = NS(world=NS(robot_ids=('r1', 'r2', 'r3'), data=NS(eq_active=[False]),
                       model=NS(opt=NS(timestep=dev.EXPECTED['timestep_s'], noslip_iterations=10))),
              scene=NS(cargo=[NS(item_id='cargoX', kind='long_beam')], config={'setup_only': {'objects': {}}}),
              static={'map_id': dev.EXPECTED['map']}, contact_record={'profile': 'cargo_noslip_v1'},
              pairs=PairTeam.__new__(PairTeam))
    assert dev.applied_settings(host) == dev.EXPECTED
    for key, wrong in [('timestep', .01), ('noslip_iterations', 0)]:
        before = getattr(host.world.model.opt, key)
        setattr(host.world.model.opt, key, wrong)
        with pytest.raises(ValueError, match='actual model'):
            dev.applied_settings(host)
        setattr(host.world.model.opt, key, before)
    host.world.data.eq_active = [True]
    with pytest.raises(ValueError):
        dev.applied_settings(host)


def test_standard_scene_has_only_beam_and_preserves_three_spawn_slots():
    p = config()
    spec = {'map': dev.EXPECTED['map'], 'seed': 901, 'goal': {'B': {'cyan': 1}},
            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': p['runs'][0]['setup_beam_xyyaw']}]}
    scene = make_scene(spec)  # configuration only: never constructs/steps a model
    from sim.session_scenes import Scene
    assert isinstance(scene, Scene)
    assert scene.config['setup_only']['objects'] == {}
    assert len(scene.cargo) == 1
    assert set(scene.config['setup_only']['spawns']) == {'r1', 'r2', 'r3'}
    assert scene.config['static_map'] == json.loads(dev.MAP.read_text())


def test_actor_submissions_are_independent_and_do_not_retry():
    a, b = dev.DevActor('r1', 60.), dev.DevActor('r2', 60.)
    calls = {'r1': [], 'r2': []}
    own = NS(job=None)
    def call(rid):
        def capture(*args):
            calls[rid].append(args)
            return {'accepted': False}
        return capture
    a.tick(own, call('r1'), 0.)
    a.tick(own, call('r1'), 60.)
    assert calls['r2'] == [] and not b.submitted
    a.tick(own, call('r1'), 61.)
    b.tick(own, call('r2'), 62.)
    assert calls['r1'] == [('look_around',), ('pair_carry', 'cargoX', 'B', 'r2')]
    assert calls['r2'][-1] == ('pair_carry', 'cargoX', 'B', 'r1')


def test_retained_endpoint_queues_are_audited_after_executor_detaches():
    eps = {r: NS(controller=NS(arm=NS(events=[1]), schedule=[2]), port=NS(commands=[3])) for r in ev.PAIR}
    slots = {r: NS(executor=NS(_pair=None), timeline=[], capture_after=False,
                   port=NS(_servo_targets={}, _motor_commands=[0, 0, 0, 0])) for r in ev.PAIR}
    host = NS(pairs=NS(sessions=[{'endpoints': eps}]), robots=slots)
    assert endpoint(host, 'r1') is eps['r1']
    assert queue_snapshot(host)['r1']['arm'] == 1
    assert queue_snapshot(host)['r2']['carry'] == 1


def wire(state, at, rid='r1'):
    return {'task_id': 'pair-fixture', 'robot_id': rid, 'state': state, 'sent_at_s': at}


def zeros():
    return {r: {'arm': 0, 'carry': 0, 'port_buffer': 0, 'macro': 0, 'capture_after': False,
                'servo_targets': 0, 'motor_nonzero': 0} for r in ev.PAIR}


@pytest.mark.parametrize('fault', ['none', 'late_go', 'missing_go', 'arm', 'carry', 'port_buffer', 'macro',
                                   'servo_targets', 'motor_nonzero', 'capture_after', 'same_tick_motion', 'late_motion', 'short_tail'])
def test_protocol_audit_detects_abort_and_go_faults(fault):
    status = [wire('carry_go_0', 1.), wire('carry_go_0', 1., 'r2'), wire('abort', 1.1)]
    shutdown = [{'t': 1.1, 'aborted': True, 'queues': zeros()}, {'t': 1.7, 'aborted': True, 'queues': zeros()}]
    commands = [{'t': 1.1, 'robot_id': 'r1', 'kind': 'hold', 'after_abort': True}]
    if fault == 'late_go':
        status[1]['sent_at_s'] = 1.002
    elif fault == 'missing_go':
        status.pop(1)
    elif fault in zeros()['r1']:
        shutdown[0]['queues']['r1'][fault] = True if fault == 'capture_after' else 1
    elif fault in ('same_tick_motion', 'late_motion'):
        commands.append({'t': 1.1 if fault == 'same_tick_motion' else 1.2, 'kind': 'arm', 'after_abort': fault == 'same_tick_motion'})
    elif fault == 'short_tail':
        shutdown[-1]['t'] = 1.2
    result = ev.audit_protocol(status, commands, shutdown, ['carry_go_0'], require_abort=True)
    assert result['ok'] is (fault == 'none')


def good_evidence():
    p = config()
    m = dev.build_manifest(p, p['runs'][0], source={}, environment={}, prereg_path=dev.PREREG, applied=dev.EXPECTED)
    m.update(state='completed', source_changed=False, inputs_changed=False, simulator_start_s=0., sim_end_s=12.)
    rows = []
    targets = {'r1': [.275, 0., 0.], 'r2': [1.725, 0., math.pi]}
    for i in range(241):
        t = round(i * .05, 8)
        x = 1. if t < 2 else (min(3.3, 1. + (t - 2) * 1.) if t < 5 else min(4.6, 3.3 + (t - 5) * .65))
        y = .05 if t < 5 else max(-2.1, .05 - (t - 5) * 1.075)
        z = .05 if 1.5 <= t < 8 else 0.
        state = 'approach' if t < 1 else ('grasp' if t < 1.5 else ('carry' if t < 8 else ('lower' if t < 9 else 'done')))
        corners = [[x + a * .3, y + b * .02, z + .016 + c * .016] for a, b, c in itertools.product((-1, 1), repeat=3)]
        rows.append({'t': t, 'states': {r: state for r in ev.PAIR}, 'segments': {r: 7 if t >= 8 else 0 for r in ev.PAIR},
                     'beam_xyz': [x, y, z], 'beam_corners': corners, 'tilt_deg': 0.,
                     'finger_n': {r: [2., 2.] if 1 <= t < 9 else [0., 0.] for r in ev.PAIR},
                     'robots': {**targets, 'r3': [-.7, -2., 0.]}, 'prestations': targets,
                     'approach_go_s': {r: .5 if t >= .5 else None for r in ev.PAIR}})
    dt = dev.EXPECTED['timestep_s']
    contacts = {'physics_steps': round(12. / dt), 'observation_start_s': 0., 'observation_end_s': 12., 'timestep_s': dt,
                'max_step_gap_s': dt, 'invalid_step_intervals': 0,
                'counts': {k: 0 for k in ('robot_robot', 'robot_wall', 'beam_wall', 'robot_beam_approach', 'r3_interference')},
                'max_eq_active': 0, 'r3_max_displacement_m': 0., 'r3_motion_commands': 0, 'r3_api_calls': 0}
    return m, p, rows, contacts, {'ok': True, 'go_seen': True, 'go_times': {'lower_go_7': 8.}}


def test_complete_synthetic_evidence_can_pass_but_needs_video():
    args = good_evidence()
    no_review = ev.score(*args)
    assert not no_review['physical_success']
    assert [k for k, v in no_review['checks'].items() if not v] == ['video']
    result = ev.score(*args, video_review={'verified': True})
    assert result['physical_success'], result


def checkpoint_evidence():
    """Insert M2's planned x=2.40 set-down/relocalize/regrasp into the good trace."""
    m, p, rows, contacts, protocol = good_evidence()
    original = copy.deepcopy(rows[68])  # t=3.40, beam x=[2.10, 2.70] straddles the slab
    pause = []
    for i in range(30):
        row = copy.deepcopy(original)
        row['t'] = round(3.4 + .05 * i, 8)
        state = ('lower' if i < 5 else 'wait_open' if i < 8 else 'cp_open' if i < 12 else
                 'pregrasp_look' if i < 16 else 'grasp' if i < 20 else 'wait_lift' if i < 22 else 'lift')
        row['states'] = {r: state for r in ev.PAIR}
        row['segments'] = {r: 1 if i < 12 else 2 for r in ev.PAIR}
        row['finger_n'] = {r: [0., 0.] if 8 <= i < 20 else [2., 2.] for r in ev.PAIR}
        if i < 25:
            row['beam_xyz'][2] -= .05
            for corner in row['beam_corners']:
                corner[2] -= .05
        pause.append(row)
    for row in rows[68:]:
        row['t'] = round(row['t'] + 1.5, 8)
        if row['segments']['r1'] == 0:
            row['segments'] = {r: 2 for r in ev.PAIR}
    rows[68:68] = pause
    m['sim_end_s'] += 1.5
    contacts.update(physics_steps=round(13.5 / contacts['timestep_s']), observation_end_s=13.5)
    protocol['go_times'] = {'lower_go_1': 3.4, 'open_go_1': 3.8, 'lift_go_2': 4.5,
                            'carry_go_2': 4.9, 'lower_go_7': 9.5}
    return m, p, rows, contacts, protocol


def test_review_p1_planned_setdown_at_240_can_complete_door_then_release():
    args = checkpoint_evidence()
    result = ev.score(*args, video_review={'verified': True})
    assert result['checks']['door'], result
    assert result['checks']['placement_release'], result
    assert result['physical_success'], result
    assert result['evidence']['planned_setdowns']
    assert result['evidence']['door_at_s'] > 4.9


def set_beam_bottom(row, height):
    dz = height - min(p[2] for p in row['beam_corners'])
    row['beam_xyz'][2] += dz
    for corner in row['beam_corners']:
        corner[2] += dz


@pytest.mark.parametrize('lost_robots', [('r1',), ('r2',), ev.PAIR])
def test_review2_p1_destination_freefall_before_floor_support_fails(lost_robots):
    m, p, rows, contacts, protocol = good_evidence()
    # At B, lower GO authorizes lowering but the beam falls horizontally from
    # 5 cm before the descending arms regain contact. Final release is normal.
    falling = [r for r in rows if 8. <= r['t'] < 8.2]
    for row, height in zip(falling, (.05, .03, .005, 0.)):
        set_beam_bottom(row, height)
        for rid in lost_robots:
            row['finger_n'][rid] = [0., 0.]
    result = ev.score(m, p, rows, contacts, protocol, video_review={'verified': True})
    assert result['checks']['placement_release'], result
    assert not result['checks']['no_drop'], result
    assert 8. in result['evidence']['drop_samples']
    assert not result['physical_success']


@pytest.mark.parametrize('fault', ['none', 'grip_loss', 'height_loss'])
def test_review2_p1_relift_closes_setdown_before_next_carry_go(fault):
    m, p, rows, contacts, protocol = checkpoint_evidence()
    # Re-lift is sustained at 4.65..4.85; delay carry GO until 5.20, leaving
    # time for a second drop in wait_carry and recovery before normal transport.
    extra = []
    for i in range(6):
        row = copy.deepcopy(rows[97])
        row['t'] = round(4.9 + .05 * i, 8)
        row['states'] = {r: 'wait_carry' for r in ev.PAIR}
        if fault != 'none':
            set_beam_bottom(row, (.05, .025, 0., 0., .05, .05)[i])
            if fault == 'grip_loss' and i < 4:
                row['finger_n'] = {r: [0., 0.] for r in ev.PAIR}
        extra.append(row)
    for row in rows[98:]:
        row['t'] = round(row['t'] + .3, 8)
    rows[98:98] = extra
    m['sim_end_s'] += .3
    contacts.update(physics_steps=round(13.8 / contacts['timestep_s']), observation_end_s=13.8)
    protocol['go_times'].update(carry_go_2=5.2, lower_go_7=9.8)
    result = ev.score(m, p, rows, contacts, protocol, video_review={'verified': True})
    assert result['checks']['no_drop'] is (fault == 'none'), result
    assert result['physical_success'] is (fault == 'none'), result
    checkpoint = next(s for s in result['evidence']['planned_setdowns'] if s['segment'] == 1)
    assert checkpoint['floor_supported_at_s'] == 3.45
    assert checkpoint['relifted_at_s'] == 4.85
    assert checkpoint['last_observed_s'] < checkpoint['relifted_at_s']
    if fault == 'none':
        assert result['checks']['placement_release'], result
    if fault != 'none':
        assert 5. in result['evidence']['drop_samples']
        assert 5.05 in result['evidence']['drop_samples']  # settled again; exemption stays closed
    if fault == 'grip_loss':
        assert 4.9 in result['evidence']['drop_samples']


@pytest.mark.parametrize('fault', ['none', 'fast_touchdown', 'one_end_on_floor', 'single_finger_lost'])
def test_review2_p1_released_beam_needs_all_corner_floor_support_and_low_vertical_speed(fault):
    m, p, rows, contacts, protocol = good_evidence()
    if fault == 'fast_touchdown':
        # Both samples are within the floor-height tolerance, but the first
        # released sample is still descending at 0.1 m/s.
        set_beam_bottom(rows[179], .005)
    elif fault == 'one_end_on_floor':
        # Rigid pitch below the transport tilt limit: only one end rests on
        # the floor. Keep it stationary so vertical speed alone cannot reject it.
        angle = .03
        for row in rows[179:181]:
            center = [sum(p[k] for p in row['beam_corners']) / 8 for k in range(3)]
            for corner in row['beam_corners']:
                x, z = corner[0] - center[0], corner[2] - center[2]
                corner[0] = center[0] + math.cos(angle) * x + math.sin(angle) * z
                corner[2] = center[2] - math.sin(angle) * x + math.cos(angle) * z
            row['beam_xyz'] = center
            set_beam_bottom(row, 0.)
            row['tilt_deg'] = math.degrees(angle)
    elif fault == 'single_finger_lost':
        # One remaining finger on r2 is insufficient before floor support.
        set_beam_bottom(rows[160], .05)
        rows[160]['finger_n']['r2'] = [2., 0.]
    result = ev.score(m, p, rows, contacts, protocol, video_review={'verified': True})
    assert result['checks']['no_drop'] is (fault == 'none'), result
    assert result['physical_success'] is (fault == 'none'), result
    if fault != 'none':
        assert (8. if fault == 'single_finger_lost' else 9.) in result['evidence']['drop_samples']


@pytest.mark.parametrize('fault', ['no_lower_go', 'one_robot_lowering', 'wrong_segment', 'off_checkpoint',
                                   'tilted_setdown', 'floor_penetration', 'wall_contact', 'drop_after_regrasp',
                                   'grounded_exit', 'ungripped_exit', 'not_carrying_exit'])
def test_review_p1_setdown_exception_never_hides_unplanned_failure(fault):
    m, p, rows, contacts, protocol = checkpoint_evidence()
    row = rows[70]
    if fault == 'no_lower_go':
        del protocol['go_times']['lower_go_1']
    elif fault == 'one_robot_lowering':
        row['states']['r2'] = 'carry'
    elif fault == 'wrong_segment':
        row['segments']['r2'] = 5
    elif fault == 'off_checkpoint':
        row['beam_xyz'][0] += .3
        for corner in row['beam_corners']:
            corner[0] += .3
    elif fault == 'tilted_setdown':
        row['tilt_deg'] = 25.
    elif fault == 'floor_penetration':
        row['beam_corners'][0][2] = -.02
    elif fault == 'wall_contact':
        contacts['counts']['beam_wall'] = 1
    elif fault == 'drop_after_regrasp':
        rows[100]['beam_corners'][0][2] = 0.
    else:
        # Leave the slab correctly, then lose load/state exactly once wholly east.
        for r in rows:
            if 5.05 <= r['t'] < 9.5:
                if fault == 'grounded_exit':
                    for corner in r['beam_corners']:
                        corner[2] = 0.
                elif fault == 'ungripped_exit':
                    r['finger_n']['r2'] = [0., 0.]
                else:
                    r['states'] = {rid: 'lower' for rid in ev.PAIR}
    result = ev.score(m, p, rows, contacts, protocol, video_review={'verified': True})
    assert not result['physical_success'], result
    if fault.endswith('_exit'):
        assert not result['checks']['door'], result


@pytest.mark.parametrize('fault', ['missing_prefix', 'missing_final_sample', 'one_contact_step', 'missing_first_step',
                                   'missing_last_step', 'extra_contact_step', 'interior_contact_gap',
                                   'wrong_timestep', 'off_grid_sample', 'missing_start', 'nonfinite_contact_time'])
def test_review_p2_observation_coverage_is_required(fault):
    m, p, rows, contacts, protocol = good_evidence()
    if fault == 'missing_prefix':
        del rows[:10]
    elif fault == 'missing_final_sample':
        rows.pop()
    elif fault == 'one_contact_step':
        contacts['physics_steps'] = 1
    elif fault == 'missing_first_step':
        contacts.update(physics_steps=contacts['physics_steps'] - 1, observation_start_s=contacts['timestep_s'])
    elif fault == 'missing_last_step':
        contacts.update(physics_steps=contacts['physics_steps'] - 1, observation_end_s=12. - contacts['timestep_s'])
    elif fault == 'extra_contact_step':
        contacts['physics_steps'] += 1
    elif fault == 'interior_contact_gap':
        contacts.update(invalid_step_intervals=1, max_step_gap_s=.004)
    elif fault == 'wrong_timestep':
        contacts['timestep_s'] = .004
    elif fault == 'off_grid_sample':
        rows[10]['t'] += contacts['timestep_s'] / 2
    elif fault == 'missing_start':
        del m['simulator_start_s']
    else:
        contacts['observation_end_s'] = float('nan')
    result = ev.score(m, p, rows, contacts, protocol, video_review={'verified': True})
    assert not result['physical_success'], result
    assert result['verdict'] == 'EVIDENCE_INCOMPLETE', result


def saved_evidence(tmp_path):
    """Only JSON and a dummy video receipt; never simulates or encodes a video."""
    m, p, rows, contacts, _ = good_evidence()
    run = tmp_path / 'run'
    dev.write_json(run / 'manifest.json', m)
    (run / 'prereg.json').write_bytes(dev.PREREG.read_bytes())
    route = [[1., .05], *p['planned_setdown']['route_endpoints_m']]
    dev.write_json(run / 'pair_records.json', [{'plan': {'route': route}}])
    status = [wire('approach_go_0', .5, rid) for rid in ev.PAIR]
    for i in range(len(route) - 1):
        for j, phase in enumerate(('lift', 'carry', 'lower', 'open')):
            at = (8. if phase == 'lower' else 9.) if i == 7 and phase in ('lower', 'open') else 1. + i * .8 + j * .1
            status.extend(wire(f'{phase}_go_{i}', at, rid) for rid in ev.PAIR)
    for name, records in [('status.jsonl', status), ('commands.jsonl', []), ('shutdown.jsonl', []),
                          ('eval_only/trace.jsonl', rows)]:
        path = run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(json.dumps(row) + '\n' for row in records))
    dev.write_json(run / 'eval_only/contacts.json', contacts)
    video = run / 'eval_only/overview.mp4'
    video.write_bytes(b'synthetic receipt only, not a real video')
    review = run / 'eval_only/synthetic-review.json'
    dev.write_json(review, {'run_id': m['run_id'], 'reviewer': 'synthetic-test-only',
                           'trace_sha256': dev.sha_file(run / 'eval_only/trace.jsonl'),
                           'videos': {video.name: dev.sha_file(video)},
                           'stages': {s: True for s in ('approach', 'joint_grasp', 'lift', 'door', 'placement_release', 'drop_contact')}})
    return run, review


@pytest.mark.parametrize('fault', ['tolerance_edited', 'hash_missing', 'hash_altered'])
def test_review_p2_prereg_hash_enforced_before_scoring(tmp_path, monkeypatch, fault):
    run, review = saved_evidence(tmp_path)
    if fault == 'tolerance_edited':
        p = json.loads((run / 'prereg.json').read_text())
        p['criteria']['footprint_tolerance_m'] = .20
        dev.write_json(run / 'prereg.json', p)
    else:
        m = json.loads((run / 'manifest.json').read_text())
        if fault == 'hash_missing':
            del m['prereg']['sha256']
        else:
            m['prereg']['sha256'] = '0' * 64
        dev.write_json(run / 'manifest.json', m)
    calls = []
    original = ev.score
    def spy(*a, **kw):
        calls.append(True)
        return original(*a, **kw)
    monkeypatch.setattr(ev, 'score', spy)
    result_path = run / 'eval_only/rescore.json'
    assert ev.main([str(run), '--video-review', str(review), '--output', str(result_path)]) == 1
    result = json.loads(result_path.read_text())
    assert result['verdict'] == 'EVIDENCE_INCOMPLETE'
    assert 'prereg' in result['error'] and 'hash' in result['error']
    assert calls == []


def test_review_p2_prepare_preserves_exact_prereg_bytes(tmp_path):
    prereg = tmp_path / 'compact-prereg.json'
    prereg.write_text(json.dumps(config(), separators=(',', ':')))
    out = tmp_path / 'prepared'
    assert dev.main(['--prereg', str(prereg), '--run-id', 'dev03', '--output', str(out)]) == 0
    m = json.loads((out / 'manifest.json').read_text())
    assert dev.sha_file(out / 'prereg.json') == m['prereg']['sha256']
    assert (out / 'prereg.json').read_bytes() == prereg.read_bytes()


def test_review_p2_unchanged_prereg_can_be_evaluated_from_saved_files(tmp_path):
    run, review = saved_evidence(tmp_path)
    result = ev.evaluate_run(run, review)
    assert result['physical_success'], result
    assert result['input_sha256']['prereg.json'] == json.loads((run / 'manifest.json').read_text())['prereg']['sha256']


def test_review_p2_failed_placement_cannot_be_rescored_with_relaxed_tolerance(tmp_path):
    run, review = saved_evidence(tmp_path)
    path = run / 'eval_only/trace.jsonl'
    rows = ev.load_lines(path)
    for row in rows:
        if row['t'] >= 8.:
            row['beam_xyz'][0] += .1
            for corner in row['beam_corners']:
                corner[0] += .1
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    receipt = json.loads(review.read_text())
    receipt['trace_sha256'] = dev.sha_file(path)
    dev.write_json(review, receipt)
    original = ev.evaluate_run(run, review)
    assert not original['physical_success'] and not original['checks']['placement_release']
    p = json.loads((run / 'prereg.json').read_text())
    p['criteria']['footprint_tolerance_m'] = .20  # 2 cm -> 20 cm after the fact
    dev.write_json(run / 'prereg.json', p)
    with pytest.raises(ValueError, match='prereg hash mismatch'):
        ev.evaluate_run(run, review)


@pytest.mark.parametrize('case_index', [0, 1])
def test_review_p1_preregistered_setdown_targets_match_actual_static_plan(case_index):
    from harness.zone_pair_executor import make_plan
    p = config()
    plan = make_plan(json.loads(dev.MAP.read_text()), p['runs'][case_index]['coarse_order_sheet'], 'B')
    assert plan['route'][1:] == p['planned_setdown']['route_endpoints_m']
    assert plan['route'][2] == [2.4, .05]


@pytest.mark.parametrize('missing_tick', [False, True])
@pytest.mark.parametrize('steps', [2, 203])
def test_review_p2_observer_counts_initial_steps_and_exact_final_trace_without_physics(tmp_path, monkeypatch, missing_tick, steps):
    import numpy as np
    from scripts import zone_pair_dev_runtime as runtime
    # All MuJoCo access is a stub; no model, renderer, stepping or model call.
    monkeypatch.setitem(sys.modules, 'mujoco', NS())
    bar = NS(name='bar', center=np.zeros(3), size=np.array([.3, .02, .016]), collision=False)
    cargo = NS(body='beam', spec=lambda: NS(parts=[bar]))
    body = NS(xmat=np.eye(3), xpos=np.array([1., .05, .016]))
    data = NS(time=1., ncon=0, eq_active=[False], body=lambda name: body)
    dt = dev.EXPECTED['timestep_s']
    host = NS(world=NS(data=data, model=NS(opt=NS(timestep=dt))), scene=NS(cargo=[cargo]),
              pairs=NS(sessions=[]), robots={r: NS(commands=[]) for r in ('r1', 'r2', 'r3')},
              _truth=lambda rid: (0., 0., 0.), api_calls=[])
    observer = runtime.EvalObserver(host, tmp_path, config()['criteria'])
    monkeypatch.setattr(observer, 'video', lambda now: None)
    observer.tick()  # initial observation, no physics interval
    observer.tick()  # same instant: no duplicate
    for step in range(1, steps + 1):
        data.time = 1. + step * dt
        if missing_tick and step == 1:
            continue
        observer.tick()
    observer.close()  # tail is less than 50 ms, but must be sampled exactly
    contacts = json.loads((tmp_path / 'eval_only/contacts.json').read_text())
    assert contacts['physics_steps'] == steps - int(missing_tick)
    assert contacts['invalid_step_intervals'] == (1 if missing_tick else 0)
    assert contacts['max_step_gap_s'] == pytest.approx(2 * dt if missing_tick else dt)
    assert contacts['observation_start_s'] == 1.
    assert contacts['observation_end_s'] == 1. + steps * dt
    rows = ev.load_lines(tmp_path / 'eval_only/trace.jsonl')
    expected_times = [1., 1.05, 1. + steps * dt] if steps > 200 else [1., 1. + steps * dt]
    assert [r['t'] for r in rows] == expected_times
    assert rows[0]['segments'] == {r: None for r in ev.PAIR}


def test_review_p2_complete_coverage_with_nonzero_simulator_start():
    m, p, rows, contacts, protocol = good_evidence()
    m.update(simulator_start_s=2., sim_end_s=14.)
    contacts.update(observation_start_s=2., observation_end_s=14.)
    protocol['go_times'] = {k: t + 2. for k, t in protocol['go_times'].items()}
    for row in rows:
        row['t'] += 2.
        row['approach_go_s'] = {r: t + 2. if t is not None else None for r, t in row['approach_go_s'].items()}
    assert ev.score(m, p, rows, contacts, protocol, video_review={'verified': True})['physical_success']


@pytest.mark.parametrize('fault', ['only_sequence_done', 'missing_trace', 'trace_gap', 'nan', 'no_grip', 'no_lift',
                                   'door_miss', 'outside_B', 'not_released', 'drop', 'contact', 'r3_motion',
                                   'weld', 'source_changed', 'wall_limit', 'abort_trial', 'wrong_applied'])
def test_physical_score_fails_closed(fault):
    m, p, rows, contacts, protocol = good_evidence()
    if fault == 'only_sequence_done':
        rows = []
        m.update(outcome='PAIR_SEQUENCE_DONE', confirmation='unconfirmed')
    elif fault == 'missing_trace':
        rows = []
    elif fault == 'trace_gap':
        del rows[20:25]
    elif fault == 'nan':
        rows[0]['tilt_deg'] = float('nan')
    elif fault == 'no_grip':
        for row in rows:
            row['finger_n']['r2'] = [0., 0.]
    elif fault == 'no_lift':
        for row in rows:
            for corner in row['beam_corners']:
                corner[2] = 0.
    elif fault == 'door_miss':
        for row in rows:
            if 3 < row['t'] < 4:
                row['beam_corners'][0][1] = .5
    elif fault == 'outside_B':
        rows[-1]['beam_corners'][0][0] = 5.
    elif fault == 'not_released':
        rows[-1]['finger_n']['r2'] = [2., 2.]
    elif fault == 'drop':
        rows[90]['beam_corners'][0][2] = 0.
    elif fault == 'contact':
        contacts['counts']['beam_wall'] = 1
    elif fault == 'r3_motion':
        contacts['r3_motion_commands'] = 1
    elif fault == 'weld':
        contacts['max_eq_active'] = 1
    elif fault == 'source_changed':
        m['source_changed'] = True
    elif fault == 'wall_limit':
        m['state'] = 'interrupted'
    elif fault == 'abort_trial':
        m['intervention'] = 'abort_after_carry_go'
    elif fault == 'wrong_applied':
        m['applied'] = {**dev.EXPECTED, 'timestep_s': .01}
    assert not ev.score(m, p, rows, contacts, protocol, video_review={'verified': True})['physical_success']


def test_ci_and_common_workflow_collect_driver_and_static_input_receipts(tmp_path):
    from scripts.run_ci_tests import TEST_PATTERNS
    from sim import workflow_manager as wm
    assert any(Path('tests/test_zone_pair_dev.py').match(pattern) for pattern in TEST_PATTERNS)
    args = ['--prereg', str(dev.PREREG), '--run-id', 'dev03', '--output', str(tmp_path / 'new')]
    plan = wm.plan(dev.ROOT, dev.WORKFLOW, args)
    assert not plan['execution_started']
    paths = {p['path'] for p in plan['inputs']}
    assert {str(dev.MAP), str(dev.CALIBRATION), str(dev.PREREG)} <= paths


def test_real_pairteam_fake_host_abort_is_auditable_without_physics():
    pytest.importorskip('mujoco', reason='frozen M2 controller imports MuJoCo; this case uses a fake world, no physical steps')
    from tests.test_zone_pair_executor import setup, start
    host, exs = setup()
    assert start(host)['accepted']
    host.call('r2', 'abort', 'dev_fixture')
    eps = host.pairs.sessions[-1]['endpoints']
    assert all(ep.terminal and not ep.controller.arm.events and not ep.controller.schedule and not ep.port.commands for ep in eps.values())
    assert all(exs[r]._pair is None for r in ev.PAIR)
    assert all(not host.robots[r].timeline for r in ev.PAIR)


@pytest.mark.parametrize('case_index', [0, 1])
@pytest.mark.parametrize('mismatched_timestep', [False, True])
@pytest.mark.parametrize('registration', [2, 3, 4])
def test_physical_entry_finalizes_real_host_pair_scheduler_on_fake_world(tmp_path, monkeypatch, case_index, mismatched_timestep, registration):
    pytest.importorskip('mujoco', reason='frozen M2 import required; physical world/observer replaced with fakes')
    import mujoco
    from harness.zone_own_team_host import OwnCamTeamHost
    from scripts import zone_pair_dev_runtime as runtime
    from tests.test_zone_pair_executor import setup, PhasedM2, PairFakeHost
    from sim.workflow_manager import source_fingerprint

    p = config() if registration == 2 else json.loads((dev.PREREG_V3 if registration == 3 else dev.PREREG_V4).read_text())
    p['limits'].update(sim_s=8., submit_at_s=.03, post_terminal_s=.6, wall_s=30.)
    case = p['runs'][case_index]
    out = tmp_path / 'physical-entry-fake-world'
    out.mkdir()
    (out / 'eval_only').mkdir()
    dev.write_json(out / 'prereg.json', p)
    m = dev.build_manifest(p, case, source={'execution_tree': source_fingerprint(dev.ROOT)}, environment={}, prereg_path=out / 'prereg.json')
    dev.write_json(out / 'manifest.json', m)
    def fake_init(self, *args, **kwargs):
        fake, _ = setup(factory=PhasedM2)
        self.__dict__.update(fake.__dict__)
        self.world.robot_ids = ('r1', 'r2', 'r3')
        self.world.model.opt.noslip_iterations = 10
        self.world.model.opt.timestep = .002 if mismatched_timestep else dev.EXPECTED['timestep_s']
        self.world.data.eq_active = [False]
        self.scene = NS(cargo=[NS(item_id='cargoX', kind='long_beam')], config={'setup_only': {'objects': {}}},
                        manifest={'scene_xml_sha256': 'fixture-only'}, record=lambda: {'fixture': True})
        self.static = kwargs['scene'].config['static_map']
        from sim.zone_start_dock import static_spawn_keepouts
        self.keepout_records = [{**{k: v for k, v in d.items() if k != 'center_m'}, 'xy_m': d['center_m']}
                                for d in static_spawn_keepouts(self.static)]
        assert args[0]['map'] == p['environment']['map']
        for slot in self.robots.values():
            slot.port._servo_targets = {}
            slot.port._motor_commands = [0, 0, 0, 0]
    class NoPhysicsObserver:
        def __init__(self, host, output, criteria):
            self.output = output
            (output / 'eval_only/trace.jsonl').touch()
        def tick(self):
            pass
        def close(self):
            dev.write_json(self.output / 'eval_only/contacts.json', {})
    def bootstrapped_actor(rid, submit):
        actor = dev.DevActor(rid, submit)
        actor.look_sent = True  # own-frame fixtures already localize each robot
        return actor
    monkeypatch.setattr(OwnCamTeamHost, '__init__', fake_init)
    monkeypatch.setattr(OwnCamTeamHost, '_physics_until', PairFakeHost._physics_until)
    monkeypatch.setattr(OwnCamTeamHost, '_capture_raw', PairFakeHost._capture_raw)
    monkeypatch.setattr(runtime, 'DevActor', bootstrapped_actor)
    monkeypatch.setattr(runtime, 'EvalObserver', NoPhysicsObserver)
    monkeypatch.setattr(mujoco, 'mj_saveLastXML', lambda path, model: Path(path).write_text('<fake/>'))
    args = NS(output=out)
    assert runtime.run_physical(args, p, case, m) == (2 if mismatched_timestep else 0), m.get('host_error')
    final = json.loads((out / 'manifest.json').read_text())
    if mismatched_timestep:
        assert final['state'] == 'host_error'
        assert 'actual model settings differ' in final['host_error']['message'], final['host_error']
        result = json.loads((out / 'eval_only/result.json').read_text())
        assert result['verdict'] == 'HOST_ERROR' and result['host_error'] == final['host_error']
        assert 'eval_only/trace.jsonl' in result['missing_evidence']
        assert not result['physical_success']
        assert (out / 'artifacts.sha256.json').is_file()
        return
    assert final['state'] == 'completed', final
    assert final['applied'] == p['environment']
    records = json.loads((out / 'pair_records.json').read_text())
    assert set(records[0]['submissions']) == {'r1', 'r2'}
    assert ev.load_lines(out / 'status.jsonl')
    assert not json.loads((out / 'eval_only/result.json').read_text())['physical_success']
    assert (out / 'artifacts.sha256.json').is_file()
    if case_index == 1:
        assert (out / 'intervention.json').is_file()
        assert ev.load_lines(out / 'shutdown.jsonl')[-1]['aborted']
        assert not any(c['kind'] in ev.MOTION and c['after_abort'] for c in ev.load_lines(out / 'commands.jsonl'))
