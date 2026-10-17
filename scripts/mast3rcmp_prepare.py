"""Offline own-RGB adapter. This module never opens a truth/command/top file.

Input contract: {frames:[{path,sha256,t_sim_s}], calibration:{K,D,width,height}}.
The manifest itself must match the sender's SHA256. Paths are relative to root.
Keep one robot/posture per manifest. No temporal subsampling or frame omission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def sha256(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def prepare(manifest, expected_sha256, root, output):
    manifest, root, output = Path(manifest), Path(root).resolve(), Path(output)
    if sha256(manifest) != expected_sha256:
        raise ValueError('manifest_sha256_mismatch')
    data = json.loads(manifest.read_text())
    frames, cal = data['frames'], data['calibration']
    if not frames:
        raise ValueError('empty_recording')
    w, h = cal['width'], cal['height']
    k, d = np.asarray(cal['K'], float), np.asarray(cal['D'], float)
    # K_out=K, R=I: preserve the established K-pinhole FOV, not an arbitrary
    # balance/zoom crop. Pixel validity and angular spans are reported below.
    mx, my = cv2.fisheye.initUndistortRectifyMap(k, d, np.eye(3), k, (w, h), cv2.CV_32FC1)
    valid = (mx >= 0) & (mx <= w-1) & (my >= 0) & (my <= h-1)
    output.mkdir(parents=True, exist_ok=False)
    images = output / 'rgb'
    images.mkdir()
    receipt = []
    for i, frame in enumerate(frames):
        src = (root / frame['path']).resolve()
        if not src.is_relative_to(root):
            raise ValueError('path_outside_root')
        # The explicit allowlist is built by the recorder, never from a run glob.
        if sha256(src) != frame['sha256']:
            raise ValueError(f'frame_sha256_mismatch:{i}')
        rgb = cv2.imread(str(src))
        if rgb is None or rgb.shape != (h, w, 3):
            raise ValueError(f'frame_decode_or_shape:{i}')
        rectified = cv2.remap(rgb, mx, my, cv2.INTER_LINEAR)
        dst = images / f'{i:08d}.png'
        if not cv2.imwrite(str(dst), rectified):
            raise OSError('frame_write_failed')
        receipt.append(dict(index=i, t_sim_s=frame['t_sim_s'], source=frame['path'],
                            source_sha256=frame['sha256'], path=str(dst), sha256=sha256(dst)))
    angles = []
    # Border rays at the original optical centre: raw fisheye vs output pinhole.
    for p in ([[0,k[1,2]],[w-1,k[1,2]]], [[k[0,2],0],[k[0,2],h-1]]):
        xy = cv2.fisheye.undistortPoints(np.asarray(p,float).reshape(-1,1,2), k, d).reshape(-1,2)
        axis = len(angles)
        raw = np.degrees(np.arctan(xy[:,axis]))
        pinhole = np.degrees(np.arctan((np.asarray(p)[:,axis]-k[axis,2])/k[axis,axis]))
        angles.append(dict(raw_border_angles_deg=raw.tolist(), pinhole_border_angles_deg=pinhole.tolist(),
                           raw_span_deg=float(np.ptp(raw)), output_span_deg=float(np.ptp(pinhole))))
    audit = dict(input_manifest_sha256=expected_sha256, all_frames=len(frames), frames=receipt,
                 calibration=cal, invalid_output_pixels=int((~valid).sum()),
                 output_pixels=int(valid.size), fov=dict(horizontal=angles[0],vertical=angles[1]),
                 interpolation='cv2.INTER_LINEAR', K_out=k.tolist(),
                 allowed_inputs=['own_rgb','fixed_K_D'], truth_reads=0, command_reads=0, top_reads=0)
    (output/'input-receipt.json').write_text(json.dumps(audit,indent=2)+'\n')
    (output/'intrinsics.yaml').write_text(f'width: {w}\nheight: {h}\ncalibration: '+json.dumps([k[0,0],k[1,1],k[0,2],k[1,2]])+'\n')
    return audit


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True)
    p.add_argument('--manifest-sha256', required=True)
    p.add_argument('--root', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    print(json.dumps({k:v for k,v in prepare(a.manifest,a.manifest_sha256,a.root,a.output).items() if k!='frames'},indent=2))
