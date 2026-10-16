"""Non-physics checks of evidence boundaries and independent analytic examples."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


prepare=module('mast3rcmp_prepare')
evaluate=module('mast3rcmp_evaluate')


class EvidenceTests(unittest.TestCase):
    def test_sim3_recovers_scale_but_rigid_does_not(self):
        x=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float)
        r=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
        y=2*x@r.T+[3,4,5]
        fitted=evaluate.align(x,y,True)
        self.assertAlmostEqual(fitted['alignment_scale'],2.)
        self.assertLess(fitted['rmse_m'],1e-12)
        self.assertGreater(evaluate.align(x,y,False)['rmse_m'],.1)

    def test_failure_stays_in_denominator(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            pts=[[0,0,0],[1,0,0],[0,1,0],[99,99,99]]
            est=[dict(index=i,t_sim_s=i,success=i!=3,pose_sim3_final=p+[0,0,0,1,1]) for i,p in enumerate(pts)]
            gt=[dict(index=i,t_sim_s=i,camera_xyz_m=p) for i,p in enumerate(pts)]
            (d/'est').write_text(json.dumps(dict(frames=est)))
            (d/'gt').write_text(json.dumps(dict(frames=gt)))
            result=evaluate.score(d/'est',d/'gt',None,d/'score')
            self.assertEqual((result['total_frames'],result['tracking_success'],result['tracking_failure'],result['scored_frames']),(4,3,1,3))
            self.assertEqual(result['se3_allowed_scale']['status'],'unknown_no_allowed_scale')

    def test_input_manifest_and_frame_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); image=np.zeros((6,8,3),np.uint8)
            cv2.imwrite(str(d/'own.png'),image)
            data=dict(frames=[dict(path='own.png',sha256=prepare.sha256(d/'own.png'),t_sim_s=0)],
                      calibration=dict(K=[[10,0,4],[0,10,3],[0,0,1]],D=[0,0,0,0],width=8,height=6))
            (d/'manifest').write_text(json.dumps(data)); sha=prepare.sha256(d/'manifest')
            with self.assertRaisesRegex(ValueError,'manifest_sha256_mismatch'):
                prepare.prepare(d/'manifest','0'*64,d,d/'out1')
            (d/'own.png').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'frame_sha256_mismatch'):
                prepare.prepare(d/'manifest',sha,d,d/'out2')

    def test_floor_scale_without_truth(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); xyz=np.ones((2,2,3));xyz[:,:,2]=2
            np.savez(d/'pointmap.npz',xyz=xyz,rgb=np.zeros((2,2,3)))
            cv2.imwrite(str(d/'mask.png'),np.full((2,2),255,np.uint8))
            ref=dict(mask_path='mask.png',mask_sha256=evaluate.digest(d/'mask.png'),floor_normal_camera=[0,0,-1],camera_height_m=.4,source='synthetic fixed calibration')
            (d/'ref').write_text(json.dumps(ref))
            scale=evaluate.freeze_scale(d/'pointmap.npz',d/'ref',d/'scale')
            self.assertAlmostEqual(scale['scale'],.2)
            self.assertEqual(scale['truth_reads'],0)


if __name__=='__main__':unittest.main()
