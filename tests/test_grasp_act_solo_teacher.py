"""Short non-physics checks: capability boundary, clocks and command lifecycle."""
from copy import deepcopy
import math
import pytest
from sim.grasp_act_solo_teacher import SoloTeacher, InputAudit, cargo, primitives


def make(kind='cyan', role='west', **kwargs):
    p = primitives()
    p.gaze = lambda target, previous, **_: dict(previous)
    return SoloTeacher(kind, role, p.folded, profile='solo_visible_only_v1',
                       held_object_hidden_v1=True, ops=p, **kwargs)


def test_hidden_and_held_lazy_reads_are_never_evaluated():
    a = InputAudit()
    def forbidden():
        raise AssertionError('forbidden position or yaw was read')
    assert a.measure('approach', visible_n=2, probe_N=9, holding=False, read_relative=forbidden) is None
    assert a.measure('lift', visible_n=9, probe_N=9, holding=True, read_relative=forbidden) is None
    assert a.measure('approach', visible_n=0, probe_N=0, holding=False, read_relative=forbidden) is None
    target = {'xyz': [.203, 0., .024], 'yaw': 0.}
    assert a.measure('align', visible_n=3, probe_N=9, holding=False, read_relative=lambda: target) == target
    assert a.record()['invisible_measurements'] == a.record()['held_world_reads'] == 0
    assert a.record()['measurements_by_phase'] == {'align': 1}
    with pytest.raises(ValueError, match='whitelist'):
        a.measure('align', visible_n=9, probe_N=9, holding=False,
                  read_relative=lambda: {**target, 'true_distance': .2})


def test_clocks_and_sample_selection_ignore_hidden_distance():
    a, b = make(), make()
    for i in range(12):
        at = 10.+i*.1
        ca, _ = a.step(at)
        cb, _ = b.step(at)
        assert ca == cb
        assert a.context(at) == b.context(at)
    assert a.context(at)['skill_elapsed_s'] == pytest.approx(1.1)
    assert 'distance' not in repr(a.context(at))
    with pytest.raises(TypeError):
        a.step(11.2, true_distance=.01)


def test_memory_is_owned_command_propagation_and_expires():
    t = make()
    t.step(0., measurement={'xyz': [.6, .1, .024], 'yaw': .5})
    pulse = t._drive(0., .05, .02, .03)
    expected = t.ops.propagate(t.target['xyz'], pulse, .1)
    yaw = t.target['yaw']-t.ops.delta(pulse, .1)[2]
    t.remember_applied(pulse)
    t.step(.1)
    assert t.target['xyz'] == pytest.approx(expected)
    assert t.target['yaw'] == pytest.approx(yaw)
    for i in range(2, 54):
        t.step(i*.1)
    assert t.target is None


@pytest.mark.parametrize('kind,role', [('cyan', 'west'), ('can', 'any'), ('tile', 'west')])
def test_real_shared_ik_and_full_issued_lifecycle_without_physics(kind, role):
    t = make(kind, role)
    angle = math.pi if role == 'east' else 0.
    # The measurement is currently visible; it never enters held phases.
    target = {'xyz': [cargo(kind).station_m or t.ops.station, 0., cargo(kind).grip_z_m], 'yaw': angle}
    saw_hold = saw_release = done = False
    for i in range(500):
        at = i*.1
        _, done = t.step(at, measurement=None if t.holding else deepcopy(target), rgb_holding='yes')
        saw_hold |= t.phase == 'hold'
        saw_release |= t.phase == 'lower'
        if done:
            break
    assert saw_hold and saw_release and done
    assert t.result == 'command_complete'
    assert not t.holding
    assert t.diagnostic()['physical_success'] is None
    assert t.skill == 'release'


def test_tile_cause_box_station_has_no_v3_ik_for_a_seven_mm_grip():
    # Why tile_low_reach_v1 exists: at the box station (arm radius 15.2 cm) and inside the
    # box-calibrated envelope no pitch gives a servo-5 pulse <= 2500 for a 7 mm target.
    from harness.visual_arm_v3 import solve_grip_site_ik
    p = primitives()
    for x in (p.station, .1932, .20, .22):
        with pytest.raises(ValueError, match='IK solution|envelope'):
            solve_grip_site_ik((x, 0., .007), preferred_pitch_deg=-66.)


@pytest.mark.parametrize('role', ['west', 'east'])
def test_tile_low_reach_full_path_is_feasible_across_the_aligned_window(role):
    t = make('tile', role)
    spec = t.spec
    assert spec.station_m == pytest.approx(.172) and spec.grip_z_m == pytest.approx(.009)
    assert dict(spec.ik_options) == {'calibrated_grasp_only': False}
    yaw = math.pi if role == 'east' else 0.
    for dx in (-spec.align_tol_m, 0., spec.align_tol_m):
        for dy in (-spec.align_tol_m, 0., spec.align_tol_m):
            low, high, descent = t._pick_geometry({'xyz': [spec.station_m+dx, dy, spec.grip_z_m], 'yaw': yaw})
            assert len(descent) == 8 and high[6] == low[6]
            # All pulses stay >= 40 inside the 500..2500 limits (the 7 mm / pitch -40 candidate is 8 away).
            assert all(540 <= v <= 2460 for pose in (low, high, *descent) for k, v in pose.items() if k in (3, 4, 5)), (dx, dy)
            pitch = t.ops.pitch(low)
            assert spec.grip_z_m-t.ops.pad_len/2*math.sin(math.radians(abs(pitch))) >= .0019   # pad stays ~2 mm off the floor


def test_aligned_but_unreachable_tile_target_still_ends_as_unreachable():
    t = make('tile', 'west')
    target = {'xyz': [t.spec.station_m, 0., .004], 'yaw': 0.}   # pad would touch the floor
    for i in range(30):
        _, done = t.step(i*.1, measurement=target)
        if t.result:
            break
    assert not done and t.result == 'visible_target_ik_unreachable' and i < 20
    assert not any(e['to'] == 'close' for e in t.events)


def test_pad_floor_guard_rejects_a_grip_the_pad_cannot_reach():
    t = make('tile', 'west')
    with pytest.raises(ValueError, match='below the floor'):
        t._pick_geometry({'xyz': [.172, 0., .004], 'yaw': 0.})


def test_runner_deferred_imports_resolve():
    """The runner imports its dependencies inside run(); resolve every from-import name."""
    import ast, importlib
    from pathlib import Path
    tree = ast.parse((Path(__file__).resolve().parents[1]/'scripts/run_solo_grasp_act_teacher.py').read_text())
    run = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'run')
    checked = 0
    for node in ast.walk(run):
        if isinstance(node, ast.ImportFrom):
            module = importlib.import_module(node.module)
            for alias in node.names:
                assert hasattr(module, alias.name), (node.module, alias.name)
                checked += 1
    assert checked >= 15


def test_mac_runner_refuses_before_world_construction(monkeypatch, tmp_path):
    from scripts import run_solo_grasp_act_teacher as runner
    monkeypatch.setattr(runner.platform, 'system', lambda: 'Darwin')
    with pytest.raises(RuntimeError, match='Mac physics/render disabled'):
        runner.run({}, tmp_path/'never-created', execution_host='gcp1')
    assert not (tmp_path/'never-created').exists()


def test_rgb_unknown_does_not_confirm_lift_and_held_input_is_rejected():
    t = make()
    t.holding = True
    with pytest.raises(ValueError, match='held target'):
        t.step(0., measurement={'xyz': [.2, 0., .024], 'yaw': 0.})
    t = make()
    target = {'xyz': [t.ops.station, 0., .024], 'yaw': 0.}
    for i in range(200):
        _, done = t.step(i*.1, measurement=None if t.holding else target)
        if t.result:
            break
    assert not done
    assert t.result == 'rgb_lift_unconfirmed'
    assert not any(e['to'] == 'lower' for e in t.events)


def test_legacy_default_requires_explicit_opt_in():
    p = primitives()
    with pytest.raises(ValueError, match='opt-in'):
        SoloTeacher('cyan', 'west', p.folded)
    with pytest.raises(ValueError, match='look-around'):
        make(setdown_lookaround_v1=True)


def test_catalogue_matches_production_shapes_and_masses():
    from sim.zone_cargo import kind, EXISTING_SOLO
    assert list(cargo('cyan').dims_m) == EXISTING_SOLO['box']['dims_m']
    assert cargo('red').mass_kg == EXISTING_SOLO['box']['mass_kg']
    for name in ('can', 'tile'):
        assert cargo(name).mass_kg == kind(name).mass_kg
        assert kind(name).required_carriers == 1


def test_solo_plans_use_registered_disjoint_seeds_mixed_kinds_and_a_free_station():
    from collections import Counter
    from harness.grasp_act_seed_splits import registry, split_of
    from scripts.make_solo_teacher_plan import prepare, GATE_QUOTA
    data = registry()
    diag, gate = prepare(split='solo_diagnostic'), prepare(split='solo_gate')
    assert [e['kind'] for e in diag['episodes']] == ['cyan', 'can', 'tile']
    assert Counter(e['kind'] for e in gate['episodes']) == Counter(GATE_QUOTA) and len(gate['episodes']) == 40
    seeds = [e['seed'] for e in diag['episodes']+gate['episodes']]
    assert len(set(seeds)) == 43
    assert {split_of(e['seed'], data) for e in diag['episodes']} == {'solo_diagnostic'}
    assert {split_of(e['seed'], data) for e in gate['episodes']} == {'solo_gate'}
    assert {'solo_gate', 'solo_diagnostic'} <= set(data['gate_seeds_never_train'])
    assert not any(e['scenario_id'].startswith('s4_') for e in gate['episodes'])      # held-out map
    assert [e['kind'] for e in gate['episodes'][:6]] == ['cyan', 'red', 'green', 'yellow', 'can', 'tile']
    for e in gate['episodes']:
        assert e['role'] in cargo(e['kind']).roles and e['robot_id'] == 'r1'
        assert .6 <= e['start_to_cargo_m'] <= 1.1 and len(e['handoff_pose_error']) == 3
