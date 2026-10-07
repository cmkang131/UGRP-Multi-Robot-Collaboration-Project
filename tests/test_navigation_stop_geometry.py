"""Evaluation-only geometry certificates and preservation of navigation semantics."""
import importlib.util
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('stop_audit',ROOT/'experiments/2026-10-07-mapfree-stop-geometry/code/audit.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


def test_disk_distance_and_continuous_certificate():
    rects=[dict(center=[0.,0.],half=[.1,.2],yaw=0.)]
    np.testing.assert_allclose(a.disk_margin([[.3,0],[0,0]],rects,[-2,2,-2,2],.05),[.15,-.15])
    cert=a.path_certificate([[.3,-1],[.3,1]],rects,[-2,2,-2,2],.05)
    assert .148<cert['continuous_clearance_lower_m']<=.15
    assert a.path_certificate([[0,-1],[0,1]],rects,[-2,2,-2,2],.05)['continuous_clearance_lower_m']<0


def test_route_witness_and_impossibility_not_overclaimed():
    rects=[dict(center=[0.,.8],half=[.1,.55],yaw=0.),dict(center=[0.,-.8],half=[.1,.55],yaw=0.)]
    w=a.witness([-.6,0],[.6,0],rects,[-1,1,-1.4,1.4],a.HALF)
    assert w['found'] and w['continuous_clearance_lower_m']>0
    assert a.rectangle_contacts([0,0,0],rects,[-1,1,-1.4,1.4],a.HALF)==[]
    bad=a.witness([0,.2],[.6,0],rects,[-1,1,-1.4,1.4],a.HALF)
    assert not bad['found'] and 'not_impossibility_proof' in bad['reason']


def test_inflation_outer_radius_is_soft_not_required_door_width():
    from harness.public_navigation.costmap import Costmap,HALF
    raw=np.zeros((30,30),np.uint8);raw[10,:]=254
    cm=Costmap(raw,[-1.5,-1.5])
    assert 0<cm.costs[13,15]<253
    assert cm.costs[11,15]==253
    assert 2*np.linalg.norm(HALF)<.5
    assert cm.pose_clear([.05,-.05,0])
