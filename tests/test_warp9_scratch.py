"""No physics/device calls: repeated workspace contents and guarded source."""
from types import SimpleNamespace
import numpy as np
import pytest
from scripts.warp9_scratch import rewrite


types=SimpleNamespace(vec5=object())
class Arrays:
    def empty(self,shape,dtype):
        return np.empty((*shape,5) if dtype is types.vec5 else shape)
wp=Arrays()


def noslip(m,d):
    noslip_L = wp.empty((d.nworld, m.nv, m.nv), dtype=float)
    noslip_Y = wp.empty((d.nworld, d.njmax, m.nv), dtype=float)
    noslip_A = wp.empty((d.nworld, d.njmax), dtype=types.vec5)
    for w in range(d.nworld):
        if not d.nefc[w]:continue
        noslip_L[w]=d.input[w]
        noslip_Y[w,:d.nefc[w]]=noslip_L[w].sum(axis=0)
        noslip_A[w,:d.nefc[w]]=noslip_Y[w,:d.nefc[w]].sum()
        d.out[w]=noslip_A[w,:d.nefc[w]].sum()


def test_persistent_scratch_preserves_active_rows_after_changed_contents():
    m=SimpleNamespace(nv=3)
    buffers={};calls=[]
    def workspace(m,d):
        calls.append(1)
        if not buffers:
            buffers.update(noslip_L=wp.empty((d.nworld,m.nv,m.nv),float),
                noslip_Y=wp.empty((d.nworld,d.njmax,m.nv),float),
                noslip_A=wp.empty((d.nworld,d.njmax),types.vec5))
        return buffers
    candidate,audit=rewrite(noslip,workspace)
    for nefc,values in (([4,2],[2.,9.]),([1,0],[-4.,1.]),([0,4],[3.,-2.])):
        args=dict(nworld=2,njmax=4,nefc=nefc,input=np.asarray(values)[:,None,None]*np.ones((2,3,3)))
        a,b=SimpleNamespace(**args,out=np.zeros(2)),SimpleNamespace(**args,out=np.zeros(2))
        noslip(m,a);candidate(m,b)
        np.testing.assert_array_equal(a.out,b.out)
    assert len(calls)==9
    assert audit['allocation_edits']==dict(noslip_L=1,noslip_Y=1,noslip_A=1)


def test_changed_upstream_allocation_fails_closed():
    def changed(m,d):
        noslip_L=wp.empty((d.nworld,m.nv,m.nv+1),dtype=float)
    with pytest.raises(ValueError,match='allocation changed'):
        rewrite(changed,lambda m,d:{})
