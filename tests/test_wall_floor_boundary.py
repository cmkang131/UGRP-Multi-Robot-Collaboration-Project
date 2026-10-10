"""Basic algorithm, projection conventions, ABI and default/off frozen-byte tests."""
import json
from pathlib import Path
import sys
import types

import numpy as np
import pytest
from harness.wall_floor_boundary import detect, hsi, histograms

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code')]
import v3_confidence_replay as replay


def test_hsi_mean_intensity_and_undefined_hue():
    hue,saturation,intensity,valid=hsi(np.array([[[0,0,255],[0,255,0],[255,0,0],[70,70,70],[0,0,0]]],np.uint8))
    np.testing.assert_allclose(hue[0,:3],[0,1/3,2/3])
    np.testing.assert_allclose(intensity[0,:3],[1/3]*3)
    assert valid.tolist()==[[True,True,True,False,False]]
    assert saturation[0,3]==0


def test_histogram_multimodal_floor_and_circular_hue():
    hue=np.tile([.001,.999],(100,100))
    intensity=np.tile([.2,.8],(100,100))
    hh,ih,_,_=histograms(hue,intensity,np.ones_like(hue,bool),np.ones_like(hue,bool))
    assert hh[0]>60 and hh[-1]>60 and hh[128]==0
    assert ih[51]>80 and ih[204]>80 and ih[128]==0


def sample(colour):
    img=np.full((200,200,3),100,np.uint8)
    img[:30]=colour
    return img,dict(camera_origin=np.array([.5,0.,.5]),camera_rotation=np.diag([1.,-1.,-1.]),
                    intrinsic=np.array([[100.,0,100],[0,100.,100],[0,0,1]]),columns=np.array([50,100,150]))


@pytest.mark.parametrize('colour',[(0,0,255),(0,0,0)])
def test_reference_floor_and_lowest_obstacle_contact(colour):
    img,args=sample(colour)
    result=detect(img,**args)
    assert result['reason']=='classified' and len(result['uv'])==3
    assert np.all(abs(result['uv'][:,1]-30)<=3)
    assert result['behind_camera_rejected']==0
    assert np.all(result['ranges']<=4)
    # Projection exactly satisfies both image rays and the ground plane.
    xyz=np.c_[result['xy'],np.zeros(3)]
    camera=(xyz-args['camera_origin'])@args['camera_rotation']
    pix=camera@args['intrinsic'].T
    np.testing.assert_allclose(pix[:,:2]/pix[:,2,None],result['uv'])


def test_no_reference_or_border_footpoint_abstains():
    img,args=sample((0,0,255))
    out=detect(img,valid_image=np.zeros(img.shape[:2],bool),**args)
    assert out['reason']=='insufficient_reference' and not len(out['uv'])
    img[170:]=[0,0,255]
    out=detect(img,**args)
    assert not len(out['uv']) and out['border_censored_columns']==3


def fixture():
    mod=types.ModuleType('height_free_before_floor_boundary')
    mod.__file__=replay.hfw.__file__
    exec((ROOT/'tests/fixtures/height_free_wall_before_floor_boundary.py.txt').read_text(),mod.__dict__)
    return mod


@pytest.mark.parametrize('loaded',[False,True])
def test_default_and_explicit_off_match_frozen_scan_and_segments_bytes(loaded):
    cm,_,_=replay.geometry({1:2000,3:1072,4:2400,5:1482,6:1500},'v3_unloaded_extrinsic_v1')
    img=np.full((480,640,3),180,np.uint8)
    img[:140]=80
    img[360:,260:380]=[190,190,25]
    old=fixture()
    scans=[old.detect(img,cm,params=replay.PARAMS,loaded=loaded),
           replay.hfw.detect(img,cm,params=replay.PARAMS,loaded=loaded),
           replay.hfw.detect(img,cm,params=replay.PARAMS,loaded=loaded,wall_detector='off')]
    assert np.isfinite(scans[0]['vb']).any() # nonempty golden, not a vacuous equivalence
    for key in scans[0]:
        assert scans[0][key].tobytes()==scans[1][key].tobytes()==scans[2][key].tobytes()
    blobs=[json.dumps(replay.hfw.link_segments(s,replay.PARAMS)).encode() for s in scans]
    assert blobs[0]==blobs[1]==blobs[2]


def test_image_adapter_off_matches_prechange_bytes(monkeypatch,tmp_path):
    cm,offset,_=replay.geometry({1:2000,3:1072,4:2400,5:1482,6:1500},'v3_unloaded_extrinsic_v1')
    img=np.full((480,640,3),180,np.uint8)
    img[:140]=80
    monkeypatch.setattr(replay.base,'sha',lambda p:'ok')
    monkeypatch.setattr(replay.mp,'undistort',lambda x:x)
    import cv2
    monkeypatch.setattr(cv2,'imread',lambda p:img.copy())
    f=dict(path='unused.jpg',sha256='ok',commanded_servo={1:2000,3:1072,4:2400,5:1482,6:1500})
    expected=fixture()
    new_detect=replay.hfw.detect
    monkeypatch.setattr(replay.hfw,'detect',lambda *a,wall_detector='off',**k:expected.detect(*a,**k))
    before=json.dumps(replay.detections(tmp_path,f,cm,offset,1.)).encode()
    monkeypatch.setattr(replay.hfw,'detect',new_detect)
    assert before==json.dumps(replay.detections(tmp_path,f,cm,offset,1.)).encode()
    assert before==json.dumps(replay.detections(tmp_path,f,cm,offset,1.,wall_detector='off')).encode()
    replay.detections(tmp_path,f,cm,offset,1.,wall_detector='floor_boundary_v1')
    with pytest.raises(ValueError,match='UNKNOWN_WALL_DETECTOR'):
        replay.detections(tmp_path,f,cm,offset,1.,wall_detector='unknown')
