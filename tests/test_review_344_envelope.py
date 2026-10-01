"""Coordinator's simulation-only disc policy: arithmetic/fakes, no physics."""
import copy
import json
import math

import pytest

from harness import zone_final_pair_clearance as clearance
from harness import zone_final_pair_contract as c
from harness.zone_final_pair_excitation import MAP_ID, UNLOADED_POSE
from tests.test_zone_final_pair_v3 import offline_only

GAINS = {'forward': 2.62, 'left': 1.86, 'turn': 2*1.149964146433179}


def event(t=0., *, forward=0., left=0., turn=0., duration=.05, rid='r1', phase='step'):
    return {'t': t, 'robot_id': rid, 'phase': phase, 'action': {
        'kind': 'mecanum', 'forward': forward, 'left': left, 'turn': turn, 'duration_s': duration}}


def envelope(events, *, gains=None, starts=None, static=None, beam=None):
    return clearance.conservative_envelope(
        c.resolve(MAP_ID)[0] if static is None else static, events,
        {'r1': UNLOADED_POSE} if starts is None else starts,
        GAINS if gains is None else gains, beam=beam)


@pytest.mark.parametrize('axis', ['forward', 'left', 'turn'])
@pytest.mark.parametrize('change', ['command', 'duration', 'gain', 'extra_lease'])
def test_bound_monotonicity(axis, change):
    command = {axis: .02}
    before = envelope([event(**command)])['bodies']['r1']['disc_radius_m']
    gain = dict(GAINS)
    duration = .05
    if change == 'command': command[axis] *= 2
    if change == 'duration': duration *= 2
    if change == 'gain': gain[axis] *= 2
    events = [event(**command, duration=duration)]
    if change == 'extra_lease': events.append(event(.05, **command))
    after = envelope(events, gains=gain)['bodies']['r1']['disc_radius_m']
    assert after > before


def test_short_schedule_allowed_and_excessive_schedule_blocked():
    short = envelope([event(forward=.02)])
    assert short['admitted']
    assert short['bodies']['r1']['disc_radius_m'] == pytest.approx(.70262)
    long = envelope([event(i*.05, forward=.1) for i in range(400)])
    assert not long['admitted']
    assert long['bodies']['r1']['disc_radius_m'] == pytest.approx(5.94)
    assert long['bodies']['r1']['wall_distance_from_start_m'] == pytest.approx(1.025)
    assert long['bodies']['r1']['remaining_clearance_m'] == pytest.approx(-4.915)


def test_small_synthetic_schedule_reaches_plan_admission(monkeypatch, capsys):
    from harness import zone_final_pair_calibration as cal
    from scripts.run_final_pair_v3 import main
    monkeypatch.setattr(cal, 'schedule', lambda _: [event(forward=.02)])
    assert main(['--check', 'calibration-unloaded', '--expected-source-sha', 'a'*40,
                 '--output', '/unused']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['runnable'] and not plan['blocked_on']
    assert plan['clearance_preflight'][0]['admitted']


def test_disc_touching_map_boundary_or_wall_is_blocked():
    static = {'bounds_m': [-.7, 10., -10., 10.],
              'obstacles': [{'kind': 'wall', 'center_m': [5., 0.], 'half_extents_m': [1., 1.]}]}
    assert not envelope([], static=static, starts={'r1': [0., 0., 0.]})['admitted']
    static['bounds_m'][0] = -10.
    assert not envelope([], static=static, starts={'r1': [3.3, 0., 0.]})['admitted']
    assert envelope([], static=static, starts={'r1': [3.2, 0., 0.]})['admitted']


@pytest.mark.parametrize('phase', ['step', 'prbs'])
def test_equal_opposite_commands_never_cancel_even_with_idle_gap(phase):
    events = [event(0., forward=.03, phase=phase), event(10., forward=-.03, phase=phase)]
    receipt = envelope(events)
    assert receipt['sign_cancellation'] == 'none'
    row = receipt['bodies']['r1']
    assert row['absolute_command_integral_s']['forward'] == pytest.approx(.003)
    assert row['translation_bound_m'] == pytest.approx(.00786)


def test_tail_command_is_counted_and_any_yaw_covers_tip_diameter():
    receipt = envelope([event(i*.05, turn=.1) for i in range(1000)] +
                       [event(369.95, forward=.03)])
    assert receipt['sim_window_s'] == [0., 370.]
    row = receipt['bodies']['r1']
    assert row['translation_bound_m'] == pytest.approx(.00393)
    assert row['absolute_yaw_bound_rad'] == pytest.approx(5*GAINS['turn'])
    assert row['yaw_tip_excursion_bound_m'] == pytest.approx(.8)


def test_loaded_discs_cover_both_carriers_and_beam_at_arbitrary_yaw():
    # Large synthetic map admits the REAL rotating loaded schedule. This is
    # an arithmetic positive control, never authority to change its map.
    from harness.zone_final_pair_calibration import schedule, teacher_stations
    from harness.zone_final_pair_excitation import LOADED_BEAM_POSE
    from sim.zone_cargo import CATALOGUE
    static = copy.deepcopy(c.resolve(MAP_ID)[0])
    starts = teacher_stations(static)
    static.update(bounds_m=[-50., 50., -50., 50.],
                  obstacles=[{'kind': 'wall', 'center_m': [40., 40.], 'half_extents_m': [1., 1.]}])
    beam = {'pose': LOADED_BEAM_POSE, 'half_extents_m': CATALOGUE['long_beam'].landing_half_extents_m}
    receipt = envelope(schedule('calibration-loaded'), starts=starts, static=static, beam=beam)
    assert receipt['admitted'] and set(receipt['bodies']) == {'r1', 'r2', 'beam'}
    bodies = receipt['bodies']
    beam_radius = math.hypot(.3, .02)
    for rid in starts:
        row = bodies[rid]
        assert row['tip_radius_from_chassis_m'] == pytest.approx(.4732+beam_radius)
        assert row['yaw_tip_excursion_bound_m'] == pytest.approx(2*(.4732+beam_radius))
        assert row['beam_radius_added_m'] >= .3
        assert math.dist(starts[rid][:2], LOADED_BEAM_POSE[:2])+row['disc_radius_m'] <= bodies['beam']['disc_radius_m']
    # Changing ONLY r2 must enlarge its disc and the beam disc; no averaging.
    events = [event(forward=.02, rid='r2')]
    moved = envelope(events, starts=starts, static=static, beam=beam)['bodies']
    still = envelope([], starts=starts, static=static, beam=beam)['bodies']
    assert moved['r1']['disc_radius_m'] == still['r1']['disc_radius_m']
    assert moved['r2']['disc_radius_m'] > still['r2']['disc_radius_m']
    assert moved['beam']['disc_radius_m'] > still['beam']['disc_radius_m']
    bigger_beam = {**beam, 'half_extents_m': [.6, .02]}
    bigger = envelope([], starts=starts, static=static, beam=bigger_beam)['bodies']
    assert all(bigger[name]['disc_radius_m'] > still[name]['disc_radius_m'] for name in still)


@pytest.mark.parametrize('fault', ['value', 'time', 'duration', 'missing_axis', 'outside', 'overlap'])
def test_invalid_schedule_is_blocked_not_a_pass(monkeypatch, fault):
    from harness import zone_final_pair_calibration as cal
    rows = [event(forward=.02)]
    if fault == 'value': rows[0]['action']['turn'] = float('nan')
    if fault == 'time': rows[0]['t'] = float('nan')
    if fault == 'duration': rows[0]['action']['duration_s'] = float('nan')
    if fault == 'missing_axis': del rows[0]['action']['left']
    if fault == 'outside': rows[0]['t'] = 370.
    if fault == 'overlap': rows.append(event(.01, forward=.02))
    monkeypatch.setattr(cal, 'schedule', lambda _: rows)
    receipt = clearance.path_preflight('calibration-unloaded', MAP_ID)
    assert not receipt['admitted'] and receipt['reason'] == 'INVALID_CONSERVATIVE_ENVELOPE_INPUT'
    json.dumps(receipt, allow_nan=False)


@pytest.mark.parametrize('fault', ['gain', 'start_yaw', 'missing_start', 'beam_size', 'wall'])
def test_nan_and_missing_geometry_are_rejected(fault):
    gains, starts = dict(GAINS), {'r1': list(UNLOADED_POSE)}
    beam, static = None, copy.deepcopy(c.resolve(MAP_ID)[0])
    if fault == 'gain': gains['turn'] = float('nan')
    if fault == 'start_yaw': starts['r1'][2] = float('nan')
    if fault == 'missing_start': starts = {}
    if fault == 'beam_size':
        starts['r2'] = [4., -.85, math.pi]
        beam = {'pose': [3.55, -.85, 0.], 'half_extents_m': [.3, float('nan')]}
    if fault == 'wall': static['obstacles'][0]['center_m'][0] = float('nan')
    with pytest.raises(ValueError):
        envelope([event()], gains=gains, starts=starts, beam=beam, static=static)


@pytest.mark.parametrize('check,integral,translation,disc', [
    ('calibration-unloaded', 1.51, 6.7648, 8.2648),
    ('calibration-fine', 1.208, 5.41184, 6.91184),
    ('calibration-loaded', 1.9525, 8.7472, 11.295597782702377),
])
def test_registered_schedules_advisory_with_both_estimates_in_plan(capsys, check, integral, translation, disc):
    from scripts.run_final_pair_v3 import main
    assert main(['--check', check, '--expected-source-sha', 'a'*40, '--output', '/unused']) == 0
    plan = json.loads(capsys.readouterr().out)
    receipt = plan['clearance_preflight'][0]
    assert plan['runnable'] and receipt['admitted'] and not plan['blocked_on']
    assert receipt['envelope_policy'] == 'ADVISORY'
    assert receipt['start_pose_check']['admitted']
    assert receipt['runtime_interlock']['required'] is True
    estimate = receipt['pair_cancellation_estimate']
    assert estimate['sign_cancellation'] == 'within_robot_step_pairs_only'
    assert estimate['bodies']['r1']['disc_radius_m'] < disc
    receipt = receipt['no_cancellation_bound']
    assert not receipt['admitted']
    assert receipt['sim_window_s'] == [0., 370.]
    assert receipt['gain_upper'] == GAINS
    assert receipt['reason'] == 'CONSERVATIVE_ENVELOPE_EXCEEDS_WALLS'
    row = receipt['bodies']['r1']
    assert row['absolute_command_integral_s'] == pytest.approx(dict.fromkeys(GAINS, integral))
    assert row['translation_bound_m'] == pytest.approx(translation)
    assert row['disc_radius_m'] == pytest.approx(disc)
    if check == 'calibration-loaded':
        assert receipt['bodies']['r2']['disc_radius_m'] == pytest.approx(disc)
        assert receipt['bodies']['beam']['disc_radius_m'] == pytest.approx(disc+.4732)
        assert [receipt['bodies'][name]['wall_distance_from_start_m'] for name in ('r1', 'r2', 'beam')] == pytest.approx([.8518, 1.3518, 1.325])
    else:
        assert row['wall_distance_from_start_m'] == pytest.approx(1.025)


def test_pair_estimate_retains_outbound_peak_and_does_not_cancel_prbs():
    events = [*[event(i*.05, forward=.03) for i in range(200)],
              *[event(11.+i*.05, forward=-.03) for i in range(200)],
              event(22., forward=.02, duration=.5, phase='prbs'),
              event(22.5, forward=-.02, duration=.5, phase='prbs')]
    result = clearance.conservative_envelope(c.resolve(MAP_ID)[0], events,
        {'r1': UNLOADED_POSE}, GAINS, pair_cancellation=True)
    row = result['bodies']['r1']
    assert row['step_peak_integral_s']['forward'] == pytest.approx(.3)
    assert row['step_net_integral_s']['forward'] == pytest.approx(0.)
    assert row['estimated_excursion_integral_s']['forward'] == pytest.approx(.32)
    assert row['translation_bound_m'] == pytest.approx(.32*2.62)
    assert 'NOT_A_MOTION_BOUND' in result['qualification']


@pytest.mark.parametrize('distance,admitted', [(.69, False), (.70, False), (.71, True)])
@pytest.mark.parametrize('wall', [False, True])
def test_explicit_start_gate_uses_robot_bound_plus_30cm(distance, admitted, wall):
    static = {'bounds_m': [0., 20., -10., 10.],
              'obstacles': [{'kind': 'wall', 'center_m': [10., 0.], 'half_extents_m': [1., 1.]}]}
    pose = [9.-distance if wall else distance, 0., 0.]
    receipt = clearance.start_pose_check(static, {'r1': pose})
    assert receipt['admitted'] is admitted
    assert receipt['bodies']['r1']['required_wall_distance_m'] == pytest.approx(.70)


@pytest.mark.parametrize('fault', ['missing', 'disabled', 'buffer', 'cadence'])
def test_bundle_cannot_disable_interlock_at_either_entry(tmp_path, monkeypatch, fault):
    import sys
    from scripts import run_final_pair_v3 as run
    from sim.final_pair_v3 import PhysicsBackend
    case = c.cases('calibration-loaded')[0]
    bundle = {**c.bundle(MAP_ID, 'calibration-loaded'), 'case': case}
    if fault == 'missing': del bundle['runtime_interlock']
    elif fault == 'disabled': bundle['runtime_interlock']['required'] = False
    elif fault == 'buffer': bundle['runtime_interlock']['abort_buffer_m'] = 0.
    else: bundle['runtime_interlock']['checks'].remove('before_substep')
    monkeypatch.setitem(sys.modules, 'sim.zone_final_v3_scene', None)
    def forbidden(*a, **kw): pytest.fail('backend must not be reached')
    with pytest.raises(ValueError, match='MANDATORY_COLLECTION_INTERLOCK_REQUIRED'):
        run.run_case(bundle, tmp_path/'case', seed=911, backend_factory=forbidden)
    with pytest.raises(ValueError, match='MANDATORY_COLLECTION_INTERLOCK_REQUIRED'):
        PhysicsBackend(bundle, tmp_path/'native', seed=911)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('fault', ['missing_interlock', 'disabled', 'buffer', 'nan_wall', 'missing_walls', 'nan_start'])
def test_invalid_geometry_or_interlock_blocks_cli_before_execution(monkeypatch, capsys, fault):
    from scripts import run_final_pair_v3 as run
    from harness import zone_final_pair_excitation as excitation
    original_read, original_resolve = c.base.read, c.resolve
    policy = original_read(c.ROOT/clearance.CLEARANCE_REVIEW)
    static, row, contract = original_resolve(MAP_ID)
    static = copy.deepcopy(static)
    if fault == 'missing_interlock': del policy['runtime_interlock']
    elif fault == 'disabled': policy['runtime_interlock']['required'] = False
    elif fault == 'buffer': policy['runtime_interlock']['abort_buffer_m'] = 0.
    elif fault == 'nan_wall': static['obstacles'][0]['center_m'][0] = float('nan')
    elif fault == 'missing_walls': static['obstacles'] = []
    else: monkeypatch.setattr(excitation, 'UNLOADED_POSE', [3.25, -.85, float('nan')])
    monkeypatch.setattr(c, 'resolve', lambda _: (static, row, contract))
    monkeypatch.setattr(c.base, 'read', lambda p: policy if p == c.ROOT/clearance.CLEARANCE_REVIEW else original_read(p))
    args = ['--check', 'calibration-unloaded', '--expected-source-sha', 'a'*40, '--output', '/unused']
    receipt = clearance.path_preflight('calibration-unloaded', MAP_ID)
    assert not receipt['admitted']
    if fault == 'nan_wall':
        # The map hash rejects NaN even earlier than CLI plan serialization.
        with pytest.raises(ValueError, match='Out of range float'):
            run.main(args)
        with pytest.raises(ValueError, match='Out of range float'):
            run.main(args+['--execute'])
        return
    assert run.main(args) == 0
    plan = json.loads(capsys.readouterr().out)
    assert not plan['runnable']
    json.dumps(plan['clearance_preflight'], allow_nan=False)
    monkeypatch.setattr(run, 'check_source', lambda *a: pytest.fail('source/physics gate reached'))
    with pytest.raises(ValueError, match='INVALID_CONSERVATIVE_ENVELOPE_INPUT'):
        run.main(args+['--execute'])


@pytest.mark.parametrize('fault', ['wall', 'nan', 'missing'])
def test_interlock_trip_ends_fake_collection_and_labels_kept_partial_data(tmp_path, monkeypatch, fault):
    from scripts import run_final_pair_v3 as run
    from tests.test_zone_final_pair_review_fixes import fake_guard
    from tests.test_zone_final_pair_v3 import FakePhysics
    guard = fake_guard(monkeypatch, True)
    out = tmp_path/'case'
    guard._append = lambda path, row: run.write(out/path, row)
    made = []
    class Physics(FakePhysics):
        def eval_sample(self):
            super().eval_sample()
            if len(self.samples) == 2:
                if fault == 'wall': guard.world.data.geom_xpos[1, 0] = 2.3
                elif fault == 'nan': guard.world.data.geom_xpos[2, 2] = float('nan')
                else: guard.world.model.ngeom = 0
            guard.collection_guard()
            run.write(out/'eval_only/partial.json', {'sample_time': self.now})
    def factory(*a, **kw):
        obj = Physics(*a, **kw)
        made.append(obj)
        return obj
    case = c.cases('calibration-loaded')[0]
    bundle = {**c.bundle(MAP_ID, 'calibration-loaded'), 'case': case}
    result = run.run_case(bundle, out, seed=911, backend_factory=factory)
    assert result['status'] == 'HOST_ERROR' and not result['protocol_complete']
    assert result['collection_data_status'] == 'PARTIAL_INVALID_HOST_ERROR'
    assert result['partial_data_retained'] and made[0].closed
    assert len(made[0].samples) == 2 and guard.held == ['r1', 'r2']
    hashes = json.loads((out/'artifacts.sha256.json').read_text())
    for path in ('eval_only/partial.json', 'eval_only/clearance_abort.jsonl'):
        assert hashes[path] == c.base.sha(out/path)
    assert result['clearance_preflight'] == bundle['clearance_preflight']
    saved = json.loads((out/'result.json').read_text())
    assert saved['clearance_preflight']['no_cancellation_bound']['bodies']
    assert saved['clearance_preflight']['pair_cancellation_estimate']['bodies']


@pytest.mark.parametrize('entry', ['issue', 'eval_sample'])
def test_command_and_50ms_eval_cannot_skip_guard(monkeypatch, entry):
    from tests.test_zone_final_pair_review_fixes import fake_guard
    from sim.final_environment_checks import PhysicsBackend as Base
    obj = fake_guard(monkeypatch, True)
    obj.world.data.geom_xpos[2, 2] = float('nan')
    monkeypatch.setattr(Base, 'eval_sample', lambda _: None)
    with pytest.raises(ValueError):
        if entry == 'issue': obj.issue('r1', {'kind': 'hold'})
        else: obj.eval_sample()
    assert obj.held == ['r1', 'r2']
    assert obj.saved[0][0] == 'eval_only/clearance_abort.jsonl'
