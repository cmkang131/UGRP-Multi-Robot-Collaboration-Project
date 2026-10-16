"""Fixed texture-on data comparison; default off, no GT/controller feedback."""
from pathlib import Path
import argparse
import json
import os
from time import monotonic

from scripts import run_wall_parallax_strafe as previous
from sim.wall_texture import DEFAULT_ASSETS, transform_xml

ROOT = previous.ROOT
EXP = ROOT / 'experiments/2026-10-07-wall-parallax-texture'
RAW = Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-texture-v1')
OLD_RAW = Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-strafe-v1')
CASES = {'tape-north': previous.CASES['strafe-north'], 'tape-south': previous.CASES['strafe-south']}
write, sha = previous.write, previous.sha


def acquire_case(case, out, source, backend_factory, *, wall_texture='off'):
    """Exact egomap15 schedule and physical parameters; only visual option added."""
    spec = CASES[case]
    bundle = dict(source_sha=source, execution_bundle_id='egomap16-tape-v1', check='parallax-texture',
        map_id='zone_wide_two_doors_final_v3', contact_profile='cargo_noslip_v1', case=case,
        task=dict(robot_id='r3', seed=spec['seed'], destination='B', pickup_slot='P1-2'),
        options=dict(drive_profile='masterpi_drive_friction_v7', camera_profile='camera_v3',
            roller_collision='mesh', idle_robot_contacts='off', min_wheel_cmd='real_v1', wall_texture=wall_texture),
        spawn=spec['spawn'], case_cap_s=18., capture_s=.1, initial_servo=previous.PULSES)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'bundle.json', bundle)
    result = dict(status='HOST_ERROR', source_sha=source, case=case, model_calls=0,
        loadavg_start=list(os.getloadavg()), qualification='authored data acquisition, not navigation or hardware success')
    backend = None
    started = monotonic()
    try:
        backend = backend_factory(bundle, out, seed=spec['seed'])
        backend.reset(5.)
        start = backend.now
        backend.set_deadline(start + 18.)
        for i in range(181):
            for action in previous.actions(case.replace('tape-', 'strafe-'), i):
                backend.issue('r3', action)
            backend.capture()
            backend.eval_sample()  # return ignored; private safety abort only
            if i % 20 == 0:
                write(out / 'progress.json', dict(sim_s=i / 10, frames=i + 1))
                print(case, 'SIM', i / 10, 'frames', i + 1, flush=True)
            if i < 180:
                backend.advance_to(round(start + (i + 1) / 10, 9))
        result.update(status='RECORDED', frames=181, total_sim_s=backend.now)
    except Exception as e:
        result.update(status='PHYSICAL_FAILURE' if type(e).__name__ == 'PhysicalStop' else 'HOST_ERROR',
            failure=dict(type=type(e).__name__, message=str(e)), enospc=getattr(e, 'errno', None) == 28)
    finally:
        if backend is not None:
            backend.close()
        result['wall_s'] = monotonic() - started
        result['loadavg_end'] = list(os.getloadavg())
        write(out / 'result.json', result)
        write(out / 'artifacts.sha256.json', {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*'))
              if p.is_file() and p.name != 'artifacts.sha256.json'})
    return result


def preview(out, source):
    """Static render only. Old recorded camera truth is used to VIEW assets only.

    No mj_step, reset, control or detector; calibration/FOV match the old camera.
    This separate preview input is never copied to own-RGB acquisition.
    """
    import xml.etree.ElementTree as ET
    import mujoco
    import numpy as np
    from PIL import Image
    from sim.wall_texture import walls_from_xml
    out.mkdir(parents=True, exist_ok=False)
    report = dict(source_sha=source, physics_steps=0, model_calls=0, camera_source='old evaluation pose; preview only', cases={})
    for case, directory in [('north', 'strafe-north-host-retry1'), ('south', 'strafe-south')]:
        old = OLD_RAW / directory
        xml = (old / 'scene.xml').read_text()
        assert transform_xml(xml) == xml
        dressed = transform_xml(xml, wall_texture='tape_v1')
        assert walls_from_xml(xml) == walls_from_xml(dressed)
        original = mujoco.MjModel.from_xml_string(xml)
        dressed_model = mujoco.MjModel.from_xml_string(dressed)
        # Visual geom count changes; all prior contact/dynamics parameters remain.
        for field in ('body_mass', 'body_inertia', 'dof_damping', 'dof_frictionloss', 'actuator_gear'):
            assert np.array_equal(getattr(original, field), getattr(dressed_model, field)), field
        for i in range(original.ngeom):
            name = mujoco.mj_id2name(original, mujoco.mjtObj.mjOBJ_GEOM, i)
            if name is None:
                continue
            j = mujoco.mj_name2id(dressed_model, mujoco.mjtObj.mjOBJ_GEOM, name)
            for field in ('geom_pos', 'geom_quat', 'geom_size', 'geom_contype', 'geom_conaffinity', 'geom_friction'):
                assert np.array_equal(getattr(original, field)[i], getattr(dressed_model, field)[j]), (name, field)
        sample = next(json.loads(line) for line in (old / 'eval_only/camera.jsonl').read_text().splitlines()
                      if json.loads(line)['t'] >= 6.3)
        quat = np.zeros(4)
        mujoco.mju_mat2Quat(quat, np.asarray(sample['camera_rotation']))
        for mode, text in [('off', xml), ('on', dressed)]:
            root = ET.fromstring(text)
            oldcam = root.find(".//camera[@name='r3__robot_cam']")
            attrs = {k: v for k, v in oldcam.attrib.items() if k not in ('name', 'pos', 'quat', 'mode', 'target')}
            ET.SubElement(root.find('worldbody'), 'camera', name='preview_eval_only',
                          pos=' '.join(map(str, sample['camera_xyz'])), quat=' '.join(map(str, quat)), **attrs)
            model = mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'))
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)  # kinematics only, no time integration
            with mujoco.Renderer(model, height=480, width=640) as renderer:
                renderer.update_scene(data, camera='preview_eval_only')
                Image.fromarray(renderer.render()).save(out / f'{case}-{mode}.png')
        report['cases'][case] = dict(source_scene_sha256=sha(old / 'scene.xml'), off_bytes_identical=True,
                                    dynamics_arrays_identical=True, visual_planes=dressed_model.ngeom - original.ngeom)
    write(out / 'preview.json', report)
    write(out / 'artifacts.sha256.json', {p.name: sha(p) for p in out.iterdir() if p.is_file()})
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=['preview', *CASES], required=True)
    p.add_argument('--wall-texture', choices=['off', 'tape_v1'], default='off')
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    receipts = previous.verify_source(a.expected_source_sha)
    assert a.output.resolve() == RAW / a.case and not a.output.exists()
    assert a.wall_texture == 'tape_v1', 'this preregistered cohort requires explicit tape_v1; default remains off'
    if a.case != 'preview':
        approval = json.loads((EXP / 'render-review.json').read_text())
        assert approval['accepted'] and approval['preview_manifest_sha256'] == sha(RAW / 'preview/artifacts.sha256.json')
    if not a.execute:
        print(json.dumps(dict(case=a.case, admitted=True, execution_started=False)))
        return 0
    from scripts.agent_lock import DEFAULT_ROOT, status, acquire, release
    assert status(DEFAULT_ROOT) is None, 'physics lock occupied'
    lock = acquire(DEFAULT_ROOT, owner='codex', branch='claude/ego-wall-map',
                   purpose='egomap16 tape render' if a.case == 'preview' else 'egomap16 frozen parallax recording',
                   pid=os.getpid(), expected_minutes=2 if a.case == 'preview' else 15)
    try:
        if a.case == 'preview':
            result = preview(a.output, a.expected_source_sha)
        else:
            from sim.wall_parallax_texture import PhysicsBackend
            result = acquire_case(a.case, a.output, a.expected_source_sha, PhysicsBackend, wall_texture=a.wall_texture)
        write(a.output / 'source-admission.json', receipts)
        write(a.output / 'lock.json', lock)
    finally:
        release(DEFAULT_ROOT, owner='codex')
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if a.case == 'preview' or result['status'] == 'RECORDED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
