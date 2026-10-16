"""Export FIXED robot geometry only; never export world pose or actual joints."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as E
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
from v3_confidence_replay import EPISODES

chains, sources = [], []
for case,episode in EPISODES.items():
    p=episode/'scene.xml'
    root=E.fromstring(p.read_bytes())
    chain=[]
    for name,servo in [('arm_base',6),('shoulder_link',5),('elbow_link',4),('wrist_link',3),('gripper',None)]:
        b=root.find(f'.//body[@name="r3__{name}"]')
        entry=dict(name=name,translation_m=[float(v) for v in b.get('pos','0 0 0').split()],
                   quaternion_wxyz=[float(v) for v in b.get('quat','1 0 0 0').split()])
        j=b.find('joint')
        if servo is not None:
            assert j is not None and j.get('pos','0 0 0')=='0 0 0'
            entry.update(servo=servo,joint_axis=[float(v) for v in j.get('axis').split()],
                         range_rad=[float(v) for v in j.get('range').split()])
        chain.append(entry)
    cam=root.find('.//camera[@name="r3__robot_cam"]')
    data=dict(schema='ugrp.own_command_camera_fk.v1',frame='chassis_yaw_floor',
        floor_to_chassis_translation_m=[0,0,.0325],chain=chain,
        camera=dict(translation_m=[float(v) for v in cam.get('pos').split()],
                    quaternion_wxyz=[float(v) for v in cam.get('quat').split()]),
        inputs='own commanded PWM only; nominal level chassis; no live pose or joint measurements',
        calibration_status='v3 structural geometry, not a sag fit or physical camera calibration')
    chains.append(data)
    sources.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
assert all(d==chains[0] for d in chains)
out=ROOT/'harness/data/servo_camera_v3_chain.json'
assert not out.exists(), 'DO_NOT_OVERWRITE_FROZEN_GEOMETRY'
out.write_text(json.dumps(chains[0],indent=2)+'\n')
(ROOT/'experiments/2026-10-07-camera-pose-projection/geometry-source.json').write_text(json.dumps(dict(
    scenes=sources,all_six_chains_equal=True,runtime_file=str(out.relative_to(ROOT)),
    sha256=hashlib.sha256(out.read_bytes()).hexdigest(),source_modules=[
        'sim/masterpi_model_v3.py','sim/masterpi_dynamics_v2.py:1134']),indent=2)+'\n')
print(hashlib.sha256(out.read_bytes()).hexdigest())
