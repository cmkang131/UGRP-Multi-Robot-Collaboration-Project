"""Audit entry-point matrix: real constructors/decisions, fake world and worker only."""
import copy
from types import SimpleNamespace as NS

import numpy as np
import pytest

from tests.test_vision_pose_source import provider, CALIB, SEARCH_POSE
from tests.test_zone_own_executor import MAP, SHEET, ROWS_Y, obs, rgb_of
from harness.zone_own_executor import ZoneOwnExecutor

BOUNDARIES = ('no_landmarks', 'no_id', 'no_size_m', 'detector_blocked')
ENTRIES = ('pair', 'goto', 'goto_loaded', 'deliver', 'm1', 'memory', 'memory_v3', 'memory_off',
           'm1_leg', 'memory_leg', 'memory_v3_leg', 'm2_adapter', 'own_host', 'study_host')


def damaged_map(boundary):
    static = copy.deepcopy(MAP)
    if boundary == 'no_landmarks':
        static.pop('landmarks')
    elif boundary in ('no_id', 'no_size_m'):
        for row in static['landmarks']['tags']:
            row.pop('id' if boundary == 'no_id' else 'size_m')
    return static


def block_measurements(monkeypatch):
    from harness import owncam_localizer, wall_tags
    from harness.owncam_drive import OwnCamDriver
    from harness.owncam_pose_source import OwnCamPoseSource
    calls = []
    def forbidden(*args, **kwargs):
        calls.append('forbidden measurement initialization')
        raise AssertionError(calls[-1])
    from harness.m1_owncam_delivery import M1OwnCamDelivery
    from harness.m1_owncam_memory import M1OwnCamDeliveryMem
    monkeypatch.setattr(M1OwnCamDelivery, '__init__', forbidden)
    monkeypatch.setattr(M1OwnCamDeliveryMem, '__init__', forbidden)
    monkeypatch.setattr(OwnCamDriver, '__init__', forbidden)
    monkeypatch.setattr(OwnCamPoseSource, '__init__', forbidden)
    monkeypatch.setattr(owncam_localizer.OwnCamLocalizer, '__init__', forbidden)
    monkeypatch.setattr(owncam_localizer, 'tags_by_id', forbidden)
    monkeypatch.setattr(wall_tags, 'tags_by_id', forbidden)
    monkeypatch.setattr(wall_tags.TagDetector, 'for_map', forbidden)
    return calls


def own(p, static, rid='r1'):
    ex = ZoneOwnExecutor(rid, static, CALIB['params'], SHEET, pose_source=p,
                         skill_factory=lambda *a, **kw: None, pose_estimate_cls=tuple, search_rows_y=ROWS_Y)
    ex.on_command({'kind': 'initial_servo_command', 't': 0., 'pulses': SEARCH_POSE})
    ex.last_obs = obs(rid, 1, 0., SEARCH_POSE)
    return ex


def host_fixture(monkeypatch, static):
    from harness.zone_own_team_host import OwnCamTeamHost
    from scripts import run_zone_study_integration as runner
    from sim import camera_robot_port, multi_masterpi_production, zone_own_scene_provider
    scene = NS(engine_layout='fixture', config={'static_map': static, 'setup_only': {'objects': {}, 'spawns': {}}},
               setup=lambda w: None, transform=lambda x: x)
    world = NS(model=NS(opt=NS(noslip_iterations=10, timestep=.00025)), data=NS(time=0.),
               robot=lambda rid: NS(servo_command_pulses=SEARCH_POSE), close=lambda: None)
    monkeypatch.setattr(zone_own_scene_provider, 'own_scene', lambda *a: scene)
    monkeypatch.setattr(multi_masterpi_production, 'MultiMasterPiProductionV2', lambda **kw: world)
    monkeypatch.setattr(camera_robot_port, 'CameraRobotPort',
                        lambda w, r, **kw: NS(capture=lambda *a: None))
    monkeypatch.setattr(OwnCamTeamHost, '_geoms', lambda self: None)
    monkeypatch.setattr(runner.zone_eval_top, 'apply_to_world', lambda *a: {})
    spec = dict(map=static['map_id'], seed=3, goal={'A': {'cyan': 1}}, order_sheet=SHEET,
                contact_profile='cargo_noslip_v1', pose_priors={r: {'mean': [-.85, -.85, 0.],
                'source': 'scenario own dock'} for r in ('r1', 'r2', 'r3')})
    student = dict(calibration='experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json',
                   skill_module='harness.wrist_zone_skill_v9', skill_class='WristZoneDeliveryV9')
    return spec, student


@pytest.mark.parametrize('boundary', BOUNDARIES)
@pytest.mark.parametrize('entry', ENTRIES)
def test_every_injected_entry_has_zero_measurement_initialization(monkeypatch, boundary, entry):
    from harness.owncam_delivery_shared import SharedPoseDelivery, SharedLegDriver
    from harness.owncam_memory_delivery import M1OwnCamDeliveryMem, SharedMemoryLeg
    from harness.m1_owncam_memory_v3 import M1OwnCamDeliveryMemV3, M1OwnCamDeliveryOffV3
    from harness.owncam_drive_mem_v3 import LegDriverMemV3
    from harness.owncam_memory_v3 import OwnCamMemoryV3
    from harness.zone_pair_executor import PairExecution, make_plan
    from harness.zone_pair_status import PairStatusChannel, PairStatusEndpoint
    from tests.test_zone_pair_executor import SHEETS
    from harness.zone_pair_guards import GuardedPairApproach
    from harness.m2_provider_adapter import ProviderM2DoorStudent
    from scripts import run_zone_study_integration as runner
    from harness.zone_own_team_host import OwnCamTeamHost

    poses = [provider(prior=False) for _ in range(3 if entry.endswith('host') else 1)]
    try:
        p = poses[0]
        before = p.loc
        calls = block_measurements(monkeypatch)
        static = damaged_map(boundary)
        if entry.endswith('host'):
            spec, student = host_fixture(monkeypatch, static)
            issued = [[] for _ in poses]
            for i, pose in enumerate(poses):
                original = pose.on_command
                def command(row, i=i, original=original):
                    issued[i].append(copy.deepcopy(row)); original(row)
                monkeypatch.setattr(pose, 'on_command', command)
            queue = iter(poses)
            if entry == 'study_host':
                monkeypatch.setattr(runner.zi, 'build_pose_provider', lambda *a: next(queue))
                host = runner.StudyTeamHost(spec, student, root=runner.ROOT,
                                           provider_spec={'uses_landmark_tags': False})
            else:
                host = OwnCamTeamHost(spec, student, root=runner.ROOT, study_layer=lambda *a: None,
                                      pose_factory=lambda *a: next(queue))
            assert [s.executor.pose for s in host.robots.values()] == poses
            assert all(len(rows) == 1 and rows[0]['kind'] == 'initial_servo_command' for rows in issued)
            assert len({id(q.loc) for q in poses}) == 3
            if entry == 'study_host':
                assert all(q.prior['source'] == 'scenario own dock' for q in poses)
            host.close()
        elif entry in ('m1', 'memory', 'memory_v3', 'memory_off'):
            cls = {'m1': SharedPoseDelivery, 'memory': M1OwnCamDeliveryMem,
                   'memory_v3': M1OwnCamDeliveryMemV3, 'memory_off': M1OwnCamDeliveryOffV3}[entry]
            ctl = cls(static, CALIB['params'], pose_source=p, box_kind='cyan', slot_id='A2', slot_xy=(4., -1.),
                      skill_factory=lambda *a: None, pose_estimate_cls=tuple, search_rows_y=ROWS_Y)
            ctl.on_command({'kind': 'initial_servo_command', 't': 0., 'pulses': SEARCH_POSE})
            frame = obs('r1', 1, 0., SEARCH_POSE)
            ctl.on_frame(0., frame, rgb_of(frame))
            for loaded in (False, True):
                ctl._start_leg((1., .05), loaded=loaded)
                assert ctl.leg.tick(0.)
            assert ctl.pose is p or ctl.pose.provider is p
        elif entry.endswith('_leg'):
            kw = dict(loaded=False, goal_xy=(1., .05), door_xy=(2.2, .05), initial_servo=SEARCH_POSE)
            if entry == 'm1_leg':
                leg = SharedLegDriver(p.loc, static, CALIB['params'], **kw)
            else:
                memory = OwnCamMemoryV3(static, CALIB['params'], robot_id='r1')
                cls = SharedMemoryLeg if entry == 'memory_leg' else LegDriverMemV3
                leg = cls(memory, p.loc, static, CALIB['params'], **kw)
            assert leg.loc is p.loc or leg.loc.inner is p.loc
            assert leg.tick(0.)
        else:
            ex = own(p, static)
            if entry == 'pair':
                plan = make_plan(static, SHEETS['cargoX'], 'B')
                ep = PairExecution(ex, PairStatusEndpoint(PairStatusChannel('cargoX'), 'r1'),
                                   {'role': 'front'}, plan, CALIB['params'])
                ep.controller._queue_grasp(0.)
                ep.controller.driver._relocalize(0.)
                assert ep.controller.driver.loc is p.loc
            elif entry == 'm2_adapter':
                driver = GuardedPairApproach(ex, CALIB['params'], goal_xyyaw=(1., .05, 0.),
                                             door_xy=ex.door_xy, initial_servo=SEARCH_POSE)
                ctl = ProviderM2DoorStudent.__new__(ProviderM2DoorStudent)
                ctl.driver, ctl.pregrasp_done, ctl.pregrasp_sweeps, ctl.version = driver, False, 0, 'v3'
                ctl.arm, ctl.set = NS(queue=lambda *a, **kw: None), lambda *a, **kw: None
                ctl._queue_grasp(0.)
                assert driver.loc is p.loc
            elif entry == 'deliver':
                assert ex.deliver('o1', 'A2')['accepted']
                monkeypatch.setattr(ex, '_tick_sweep', lambda *a: None)
                ex.step(0.); ex.step(0.)
                assert ex.job.ctl.pose is p
                for loaded in (False, True):
                    ex.job.ctl._start_leg((1., .05), loaded=loaded)
                    assert ex.job.ctl.leg.loc is p.loc
            else:
                loaded = entry == 'goto_loaded'
                # Goto takes the executor's own holding assumption, not PF load state.
                ex._holding_after = {'answer': 'unknown' if loaded else 'no',
                                     'source': 'synthetic own-command holding assumption'}
                assert ex.goto((1., .05))['accepted']
                ex.step(0.); ex.step(0.)
                assert ex.job.driver.loc is p.loc
                assert ex.job.driver.loaded is loaded
        assert p.loc is before and calls == []
        assert all(q.worker.calls == [] for q in poses)
    finally:
        for p in poses:
            p.close()


@pytest.mark.parametrize('boundary', BOUNDARIES)
def test_vision_pf_factory_never_enters_frozen_measurement_constructor(monkeypatch, boundary):
    from harness import vision_loc_protocol as vp
    from harness.vision_motion_init import motion_module
    vl, vpf = vp.load_vis3()
    frozen = vl.mp.load_m1_localizer()
    def forbidden(*a, **kw):
        pytest.fail('frozen measurement constructor entered')
    monkeypatch.setattr(frozen.OwnCamLocalizer, '__init__', forbidden)
    monkeypatch.setattr(frozen, 'tags_by_id', forbidden)
    block_measurements(monkeypatch)
    pf = vpf.make_robust_pf(motion_module(frozen), damaged_map(boundary), CALIB['params'], {}, {}, {}, 3)
    assert not pf.initialized and not hasattr(pf, 'tags')


def test_m1_active_constructor_preserves_every_frozen_non_provider_field():
    from harness.m1_owncam_delivery import M1OwnCamDelivery
    from harness.owncam_delivery_shared import SharedPoseDelivery
    kw = dict(box_kind='cyan', slot_id='A2', slot_xy=(4., -1.), skill_factory=tuple,
              pose_estimate_cls=tuple, search_rows_y=ROWS_Y)
    frozen = M1OwnCamDelivery(MAP, CALIB['params'], **kw)
    p = provider(prior=False)
    try:
        current = SharedPoseDelivery(MAP, CALIB['params'], pose_source=p, **kw)
        assert {k: v for k, v in vars(frozen).items() if k != 'pose'} == {
            k: v for k, v in vars(current).items() if k != 'pose'}
    finally:
        p.close()


def test_vision_motion_initialization_preserves_scored_fields_and_rng():
    from harness import vision_loc_protocol as vp
    from harness.vision_motion_init import motion_module
    from tests.test_vision_pose_source import VIS3_MAP
    vl, vpf = vp.load_vis3()
    m1 = vl.mp.load_m1_localizer()
    args = (VIS3_MAP, CALIB['params'], {}, {}, {}, 17)
    old = vpf.make_robust_pf(m1, *args)
    new = vpf.make_robust_pf(motion_module(m1), *args)
    assert old.rng.bit_generator.state == new.rng.bit_generator.state
    assert set(vars(old)) - set(vars(new)) == {'tags'}
    for key in ('px', 'scale', 'logw', 'cmd', 'vel', 'rects', 'stuck'):
        np.testing.assert_array_equal(getattr(old, key), getattr(new, key))
    for key in ('params', 'n', 't', 'bounds', 'stats', 'initialized', 'motion_profile', 'last_servo_cmd_t'):
        assert getattr(old, key) == getattr(new, key)
    for pf in (old, new):
        pf.init_gaussian((-.85, -.85, 0.), (.15, .15, .17))
        pf.command({'kind': 'mecanum', 't': 0., 'forward': .1, 'left': 0., 'turn': .1, 'duration_s': .1})
        pf.predict_to(.2)
    np.testing.assert_array_equal(old.px, new.px)
    assert old.rng.bit_generator.state == new.rng.bit_generator.state


@pytest.mark.parametrize('boundary', BOUNDARIES)
def test_geometry_scene_and_public_projection_bypass_marker_transforms(monkeypatch, boundary):
    from sim.zone_geometry_scene import GeometryCargoZoneScene
    from sim.zone_own_scene_provider import own_scene
    from sim import zone_landmarks
    from harness.zone_map_schematic import public_map, render_schematic
    from sim.multi_masterpi_production import build_multi_robot_xml as source_xml
    def forbidden(*a, **kw):
        pytest.fail('geometry scene called tagged transform')
    monkeypatch.setattr(zone_landmarks.TaggedZoneScene, 'transform', forbidden)
    monkeypatch.setattr(zone_landmarks, 'add_tag_geoms', forbidden)
    block_measurements(monkeypatch)
    spec = {'map': 'zone_wide_door_geometry_v2', 'seed': 907, 'goal': {'B': {'cyan': 1}},
            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': [1., .05, 0.]}]}
    scene = own_scene(spec, 'cargo_noslip_v1')
    assert isinstance(scene, GeometryCargoZoneScene)
    # Deliberately malformed metadata must be irrelevant to geometry transforms.
    bad = damaged_map(boundary)
    if 'landmarks' in bad:
        scene.config['static_map']['landmarks'] = bad['landmarks']
    result = scene.transform(source_xml())
    assert 'tag_' not in result and 'team_' in result
    assert own_scene(spec, 'cargo_noslip_v1', scene) is scene
    projection = public_map(scene.config['static_map'], landmark_detail='none')
    assert 'landmarks' not in projection
    png, _ = render_schematic(scene.config['static_map'], landmark_detail='none')
    assert png.startswith(b'\x89PNG')


def test_registered_geometry_study_bundle_uses_same_map_as_scene_without_tag_lookup(monkeypatch):
    import json
    from scripts import run_zone_study_integration as runner
    from sim import zone_landmarks
    pre = runner.load_prereg('experiments/2026-09-26-zone-study-integration/prereg.json')
    pre['pose_provider'] = 'vision_zero_tag_v2'
    episode = copy.deepcopy(pre['episodes'][0])
    episode.update(map='zone_wide_door_geometry_v2',
                   scenario='configs/zone_study_integration/i1_cyan_three_slots_geometry_v2.json')
    monkeypatch.setattr(zone_landmarks, 'tagged_map', lambda *a: pytest.fail('tagged map selected'))
    block_measurements(monkeypatch)
    bundle, _, maps, spec = runner.run_bundle(pre, episode)
    assert maps['landmark_detail'] == 'none' and 'landmarks' not in maps['public_map']
    assert bundle['pose_provider']['pose_provider'] == 'vision_zero_tag_v2'
    assert spec['uses_landmark_tags'] is False
    assert bundle['weld'] == 'off'
    assert bundle['physical']['contact_profile'] == 'cargo_noslip_v1'


@pytest.mark.parametrize('kind', ['m1', 'memory', 'memory_v3', 'memory_off'])
def test_default_constructs_exactly_one_final_provider(monkeypatch, kind):
    from harness.wall_tags import TagDetector
    from harness.owncam_delivery_shared import SharedPoseDelivery
    from harness.owncam_memory_delivery import M1OwnCamDeliveryMem
    from harness.m1_owncam_memory_v3 import M1OwnCamDeliveryMemV3, M1OwnCamDeliveryOffV3
    classes = dict(m1=SharedPoseDelivery, memory=M1OwnCamDeliveryMem,
                   memory_v3=M1OwnCamDeliveryMemV3, memory_off=M1OwnCamDeliveryOffV3)
    original, calls = TagDetector.for_map, []
    def build(*a, **kw):
        calls.append(1)
        return original(*a, **kw)
    monkeypatch.setattr(TagDetector, 'for_map', build)
    ctl = classes[kind](MAP, CALIB['params'], box_kind='cyan', slot_id='A2', slot_xy=(4., -1.),
                        skill_factory=tuple, pose_estimate_cls=tuple, search_rows_y=ROWS_Y)
    assert len(calls) == 1
    if kind.startswith('memory'):
        assert ctl.summary()['landmark_provider']['result_label'] == 'interim, tag provider'


@pytest.mark.parametrize('kind', ['m1', 'memory', 'memory_v3', 'memory_off'])
@pytest.mark.parametrize('source', ['gt_stub_eval_only', 'owncam_pf_fake:cannot_spoof_registration'])
def test_active_m1_and_memory_reject_truth_and_unregistered_sources(kind, source):
    from harness.owncam_delivery_shared import SharedPoseDelivery
    from harness.owncam_memory_delivery import M1OwnCamDeliveryMem
    from harness.m1_owncam_memory_v3 import M1OwnCamDeliveryMemV3, M1OwnCamDeliveryOffV3
    classes = dict(m1=SharedPoseDelivery, memory=M1OwnCamDeliveryMem,
                   memory_v3=M1OwnCamDeliveryMemV3, memory_off=M1OwnCamDeliveryOffV3)
    from harness.m1_owncam_contract import M1ContractError
    with pytest.raises((ValueError, M1ContractError), match='pose source|registered own-camera'):
        classes[kind](MAP, CALIB['params'], pose_source=NS(source=source, loc=NS()),
                      box_kind='cyan', slot_id='A2', slot_xy=(4., -1.),
                      skill_factory=tuple, pose_estimate_cls=tuple, search_rows_y=ROWS_Y)


def test_v3_requires_explicit_consistency_evidence_from_injected_provider(monkeypatch):
    from dataclasses import replace
    from harness.owncam_pose_guard_provider import GuardedPoseProviderV3
    from harness.owncam_pose_guard_v3 import PoseGuardV3, UNTRUSTED_XY_M
    p = provider()
    try:
        guard = PoseGuardV3()
        wrapped = GuardedPoseProviderV3(p, guard)
        def raw(now, rgb, evidence=None):
            return replace(p.report(now), std_xy_m=.001, std_yaw_rad=.001,
                           cov=((1e-6, 0., 0.), (0., 1e-6, 0.), (0., 0., 1e-6)),
                           observation_quality={'accepted': True, 'consistency': evidence or {}})
        monkeypatch.setattr(p, 'on_frame', raw)
        report = wrapped.on_frame(.5, None)
        assert not guard.consistent(.5) and report.std_xy_m >= UNTRUSTED_XY_M
        monkeypatch.setattr(p, 'on_frame', lambda t, rgb: raw(t, rgb, dict(nis=1., log_likelihood=-1., settled=True)))
        wrapped.on_frame(.7, None)
        assert not guard.consistent(.7)
        wrapped.on_frame(.9, None)
        assert guard.consistent(.9)
        assert wrapped.loc.inner is p.loc
    finally:
        p.close()


def test_registered_geometry_provider_constructs_without_any_measurement_initialization(monkeypatch):
    from harness.vision_pose_source import VisionPoseSourceV2
    from harness.vision_loc_client import InProcessWorker
    from sim.zone_geometry_scene import geometry_map
    calls = block_measurements(monkeypatch)
    worker = InProcessWorker(lambda *a: pytest.fail('model/measurement not expected'))
    p = VisionPoseSourceV2(geometry_map('zone_wide_door_geometry_v2'), CALIB['params'], worker=worker)
    try:
        assert p.source.startswith('owncam_pf_vision_zero_tag_v2:')
        assert p.report(0.).fix_source == 'vision_zero_tag_v2'
        assert not hasattr(p.loc._pf, 'tags') and not calls and not worker.calls
    finally:
        p.close()
