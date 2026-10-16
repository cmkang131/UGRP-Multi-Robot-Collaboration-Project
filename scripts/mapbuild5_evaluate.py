"""Finish sealed mapbuild5 evaluation in a fresh, frozen-vision interpreter.

No replay, physics integration, source mutation, or estimator calibration.  The
original prediction directory and recording manifest remain immutable.  Camera
truth is evaluation-only and must be shared only after the comparison worker
announces its prediction/scale seal in ops-alert.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def verify_seal(prediction):
    seal = json.loads((prediction/'prediction-seal.json').read_text())
    for path, expected in seal['inputs'].items():
        if sha(path) != expected:
            raise ValueError('SEALED_INPUT_CHANGED:' + path)
    for name, expected in seal['predictions'].items():
        path = prediction/name
        if path.parent != prediction or sha(path) != expected:
            raise ValueError('SEALED_PREDICTION_CHANGED:' + name)
    return seal


def estimated_camera(pose, calibration):
    """Nominal camera centre in the start-body gauge, no evaluation input."""
    import numpy as np
    x, y, yaw = pose
    c, s = np.cos(yaw), np.sin(yaw)
    rotation = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    return (rotation@np.asarray(calibration['camera_origin_body_m']) + [x, y, 0.],
            rotation@np.asarray(calibration['camera_to_body_rotation']))


def run(a):
    import platform
    if platform.system() != 'Linux' or not platform.node().startswith('ugrp-act-l4-gcp5'):
        raise ValueError('GCP5_EVALUATION_ONLY')
    source = json.loads((ROOT/'SOURCE_FILES.json').read_text())
    if any(sha(ROOT/p) != h for p, h in source.items()):
        raise ValueError('SOURCE_BYTES_CHANGED')
    queue = json.loads(a.queue.read_text())
    table = Path(queue['rejection_table'])
    if not table.is_absolute() or not table.is_file():
        raise ValueError('EXISTING_ABSOLUTE_FUNNEL_REQUIRED')
    if queue['source_sha'] != (ROOT/'SOURCE_SHA').read_text().strip():
        raise ValueError('PINNED_SOURCE_REQUIRED')
    seal = verify_seal(a.prediction)
    # Python caches package paths.  Import frozen scene packages FIRST in this
    # new evaluator process; changing sys.path after replay cannot undo imports.
    sys.path[:0] = [str(a.vision), str(a.vision/'scripts'), str(ROOT), str(ROOT/'scripts')]
    import sim, scripts, harness
    sim.__path__.append(str(ROOT/'sim'))
    scripts.__path__.append(str(ROOT/'scripts'))
    harness.__path__.append(str(ROOT/'harness'))
    import numpy as np
    import mujoco
    from scripts import probe_scene_tex2 as tools
    from scripts.generate_scene_textures import MAPS
    os.chdir(a.vision)
    model, scene, hardware, xml, audit = tools.build_model(MAPS[0], 'walls_floor_contrast_v5_indigo110_s80')
    recording = json.loads((a.input/'summary.json').read_text())
    # Match the recorder's owner-provided XML transformation byte for byte.
    # This changes no geometry and runs no physics; checking the resulting XML
    # also catches accidentally evaluating the retired noslip10 model.
    import importlib.util
    owner = ROOT/'experiments/2026-10-16-mapbuild4/vendor/warp_native_contact.py'
    if sha(owner) != 'a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a':
        raise ValueError('WARPFIT_MODULE_CHANGED')
    spec = importlib.util.spec_from_file_location('warpfit_contact', owner)
    contact = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contact)
    if recording['contact_profile']['profile'] != 'warp_native_contact_v1':
        raise ValueError('NATIVE_V1_RECORDING_REQUIRED')
    xml = contact.apply(xml, 'warp_native_contact_v1')
    if hashlib.sha256(xml.encode()).hexdigest() != recording['scene_xml_sha256']:
        raise ValueError('RECORDING_XML_MISMATCH')
    model = mujoco.MjModel.from_xml_string(xml)
    a.output.mkdir(parents=True, exist_ok=False)
    # Hard links avoid duplicate large scans.  Neither evaluator modifies them.
    for name in seal['predictions']:
        os.link(a.prediction/name, a.output/name)
    rows = json.loads((a.prediction/'trajectory.json').read_text())
    events = json.loads((a.prediction/'events.json').read_text())
    from mapbuild5_replay import evaluate
    evaluate(a.input, a.vision, a.output, rows, events, model=model, scene=scene)

    own = json.loads((a.input/'own.json').read_text())['frames']
    qpos = np.load(a.input/'eval-state.npz')['qpos']
    if len(qpos) != len(own) or len(rows) != len(own):
        raise ValueError('EXACT_FRAME_COVERAGE_REQUIRED')
    labels = json.loads((a.input/'eval-only.json').read_text())
    ox, oy, yaw = labels['first_origin'][0]
    c, s = np.cos(yaw), np.sin(yaw)
    start_r = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    start_xyz = np.array([ox, oy, 0.])
    data = mujoco.MjData(model)
    camera = model.camera('r1__robot_cam').id
    truth = []
    for frame, q in zip(own, qpos):
        data.qpos[:] = q
        mujoco.mj_forward(model, data)  # geometry only; zero mj_step calls
        world_xyz = data.cam_xpos[camera].copy()
        # MuJoCo camera: right/up/back. OpenCV: right/down/forward.
        world_r = data.cam_xmat[camera].reshape(3, 3)@np.diag([1., -1., -1.])
        truth.append(dict(frame_id=frame['frame_id'], t=frame['t'],
            camera_xyz_m=world_xyz.tolist(), camera_to_world_rotation=world_r.tolist(),
            camera_xyz_start_body_m=(start_r.T@(world_xyz-start_xyz)).tolist(),
            camera_to_start_body_rotation=(start_r.T@world_r).tolist()))
    dump(a.output/'camera-evaluation-only.json', dict(evaluation_only=True, frames=truth,
        source_qpos=dict(path=str(a.input/'eval-state.npz'), sha256=sha(a.input/'eval-state.npz')),
        scene_xml_sha256=recording['scene_xml_sha256'], camera='r1__robot_cam',
        convention='rotation columns are OpenCV camera axes in reference frame',
        cpu_physics_steps=0, control_truth_transfers=0))
    cal = json.loads((a.input/'fixed-floor-calibration.json').read_text())
    estimates = {}
    for method in ('lk', 'rbpf'):
        estimates[method] = []
        for row in rows:
            xyz, rotation = estimated_camera(row[method+'_pose'], cal)
            estimates[method].append(dict(frame_id=row['frame_id'], t=row['t'],
                camera_xyz_m=xyz.tolist(), camera_to_start_body_rotation=rotation.tolist()))
    dump(a.output/'estimated-cameras.json', dict(frame='r1/start planar-body gauge', methods=estimates,
        source_prediction_seal=sha(a.prediction/'prediction-seal.json'),
        nominal_calibration_sha256=sha(a.input/'fixed-floor-calibration.json'), truth_inputs=0,
        limitation='fixed FK; chassis roll/pitch, height variation and joint sag unobserved'))
    summary = json.loads((a.output/'summary.json').read_text())
    corrections = summary['return_scan_corrections']
    wall = json.loads((a.output/'wall-reobservation.json').read_text())
    dump(a.output/'return-summary.json', dict(common_nearest_walls=wall['common_nearest_walls'],
        matching_attempts=len(corrections), improved_xy=sum(r['after_xy_m'] < r['before_xy_m'] for r in corrections),
        worsened_xy=sum(r['after_xy_m'] > r['before_xy_m'] for r in corrections),
        mean_before_m=float(np.mean([r['before_xy_m'] for r in corrections])),
        mean_after_m=float(np.mean([r['after_xy_m'] for r in corrections])),
        scope='XY error only at return updates; nearest wall identity is evaluation-only, not loop admission'))
    # New manifest extends the original without rewriting its shared bytes.
    original = a.input/'manifest.json'
    shared = json.loads(original.read_text())
    additions = [a.output/'camera-evaluation-only.json', a.output/'estimated-cameras.json']
    shared.update(schema='ugrp.shared_recording.v2', parent_manifest=str(original),
        parent_manifest_sha256=sha(original),
        camera_evaluation_only=str(additions[0]), estimated_cameras=str(additions[1]),
        disclosure='WITHHOLD evaluation files until mast3rcmp prediction and scale seal announced in ops-alert')
    shared['files'] += [dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p)) for p in additions]
    dump(a.output/'manifest-evaluation-v2.json', shared)
    verify_seal(a.prediction)
    dump(a.output/'completion.json', dict(status='EVALUATION_COMPLETE', source_sha=queue['source_sha'],
        input_prediction_seal=sha(a.prediction/'prediction-seal.json'), predictions_unchanged=True,
        frame_count=len(truth), model_xml_verified=True, cpu_physics_steps=0,
        control_truth_transfers=0, evaluation_disclosure='withheld_pending_external_seal',
        files={p.name:dict(bytes=p.stat().st_size, sha256=sha(p)) for p in a.output.iterdir() if p.is_file()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'vision', 'prediction', 'output', 'queue'):
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())
