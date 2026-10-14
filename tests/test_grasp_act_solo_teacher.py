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


@pytest.mark.parametrize('mode,limit', [('off', 3.), ('solo_rgb_lift_v2', 5.), ('solo_lift_lookback_v1', 5.)])
def test_rgb_unknown_never_authorizes_setdown_with_either_timeout(mode, limit):
    t = make(rgb_lift_mode=mode)
    t.phase = 'verify_lift'; t.phase_t = 0.; t.skill_started = 0.; t.holding = True
    for i in range(int(limit*10)+2):
        t.step(i*.1, rgb_holding='unknown')
    assert t.phase == 'failed' and t.result == 'rgb_lift_unconfirmed'
    assert t.holding and not any(e['to'] in ('lower', 'open') for e in t.events)


def test_v2_gate_uses_its_own_registered_forty_seeds_and_preserves_kind_quota():
    from scripts.make_solo_teacher_plan import prepare, GATE_QUOTA
    from harness.grasp_act_seed_splits import registry, split_of
    p = prepare(split='solo_rgb_lift_v2_gate'); reg = registry()
    assert [e['seed'] for e in p['episodes']] == list(range(79500, 79540))
    assert all(split_of(e['seed'], reg) == 'solo_rgb_lift_v2_gate' for e in p['episodes'])
    assert 'solo_rgb_lift_v2_gate' in reg['gate_seeds_never_train']
    assert p['distribution']['kinds'] == GATE_QUOTA and not p['student_evaluation']


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


def stable(kind='can', role='any', **kwargs):
    return make(kind, role, teacher_stability='align_relook_v1', reach_mode='pad_window_v2', **kwargs)


@pytest.mark.parametrize('kind,role', [('cyan', 'west'), ('can', 'any')])
def test_pad_window_reuses_release_reach_and_excludes_old_ik_hole(kind, role):
    from harness.visual_arm_v3 import MOUNT_X_M
    from sim.grasp_act_release_teacher import PAD_MID_M, PAD_TOL_M
    old, t = make(kind, role), stable(kind, role)
    old_x = old.ops.station-old.spec.align_tol_m
    with pytest.raises(ValueError, match='envelope'):
        old._pick_geometry({'xyz': [old_x, 0., .024], 'yaw': 0.})
    assert t.spec.station_m == pytest.approx(MOUNT_X_M+PAD_MID_M)
    assert t.spec.align_tol_m == PAD_TOL_M
    # Saved floor penetration is ~0.14 mm. The square covers the circular
    # ready window and checks low + hover + every intermediate descent pose.
    for dx in (-PAD_TOL_M, 0., PAD_TOL_M):
        for dy in (-PAD_TOL_M, 0., PAD_TOL_M):
            for z in (.0238, .024):
                low, high, descent = t._pick_geometry(
                    {'xyz': [t.spec.station_m+dx, dy, z], 'yaw': 0.})
                assert len(descent) == 8 and low and high
    assert stable('tile', 'west').spec == cargo('tile')


def test_alignment_replaces_futile_route_pulse_and_reaches_canonical_hover():
    # 76901 stopped ~21.5 cm from the can: no physical-pad IK there.
    # A route callback returning only the old tiny strafe must not control align.
    calls = []
    def route(*args):
        calls.append(args)
        return 0., .003, 0.
    t = stable(route=route)
    far = {'xyz': [.6, 0., .024], 'yaw': 0.}
    for i in range(10):
        t.step(i*.1, measurement=deepcopy(far))
    assert calls and t.ik_checks == 0
    calls.clear()
    near = {'xyz': [.215, 0., .02386], 'yaw': 0.}
    value, _ = t.step(1., measurement=near)
    assert t.phase == 'align' and not calls
    assert value['wheels'] == [.35]*4 and all(.04 <= d <= .15 for d in value['duration_s'])
    assert t.ik_rejections == 1 and t.ik_rejection_reasons
    for i in range(11, 16):
        t.step(i*.1, measurement={'xyz': [t.spec.station_m, 0., .02386], 'yaw': 0.})
    assert t.phase == 'hover' and t.grasp_xyz is not None


def test_alignment_deadbands_stop_lateral_chatter_and_four_flips_relook():
    t = stable()
    t.phase, t.phase_t, t.skill_started = 'align', 0., 0.
    t._align_drive(0., (.012, .005, 0.), True)
    t._align_drive(.1, (.012, .0015, 0.), True)
    t._align_drive(.2, (.012, .0025, 0.), True)
    assert not t.align_active[1]
    t._reset_alignment()
    for k in range(5):
        value = t._align_drive(k*.1, ((-1)**k*.006, 0., 0.), False)
    assert t.phase == 'relook' and not any(value['wheels'])
    assert t.target is None and not any(t.align_integral)


def test_alignment_no_progress_sweeps_stationary_and_requires_fresh_view():
    t = stable()
    t.phase, t.phase_t, t.skill_started = 'align', 0., 0.
    target = {'xyz': [.215, 0., .024], 'yaw': 0.}
    for i in range(31):
        value, _ = t.step(i*.1, measurement=deepcopy(target))
    assert t.phase == 'relook' and not any(value['wheels'])
    pans = []
    # A visible measurement cannot shortcut the stationary sweep.
    for i in range(31, 66):
        value, _ = t.step(i*.1, measurement=deepcopy(target))
        assert t.phase == 'relook' and not any(value['wheels'])
        pans.append(value['pwm']['6'])
    assert len(set(pans)) > 3
    value, _ = t.step(6.6)
    assert t.phase == 'relook' and not any(value['wheels'])
    value, _ = t.step(6.7, measurement=deepcopy(target))
    assert t.phase == 'align' and not any(value['wheels'])
    t._begin_relook(6.8, 'test')
    t._begin_relook(6.9, 'test')
    assert t.result == 'alignment_no_progress'


def test_six_diagnostic_plan_preserves_replays_and_appends_fresh_seeds():
    import json
    from pathlib import Path
    from scripts.make_solo_teacher_plan import prepare
    old = json.loads((Path(__file__).parents[1]/'experiments/2026-10-14-act-solo-teacher/solo-diagnostic-plan.json').read_text())
    new = prepare(split='solo_diagnostic', fresh_diagnostics=True)
    assert new['episodes'][:3] == old['episodes']
    assert [p['seed'] for p in new['episodes']] == list(range(76900, 76906))
    assert [p['kind'] for p in new['episodes']] == ['cyan', 'can', 'tile']*2
    assert all(p['split'] == 'solo_diagnostic' and p['scenario_id'] != 's4_narrow_door_standoff_v4'
               for p in new['episodes'])


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
