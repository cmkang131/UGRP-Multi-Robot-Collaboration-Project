import hashlib
import json
import cv2
import numpy as np
import pytest
from scripts.mapbuild1_replay import read_frame, replay, score
from scripts.score_mapbuild1 import score as map_score


def record(path,frame=0):
    image=np.zeros((480,640,3),np.uint8)
    ok,raw=cv2.imencode('.jpg',image);assert ok
    (path/'own.jpg').write_bytes(raw.tobytes())
    return dict(sequence='blank',robot_id='r1',frame_id=frame,t=float(frame)/10,rgb='own.jpg',
        sha256=hashlib.sha256(raw).hexdigest(),servo={'1':2000,'3':1100,'4':1500,'5':1900,'6':1500},
        command_delta=[0.,0.,0.],command_covariance=np.zeros((3,3)).tolist())


def test_strict_own_record_rejects_truth_path_and_corruption(tmp_path):
    row=record(tmp_path)
    assert read_frame(tmp_path,row).shape==(480,640,3)
    with pytest.raises(ValueError,match='STRICT_OWN'):
        read_frame(tmp_path,{**row,'truth_pose':[0,0,0]})
    with pytest.raises(ValueError,match='PATH_ESCAPE'):
        read_frame(tmp_path,{**row,'rgb':'../outside.jpg'})
    with pytest.raises(ValueError,match='HASH_MISMATCH'):
        read_frame(tmp_path,{**row,'sha256':'0'*64})


def test_blank_image_is_unknown_and_never_visual_tracking(tmp_path):
    manifest=dict(schema='ugrp.mapbuild1.own.v1',backend='mjwarp_render',
        frames=[record(tmp_path,i) for i in range(2)])
    rows=replay(tmp_path,manifest)
    assert rows[1]['lk']['status']=='unknown_identical_rgb'
    assert rows[1]['slam']['inliers']==0
    # Empty floor observations must not be counted as tracked bootstrap.
    metrics=score(rows,dict(frames=[dict(sequence='blank',frame_id=i,pose=[i*.1,0,0]) for i in range(2)]))
    assert all(m['tracked_n']==0 and m['pairs']==1 for m in metrics)
    assert all(m['ate_xy_m']['max']==pytest.approx(.1) for m in metrics)


def test_evaluation_requires_exact_label_coverage(tmp_path):
    rows=replay(tmp_path,dict(schema='ugrp.mapbuild1.own.v1',backend='mjwarp_render',frames=[record(tmp_path)]))
    with pytest.raises(ValueError,match='EXACT_EVALUATION'):
        score(rows,dict(frames=[]))
    with pytest.raises(ValueError,match='DUPLICATE_EVALUATION'):
        score(rows,dict(frames=[dict(sequence='blank',frame_id=0,pose=[0,0,0])]*2))


def test_loaded_camera_remains_unknown_without_truth_fallback(tmp_path):
    row=record(tmp_path);row['servo']['1']=1500
    rows=replay(tmp_path,dict(schema='ugrp.mapbuild1.own.v1',backend='mjwarp_render',frames=[row]))
    assert rows[0]['slam']['reason']=='unqualified_camera:loaded_or_unknown_load_not_qualified'
    assert rows[0]['lk']['status']=='unknown_camera:loaded_or_unknown_load_not_qualified'
    assert rows[0]['lk_pose']==[0.,0.,0.]


def test_map_unknowns_remain_omissions_and_false_occupied_is_not_coverage_success():
    base=dict(resolution_m=.1,frame='r1/start')
    truth=dict(**base,cells=[[0,0,'occupied'],[1,0,'free'],[2,0,'occupied']],wall=[[0.,0.],[.2,0.]])
    predicted=dict(**base,cells=[[0,0,'occupied'],[1,0,'occupied']],wall=[[0.,0.]])
    result=map_score(predicted,truth)
    assert result['coverage']==pytest.approx(2/3)
    assert result['unknown_truth_cells']==1
    assert (result['occupied_tp'],result['occupied_fp'],result['occupied_fn_including_unknown'])==(1,1,1)
    assert result['occupied_iou']==pytest.approx(1/3)
    assert result['geometry']['wall']['truth_to_predicted_m']['max']==pytest.approx(.2)
    empty=map_score(dict(**base,cells=[]),truth)
    assert empty['coverage']==0 and empty['occupied_fn_including_unknown']==2
    assert empty['geometry']['wall']['status']=='unobserved'
    assert empty['geometry']['wall']['truth_to_predicted_m']['p50'] is None
