"""Nonphysics regressions for peer-TTL-independent destination reservations."""
from copy import deepcopy
from types import ModuleType
import sys
import pytest

from harness.beampair_peer_yield import MODE, PeerYieldMixin, reserved_teal_stance


def world(n=15):
    return dict(t=3., beam=dict(pose=[0., 0., 0.], ends=dict(teal=[-.27, 0., .02])),
        robots=dict(r1=dict(pose=[-.5, .1, 0.])),
        visibility=dict(r1=dict(visible_probes=n)))


def teacher(monkeypatch, mode=MODE):
    mod = ModuleType('sim.grasp_act_teacher');mod.STATION_M=.203
    monkeypatch.setitem(sys.modules, mod.__name__, mod)
    class Base:
        cs=(.13, [(9.,9.,.17)], [])
        def _constraints(self,w):return self.cs
        def diagnostic(self):return dict(original=True)
    class T(PeerYieldMixin,Base):pass
    t=T();t.rid='r1';t.end='blue';t.folded_ready=True;t.phase='approach'
    t.peer_yield=mode;t.peer_yield_log=[]
    return t


def test_default_off_returns_the_exact_original_constraints(monkeypatch):
    t=teacher(monkeypatch,'off')
    assert t._constraints(world()) is t.cs
    assert t.peer_yield_log==[]


def test_reservation_survives_missing_dynamic_peer_but_never_mutates_inputs(monkeypatch):
    t=teacher(monkeypatch);w=world();before=deepcopy(w)
    radius,discs,rects=t._constraints(w)
    assert discs[-1]==pytest.approx((-.473,0.,.21))
    assert radius+discs[-1][2]==pytest.approx(.34)
    assert w==before and len(t.cs[1])==1
    t._constraints(w)
    assert len(t.peer_yield_log)==1 and t.peer_yield_log[0]['blocked']
    assert t.peer_yield_log[0]['blocked_object']=='reserved:teal_stance'


def test_hidden_band_and_held_phase_do_not_read_beam_geometry(monkeypatch):
    t=teacher(monkeypatch)
    class Hidden(dict):
        def __getitem__(self,key):raise AssertionError('hidden beam geometry')
    w=world(n=4);w['beam']=Hidden()
    assert t._constraints(w) is t.cs
    w['visibility']['r1']['visible_probes']=15;t.phase='pick'
    assert t._constraints(w) is t.cs
    w['beam']=None;t.phase='approach'
    assert t._constraints(w) is t.cs


def test_teal_leader_unchanged_and_rotation_covariant(monkeypatch):
    t=teacher(monkeypatch);t.end='teal'
    assert t._constraints(world()) is t.cs
    w=world()
    import math
    w['beam']['pose']=[1.,2.,math.pi/2];w['beam']['ends']['teal']=[1.,1.73,.02]
    assert reserved_teal_stance(w,'r1','blue',False,.203)==pytest.approx((1.,1.527,.17))


def queue_fixture(tmp_path,monkeypatch):
    import json
    import scripts.queue_beampair7 as q
    source='a'*40
    plan=(q.ROOT/q.PLAN).read_bytes()
    monkeypatch.setattr(q.subprocess,'check_output',lambda args,**kw:source+'\n' if args[1]=='rev-parse' else plan)
    table=tmp_path/'rejection_table.json';table.write_text(json.dumps(dict(source_sha=source)))
    proof=dict(source_sha=source,N=5,n=5,runs=[dict(seed=s,adapter_sha=source,
        peer_yield=MODE,strict_success=True,visible_eligible=True,held_object_hidden_v1=True,
        audit=dict(enabled=True,invisible_measurements=0,held_world_reads=0)) for s in q.SHORT])
    evidence=tmp_path/'summary.json';evidence.write_text(json.dumps(proof))
    return q,source,table,evidence,proof


def test_gate_requires_existing_funnel_and_pins_sentinel_first(tmp_path,monkeypatch):
    q,source,table,evidence,proof=queue_fixture(tmp_path,monkeypatch)
    value=q.build(source,'gate',table,evidence)
    assert value['status']=='APPROVED_PINNED' and value['max_parallel']==16
    assert value['review_detail']=='REVIEW_SKIPPED_BY_USER (10/15 run-first rule)'
    assert len(value['runs'])==40 and value['runs'][0]['seed']==8318711
    table.unlink()
    with pytest.raises(ValueError,match='rejection_table'):q.build(source,'gate',table,evidence)


@pytest.mark.parametrize('corrupt',('strict_success','held_world_reads'))
def test_summary_count_cannot_override_failed_or_forbidden_raw_row(tmp_path,monkeypatch,corrupt):
    import json
    q,source,table,evidence,proof=queue_fixture(tmp_path,monkeypatch)
    if corrupt=='strict_success':proof['runs'][0]['strict_success']=False
    else:proof['runs'][0]['audit']['held_world_reads']=1
    evidence.write_text(json.dumps(proof))
    with pytest.raises(ValueError,match='five exact-source'):q.build(source,'gate',table,evidence)


def test_deep_reserved_start_gets_a_checked_connector_beyond_old_20cm_limit():
    from harness.beampair_peer_yield import ReservationNavigation
    from types import SimpleNamespace
    import math
    class Native:
        def free(self,p,ds,rs,r):return all(math.dist(p,d[:2])>=d[2]+r for d in ds)
        def segment_free(self,a,b,ds,rs,r):
            dx,dy=b[0]-a[0],b[1]-a[1];norm=dx*dx+dy*dy
            for x,y,z in ds:
                initial=math.dist(a,(x,y));dot=(a[0]-x)*dx+(a[1]-y)*dy
                if initial<z+r and dot<0:return False
                u=max(0,min(1,-dot/norm)) if norm else 0
                if math.hypot(a[0]+u*dx-x,a[1]+u*dy-y)<min(initial,z+r)-1e-10:return False
            return True
        def plan_path(self,a,b,bounds,ds,*,rects,radius):
            if not self.free(a,ds,rects,radius):return None
            return [a,b] if self.segment_free(a,b,ds,rects,radius) else None
    t=SimpleNamespace(rid='r1',peer_yield_failed_anchors=set(),peer_yield_connector_log=[])
    w=dict(t=6.,robots=dict(r1=dict(pose=[.105,0.,0.])),objects={},visibility=dict(r1=dict(observations={})))
    disc=(0.,0.,.21);ds=[(9.,9.,.02)]*5+[disc];nav=Native()
    proxy=ReservationNavigation(nav,t,w,disc,(.13,ds,[]))
    path=proxy.plan_path((.105,0.),(1.,0.),(-20,20,-20,20),ds,rects=[],radius=.13)
    assert path and math.dist(path[0],path[1])>.2
    assert nav.free(path[1],ds,[],.13) and nav.segment_free(path[0],path[1],ds,[],.13)
    assert t.peer_yield_connector_log[-1]['grid_population_N']<1000
    assert all(c['reason_category'] and c['blocked_object'] for c in t.peer_yield_connector_log[-1]['candidates'])
    # Put a real obstacle across the formerly selected outward connector.
    # The new graph connection must go around it, without dropping that disc.
    blocked=[(.3,0.,.02),*ds[1:]]
    proxy=ReservationNavigation(nav,t,w,disc,(.13,blocked,[]))
    path=proxy.plan_path((.105,0.),(1.,1.),(-20,20,-20,20),blocked,rects=[],radius=.13)
    if path is None:
        assert len(t.peer_yield_failed_anchors)==1
        path=proxy.plan_path((.105,0.),(1.,1.),(-20,20,-20,20),blocked,rects=[],radius=.13)
    assert path and path[1]!=(.35,0.)
    assert all(nav.segment_free(a,b,blocked,[],.13) for a,b in zip(path,path[1:]))
