"""Content-key regression: in-place PF changes must invalidate pure summaries."""
import copy
import numpy as np
import pytest

from harness import zone_s3_exact_cache as cache
from harness.zone_solo_cyan_augmented_start import belief_report
from harness.zone_solo_cyan_best_cluster import extract, connected_labels


def test_off_is_identity():
    own=object()
    assert cache.attach(own) is own


@pytest.mark.parametrize('content_key',[cache.key, cache.ArrayRevision()])
def test_global_memo_preserves_results_invalidates_weights_and_mutations(content_key):
    px=np.array([[0.,0.,0.],[.1,.1,.1],[4.,0.,2.9]])
    w=np.array([.3,.3,.4]);audit=dict(hits=0,misses=0)
    fast=cache.memo_summary(belief_report,audit,content_key)
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


@pytest.mark.parametrize('content_key',[cache.key, cache.ArrayRevision()])
def test_cluster_memo_retains_fresh_time_health_and_pan_offset(content_key):
    px=np.array([[0.,0.,0.],[.1,.1,.1],[4.,0.,2.9]])
    w=np.array([.3,.3,.4]);labels=connected_labels(px)
    audit=dict(hits=0,misses=0);fast=cache.memo_extract(extract,audit,content_key)
    for old in [dict(t=1.,initialized=True,pan_yaw_offset=.1),
                dict(t=2.,initialized=True,fix_age_s=1.,pan_yaw_offset=.1),
                dict(t=3.,initialized=True,pan_yaw_offset=.3)]:
        assert fast(px,w,labels,old)==extract(px,w,labels,old)
    assert audit==dict(hits=1,misses=2)
    w[:]=[.1,.1,.8]
    assert fast(px,w,labels,old)==extract(px,w,labels,old)
    assert audit['misses']==3


def test_revision_tracks_bits_replacement_shapes_and_labels_between_frames():
    key=cache.ArrayRevision(); px=np.zeros((2,3)); w=np.ones(2)
    a=key(px,w)
    assert key(px.copy(),w.copy())==a
    px[0,0]=-0.
    b=key(px,w);assert b!=a
    assert key(px,w)==b
    px[0,0]=1.
    assert key(px,w)!=b
    assert key(px[:,::2],w)==key(px[:,::2].copy(),w.copy())
    assert key(px.reshape(3,2),w)!=key(px,w)


def test_buffered_jsonl_preserves_bytes_and_flushes_before_referee(tmp_path, monkeypatch):
    from sim.s3_buffered_io import PhysicsBackend, Previous, OPTION
    fast=PhysicsBackend.__new__(PhysicsBackend)
    fast.out=tmp_path/'fast';fast.streams={};fast.io_mode=OPTION;fast.host_timing={}
    old=Previous.__new__(Previous);old.out=tmp_path/'old';old.streams={}
    rows=[dict(t=i/20,text='로봇',items=[None,True,float(i)]) for i in range(201)]
    for row in rows:
        fast._append('eval_only/referee_truth.jsonl',row)
        old._append('eval_only/referee_truth.jsonl',row)
    def evaluate(self,*a,**k):
        return (self.out/'eval_only/referee_truth.jsonl').read_bytes()
    monkeypatch.setattr(Previous,'evaluate',evaluate)
    assert fast.evaluate([], {})==evaluate(old)
    assert fast.host_timing['jsonl_append']['calls']==len(rows)
    for obj in (fast,old):
        for stream in obj.streams.values():stream.close()
