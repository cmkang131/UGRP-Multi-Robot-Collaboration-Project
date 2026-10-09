"""Read saved HIGH PNGs through the existing image gate/OpenCV wall observer.

No simulator, renderer, model inference, or command execution. Candidate wall
columns are not a PF fix or proof of successful localization/grasp.
"""
import base64
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness import zone_solo_cyan_camera_v3 as extension
from harness import zone_solo_cyan_contract_v106 as contract
from harness import zone_pair_highpose_frame_gate as gate
from harness.vision_pose_source_final import measured_column_model
from harness import vision_loc_protocol as protocol
from harness.opencv_wall_observation import OpenCVObserver


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root):
    summary_path = root/'summary.json'
    summary = json.loads(summary_path.read_text())
    cal = contract.hp.student_calibration(contract.hp.calibration_for(
        contract.hp.DEV_PILOT, contract.ROOT/contract.CALIBRATION,
        contract.CALIBRATION_SHA, contract.MAP_ID))
    derived = extension.camera_calibration(cal)
    vl, _ = protocol.load_vis3()
    cameras = {}
    for name, data in [('baseline', cal), ('user_v3', derived)]:
        rec = contract.hp.camera_record(data, 'loaded', extension.legacy.high.HIGH)
        cameras[name] = measured_column_model(vl.mp, rec, vl.column_positions(96, 2))
    rows = []
    for row in summary['results']:
        if row['phase'] != 'HIGH' or row['variant'] not in cameras:
            continue
        path = root/row['image']
        if sha(path) != row['sha256']:
            raise ValueError('saved PNG hash mismatch: '+str(path))
        bgr = cv2.imread(str(path))
        jpeg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()
        obs = {'robot_id': 'r3', 'camera': 'robot_cam', 'sim_time': row['t'],
               'frame_id': len(rows)+1, 'image': base64.b64encode(jpeg).decode(),
               'sha256': hashlib.sha256(jpeg).hexdigest()}
        verdict, reason = gate.gate().assess(obs, 'r3', row['t'], ob=False)
        worker = OpenCVObserver(vl, lambda: cameras[row['variant']], contract.hp.own_image_gates()['values'])
        try:
            # Same JPEG decode used by the controller, not the pristine PNG.
            decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            wall = worker.observe(decoded)
            edge_count = int(np.count_nonzero(wall.b_kind == vl.EDGE))
        finally:
            worker.close()
        rows.append({'image': str(path), 'sha256': row['sha256'], 't': row['t'],
                     'variant': row['variant'], 'full_fraction': row['full_fraction'],
                     'gate': verdict, 'gate_reason': reason, 'wall_edge_columns': edge_count})
    return {'scope': 'saved HIGH JPEG95 gate and wall-candidate audit only; no PF fix or grasp claim',
            'source': {'path': str(summary_path), 'sha256': sha(summary_path)},
            'camera_derivation': derived['camera_v3_derivation'], 'rows': rows,
            'new_simulations': 0, 'model_calls': 0, 'physical_success': None,
            'pregrasp': 'UNVERIFIED: this saved lift starts at floor close; no pre-close open-hover/align sequence',
            'grasp_receipt': 'own issued close; carry has no cyan visibility condition and cannot detect a drop'}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.source)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'frames': len(result['rows']), 'output': str(args.output)}))
