"""PR480 saved-RGB adapter; never renders or reads eval_only.

Missing RGB is an error, not a no-return scan. Frame IDs and encoded JPEG hashes
are verified before reusing the original own-RGB floor/wall measurements.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from scripts.e2e_stage_pose_eval import read


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_file(path):
    return path if path.exists() else Path(str(path)+'.zst')


def source_sha256(path):
    """Original bytes, including verified losslessly compressed text sources."""
    path = Path(path)
    if path.exists():
        return sha256(path)
    with subprocess.Popen(['zstd', '-qdc', str(source_file(path))], stdout=subprocess.PIPE) as proc:
        digest = hashlib.file_digest(proc.stdout, 'sha256').hexdigest()
        if proc.wait() != 0:
            raise ValueError('COMPRESSED_SOURCE_READ_FAILED:'+str(path))
    return digest


def packets(raw, rid):
    """Only explicitly permitted fields cross from historical own logs."""
    frames = read(raw/f'robots/{rid}/frames.jsonl', True)
    lookup = {f['frame_id']: f for f in frames}
    if len(lookup) != len(frames):
        raise ValueError('DUPLICATE_FRAME_ID')
    own = read(raw/f'robots/{rid}/ownmap.jsonl', True)
    result, previous = [], -float('inf')
    for o in own:
        f = lookup[o['frame_id']]
        if f['sha256'] != o['sha256'] or float(o['t']) <= previous:
            raise ValueError('OWN_FRAME_IDENTITY_OR_CLOCK_MISMATCH')
        previous = float(o['t'])
        image = (raw/f['path']).resolve()
        if not image.is_relative_to((raw/f'robots/{rid}/rgb').resolve()):
            raise ValueError('OWN_RGB_PATH_REQUIRED')
        motion = o['stall_odometry']
        active = bool(motion.get('command_substeps'))
        result.append(dict(robot_id=rid, t=previous, physical_t=float(f['sim_time']),
            frame_id=o['frame_id'], sha256=o['sha256'], image_path=str(image),
            servo={int(k): int(v) for k, v in f['commanded_servo'].items()},
            command_delta=motion['command_delta'] if active else [0., 0., 0.],
            fused_delta=motion['fused_delta'] if active else [0., 0., 0.]))
    return result


def availability(rows):
    missing = [dict(frame_id=r['frame_id'], sha256=r['sha256'], path=r['image_path'])
               for r in rows if not Path(r['image_path']).is_file()]
    return dict(expected=len(rows), available=len(rows)-len(missing), missing=len(missing),
                first_missing=missing[:3])


def extract(raw, static_map, output, robot_ids=('r1', 'r2')):
    inputs = {rid: packets(raw, rid) for rid in robot_ids}
    inventory = {rid: availability(rows) for rid, rows in inputs.items()}
    if any(r['missing'] for r in inventory.values()):
        raise FileNotFoundError('SAVED_OWN_RGB_REQUIRED:' + json.dumps(inventory))
    import cv2
    from harness.self_map_closed_loop import own_measurement
    from harness.self_map_landmark_sensor import Sensor
    from harness.own_map_amcl_vendor.landmarks import MapFeatures
    mapped = MapFeatures(read(static_map))
    output.mkdir(parents=True, exist_ok=False)
    files, source_hashes = {}, {str(source_file(static_map)): sha256(source_file(static_map))}
    for rid, rows in inputs.items():
        sensor = Sensor(mapped.hues)
        last_servo, changed = None, None
        path = output/f'{rid}.jsonl'
        with path.open('w') as stream:
            for original in rows:
                r = dict(original)
                servo, t = r['servo'], r['t']
                if servo != last_servo:
                    changed, last_servo = t, servo
                settled = t-changed >= (2.25 if servo.get(1, 2000) <= 1600 else .25)-1e-8
                data = Path(r.pop('image_path')).read_bytes()
                if hashlib.sha256(data).hexdigest() != r['sha256']:
                    raise ValueError('OWN_RGB_SHA256_MISMATCH')
                points, features = [], []
                if settled:
                    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                    if bgr is None:
                        raise ValueError('OWN_RGB_DECODE_FAILED')
                    measurement = own_measurement(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), servo)
                    points = measurement['points']
                    features = sensor.measure(bgr, servo, measurement)
                    if len(points) > 60:
                        points = [points[i] for i in np.linspace(0, len(points)-1, 60, dtype=int)]
                stream.write(json.dumps(dict(r, settled=settled, points=points, features=features),
                                        separators=(',', ':'))+'\n')
        files[path.name] = sha256(path)
        for name in ('frames.jsonl', 'ownmap.jsonl'):
            source = source_file(raw/f'robots/{rid}/{name}')
            source_hashes[str(source)] = sha256(source)
    manifest = dict(schema='saved-own-rgb-features/1', source_raw=str(raw),
        static_map_sha256=source_sha256(static_map), frames={rid: len(rows) for rid, rows in inputs.items()},
        source_hashes=source_hashes, files=files,
        scope='Saved own RGB, commanded servo and command/RGB increments only; no render or eval input')
    (output/'summary.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--static-map', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(extract(a.raw, a.static_map, a.output)))


if __name__ == '__main__':
    main()
