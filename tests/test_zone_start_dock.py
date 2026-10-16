"""Dock-only v3: static geometry/configuration, no world or physical stepping."""
from __future__ import annotations

import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

from harness.zone_own_guards import (CHASSIS_X_M, CHASSIS_Y_M, OwnPose, SweepGuard, body_spheres)
from scripts import run_zone_pair_dev as dev
from scripts.zone_pair_dev_runtime import make_scene
from sim.zone_landmarks import tagged_map
from sim.zone_start_dock import (MAP_ID, PARENT_MAP_ID, profile_record, static_spawn_keepouts,
                                 build_dock_map, dock_map, static_map_text)

# Issued reset posture, not measured joints. Check against the production constant below.
INITIAL_PWM = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


@pytest.fixture(autouse=True)
def no_physics(monkeypatch):
    # Defensive tripwire, including hidden constructor settle/reset calls.
    import importlib.util
    if importlib.util.find_spec('mujoco'):
        import mujoco
        def forbidden(*args, **kwargs):
            pytest.fail('physical stepping is forbidden in dock static tests')
        for name in ('mj_step', 'mj_step1', 'mj_step2'):
            monkeypatch.setattr(mujoco, name, forbidden)


def prereg():
    return json.loads(dev.PREREG_V3.read_text())


# v5d extracted static scene construction from the host into this source.
# Historical receipts keep their exact source set; latest registration pins it.
ADDED_SCENE_SOURCES = {'sim/zone_own_scene_provider.py'}


# The cargo catalogue record contains trig-derived floats (grasp approach yaw/offsets, tri_frame parts) whose
# last bits come from the platform libm, so its sha256 -- and every resolved scene hash that embeds it -- is
# host-specific. prereg_v3 receipts were registered on the macOS execution host, where the catalogue hash
# equals the recorded 2026-09-25 catalogue (experiments/2026-09-25-zone-cargo-catalogue/results.json).
REGISTRATION_CATALOGUE_SHA256 = '89245cca1497da4d6537eeed3dc7160882b006e0922542c2a0a7a3a23f926c6a'


def registration_host_catalogue():
    from sim.zone_cargo import catalogue_record
    return catalogue_record()['sha256'] == REGISTRATION_CATALOGUE_SHA256


def registered_tree(registration=dev.PREREG_V3):
    """Latest receipt must match; historical source differences never become executable.

    Every receipt is first audited against the git blobs of its own
    registration commit (provenance only, never execution admission).
    """
    from scripts.zone_pair_registered_source import verify_registered_source

    verify_registered_source(registration)
    current = dev.scene_contract()
    registered = json.loads(registration.read_text())['scene_contract']
    if current == registered:
        return True
    old_sources = set(registered['source_sha256'])
    assert set(current['source_sha256']) == old_sources | ADDED_SCENE_SOURCES
    strip = lambda c: {k: v for k, v in c.items() if k not in ('source_sha256', 'sha256')}
    assert strip(current) == strip(registered)
    return False


def scene_for(case, map_id=MAP_ID):
    return make_scene({'map': map_id, 'seed': case['seed'], 'goal': {'B': {'cyan': 1}},
                       'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam',
                                       'pose': case['setup_beam_xyyaw']}]})


def inflated_radius(guard, pose):
    """Conservative entire-body XY disc, including both robots' uncertainty."""
    lever = math.hypot(max(abs(v) for v in CHASSIS_X_M), CHASSIS_Y_M)
    chassis = lever + guard.margin(pose, lever)
    arm = max(math.hypot(x, y) + r + guard.margin(pose, math.hypot(x, y))
              for x, y, z, r in body_spheres(INITIAL_PWM, loaded=False))
    return max(chassis, arm)


def test_parent_map_and_all_non_dock_geometry_preserved():
    assert dev.sha_file(dev.MAP) == 'f9b0ef0d9f35457b34711c0ec5d11688af3130238560195c982660137ad3e73b'
    parent, new = tagged_map(PARENT_MAP_ID), dock_map()
    assert new == build_dock_map()
    assert new['start_dock'] == profile_record()
    stripped = {k: v for k, v in new.items() if k not in ('parent_map', 'start_dock')}
    stripped.update(map_id=parent['map_id'], version=parent['version'])
    assert stripped == parent  # walls, tags/posts, cameras, zones, pickup geometry all identical
    assert {o['height_m'] for o in new['obstacles']} == {.10}
    assert 'walls_v3' not in json.dumps(new)
    assert 'x=-0.65 m' in static_map_text(new)
    assert 'zone_start_dock_v3' not in static_map_text(parent)


@pytest.mark.parametrize('case_index', [0, 1])
def test_three_seeded_spawns_keepouts_and_scene_receipt_agree(case_index):
    p = prereg()
    case = p['runs'][case_index]
    old, scene = scene_for(case, PARENT_MAP_ID), scene_for(case)
    receipt_host = registration_host_catalogue()
    if receipt_host:
        dev.validate_scene(p, scene)
    else:
        # The receipt is host-specific: the runner must refuse rather than accept a different configuration hash.
        with pytest.raises(ValueError, match='resolved scene configuration hash mismatch'):
            dev.validate_scene(p, scene)
    a, b = old.config['setup_only'], scene.config['setup_only']
    for rid in ('r1', 'r2', 'r3'):
        assert a['spawns'][rid][0] == -.85
        assert b['spawns'][rid] == [-.65, *a['spawns'][rid][1:]]
    assert a['objects'] == b['objects'] == {}
    assert old.config['cargo_set'] == scene.config['cargo_set']
    discs = static_spawn_keepouts(scene.config['static_map'])
    assert {tuple(d['center_m']) for d in discs} == {tuple(p[:2]) for p in b['spawns'].values()}
    assert all(d['radius_m'] == .17 for d in discs)
    assert all(d['center_m'][0] == -.85 for d in static_spawn_keepouts(old.config['static_map']))
    if receipt_host:
        assert scene.record()['resolved_sha256'] == p['scene_instances'][case['id']]['resolved_sha256']
    scene.config['setup_only']['spawns']['r3'][0] = -.85
    with pytest.raises(ValueError, match='scene configuration'):
        dev.validate_scene(p, scene)


@pytest.mark.parametrize('case_index', [0, 1])
def test_all_robots_wall_peer_r3_and_cargo_clearance(case_index):
    p = prereg()
    scene = scene_for(p['runs'][case_index])
    static = scene.config['static_map']
    guard = SweepGuard(static)
    wall = next(o for o in static['obstacles'] if o['id'] == 'wall_west')
    inner = wall['center_m'][0] + wall['half_extents_m'][0]
    assert inner == pytest.approx(-1.025)
    poses = {rid: OwnPose(v[0], v[1], v[3], .05, .06)
             for rid, v in scene.config['setup_only']['spawns'].items()}
    margin = .020 + .015 + 2 * .05 + 2 * .06 * math.hypot(.15, .09)
    expected = (-.65 - .15) - inner - margin
    assert expected == pytest.approx(.06900857317855691)
    for rid, pose in poses.items():
        assert guard.chassis_clearance(pose)[0] == pytest.approx(expected), rid
        assert guard.arm_clearance(INITIAL_PWM, pose, loaded=False)[0] > .188, rid
        assert guard.translation_clear(INITIAL_PWM, pose, .08, 0., loaded=False), rid
        # The old dock must fail this criterion; no safety threshold was relaxed.
        assert guard.chassis_clearance(OwnPose(-.85, pose.y, 0., 0., 0.))[0] == pytest.approx(-.01)
    for a, b in itertools.combinations(poses, 2):
        pa, pb = poses[a], poses[b]
        gap = math.hypot(pa.x - pb.x, pa.y - pb.y) - inflated_radius(guard, pa) - inflated_radius(guard, pb)
        assert gap >= .73816, (a, b, gap)  # r1/r2, r1/r3 and r2/r3, each uncertainty inflated
    # r3 versus the initial bar and the authored carry path, using the whole
    # beam's circumscribed disc. No live beam pose or route completion assumed.
    r3 = poses['r3']
    cargo = scene.cargo[0].spec()
    bar = next(part for part in cargo.parts if part.name == 'bar')
    beam_radius = math.hypot(*bar.size[:2])
    centers = [p['runs'][case_index]['setup_beam_xyyaw'][:2], *p['planned_setdown']['route_endpoints_m']]
    # All straight segments keep x >= the minimum endpoint; reserve an extra
    # 0.12 m preregistered set-down tolerance. This proves static x separation.
    gap = min(v[0] for v in centers) - beam_radius - .12 - (r3.x + inflated_radius(guard, r3))
    assert gap > .8, gap


def test_initial_posture_is_production_command_not_a_measured_pose():
    pytest.importorskip('mujoco')  # constants import only, never construct a robot
    from sim.masterpi_production_v2 import SEARCH_POSE
    assert INITIAL_PWM == SEARCH_POSE


def test_registered_v3_keeps_all_v2_scoring_and_single_variable():
    p, v2 = prereg(), json.loads(dev.PREREG.read_text())
    assert p['status'] == 'REGISTERED' and p['execution_source_sha'] is None
    assert p['execution_status'] == 'not_run'
    # Historical v3 pins the original driver source. The v4 successor has a
    # new source receipt while preserving the same physical dock/map contract.
    assert p['scene_contract']['map'] == dev.scene_contract()['map']
    assert p['scene_contract']['start_dock'] == dev.scene_contract()['start_dock']
    registered_tree()
    v4 = json.loads(dev.PREREG_V4.read_text())
    registered_tree(dev.PREREG_V4)
    for key in ('map', 'parent_map', 'start_dock'):
        assert v4['scene_contract'][key] == p['scene_contract'][key]
    for k in ('criteria', 'planned_setdown', 'limits', 'timing', 'contact_profile_contract', 'safety_coverage'):
        assert p[k] == v2[k], k
    assert {k: v for k, v in p['stage_rules'].items() if k != 'admission_diagnostics'} == v2['stage_rules']
    assert p['inputs']['order_sheet_sha256'] == v2['inputs']['order_sheet_sha256'] == dev.digest(dev.ORDER)
    assert p['inputs']['calibration'] == v2['inputs']['calibration']
    assert p['environment'] == {**v2['environment'], 'map': MAP_ID}


def test_applied_settings_reject_old_spawn_keepouts_even_when_map_id_matches():
    from harness.zone_pair_executor import PairTeam
    p = prereg()
    static = dock_map()
    records = [{**{k: v for k, v in d.items() if k != 'center_m'}, 'xy_m': d['center_m']}
               for d in static_spawn_keepouts(static)]
    host = NS(static=static, keepout_records=records, pairs=PairTeam.__new__(PairTeam),
              world=NS(robot_ids=('r1', 'r2', 'r3'), data=NS(eq_active=[False]),
                       model=NS(opt=NS(noslip_iterations=10, timestep=.00025))),
              scene=NS(cargo=[NS(item_id='cargoX', kind='long_beam')], config={'setup_only': {'objects': {}}}),
              contact_record={'profile': 'cargo_noslip_v1'})
    assert dev.applied_settings(host, expected=p['environment']) == p['environment']
    host.keepout_records[2]['xy_m'][0] = -.85
    with pytest.raises(ValueError, match='keepouts differ'):
        dev.applied_settings(host, expected=p['environment'])


@pytest.mark.parametrize('fault', ['map_path', 'scene_hash', 'criteria', 'stage_rules', 'cargo', 'readiness'])
def test_registered_v3_rejects_drift_before_world_import(tmp_path, fault):
    p = prereg()
    p['scene_contract'] = dev.scene_contract()  # synthetic current-source fixture to isolate each predicate
    if fault == 'map_path': p['inputs']['map']['path'] = p['scene_contract']['parent_map']['path']
    elif fault == 'scene_hash': p['scene_contract']['sha256'] = '0' * 64
    elif fault == 'criteria': p['criteria']['lift_bottom_m'] /= 2
    elif fault == 'stage_rules': p['stage_rules']['contacts'] = 'allow contacts'
    elif fault == 'cargo': p['runs'][0]['setup_beam_xyyaw'][0] += .01
    else: p['execution_readiness']['spawn_change_applied'] = False
    path = tmp_path / 'altered.json'
    path.write_text(json.dumps(p))
    args = dev.parser().parse_args(['--prereg', str(path), '--run-id', 'dev05', '--output', str(tmp_path / 'out')])
    with pytest.raises(ValueError):
        dev.load_config(args)
    assert not args.output.exists()


def assert_committed_receipt_is_prepare_only(registration, run_id, tmp_path):
    """The committed receipt never carries an authorization envelope.

    dev13/dev14 ran with a coordinator envelope added only to their execution
    checkout; the committed bytes stay prepare-only on every host. Use the
    host's own primary checkout so the output guard is not what refuses it.
    """
    assert json.loads(registration.read_text()).get('execution_authorization') is None
    execute = ['--execute', '--expected-source-sha', 'a' * 40, '--lock-owner', 'codex']
    outside = dev.parser().parse_args(['--prereg', str(registration), '--run-id', run_id,
                                       '--output', str(tmp_path / 'not-primary-outputs'), *execute])
    with pytest.raises(ValueError, match='^physical raw output must be absolute under primary checkout outputs/$'):
        dev.load_config(outside)
    primary = dev.primary_root() / 'outputs' / f'dock-NOT-EXECUTED-{run_id}-{tmp_path.name}'
    args = dev.parser().parse_args(['--prereg', str(registration), '--run-id', run_id,
                                    '--output', str(primary), *execute])
    with pytest.raises(ValueError, match='^prepare-only: execution_authorization from coordinator is required$'):
        dev.load_config(args)
    assert not primary.exists() and not outside.output.exists()


@pytest.mark.parametrize('registration,run_id', [
    (dev.PREREG_V3, 'dev05'), (dev.PREREG_V3, 'dev06'),
    (dev.PREREG_V4, 'dev07'), (dev.PREREG_V4, 'dev08'),
    (dev.PREREG_V5B, 'dev09'), (dev.PREREG_V5B, 'dev10'),
    (dev.PREREG_V5D, 'dev11'), (dev.PREREG_V5D, 'dev12'),
    (dev.PREREG_V5G, 'dev11'), (dev.PREREG_V5G, 'dev12'),
    (dev.PREREG_V5H, 'dev13'), (dev.PREREG_V5H, 'dev14'),
    ('current_source_v5h', 'dev13'), ('current_source_v5h', 'dev14'),
])
def test_registered_prepare_and_workflow_inputs_without_mujoco_import(tmp_path, registration, run_id):
    synthetic = registration == 'current_source_v5h'
    if synthetic:
        from tests.zone_pair_current_source import write_current_source_v5h
        registration = write_current_source_v5h(tmp_path / 'synthetic-current-source-v5h.json')
    code = '''
import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'mujoco' or name.startswith('mujoco.'):
        raise AssertionError('prepare imported MuJoCo')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from scripts.run_zone_pair_dev import main
raise SystemExit(main(sys.argv[1:]))
'''
    out = tmp_path / run_id
    argv = ['--prereg', str(registration), '--run-id', run_id, '--output', str(out)]
    result = subprocess.run([sys.executable, '-c', code, *argv], cwd=dev.ROOT, text=True, capture_output=True,
                            env={**os.environ, 'OMP_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
    if not synthetic and not registered_tree(registration):
        # Historical registrations require their pinned source, including v4.
        assert result.returncode != 0 and 'scene contract/hash mismatch' in result.stderr, result.stderr
        assert not out.exists()
        return
    from scripts.zone_pair_grasp_contract import grasp_contract
    if json.loads(registration.read_text())['grasp_contract'] != grasp_contract():
        # v5h dev13/dev14 already executed at their pinned source (f87921dc).
        # Later source (the v69 main merge) must not re-prepare or re-admit them.
        from tests.zone_pair_current_source import assert_executed_v5h_is_historical
        assert registration == dev.PREREG_V5H
        assert_executed_v5h_is_historical(tmp_path, run_id)
        assert result.returncode != 0 and 'grasp contract/hash mismatch' in result.stderr, result.stderr
        assert not out.exists()
        return
    assert result.returncode == 0, result.stderr
    manifest = json.loads((out / 'manifest.json').read_text())
    assert manifest['state'] == 'prepared_not_executed' and manifest['applied'] is None
    assert manifest['scene_contract'] == dev.scene_contract()
    assert manifest['model_calls'] == 0 and manifest['physical_success'] is None
    assert (out / 'prereg.json').read_bytes() == registration.read_bytes()
    static = json.loads((out / 'inputs/static.json').read_text())
    assert static['map'] == dock_map()
    assert 'spawns' not in json.dumps(static) and static['order_sheet'] == dev.ORDER
    from sim import workflow_manager as wm
    plan = wm.plan(dev.ROOT, dev.WORKFLOW, [*argv[:-1], str(tmp_path / 'planned-not-run')])
    paths = {r['path'] for r in plan['inputs']}
    assert {str(registration), str(dev.MAP), str(dev.map_path(prereg())), str(dev.CALIBRATION)} <= paths
    assert_committed_receipt_is_prepare_only(registration, run_id, tmp_path)
