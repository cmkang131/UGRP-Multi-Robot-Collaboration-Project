"""Rebuild the C312 compiled references from the integrated owner scene builder.

The recorded references (act17-v7 record-references-r1) were exported through
`act17_v7.installed()`, which post-processes the final XML with `<custom>` text
and teal/blue beam-band RGBA.  The integrated owner (`warp_act_api.Owner.context`)
calls `warp_act_scene.make_scene` directly, so its runtime XML has the same
geometry, contact parameters and mesh sources but different metadata/visual
colour text.  `simalt_compiled_compat.apply_geometry`/`apply_reference` bind the
compiled assets to the exact XML SHA-256, so the recorded assets are rejected
even though the compiled geometry is identical.

This tool re-exports the two compiled assets from the owner-built scene for the
recorded plans, preserving case ids/seeds/scenario hashes.  It uses the frozen
teacher/qualified source modules in the same order as the owner process:
teacher `sim` first, then the integrated owner's `sim`, then the qualified
`sim`; the native-contact transport adapter and native sleep policy are applied.
The scene is built from the validated scenario dict (byte-equal to the config
file) so the frozen teacher's v2-v4-only registry cannot silently change which
scenario file is loaded.

No GPU, warp or VM lifecycle action is used.  MuJoCo 3.12.0 (CPU) must be the
interpreter's binding; the generated asset is only valid when the owner builds
the same XML on the same host paths.

Usage (gcp2, C312 env; never on a Mac):

    /home/ugrp/ugrp-sim/runs/simalt3/c-env/bin/python \\
      scripts/act17_v7_rebuild_compiled_references.py --enabled \\
      --plans /home/ugrp/ugrp-sim/runs/act17-v7/record-references-r1/plans.json \\
      --reference-root /home/ugrp/ugrp-sim/runs/act17-v7/record-references-r1 \\
      --teacher-source /home/ugrp/ugrp-sim/src/warp1-teacher-snapshot-6f057f7e \\
      --qualified-source /home/ugrp/ugrp-sim/src/f0db6b1abb842ea65b71c433738210254f300a7c \\
      --owner-source /home/ugrp/ugrp-sim/src/<integration-worktree> \\
      --out /home/ugrp/ugrp-sim/runs/act17-v7/record-references-r1-owner-regen

Then pass the regenerated `per-world-references.json` and `case-000` assets to
the pilot.  The regenerated `compiled-312.json` must carry the same xml_sha256
the owner writes to `runtime-scene.xml` (recorded pilot value 7888d1fc54ea...).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

EXPECTED_PLANS_SHA256 = 'b52318a22f9ace59ac3cd9578d5d90dd9fc875954e3c6b89cf993f315c3ce180'
EXPECTED_TEACHER_SHA = '6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'
EXPECTED_QUALIFIED_SHA = 'f0db6b1abb842ea65b71c433738210254f300a7c'
EXPECTED_MUJOCO = '3.12.0'
SCHEMA = 'ugrp.act17.v7.compiled_references.owner_regen.v1'
SEMANTIC_KEYS = ('scenario_setup', 'robot_xml_sha256', 'static_map_sha256',
                 'box_prototype_signature', 'box_replicas', 'weld',
                 'appearance_change', 'cargo_contact_profile',
                 'contact_solver_profile', 'replica_finger_contact_pairs',
                 'cargo', 'geometry_map_id', 'wall_profile', 'robot_model',
                 'scene_version')
STRUCTURAL = ('geom_type', 'geom_bodyid', 'geom_dataid', 'geom_friction',
              'geom_solref', 'geom_solimp', 'geom_margin', 'geom_gap',
              'geom_condim', 'geom_contype', 'geom_conaffinity', 'geom_solmix',
              'geom_priority')
DOOR_PREFIXES = ('zone_wall_',)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def load_plans(path, expected=EXPECTED_PLANS_SHA256):
    raw = Path(path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if expected is not None and actual != expected:
        raise ValueError('plans sha256 mismatch: ' + actual)
    plans = json.loads(raw)
    episodes = plans.get('episodes')
    if plans.get('schema') != 'ugrp.act17.v7.plans.v1' or not isinstance(episodes, list) or not episodes:
        raise ValueError('recorded act17-v7 plans required')
    seeds = [p.get('seed') for p in episodes]
    ids = [p.get('episode_id') for p in episodes]
    if any(type(s) is not int for s in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError('unique integer plan seeds required')
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('unique plan episode ids required')
    for plan in episodes:
        if plan.get('kind') not in ('cyan', 'red', 'green', 'yellow') or plan.get('robot_id') != 'r1':
            raise ValueError('solo r1 box plans required')
        if not isinstance(plan.get('spawns'), dict) or set(plan['spawns']) != {'r1', 'r2', 'r3'}:
            raise ValueError('r1/r2/r3 spawns required')
    return plans, actual


def scenario_for(plan, config_root):
    """Load the exact authored scenario bytes and bind them to the plan hash."""
    path = Path(config_root) / 'configs' / 'zone_study_scenarios_v7' / (plan['scenario_id'] + '.json')
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != plan['scenario_source_sha256']:
        raise ValueError('plan/scenario source mismatch: ' + str(path))
    scenario = json.loads(raw)
    if scenario.get('scenario_id') != plan['scenario_id']:
        raise ValueError('scenario id mismatch: ' + str(path))
    return scenario, path, actual


def case_paths(out, index):
    case = Path(out) / f'case-{index:03d}'
    return dict(case=case, world=case / 'world-000', scene=case / 'runtime-scene.xml',
                actuator=case / 'compiled-312.json',
                geometry=case / 'compiled-geometry312.npz',
                geometry_meta=case / 'compiled-geometry312.npz.json',
                record=case / 'case.json')


def _close(left, right, atol=1e-9):
    import numpy as np
    left, right = np.asarray(left), np.asarray(right)
    if left.shape != right.shape:
        return False, None
    return bool(np.allclose(left, right, rtol=0, atol=atol)), float(np.max(np.abs(left - right))) if left.size else 0.


def compare_scene_semantics(manifest, model, plan, reference_case):
    """Fail-closed comparison against the recorded reference for one case."""
    import numpy as np
    reference_case = Path(reference_case)
    reference_scene = json.loads((reference_case / 'world-000' / 'scene.json').read_text())
    reference_meta = json.loads((reference_case / 'compiled-geometry312.npz.json').read_text())
    reference_actuator = json.loads((reference_case / 'compiled-312.json').read_text())
    reference_arrays = np.load(reference_case / 'compiled-geometry312.npz', allow_pickle=False)
    checks = {}
    for key in SEMANTIC_KEYS:
        checks['manifest.' + key] = manifest.get(key) == reference_scene.get(key)
    checks['geom_names'] = [model.geom(i).name for i in range(model.ngeom)] == reference_meta['geom_names']
    checks['actuator_names'] = [model.actuator(i).name for i in range(model.nu)] == reference_actuator['actuator_names']
    for field in STRUCTURAL:
        checks['structural.' + field] = bool(np.array_equal(getattr(model, field), reference_arrays[field]))
    names = reference_meta['geom_names']
    door = [i for i, name in enumerate(names) if name.startswith(DOOR_PREFIXES)]
    door_checks = {}
    for field in ('geom_type', 'geom_dataid', 'geom_size', 'geom_pos', 'geom_quat'):
        values = getattr(model, field)[door]
        expected = reference_arrays[field][door]
        good, delta = _close(values, expected)
        door_checks[field] = dict(passed=good, max_abs_delta=delta, entries=len(door))
    checks['door_geometry'] = all(v['passed'] for v in door_checks.values()) and len(door) > 0
    reference_plan = reference_case / 'world-000' / 'plan.json'
    checks['spawns'] = (plan.get('spawns') == json.loads(reference_plan.read_text()).get('spawns')
                        if reference_plan.exists() else True)
    failed = sorted(k for k, v in checks.items() if not v)
    return dict(checks=checks, door_geometry=door_checks, door_geoms=len(door),
                failed=failed, unchanged=not failed)


def export_compiled_assets(model, scene_path, actuator_path, geometry_path, version):
    """Export the two C312 assets and verify both apply to a fresh model later."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from simalt_compiled_compat import export_geometry, export_reference
    xml = Path(scene_path).read_text()
    export_reference(model, scene_path, version, actuator_path)
    export_geometry(model, scene_path, version, geometry_path)
    actuator = json.loads(Path(actuator_path).read_text())
    geometry = json.loads(Path(str(geometry_path) + '.json').read_text())
    if actuator['xml_sha256'] != text_digest(xml) or geometry['xml_sha256'] != text_digest(xml):
        raise ValueError('exported asset does not bind the written scene XML')
    if actuator['mujoco'] != version or geometry['mujoco'] != version:
        raise ValueError('exported asset compiler version mismatch')
    if geometry['npz_sha256'] != digest(geometry_path):
        raise ValueError('exported geometry npz hash mismatch')
    return actuator, geometry


def verify_compiled_assets(scene_path, actuator_path, geometry_path):
    """Compile the written XML again and run the unchanged fail-closed appliers."""
    import mujoco
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from simalt_compiled_compat import apply_geometry, apply_reference
    model = mujoco.MjModel.from_xml_string(Path(scene_path).read_text())
    actuator = apply_reference(model, scene_path, actuator_path)
    geometry = apply_geometry(model, scene_path, geometry_path)
    return dict(actuator_mode=actuator['mode'], geometry_mode=geometry['mode'],
                geometry_fields=int(geometry['fields_copied']),
                actuator_changes=len(actuator['changes']))


def source_sha(root, expected=None, *, allow_unversioned=False, require_clean=True):
    root = Path(root).resolve()
    if (root / '.git').exists():
        actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=no'], text=True).strip()
        if expected is not None and actual != expected:
            raise ValueError(f'frozen source SHA mismatch: {root} {actual}')
        if dirty and require_clean:
            raise ValueError(f'frozen source must be clean: {root}')
        if dirty:
            actual = actual + '+dirty'
        return actual, 'git'
    if not allow_unversioned:
        raise ValueError(f'unversioned source is only allowed for local validation: {root}')
    for required in ('sim/__init__.py', 'scripts'):
        if not (root / required).exists():
            raise ValueError(f'source tree missing {required}: {root}')
    return None, 'unversioned'


def install_paths(teacher, qualified, owner):
    """Match the owner process: teacher sim first, then owner/qualified sim."""
    sys.path.insert(0, str(Path(owner) / 'scripts'))
    sys.path.insert(0, str(Path(qualified) / 'scripts'))
    sys.path.insert(0, str(teacher))
    import sim
    sim.__path__.append(str(Path(owner) / 'sim'))
    sim.__path__.append(str(Path(qualified) / 'sim'))
    return sim


def build_case(index, plan, scenario, args, env):
    """Build one owner scene and export/verify its compiled assets."""
    import mujoco
    from sim.s2_realism_camera_binding import bind_camera
    from sim.masterpi_drive_friction_v7 import PROFILE, build_world
    from act16w_native_contact import NativeTransport
    import warp_act_scene

    paths = case_paths(args.out, index)
    paths['world'].mkdir(parents=True, exist_ok=False)
    (paths['world'] / 'plan.json').write_text(json.dumps(plan, indent=2, allow_nan=False) + '\n')

    scene = warp_act_scene.make_scene({**plan, 'scenario_id': scenario, 'end_color_scene': 'off'})
    scene.config['setup_only']['spawns'].update(plan['spawns'])
    hooks = NativeTransport(env['host'], env['owner_sha'] or 'unversioned', 'mjwarp_batch_v1',
                            paths['case'] / 'owner', native_sleep_policy_compat_v1=True)
    hooks.scene_v5_v1 = True
    hooks.batch_sleep_v1 = True
    hooks.numpy_teacher_v1 = False
    try:
        world, scene = hooks.make_world(plan, scene, build_world, bind_camera, drive_profile=PROFILE,
            seed=plan['seed'], width=640, height=480, render=False,
            warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None,
            roller_collision='mesh', idle_robot_contacts='off')
        xml = world.scene_xml
        paths['scene'].write_text(xml)
        (paths['world'] / 'scene.xml').write_text(xml)
        (paths['world'] / 'scene.json').write_text(json.dumps(scene.manifest, indent=2, allow_nan=False) + '\n')
        actuator, geometry = export_compiled_assets(world.model, paths['scene'], paths['actuator'],
                                                    paths['geometry'], mujoco.__version__)
        verification = verify_compiled_assets(paths['scene'], paths['actuator'], paths['geometry'])
        semantics = None
        if args.reference_root:
            semantics = compare_scene_semantics(scene.manifest, world.model, plan,
                                                Path(args.reference_root) / f'case-{index:03d}')
            if not semantics['unchanged']:
                raise ValueError('scene semantics differ: ' + repr(semantics['failed']))
        record = dict(schema=SCHEMA, index=index, episode_id=plan['episode_id'], seed=plan['seed'],
            scenario_id=plan['scenario_id'], scenario_source_sha256=plan['scenario_source_sha256'],
            xml_sha256=text_digest(xml), scene_xml=str(paths['scene'].resolve()),
            actuator=str(paths['actuator'].resolve()), geometry=str(paths['geometry'].resolve()),
            npz_sha256=geometry['npz_sha256'], mujoco=mujoco.__version__,
            model_counts={k: int(getattr(world.model, k)) for k in ('nq', 'nv', 'nu', 'nbody', 'ngeom')},
            actuator_sha256=digest(paths['actuator']), geometry_sha256=digest(paths['geometry']),
            verification=verification, semantics=semantics,
            scene_source='integrated owner: warp_act_scene v5 + native contact/sleep; no act17_v7 annotation')
        paths['record'].write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')
        return record
    finally:
        try:
            hooks.close()
        except Exception:
            pass


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--plans', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--teacher-source', type=Path, required=True)
    p.add_argument('--qualified-source', type=Path, required=True)
    p.add_argument('--owner-source', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--reference-root', type=Path,
                   help='recorded record-references-r1; enables semantic comparison and reference plan binding')
    p.add_argument('--cases', type=int, nargs='+')
    p.add_argument('--workers', type=int, default=1)
    p.add_argument('--assets-cwd', type=Path,
                   help='directory whose sim/assets resolves relative texturedir; default qualified source')
    p.add_argument('--expected-owner-xml', type=Path,
                   help='recorded owner runtime-scene.xml for --verify-case; exact bytes required')
    p.add_argument('--verify-case', type=int, default=0)
    p.add_argument('--host-instance', default='local-cpu')
    p.add_argument('--host-machine-type', default='local-cpu')
    p.add_argument('--host-zone', default='local')
    p.add_argument('--allow-unversioned-source', action='store_true')
    a = p.parse_args()
    if not a.enabled:
        p.error('compiled reference rebuild is default OFF')
    if platform.system() != 'Linux':
        p.error('Linux C312 host required; Mac physics forbidden')
    if not 1 <= a.workers <= 8:
        p.error('1..8 worker builds')
    a.out = a.out.resolve()
    if a.out.exists():
        p.error('new output directory required')
    a.out.mkdir(parents=True)

    import mujoco
    if mujoco.__version__ != EXPECTED_MUJOCO:
        raise ValueError('C312 environment required; got mujoco ' + mujoco.__version__)

    teacher_sha, teacher_mode = source_sha(a.teacher_source, EXPECTED_TEACHER_SHA,
                                           allow_unversioned=a.allow_unversioned_source)
    qualified_sha, qualified_mode = source_sha(a.qualified_source, EXPECTED_QUALIFIED_SHA,
                                               allow_unversioned=a.allow_unversioned_source)
    owner_sha, owner_mode = source_sha(a.owner_source, allow_unversioned=a.allow_unversioned_source,
                                       require_clean=False)
    plans, plans_sha = load_plans(a.plans)
    episodes = plans['episodes']
    if a.reference_root:
        reference_plans = json.loads((Path(a.reference_root) / 'plans.json').read_text())
        if reference_plans != plans:
            raise ValueError('reference plans and input plans differ')
    selected = sorted(set(a.cases if a.cases else range(len(episodes))))
    if any(i < 0 or i >= len(episodes) for i in selected):
        raise ValueError('case index out of range')
    if a.workers > 1 and len(selected) > 1:
        print(json.dumps(dict(warning='parallel builds share the frozen sim package; use workers=1 for audited runs')))

    sim = install_paths(a.teacher_source, a.qualified_source, a.owner_source)
    # Default OFF scene-fit test (UGRP_ACT18_SCENE_FIT); no-op when unset.
    from act18_scene_fit import install_if_requested, requested
    install_if_requested()
    scene_fit = requested()
    assets_cwd = (a.assets_cwd or a.qualified_source).resolve()
    if not (assets_cwd / 'sim' / 'assets').is_dir():
        raise ValueError('assets-cwd must contain sim/assets: ' + str(assets_cwd))
    os.chdir(assets_cwd)

    scenarios = {}
    for index in selected:
        scenario, path, actual = scenario_for(episodes[index], a.qualified_source)
        scenarios[index] = scenario

    env = dict(host=dict(project_id='local', instance=a.host_instance,
                         machine_type=a.host_machine_type, zone=a.host_zone),
               owner_sha=owner_sha)
    (a.out / 'plans.json').write_bytes(Path(a.plans).read_bytes())
    if digest(a.out / 'plans.json') != plans_sha:
        raise ValueError('copied plans changed')
    results = []
    def one(index):
        try:
            return build_case(index, episodes[index], scenarios[index], a, env)
        except BaseException as error:
            return dict(index=index, seed=episodes[index]['seed'], error=repr(error))
    if a.workers > 1:
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            results = list(pool.map(one, selected))
    else:
        results = [one(index) for index in selected]
    failures = [r for r in results if 'error' in r]
    ok = [r for r in results if 'error' not in r]
    if a.expected_owner_xml is not None:
        expected = Path(a.expected_owner_xml).read_bytes()
        generated = case_paths(a.out, a.verify_case)['scene'].read_bytes()
        if generated != expected:
            raise ValueError('generated owner XML differs from recorded owner XML; '
                             'check --teacher-source paths and owner build order')
    inventory = [dict(index=r['index'], seed=r['seed'], xml_sha256=r['xml_sha256'],
                      scene_xml=r['scene_xml'], actuator=r['actuator'], geometry=r['geometry'])
                 for r in sorted(ok, key=lambda x: x['index'])]
    per_world = {r['xml_sha256']: dict(actuator=r['actuator'], geometry=r['geometry'])
                 for r in inventory}
    if len(per_world) != len(inventory) or len({r['xml_sha256'] for r in inventory}) != len(inventory):
        raise ValueError('duplicate scene XML hashes')
    (a.out / 'inventory.json').write_text(json.dumps(inventory, indent=2, allow_nan=False) + '\n')
    (a.out / 'per-world-references.json').write_text(json.dumps(per_world, indent=2, allow_nan=False) + '\n')
    summary = dict(schema=SCHEMA, status='complete' if not failures else 'failed',
        complete=not failures, N=len(inventory), requested=len(selected), failed=failures,
        plans_sha256=plans_sha, plans_count=len(episodes),
        teacher_source=dict(path=str(a.teacher_source.resolve()), sha256=teacher_sha, mode=teacher_mode),
        qualified_source=dict(path=str(a.qualified_source.resolve()), sha256=qualified_sha, mode=qualified_mode),
        owner_source=dict(path=str(a.owner_source.resolve()), sha256=owner_sha, mode=owner_mode),
        mujoco=mujoco.__version__, platform=platform.platform(),
        scene_fit=('v6_neutral_pickup_v1' if scene_fit else 'off'),
        scope='compiled C312 export only; no physics rollout, GPU, teacher action or task-success claim',
        semantics='all regenerated assets compared with the recorded reference manifest/geometry when --reference-root is set',
        cases=ok)
    if failures:
        summary['status'] = 'failed'
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(status=summary['status'], N=len(inventory), failed=len(failures),
                          plans_sha256=plans_sha, out=str(a.out)), indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
