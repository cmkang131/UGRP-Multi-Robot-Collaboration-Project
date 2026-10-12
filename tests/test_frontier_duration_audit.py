"""The post-run audit exposes the upstream size filter without changing control."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from harness.active_wall_recovery import ExplorationRecoveryNavigator

@pytest.mark.parametrize('half_size,expected_native',[(0,0),(3,1)])
def test_audit_clusters_match_upstream_after_original_size_filter(tmp_path,half_size,expected_native):
    path=Path(__file__).resolve().parents[1]/'experiments/2026-10-08-frontier-duration/code/exhaustion.py'
    spec=importlib.util.spec_from_file_location('duration_audit',path)
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    audit.OUT=tmp_path
    raw=np.full((41,41),255,np.uint8)
    raw[20-half_size:21+half_size,20-half_size:21+half_size]=0
    pose=np.array([1.025,1.025,0.]);origin=np.zeros(2)
    all_clusters=audit.upstream_clusters(raw,origin,.05,pose)
    native=ExplorationRecoveryNavigator().core.frontiers(raw,origin,.05,pose[:2])
    assert len(all_clusters)==1
    assert len(native)==expected_native
    np.testing.assert_array_equal(all_clusters[all_clusters[:,5]*.05>=.75],native)
