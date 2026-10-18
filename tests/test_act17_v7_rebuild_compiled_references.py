"""Array/XML-only checks for the owner-scene compiled reference rebuild."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    'act17_v7_rebuild_compiled_references',
    ROOT / 'scripts/act17_v7_rebuild_compiled_references.py')
regen = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(regen)


def plan(scenario_sha='a' * 64):
    return dict(episode_id='act17-v7-88600', seed=88600, scenario_id='s1_normal_mixed_v7',
                scenario_source_sha256=scenario_sha, kind='cyan', item_id='cyan_1',
                robot_id='r1', spawns={'r1': [0, 0, 0, 0], 'r2': [1, 1, 0, 0], 'r3': [2, 2, 0, 0]})


def test_load_plans_preserves_ids_and_refuses_ambiguous_sets(tmp_path):
    path = tmp_path / 'plans.json'
    path.write_text(json.dumps(dict(schema='ugrp.act17.v7.plans.v1', episodes=[plan()])))
    plans, sha = regen.load_plans(path, expected=None)
    assert plans['episodes'][0]['seed'] == 88600 and sha == regen.digest(path)
    path.write_text(json.dumps(dict(schema='other', episodes=[plan()])))
    with pytest.raises(ValueError, match='recorded act17-v7 plans'):
        regen.load_plans(path, expected=None)
    path.write_text(json.dumps(dict(schema='ugrp.act17.v7.plans.v1', episodes=[plan(), plan()])))
    with pytest.raises(ValueError, match='unique integer plan seeds'):
        regen.load_plans(path, expected=None)
    path.write_text(json.dumps(dict(schema='ugrp.act17.v7.plans.v1',
                                    episodes=[dict(plan(), kind='can')])))
    with pytest.raises(ValueError, match='solo r1 box'):
        regen.load_plans(path, expected=None)


def test_scenario_bytes_are_bound_to_the_plan_hash(tmp_path):
    config = tmp_path / 'configs' / 'zone_study_scenarios_v7'
    config.mkdir(parents=True)
    scenario = dict(scenario_id='s1_normal_mixed_v7', eval={'setup': {}})
    path = config / 's1_normal_mixed_v7.json'
    path.write_text(json.dumps(scenario))
    row = plan(regen.digest(path))
    loaded, source, sha = regen.scenario_for(row, tmp_path)
    assert loaded == scenario and source == path and sha == row['scenario_source_sha256']
    path.write_text(json.dumps(dict(scenario, scenario_id='s2_unmapped_blockage_v7')))
    with pytest.raises(ValueError, match='plan/scenario source mismatch'):
        regen.scenario_for(row, tmp_path)


def test_case_paths_keep_recorded_case_ids(tmp_path):
    paths = regen.case_paths(tmp_path, 7)
    assert paths['case'].name == 'case-007'
    assert paths['scene'] == paths['case'] / 'runtime-scene.xml'
    assert paths['world'] == paths['case'] / 'world-000'


def test_owner_scene_asset_binds_owner_xml_not_recorded_reference(tmp_path):
    def model():
        return SimpleNamespace(nu=1, actuator=lambda i: SimpleNamespace(name='a'),
            ngeom=1, geom=lambda i: SimpleNamespace(name='zone_wall_north'),
            actuator_gainprm=np.ones((1, 3)), actuator_biasprm=np.ones((1, 3)),
            geom_type=np.array([7], dtype=np.int32), geom_quat=np.tile([1., 0, 0, 0], (1, 1)),
            geom_friction=np.ones((1, 3)), geom_solref=np.ones((1, 2)),
            geom_solimp=np.ones((1, 5)), mesh_vert=np.ones((2, 3)), bvh_aabb=np.ones((2, 6)),
            body_mass=np.ones((2, 1)), body_inertia=np.ones((2, 3)),
            dof_damping=np.ones((1, 1)), dof_armature=np.ones((1, 1)))
    owner_xml = tmp_path / 'owner.xml'
    recorded_xml = tmp_path / 'recorded.xml'
    owner_xml.write_text('owner XML')
    recorded_xml.write_text('recorded XML')
    source = model()
    actuator, geometry = regen.export_compiled_assets(
        source, owner_xml, tmp_path / 'compiled-312.json', tmp_path / 'compiled-geometry312.npz', '3.12.0')
    assert actuator['xml_sha256'] == regen.text_digest('owner XML')
    assert geometry['xml_sha256'] == regen.text_digest('owner XML')
    from scripts.simalt_compiled_compat import apply_geometry, apply_reference
    target = model()
    assert apply_reference(target, owner_xml, tmp_path / 'compiled-312.json')['mode'] == 'compiled-312-v1'
    assert apply_geometry(target, owner_xml, tmp_path / 'compiled-geometry312.npz')['fields_copied'] == 7
    with pytest.raises(ValueError, match='version/XML'):
        apply_reference(model(), recorded_xml, tmp_path / 'compiled-312.json')
    with pytest.raises(ValueError, match='version/XML/hash'):
        apply_geometry(model(), recorded_xml, tmp_path / 'compiled-geometry312.npz')


def _reference_case(root, manifest):
    case = root / 'case-000'
    (case / 'world-000').mkdir(parents=True)
    (case / 'world-000' / 'scene.json').write_text(json.dumps(manifest))
    (case / 'world-000' / 'plan.json').write_text(json.dumps(plan()))
    names = ['zone_wall_north', 'robot']
    (case / 'compiled-312.json').write_text(json.dumps(dict(actuator_names=['a'])))
    (case / 'compiled-geometry312.npz.json').write_text(json.dumps(dict(geom_names=names)))
    np.savez(case / 'compiled-geometry312.npz', geom_type=np.array([7, 7], dtype=np.int32),
             geom_bodyid=np.array([1, 1], dtype=np.int32), geom_dataid=np.array([0, 0], dtype=np.int32),
             geom_friction=np.ones((2, 3)), geom_solref=np.ones((2, 2)), geom_solimp=np.ones((2, 5)),
             geom_margin=np.zeros(2), geom_gap=np.zeros(2), geom_condim=np.array([3, 3], dtype=np.int32),
             geom_contype=np.ones(2, dtype=np.int32), geom_conaffinity=np.ones(2, dtype=np.int32),
             geom_solmix=np.ones(2), geom_priority=np.zeros(2, dtype=np.int32),
             geom_size=np.ones((2, 3)), geom_pos=np.zeros((2, 3)),
             geom_quat=np.tile([1., 0, 0, 0], (2, 1)))
    return case


def test_scene_semantics_compare_fails_on_robot_or_map_change(tmp_path):
    manifest = {key: key + '-value' for key in regen.SEMANTIC_KEYS}
    case = _reference_case(tmp_path, manifest)
    model = SimpleNamespace(nu=1, actuator=lambda i: SimpleNamespace(name='a'), ngeom=2,
        geom=lambda i: SimpleNamespace(name=['zone_wall_north', 'robot'][i]),
        geom_type=np.array([7, 7], dtype=np.int32), geom_bodyid=np.array([1, 1], dtype=np.int32),
        geom_dataid=np.array([0, 0], dtype=np.int32), geom_friction=np.ones((2, 3)),
        geom_solref=np.ones((2, 2)), geom_solimp=np.ones((2, 5)), geom_margin=np.zeros(2),
        geom_gap=np.zeros(2), geom_condim=np.array([3, 3], dtype=np.int32),
        geom_contype=np.ones(2, dtype=np.int32), geom_conaffinity=np.ones(2, dtype=np.int32),
        geom_solmix=np.ones(2), geom_priority=np.zeros(2, dtype=np.int32),
        geom_size=np.ones((2, 3)), geom_pos=np.zeros((2, 3)),
        geom_quat=np.tile([1., 0, 0, 0], (2, 1)))
    result = regen.compare_scene_semantics(manifest, model, plan(), case)
    assert result['unchanged'] and result['door_geoms'] == 1
    changed = dict(manifest, robot_xml_sha256={'r1__robot': 'different'})
    result = regen.compare_scene_semantics(changed, model, plan(), case)
    assert not result['unchanged'] and 'manifest.robot_xml_sha256' in result['failed']
    changed = dict(manifest, static_map_sha256='different')
    assert 'manifest.static_map_sha256' in regen.compare_scene_semantics(changed, model, plan(), case)['failed']


def test_unversioned_source_requires_explicit_local_opt_in(tmp_path):
    with pytest.raises(ValueError, match='unversioned source'):
        regen.source_sha(tmp_path)
    (tmp_path / 'sim').mkdir()
    (tmp_path / 'sim' / '__init__.py').write_text('')
    (tmp_path / 'scripts').mkdir()
    sha, mode = regen.source_sha(tmp_path, allow_unversioned=True)
    assert sha is None and mode == 'unversioned'
