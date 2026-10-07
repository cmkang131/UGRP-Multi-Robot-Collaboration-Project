"""No simulation: fixed calibration, own-only evidence and signed ray updates."""
import json
from pathlib import Path
import sys
import numpy as np
import pytest
from harness.wall_camera_calibration import camera_transform,calibration
from harness.wall_confidence import confidence,weighted_insert
from harness.self_odom_grid import OdomGrid

FEATURE={'height_m':.2,'fy':622.,'contrast':30.,'band_std':1.,'sharpness':30.,'body_settling':1.}
SEG=np.array([[1.,-.2],[1.,.2]])

def test_calibration_compose_once_and_loaded_unknown_fail_closed():
    assert camera_transform(object())==(None,'off')
    key=next(iter(calibration()['camera_models']['unloaded']))
    s=dict(zip((3,4,5,6),map(int,key.split(','))))|{1:2000}
    (o,r),reason=camera_transform(s,wall_camera_calibration='v3_unloaded_extrinsic_v1')
    entry=calibration()['camera_models']['unloaded'][key]
    np.testing.assert_allclose(o,np.array(entry['origin_m'])+[0,0,.0325])
    np.testing.assert_allclose(r,entry['rotation'])
    assert reason=='calibrated_unloaded'
    for bad in [s|{1:1500},s|{3:1}]:
        assert camera_transform(bad,wall_camera_calibration='v3_unloaded_extrinsic_v1')[0] is None


def test_factors_decrease_with_uncertainty_range_and_low_edge_quality():
    def w(seg=SEG,f=FEATURE,cov=None):
        return confidence(seg,[0.,0.],f,np.zeros((3,3)) if cov is None else cov)['weight']
    reference=w()
    assert 0<reference<1
    assert w(SEG*3)<reference
    assert w(cov=np.diag([.1,.1,.01]))<reference
    assert w(f=FEATURE|{'sharpness':0.})==0
    assert w(f=FEATURE|{'contrast':5.})<reference
    assert w(f=FEATURE|{'body_settling':.5})==reference*.5
    assert w(np.array([[.5,0.],[1.5,0.]]))==0
    with pytest.raises(ValueError): w(cov=-np.eye(3))


def test_weighted_free_carving_and_once_per_frame_hit_precedence():
    legacy,weighted=OdomGrid('r1'),OdomGrid('r1')
    legacy.insert([0.,0.],[SEG])
    weighted_insert(weighted,[0.,0.],[SEG],[1.])
    assert legacy.export()==weighted.export()
    half=OdomGrid('r1')
    weighted_insert(half,[0.,0.],[SEG,SEG],[.2,.5])
    assert all(v==legacy.cells[k]*.5 for k,v in half.cells.items())
    assert any(v<0 for v in half.cells.values())
    hit=(10,0)
    before=half.cells[hit]
    weighted_insert(half,[0.,0.],[SEG*2],[1.])
    assert half.cells[hit]<before


@pytest.mark.parametrize('mode',['off','own_map_csm_v1','own_map_csm_v2','own_map_csm_prob_v1','own_map_rbpf_v1'])
def test_confidence_default_explicit_off_frozen_bytes(mode):
    import types
    from harness.self_wall_memory import SelfWallMemory
    from tests.test_wall_projection_guard import rec,FRONT,BACK,ORIGIN,ROT
    old=types.ModuleType('before_confidence')
    exec((Path(__file__).parent/'fixtures/self_wall_memory_before_confidence.py.txt').read_text(),old.__dict__)
    args=dict(self_map='odom_grid_v1',pose_correction=mode,wall_projection_guard='positive_depth_v1',
              self_map_options={'settle_s':None},clock=lambda:9.)
    memories=[old.SelfWallMemory('r1',**args),SelfWallMemory('r1',**args),SelfWallMemory('r1',wall_confidence='off',**args)]
    for i in range(3):
        for m in memories:
            m.command({'t':float(i),'kind':'drive','forward':.01,'turn':.01,'duration_s':.2})
            m.observe_wall(rec([FRONT,BACK],float(i),i),camera_xy=ORIGIN[:2],robot_id='r1',camera_origin=ORIGIN,camera_rotation=ROT)
        blobs=[json.dumps([m.snapshot(),m.self_map.export()]).encode() for m in memories]
        assert blobs[0]==blobs[1]==blobs[2]


def test_rbpf_weighted_ledger_graph_rebuild_and_particle_isolation():
    from harness.self_wall_memory import SelfWallMemory
    from harness.self_pose_graph import rebuild
    from tests.test_wall_projection_guard import rec,FRONT,BACK,ORIGIN,ROT
    m=SelfWallMemory('r1',self_map='odom_grid_v1',pose_correction='own_map_rbpf_v1',
        wall_projection_guard='positive_depth_v1',pose_graph='own_submap_v1',
        wall_confidence='inverse_sensor_v1',self_map_options={'settle_s':None})
    m.observe_wall(rec([FRONT,BACK],1.,1),camera_xy=ORIGIN[:2],robot_id='r1',camera_origin=ORIGIN,camera_rotation=ROT,
                   wall_features=[FEATURE,FEATURE|{'sharpness':0.}])
    grid=m.self_map
    assert len(grid.ledger[0]['insertion_weights'])==1
    assert grid._wall_features is None
    assert rebuild('r1',grid.ledger).export()['cells']==grid.export()['cells']
    before=json.dumps(grid.export())
    m.finalize_pose_graph()
    assert m._graph_view.export()['cells']==grid.export()['cells']
    assert json.dumps(grid.export())==before
    grid.weights[:]=0
    grid.weights[0]=1
    grid.resample_if_needed()
    grid.maps[0].cells[(999,999)]=1
    assert (999,999) not in grid.maps[1].cells


def test_calibrated_column_model_has_same_off_geometry():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/2026-09-26-markerless-probe'))
    import markerless_probe as mp
    servo={1:2000,3:1072,4:2400,5:1482,6:1500}
    cols=mp.column_positions(96,2)
    old=mp.column_model(servo,0.,cols)
    explicit=mp.ColumnModel(tuple(servo.items()),0.,cols,camera_transform=None)
    for name in ('origin','q0','d','alpha','beta','gamma'):
        assert getattr(old,name).tobytes()==getattr(explicit,name).tobytes()
    rigid,_=camera_transform(servo,wall_camera_calibration='v3_unloaded_extrinsic_v1')
    calibrated=mp.ColumnModel(tuple(servo.items()),0.,cols,camera_transform=rigid)
    np.testing.assert_array_equal(calibrated.origin,rigid[0])
    v=np.full(len(cols),400.)
    np.testing.assert_allclose(calibrated.rows(calibrated.t_of_row(v)),v,atol=1e-8)


def test_empty_detector_frame_is_valid_no_evidence(monkeypatch,tmp_path):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import v3_confidence_replay as replay
    import cv2
    monkeypatch.setattr(replay.base,'sha',lambda p:'ok')
    monkeypatch.setattr(cv2,'imread',lambda p:np.zeros((480,640,3),np.uint8))
    monkeypatch.setattr(replay.hfw,'detect',lambda *a,**k:{})
    monkeypatch.setattr(replay.hfw,'link_segments',lambda *a,**k:[])
    servo={1:2000,3:1072,4:2400,5:1482,6:1500}
    cm,offset,_=replay.geometry(servo,'v3_unloaded_extrinsic_v1')
    segs,features,decision=replay.detections(tmp_path,{'path':'unused.jpg','sha256':'ok','commanded_servo':servo},cm,offset,1.)
    assert segs==features==[] and decision['accepted_segments']==0
