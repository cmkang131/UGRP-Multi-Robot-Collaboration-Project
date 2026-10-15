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
