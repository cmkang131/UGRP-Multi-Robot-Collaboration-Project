"""Content-key regression: in-place PF changes must invalidate pure summaries."""
import copy
import numpy as np

from harness import zone_s3_exact_cache as cache
from harness.zone_solo_cyan_augmented_start import belief_report
from harness.zone_solo_cyan_best_cluster import extract, connected_labels


def test_off_is_identity():
    own=object()
    assert cache.attach(own) is own


def test_global_memo_preserves_results_invalidates_weights_and_mutations():
    px=np.array([[0.,0.,0.],[.1,.1,.1],[4.,0.,2.9]])
    w=np.array([.3,.3,.4]);audit=dict(hits=0,misses=0)
    fast=cache.memo_summary(belief_report,audit)
    for _ in range(2):
        expected=belief_report(px,w);actual=fast(px,w)
        for a,b in zip(actual[:2],expected[:2]):np.testing.assert_array_equal(a,b)
        assert actual[2]==expected[2]
    assert audit==dict(hits=1,misses=1)
    actual[0][:]=100  # callers cannot poison the cache
    px[0,0]=.5;w[:]=[.4,.3,.3]
    actual=fast(px,w);expected=belief_report(px,w)
    for a,b in zip(actual[:2],expected[:2]):np.testing.assert_array_equal(a,b)
    assert actual[2]==expected[2] and audit['misses']==2


def test_cluster_memo_retains_fresh_time_health_and_pan_offset():
    px=np.array([[0.,0.,0.],[.1,.1,.1],[4.,0.,2.9]])
    w=np.array([.3,.3,.4]);labels=connected_labels(px)
    audit=dict(hits=0,misses=0);fast=cache.memo_extract(extract,audit)
    for old in [dict(t=1.,initialized=True,pan_yaw_offset=.1),
                dict(t=2.,initialized=True,fix_age_s=1.,pan_yaw_offset=.1),
                dict(t=3.,initialized=True,pan_yaw_offset=.3)]:
        assert fast(px,w,labels,old)==extract(px,w,labels,old)
    assert audit==dict(hits=1,misses=2)
    w[:]=[.1,.1,.8]
    assert fast(px,w,labels,old)==extract(px,w,labels,old)
    assert audit['misses']==3
