"""Read ARM originals and emit only numeric pose diagnostics as JSONL.

The entrypoint receives dominant_cluster from the exact reporter source when
run via stdin on ARM; no repository install, original writes or raw media fetch.
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import numpy as np


def extract(root):
    for folder in sorted(Path(root).glob('egomap70-*')):
        if not folder.is_dir():
            continue
        provenance = []
        def read(name, lines=False):
            p = folder/name
            if not p.exists():
                p = Path(str(p)+'.zst')
            provenance.append(dict(path=str(p), bytes=p.stat().st_size,
                sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
            raw = subprocess.check_output(['zstd', '-qdc', str(p)]) if p.suffix == '.zst' else p.read_bytes()
            return [json.loads(x) for x in raw.splitlines()] if lines else json.loads(raw)
        decisions = read('decisions.json')
        own = read('own-controller.jsonl', True)
        online = read('online-maps.jsonl', True)
        route = read('route-map.json')
        print(json.dumps(dict(kind='sources', run=folder.name, sources=provenance)), flush=True)
        by_t = {round(x['t'], 6):x for x in decisions}
        clouds = {round(x['t'], 6):x['grid'] for x in online}
        offsets = {round(x['t'], 6):x['delta'] for x in route['offsets']}
        previous_driver = np.zeros(3)
        poses = weights = None
        previous_selected = None
        for row in own:
            t = round(row['t'], 6)
            d = by_t.get(t, {})
            driver = np.asarray(d.get('motion_gate', {}).get('previous', previous_driver), float)
            delta = driver-previous_driver
            c, s = math.cos(previous_driver[2]), math.sin(previous_driver[2])
            delta[:2] = np.array([[c,s],[-s,c]])@delta[:2]
            delta[2] = math.atan2(math.sin(delta[2]), math.cos(delta[2]))
            if t in clouds:
                poses = np.asarray(clouds[t]['particle_poses'])
                weights = np.asarray(clouds[t]['weights'])
            elif poses is not None:
                c, s = np.cos(poses[:, 2]), np.sin(poses[:, 2])
                poses += np.column_stack((c*delta[0]-s*delta[1], s*delta[0]+c*delta[1], np.full(len(c), delta[2])))
                if t in offsets:
                    o = offsets[t]; c, s = math.cos(o[2]), math.sin(o[2])
                    poses[:, :2] = poses[:, :2]@np.array([[c,s],[-s,c]])+o[:2]
                    poses[:, 2] += o[2]
            cluster, info = (None, None) if poses is None else dominant_cluster(poses, weights)
            pe = d.get('particle_events')
            selected = d.get('selected_before_resampling')
            prior_lineage_pose = None
            if pe and previous_selected is not None:
                prior_lineage_pose = pe[previous_selected].get('pose')
            print(json.dumps(dict(kind='sample', run=folder.name, t=row['t'], frame_id=row['frame_id'],
                command_odom=driver.tolist(), body_delta=delta.tolist(),
                cluster_pose=None if cluster is None else cluster.tolist(), cluster=info,
                measurement=bool(pe), reason=d.get('reason'), raw_pose=d.get('pose'),
                selected_previous=previous_selected, selected_before_resampling=selected,
                selected_after_resampling=d.get('selected_after_resampling'),
                previous_lineage_current_pose=prior_lineage_pose,
                selected_proposal=None if not pe else pe[selected],
                sensor_weight_update=d.get('sensor_weight_update'), resampled=d.get('resampled'),
                yaw_prior=d.get('yaw_prior'), route_delta=offsets.get(t),
                motion_gate=d.get('motion_gate'))), flush=True)
            if selected is not None:
                previous_selected = d['selected_after_resampling']
            previous_driver = driver


if __name__ == '__main__':
    if 'dominant_cluster' not in globals():
        from harness.ego_pose_continuity import dominant_cluster
    extract(sys.argv[1])
