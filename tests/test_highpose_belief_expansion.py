"""R2: one-shot belief expansion of the v98 HIGH provider, armed only by the arrival-rejection path (simulator-free)."""
import numpy as np

from harness import zone_pair_highpose_arrival_confirm as ac
from harness import vision_pose_source_highpose as hp
from tests.test_zone_final_pair_highpose import synthetic, MAPS, c


def _provider(tmp_path, monkeypatch):
    path, _ = synthetic(tmp_path, monkeypatch)
    dsrc = hp.build_provider(c.resolve(MAPS[0])[0], path, c.base.sha(path), seed=3)
    dsrc.init_prior((1., 0., 0.), (.1, .1, .1), source='synthetic public dock')
    return dsrc, dsrc.provider


def _stats(pf):
    return pf.px.mean(0), pf.px.std(0), pf.logw.copy()


def test_relocalization_keeps_the_belief_unless_the_arrival_path_armed_it(tmp_path, monkeypatch):
    dsrc, src = _provider(tmp_path, monkeypatch)
    pf = src.loc._pf
    assert src.runtime_contract['pf_expansion'] == {'radius': list(hp.EXPANSION_RADIUS), 'trigger': 'own arrival-view rejection only (one shot)'}
    dsrc.begin_relocalization(1.0, {})                                   # DR checkpoint / look-around style call: not armed
    assert src.lifecycle[-1]['event'] == 'begin_relocalization' and src.lifecycle[-1]['belief_preserved'] is True
    assert 'expansion_radius' not in src.lifecycle[-1]
    assert src.lifecycle[-1]['before']['particles_sha256'] == src.lifecycle[-1]['after']['particles_sha256']
    before_mean, before_std, _ = _stats(pf)
    assert ac.request_belief_expansion(dsrc) is True and src._expand_next is True      # delayed wrapper -> provider
    dsrc.begin_relocalization(2.0, {})
    row = src.lifecycle[-1]
    assert row['belief_preserved'] is False and row['expansion_radius'] == list(hp.EXPANSION_RADIUS)
    mean, std, logw = _stats(pf)
    assert np.all(logw == 0.) and src._expand_next is False
    radius = np.asarray(hp.EXPANSION_RADIUS)
    assert np.all(std > np.sqrt(before_std**2 + (radius/np.sqrt(3.))**2)*.9)       # uniform +-r adds variance r^2/3
    assert np.all(np.abs(mean - before_mean) < radius/3.)                          # expanded around the belief, not re-initialised
    assert np.all(np.abs(pf.px[:, 2]) <= np.pi + 1e-9)
    dsrc.begin_relocalization(3.0, {})                                             # one shot: the next relocalization keeps its belief
    assert 'expansion_radius' not in src.lifecycle[-1] and src.lifecycle[-1]['belief_preserved'] is True


def test_clear_disarms_a_request_that_was_never_consumed(tmp_path, monkeypatch):
    dsrc, src = _provider(tmp_path, monkeypatch)
    ac.request_belief_expansion(dsrc)
    assert src._expand_next is True
    ac.clear_belief_expansion(dsrc)
    dsrc.begin_relocalization(1.0, {})
    assert 'expansion_radius' not in src.lifecycle[-1]


def test_rejected_arrival_expands_the_real_provider_belief_through_the_real_delayed_pose_source(tmp_path, monkeypatch):
    """The production call site (ViewConfirmedArrival._arrive) with the real DelayedPoseSource + HighPoseSource: GuardedPairApproach._relocalize
    is ``shared_pose.begin_relocalization(now, servo)``; a rejected arrival expands once, a confirmed arrival never."""
    import cv2
    from tests import test_highpose_arrival_confirm as t

    class RealPoseBase(t.Base):
        def _relocalize(self, now):
            self.relocalized += 1
            self._shared_pose.begin_relocalization(now, self.servo)
            return [{'kind': 'look'}]

    def drive(name):
        dsrc, src = _provider(tmp_path, monkeypatch)
        drv = ac.adopt(RealPoseBase)()
        drv._shared_pose = dsrc
        drv.arrival_view = t.view('r1')
        drv.on_command({'t': 10., 'kind': 'arm', 'servo_id': 3, 'pulse': 740})
        drv.observe(20., cv2.cvtColor(t.frame(name), cv2.COLOR_BGR2RGB))
        return drv, src

    drv, src = drive('false_arrival_r1_t118p50')
    std0 = src.loc._pf.px.std(0).copy()
    assert drv._arrive(20.2) == [{'kind': 'look'}] and drv.relocalized == 1
    row = src.lifecycle[-1]
    assert row['event'] == 'begin_relocalization' and row['belief_preserved'] is False
    assert row['expansion_radius'] == list(hp.EXPANSION_RADIUS) and src._expand_next is False
    assert np.all(src.loc._pf.px.std(0) > std0)
    drv, src = drive('dock_r1_t10p20')
    assert drv._arrive(20.2) == [{'kind': 'arrived'}] and drv.relocalized == 0
    assert all(r['event'] != 'begin_relocalization' for r in src.lifecycle) and src._expand_next is False
