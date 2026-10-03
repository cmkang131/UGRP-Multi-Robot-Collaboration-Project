"""Independent v88 review: recorded arrays only; no engine/render/model."""
from pathlib import Path
import copy
import hashlib
import json
import subprocess
import sys
import types
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path('/Users/changmin/projects/ugrp-wt/review-358')
sys.path.insert(0, str(ROOT))
from scripts import final_pair_calibration_io as new

s = json.loads(Path('/tmp/review358r2-state.json').read_text())
dest = Path(s['evidence'])
fixture = json.loads((ROOT/'tests/fixtures/review_358_chassis.json').read_text())
loaded = (Path(s['raw_root'])/'calibration-loaded').resolve()
folder = loaded/new.MAP_ID
assert str(folder) == fixture['source_root']
def rows(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]
assert json.loads((folder/'bundle.json').read_text())['source_sha'] == fixture['source_sha']
for path, digest in fixture['source_sha256'].items():
    assert new.file_sha(folder/path) == digest, path
poses = rows(folder/'eval_only/r1/pose.jsonl')
trace = rows(folder/'eval_only/trajectory.jsonl')
labels = rows(folder/'eval_only/r1/camera_labels.jsonl')
assert fixture['label'] == labels[522]
for sample in fixture['samples']:
    i = sample['pose']['sample_index']
    assert sample['pose'] == poses[i]
    assert sample['qpos'] == trace[i]['qpos']
    assert sample['qvel'] == trace[i]['qvel']
report = {'pr_head':s['pr_head'], 'execution_source':s['review_source'],
          'fixture_full_rows_and_source_hashes_match': True, 'collections':{}, 'counterexamples':[]}
for profile in ('unloaded', 'fine', 'loaded'):
    root = (Path(s['raw_root'])/('calibration-'+profile)).resolve()
    assert str(root).startswith('/Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001')
    folder = root/new.MAP_ID
    inputs = new.Inputs()
    data = new.load_collection(root, profile, inputs)
    trace = rows(folder/'eval_only/trajectory.jsonl')
    qpos = np.array([r['qpos'] for r in trace])
    qvel = np.array([r['qvel'] for r in trace])
    scene = ET.parse(folder/'scene.xml').getroot()
    nq, nv, addresses = 0, 0, {}
    for joint in scene.find('worldbody').iter():
        if joint.tag in ('joint', 'freejoint'):
            kind = joint.get('type', 'free' if joint.tag == 'freejoint' else 'hinge')
            addresses[joint.get('name')] = (nq, nv)
            nq += {'free':7, 'ball':4, 'hinge':1, 'slide':1}[kind]
            nv += {'free':6, 'ball':3, 'hinge':1, 'slide':1}[kind]
    dt = float(scene.find('option').get('timestep'))
    record = {'collection_audit':'PASS', 'root':str(root), 'addresses':{}, 'robots':{}}
    for rid in ('r1', 'r2'):
        qa, va = addresses[rid+'__base_free']
        record['addresses'][rid] = [qa,va]
        pose = rows(folder/f'eval_only/{rid}/pose.jsonl')
        labels = rows(folder/f'eval_only/{rid}/camera_labels.jsonl')
        p = np.array([r['base_position_m'] for r in pose])
        r = np.array([r['base_rotation'] for r in pose])
        lp = np.array([v['base_position_m'] for v in labels])
        lr = np.array([v['base_rotation'] for v in labels])
        cp = qpos[:,qa:qa+3]
        cr = Rotation.from_quat(qpos[:,qa+3:qa+7][:,[1,2,3,0]]).as_matrix()
        pp = cp-dt*qvel[:,va:va+3]
        pr = cr @ Rotation.from_rotvec(-dt*qvel[:,va+3:va+6]).as_matrix()
        pp[0], pr[0] = cp[0], cr[0]
        errors = {'label_position_m':float(np.max(np.abs(lp-cp[::4]))),
                  'label_rotation_element':float(np.max(np.abs(lr-cr[::4]))),
                  'pose_position_m':float(np.max(np.abs(p-pp))),
                  'pose_rotation_element':float(np.max(np.abs(r-pr)))}
        assert max(errors.values()) < 1e-8
        fit_pose = np.column_stack((p[:,:2], np.unwrap(np.arctan2(r[:,1,0],r[:,0,0]))))
        assert np.array_equal(data['robots'][rid]['pose'], fit_pose)
        errors['fit_pose_exactly_original'] = True
        errors['pose_count'], errors['label_count'] = len(p), len(lp)
        record['robots'][rid] = errors
    inputs.verify()
    record['raw_reverified'] = True
    report['collections'][profile] = record

old = types.ModuleType('review358r2_old_io')
blob = subprocess.check_output(['git','show','9b8a89c4:scripts/final_pair_calibration_io.py'],cwd=ROOT)
exec(compile(blob, '<9b8a89c4-io>', 'exec'),old.__dict__)
for target, components in [('pose','position'),('pose','rotation'),('pose','both'),('label','rotation')]:
    result = {'target':target, 'components':components}
    keys = ['base_position_m','base_rotation'] if components == 'both' else ['base_position_m' if components=='position' else 'base_rotation']
    for name,module in [('old',old),('new',new)]:
        class Corrupt(module.Inputs):
            def rows(self,path):
                values = super().rows(path)
                relative = 'eval_only/r1/'+('pose.jsonl' if target=='pose' else 'camera_labels.jsonl')
                if path == loaded/new.MAP_ID/relative:
                    for key in keys:
                        values[2088 if target=='pose' else 522][key] = copy.deepcopy(fixture['samples'][1]['pose'][key])
                return values
        inputs = Corrupt()
        try:
            module.load_collection(loaded, 'loaded', inputs)
        except ValueError as exc:
            result[name] = {'accepted':False,'reason':str(exc)}
        else:
            result[name] = {'accepted':True}
        inputs.verify()
    assert result['old']['accepted'] and not result['new']['accepted'], result
    report['counterexamples'].append(result)
report['all_raw_hashes_reverified'] = True
(dest/'independent-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
