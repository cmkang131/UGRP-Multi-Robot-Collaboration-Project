"""Evaluation interventions must isolate baseline and preserve frozen geometry."""
import copy
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from harness import wall_parallax as p

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('baseline_diagnostic',ROOT/
    'experiments/2026-10-07-wall-parallax-baseline/code/diagnose_baseline.py')
d=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)
K=np.array([[400.,0.,320.],[0.,400.,240.],[0.,0.,1.]])
R=np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])
ORIGIN=np.array([.08,.02,.3])


def synthetic():
    histories=[]
    truth={}
    for i in range(4):
        actual=np.array([0.,i*.08,0.])
        centre,rot=p.camera(actual,ORIGIN,R)
        pixel=K@rot.T@(np.array([1.5,.3,.12])-centre)
        command=actual.copy()
        command[:2]*=2.2
        histories.append(dict(frame_id=i,pose=command,cov=np.eye(3)*i*.001,uv=pixel[:2]/pixel[2]))
        truth[i]=actual[:2]
    return histories,truth


@pytest.mark.parametrize('mode',d.MODES)
def test_known_baseline_recovers_metric_depth_without_altering_observations(mode):
    history,truth=synthetic()
    saved=copy.deepcopy(history)
    wrong,reason=p.triangulate(history,ORIGIN,R,K)
    assert reason=='accepted' and abs(wrong['xyz'][0]-1.5)>.5
    corrected=d.baseline_history(history,truth,ORIGIN,R,mode)
    value,reason=p.triangulate(corrected,ORIGIN,R,K)
    assert reason=='accepted'
    np.testing.assert_allclose(value['xyz'],[1.5,.06,.12],atol=1e-10)
    for before,after,original in zip(history,corrected,saved):
        for field in ('uv','cov'):
            np.testing.assert_array_equal(before[field],after[field])
        assert before['pose'][2]==after['pose'][2]
        np.testing.assert_array_equal(before['pose'],original['pose'])


def test_length_only_preserves_current_camera_and_scales_offsets_with_lever_arm():
    history,truth=synthetic()
    for i,row in enumerate(history):row['pose'][2]=i*.04
    modified=d.baseline_history(history,truth,ORIGIN,R,'eval_gt_length_only')
    centres=np.array([p.camera(h['pose'],ORIGIN,R)[0] for h in history])
    new=np.array([p.camera(h['pose'],ORIGIN,R)[0] for h in modified])
    np.testing.assert_allclose(new[-1],centres[-1],atol=1e-14)
    np.testing.assert_allclose(new-new[-1],(centres-centres[-1])/2.2,atol=1e-14)
    for a,b in zip(history,modified):assert a['pose'][2]==b['pose'][2]


def test_zero_baseline_is_not_manufactured_and_own_option_rejects_oracle_name():
    history,truth=synthetic()
    for row in history:row['pose'][:2]=0.
    same=d.baseline_history(history,truth,ORIGIN,R,'eval_gt_length_only')
    for a,b in zip(history,same):np.testing.assert_array_equal(a['pose'],b['pose'])
    with pytest.raises(ValueError,match='UNKNOWN_WALL_DETECTOR'):
        p.ParallaxWallDetector('r3',intrinsic=K,wall_detector='eval_gt_translation_only')
    assert p.detect(b'old\x00bytes',state=object())==b'old\x00bytes'


def test_no_candidate_retains_recall_denominator_and_never_claims_operational_success(monkeypatch):
    monkeypatch.setattr(d.frozen.metric,'project',lambda uv,*a:(np.zeros((len(uv),2)),np.ones(len(uv)),np.ones(len(uv),bool)))
    frame=dict(frame_id=1,t=1.,origin=ORIGIN.tolist(),rotation=R.tolist(),candidate=[],
        baseline=[dict(uv=[100.,50.],xy=[0.,0.],range_m=1.)])
    report,_=d.summarize([frame],{1.:np.zeros(3)},np.array([[1.,0.,1.,1.]]),
        {1:dict(polylines=[[[0,50],[639,50]]],ignore=[])},True)
    result=report['reports']['candidate']
    assert result['points']['precision'] is None and result['points']['median'] is None
    assert result['annotated']['all']['positive']==96 and result['annotated']['all']['recall']==0.
    assert not report['own_only'] and not report['adopted'] and not report['operational_gate_passed']


def test_frozen_detector_and_original_thresholds_unchanged():
    d.source.verify()


def test_correlated_uncertainty_is_preserved_when_mean_baseline_changes():
    history,truth=synthetic()
    common=np.diag([.01,.01,.001])
    for row in history:
        transition=np.eye(3)
        transition[:2,2]=[-row['pose'][1],row['pose'][0]]
        row['cov']=transition@common@transition.T
    modified=d.baseline_history(history,truth,ORIGIN,R,'eval_gt_translation_only')
    original=p.joint_pose_covariance
    with pytest.raises(ValueError,match='INCONSISTENT_COMMAND_POSE_COVARIANCE'):
        p.triangulate(modified,ORIGIN,R,K)
    result,reason=d.triangulate_with_original_joint(history,modified,ORIGIN,R,K)
    assert reason=='accepted' and p.joint_pose_covariance is original
    np.testing.assert_allclose(result['xyz'],[1.5,.06,.12],atol=1e-10)
    assert np.linalg.eigvalsh(result['covariance']).min()>-1e-10
    # No intervention must be exactly identical, including propagated covariance.
    assert d.triangulate_with_original_joint(history,history,ORIGIN,R,K)==p.triangulate(history,ORIGIN,R,K)
