"""Share a recording without copying credentials or changing its originals."""
import argparse
import hashlib
import json
from pathlib import Path


def manifest(root, vision, output):
    own = json.loads((root/'own.json').read_text())
    paths = [root/r['rgb'] for r in own['frames']]
    paths += [root/n for n in ('own.json', 'commands.json', 'eval-only.json', 'summary.json')]
    paths += [vision/n for n in ('sim/masterpi_camera_profile.py', 'harness/servo_camera_fk.py', 'harness/active_camera.py')]
    calibration = root/'camera-calibration.json'
    if calibration.is_file():
        paths.append(calibration)
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
