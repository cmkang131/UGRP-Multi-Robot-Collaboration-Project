"""Read-only post-replay checks; emits a new receipt, never changes raw artifacts."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import numpy as np
import v3_confidence_replay as run
from harness.self_pose_graph import rebuild
from harness.wall_camera_calibration import SHA256,TABLE,camera_transform
from harness.wall_projection_guard import floor_depths


def verify():
    receipt={'calibration_sha256':run.base.sha(TABLE),'cases':{},'tests':{}}
    assert receipt['calibration_sha256']==SHA256
    for seed in range(1042,1048):
        case=f's{seed}'
        case_receipt={}
        dr_blobs=[]
        for camera in ('off','v3_unloaded_extrinsic_v1'):
            root=run.OUT/case/camera
            extract=run.load(root/'extract-summary.json')
            for path in extract['sources']:
                assert run.base.sha(path['path'])==path['sha256']
            for name,h in extract['prediction_hashes'].items():
                assert run.base.sha(root/name)==h
            dr_blobs.append((root/'dr-poses.jsonl').read_bytes())
            contacts=run.base.read_rows(root/'contacts.jsonl')
            frames,_=run.own_inputs(run.EPISODES[case],'r3')
            frames={f['frame_id']:f for f in frames}
            for row in contacts:
                assert row['robot_id']=='r3'
                z,t,valid=floor_depths(row['segments'],row['camera_origin'],row['camera_rotation'])
                assert valid.all() and (z>0).all() and (t>0).all()
                assert all(np.linalg.norm(np.array(s)-row['camera'],axis=1).max()<4 for s in row['segments'])
                if camera!='off':
                    rigid,reason=camera_transform(frames[row['frame_id']]['commanded_servo'],wall_camera_calibration=camera)
                    assert rigid is not None and reason=='calibrated_unloaded'
                    np.testing.assert_allclose(rigid[0],row['camera_origin'],atol=1e-12,rtol=0)
                    np.testing.assert_allclose(rigid[1],row['camera_rotation'],atol=1e-12,rtol=0)
            for variant in (('unweighted',) if camera=='off' else ('unweighted','confidence')):
                p=root/variant
                prediction=run.load(p/'prediction.json')
                assert prediction['inputs_sha256']==run.base.sha(root/'contacts.jsonl')
                for name,h in prediction['hashes'].items():
                    assert run.base.sha(p/name)==h
                for kind,gridname in [('frontend','frontend-grid.json'),('graph','grid.json')]:
                    ledger=run.base.read_rows(p/(kind+'-ledger.jsonl'))
                    assert rebuild('r3',ledger).export()['cells']==run.load(p/gridname)['cells']
                    for row in ledger:
                        if variant=='confidence':
                            for weight,conf in zip(row['insertion_weights'],row['wall_confidence']):
                                assert 0<=weight<=1 and math.isclose(weight,math.prod(conf['factors'].values()),rel_tol=1e-12)
                case_receipt[camera+'/'+variant]={'inserted':prediction['inserted'],'loop_counts':prediction['loop_counts'],
                    'prediction_sha256':run.base.sha(p/'prediction.json'),'rebuild_exact':True}
        assert dr_blobs[0]==dr_blobs[1]
        case_receipt['dr_camera_option_pose_bytes']=True
        summary=run.load(run.OUT/case/'evaluation/complete-summary.json')
        for name,checks in summary['checks'].items():
            assert summary['success'][name]==all(checks.values())
            assert not checks['guard_visible_recall_verified']
        receipt['cases'][case]=case_receipt
    testlog=run.OUT/'verification/tests-lazy-off.log'
    assert '49 passed' in testlog.read_text()
    receipt['tests']={'path':str(testlog),'sha256':run.base.sha(testlog),'passed':49,
        'files':['tests/test_wall_confidence.py','tests/test_self_pose_graph.py','tests/test_self_map_prob.py']}
    receipt['runtime_files']={str(p):run.base.sha(p) for p in [Path('harness')/n for n in
        ('self_wall_memory.py','self_map_rbpf.py','self_pose_graph.py','wall_confidence.py','wall_camera_calibration.py')]}
    target=run.RESULTS/'verification.json'
    if target.exists(): raise FileExistsError(target)
    run.base.dump(target,receipt)
    files=[p for p in run.OUT.rglob('*') if p.is_file()]
    artifacts=[p for p in run.RESULTS.rglob('*') if p.is_file() and p.name!='manifest.json']
    manifest={'local':[{'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':run.base.sha(p)} for p in files],
              'git_artifacts':[{'path':str(p.relative_to(run.ROOT)),'bytes':p.stat().st_size,'sha256':run.base.sha(p)} for p in artifacts]}
    run.base.dump(run.RESULTS/'manifest.json',manifest)
    print('verified',len(receipt['cases']),'cases',len(files),'local files',len(artifacts),'Git artifacts')

if __name__=='__main__': verify()
