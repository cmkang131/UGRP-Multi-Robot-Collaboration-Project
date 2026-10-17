"""Diagnostic gate and gauge isolation; no physics, renderer or truth input."""
import copy
import numpy as np
import pytest
from harness.mapbuild10_diagnostic import DiagnosticCorrection
from tests.test_mapbuild10 import STATIC,CAL,REQ,ZONE


def test_unqualified_diagnostic_is_explicit_and_closed_until_distribution_ready():
    with pytest.raises(ValueError,match='EXPLICIT'):
        DiagnosticCorrection(STATIC,CAL,REQ,ZONE)
    d=DiagnosticCorrection(STATIC,CAL,REQ,ZONE,enabled=True)
    assert not d.navigation_ready
    assert d.initialize_static()['status']=='rejected'
    original=d.amcl.field.dist.copy()
    p,e=d.step(0.,0,[.1,0,0],np.eye(3)*.01,dict(status='unavailable'),
        dict(segments=[],columns=[]),servo={'6':1500})
    np.testing.assert_allclose(p,[.1,0,0])
    assert not e['accepted'] and not e['diagnostic_navigation_pose_used']
    assert not e['production_qualified'] and e['adopted_pose'] is None
    np.testing.assert_array_equal(original,d.amcl.field.dist)


def test_static_gauge_is_fixed_and_only_experimental_local_pose_tracks_new_proposal():
    d=DiagnosticCorrection(STATIC,CAL,REQ,ZONE,enabled=True)
    # Inject a synthetic belief, not a real experiment success.
    d.amcl.odom=np.array([.1,0,0]);d.amcl.sensor_odom=d.amcl.odom.copy()
    d.amcl.current=dict(candidate_pose=[.3,.2,.1],converged=True)
    assert d.initialize_static()['status']=='accepted'
    gauge=d.static_from_own.copy()
    d.amcl.current['candidate_pose']=[.4,.2,.1]
    d.initialize_static()
    np.testing.assert_array_equal(d.static_from_own,gauge)
    assert not np.allclose(d.pose,d.amcl.odom)
    assert d.amcl.current.get('runtime_qualified',False) is False
