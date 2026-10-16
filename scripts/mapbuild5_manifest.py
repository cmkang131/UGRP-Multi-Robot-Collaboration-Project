"""Share a recording without copying credentials or changing its originals."""
import argparse
import hashlib
import json
from pathlib import Path


def fixed_floor_calibration(servo):
    """Nominal fixed mount only; no frame, runtime joint or evaluation input."""
    import numpy as np
    from harness.servo_camera_fk import transform_from_commands, MODEL, MODEL_SHA256
    value,reason=transform_from_commands(servo,camera_pose='servo_fk_v1')
    if value is None:raise ValueError(reason)
    origin,rotation=value
    return dict(camera_height_m=float(origin[2]),
        floor_normal_camera=(rotation.T@np.array([0.,0.,1.])).tolist(),
        floor_plane_equation='normal_camera dot point_camera + camera_height_m = 0',
        camera_origin_body_m=origin.tolist(),camera_to_body_rotation=rotation.tolist(),
        fixed_servo_command={str(k):v for k,v in servo.items()},
        source='fixed unloaded servo_camera_fk nominal geometry; fixed declared PWM; not runtime commands/joints/GT',
        geometry_path=str(MODEL),geometry_sha256=MODEL_SHA256,
        limitations='nominal mount, unmeasured gravity sag/chassis roll-pitch; not a live pose measurement')


def manifest(root, vision, output):
    own = json.loads((root/'own.json').read_text())
    paths = [root/r['rgb'] for r in own['frames']]
    paths += [root/n for n in ('own.json', 'commands.json', 'eval-only.json', 'summary.json')]
    paths += [vision/n for n in ('sim/masterpi_camera_profile.py', 'harness/servo_camera_fk.py', 'harness/active_camera.py')]
    calibration = root/'camera-calibration.json'
    if calibration.is_file():
        paths.append(calibration)
        poses={tuple(sorted(r['servo'].items())) for r in own['frames']}
        declared=json.loads(calibration.read_text())['servo']
        if poses!={tuple(sorted((str(k),v) for k,v in declared.items()))}:
            raise ValueError('FIXED_SERVO_RECORDING_REQUIRED')
        import sys
        sys.path.insert(0,str(vision))
        auxiliary=root/'fixed-floor-calibration.json'
        if auxiliary.exists():raise ValueError('NO_CALIBRATION_OVERWRITE')
        auxiliary.write_text(json.dumps(fixed_floor_calibration({int(k):v for k,v in declared.items()}),indent=2)+'\n')
        paths.append(auxiliary)
        paths.append(vision/'harness/data/servo_camera_v3_chain.json')
    contact=root/'contact-profile.json'
    if contact.is_file():paths.append(contact)
    rows = [dict(path=str(p.resolve()), bytes=p.stat().st_size,
                 sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
    out = dict(schema='ugrp.shared_recording.v1', recording_root=str(root.resolve()),
               own_manifest=str((root/'own.json').resolve()), evaluation_only=str((root/'eval-only.json').resolve()),
               frames=len(own['frames']), frame_hz=10, scene='walls_floor_contrast_v5_indigo110_s80', files=rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('NO_MANIFEST_OVERWRITE')
    output.write_text(json.dumps(out, indent=2)+'\n')
    assert all(hashlib.sha256(Path(r['path']).read_bytes()).hexdigest() == r['sha256'] for r in rows)
    return dict(manifest=str(output), sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                frames=len(own['frames']), verified_files=len(rows))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('input', 'vision', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(manifest(a.input, a.vision, a.output)))
