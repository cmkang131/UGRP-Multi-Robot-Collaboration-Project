"""Small nonphysics regressions for peer deadlines and visible motion input."""
from types import SimpleNamespace
from copy import deepcopy
import pytest

from harness.grasp_act_peer_rendezvous import MODE,PeerRendezvous,RendezvousTeacherMixin


def test_observed_peer_velocity_uses_only_current_own_camera_and_issued_frame():
    rv=PeerRendezvous(MODE)
    world={'robots':{'r1':{'pose':[0,0,0]},'r2':{'pose':[1,0,0]}},
        'visibility':{'r1':{'peers':['r2']}}}
    rv.observe(world,'r1',1.)
    world['robots']['r2']['pose']=[1.1,.2,0];rv.observe(world,'r1',2.)
    assert rv.velocity['r2']==pytest.approx((.1,.2))
    world['visibility']['r1']['peers']=[];rv.observe(world,'r1',3.)
    assert rv.velocity=={}  # Remembered motion cannot renew a fresh observation.


class Base:
    def _step(self,world,now,*,permit_pick):
        self.called=True
        self.outcome='approach_blocked_handoff' if self.peer_wait_since is not None and now-self.peer_wait_since>=12-1e-8 else None
        return 'command',False


def teacher(mode):
    class T(RendezvousTeacherMixin,Base):pass
    t=T();t.rid='r1';t.peer_wait_since=8.9;t.outcome=None;t.called=False
    t.rendezvous=SimpleNamespace(mode=mode,observe=lambda *a:None)
    def retry(*a):t.peer_wait_since=None;t.outcome=None
    t.rendezvous.retry=retry
    return t


def test_deadline_replans_before_the_legacy_terminal_return():
    t=teacher(MODE)
    assert t._step({},20.9,permit_pick=False)==('command',False)
    assert t.called and t.outcome is None and t.peer_wait_since is None


def test_toggle_off_preserves_the_saved_terminal_behavior():
    t=teacher('off');t._step({},20.9,permit_pick=False)
    assert t.outcome=='approach_blocked_handoff'


def test_hidden_target_retry_does_not_query_cargo_geometry():
    rv=PeerRendezvous(MODE)
    class T:
        rid='r1';folded_ready=True;peer_wait_since=1.;peer_wait_ids={'r2'}
        reobserver=SimpleNamespace(active=None)
        peer_trigger=SimpleNamespace(reset=lambda:None)
        peer_progress=SimpleNamespace(reset=lambda:None)
        progress=SimpleNamespace(reset=lambda:None)
        def _geometry(self,w):raise AssertionError('hidden cargo geometry read')
    t=T();world={'beam':None,'visibility':{'r1':{'visible_probes':0}}}
    rv.retry(t,world,13.,'encounter_deadline_replan')
    assert t.peer_wait_since is None and t.outcome is None
    assert rv.events[0]['reason_category']=='target_not_visible'
