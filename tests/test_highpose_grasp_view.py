"""v98: the grasp-time own grip view is LOG-ONLY (no simulator, no renderer, no model).

The floor grasp pose leaves the beam outside the masterpi_v3 camera view, so the grip view cannot gate the
close or confirm the grasp there. Readiness comes from own command history and the fixed-enum close barrier;
the view values are written to the grip monitor (evaluation output) with ``applied=False``.
"""
import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import zone_pair_grasp as grasp
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_grip as grip
from harness import zone_pair_highpose_runtime as rt
from harness.m2_provider_adapter import ProviderM2DoorStudent
from harness.zone_final_pair_skill import V3Controller
from scripts import run_m2_pair as m2

ROOT = Path(__file__).resolve().parents[1]
OPEN, CLOSED = m2.study.OPEN, m2.study.CLOSED
UNSEEN = {'seen': False, 'dark_fraction': .91, 'top_beam_fraction': 0., 'bottom_beam_fraction': 0.}


def representative_class():
    # zone_pair_executor.m2_controller: RoutedM2(PairGraspRelook, ProviderM2DoorStudent), then V3Controller.
    routed = type('RoutedM2', (grasp.PairGraspRelook, ProviderM2DoorStudent), {})
    return rt.controller_class(type('FinalV3PairController', (V3Controller, routed), {}))


def test_routed_controller_bases_are_the_ones_the_representative_class_uses():
    from harness import zone_pair_executor as pair
    source = inspect.getsource(pair.m2_controller)
    assert re.search(r'class RoutedM2\(PairGraspRelook, ProviderM2DoorStudent\):', source)
    assert "version='v3'" in source


def test_log_only_grasp_adapter_sits_between_the_issued_close_check_and_the_legacy_grip_check():
    mro = representative_class().__mro__
    i_high, i_relook = mro.index(rt.HighController), mro.index(grasp.PairGraspRelook)
    i_adapter, i_m2 = mro.index(rt.GraspViewLogOnly), mro.index(m2.M2DoorStudent)
    assert i_high < i_relook < i_adapter < i_m2
    # Nothing between the parent issued-close check and the adapter defines _grasp, so the parent's
    # super()._grasp reaches the adapter, never M2DoorStudent._grasp (GRIP_NOT_SEEN).
    assert not [k for k in mro[i_relook+1:i_adapter] if '_grasp' in vars(k)]
    assert '_wait_close' in vars(rt.HighController)


class Fake:
    """Duck-typed controller state for one robot at the grasp pose (own issued servo history only)."""
    def __init__(self, *, servo_open=True, pose_ready=True, phase='GO'):
        self.rid, self.version, self.state, self.state_t = 'r1', 'v3', 'wait_close', 10.
        self.policy = SimpleNamespace(beam_relative=False, own_image_ob=False)
        self.pregrasp_done, self.pose_ready = True, pose_ready
        self.grasp_pose = {1: OPEN, 3: 2400, 4: 1482}
        servo = {**self.grasp_pose, 1: OPEN if servo_open else CLOSED}
        self.port = SimpleNamespace(own=SimpleNamespace(servo=servo,
                                                        last_report=SimpleNamespace(last_fix_t=9.9, t_est=10.)))
        self.obs = {'image': 'jpeg', 'frame_id': 7, 'sim_time': 10.}
        self.phase, self.logs, self.monitor, self.reports, self.queued = phase, [], [], [], []
        self.failed = self.claims = None
        self.claims = {}
        self.arm = SimpleNamespace(queue=lambda pose, at, **k: self.queued.append((pose, at)))

    def look(self, now): return self.obs
    def _grasp_pose_ready(self, now): return self.pose_ready
    def _grasp_pose_checks(self, now): return {'fix': self.pose_ready}
    def preclose_check(self, now, obs): return True
    def report(self, key, obs, now, ready=True, reason=''): self.reports.append((key, ready, reason))
    def log(self, rid, kind, now, **values): self.logs.append((kind, values))
    def _monitor(self, kind, now, **values): self.monitor.append((kind, values))
    def sync_for(self, name):
        return SimpleNamespace(authorize=lambda now: {'phase': self.phase, 'go_at_s': now+.1})
    def set(self, state, now, **detail): self.state = state
    def fail(self, reason, now): self.state, self.failed = 'failed', reason


@pytest.fixture
def unseen(monkeypatch):
    monkeypatch.setattr(m2, 'grip_view_m2', lambda image: dict(UNSEEN))
    monkeypatch.setattr(grasp, 'valid_frame', lambda obs, rid, now: True)
    monkeypatch.setattr(m2.ob2, 'grip_view', lambda image: {'dark_fraction': .91})
    monkeypatch.setattr(m2.lv3, 'co_motion_signature', lambda image: 'signature')


def test_close_goes_ahead_with_an_unseen_grip_view_and_logs_it_unapplied(unseen):
    legacy, new = Fake(), Fake()
    grasp.PairGraspRelook._wait_close(legacy, 10.5, True)
    assert legacy.failed == 'PREGRASP_NOT_READY'              # v96: the unseen view blocked the close
    rt.HighController._wait_close(new, 10.5, True)
    assert new.failed is None and new.state == 'grasp' and new.queued == [({1: CLOSED}, 10.6)]
    assert new.monitor == [('close_grip_view', {'frame_id': 7, 'applied': False, **UNSEEN})]
    assert new.reports[-1][:2] == ('close', True) and 'log-only' in new.reports[-1][2]


@pytest.mark.parametrize('kwargs, reason', [({'pose_ready': False}, 'PREGRASP_NOT_READY'),
                                            ({'servo_open': False}, 'PREGRASP_NOT_READY'),
                                            ({'phase': 'ABORT'}, 'BARRIER_CLOSE_ABORT')])
def test_every_other_close_term_still_applies(unseen, kwargs, reason):
    ctl = Fake(**kwargs)
    rt.HighController._wait_close(ctl, 10.5, True)
    assert ctl.failed == reason and ctl.queued == []


def test_close_waits_for_the_barrier_and_times_out_as_before(unseen):
    ctl = Fake(phase='WAIT')
    rt.HighController._wait_close(ctl, 10.5, True)
    assert ctl.state == 'wait_close' and ctl.failed is None
    rt.HighController._wait_close(ctl, 10.+grasp.CLOSE_WAIT_S+.1, True)
    assert ctl.failed == 'BARRIER_CLOSE_TIMEOUT'


def test_post_close_grip_view_is_logged_not_applied(unseen):
    legacy, new = Fake(), Fake()
    m2.M2DoorStudent._grasp(legacy, 11., True)
    assert legacy.failed == 'GRIP_NOT_SEEN'                    # v96: legacy post-close check
    rt.GraspViewLogOnly._grasp(new, 11., True)
    assert new.failed is None and new.state == 'wait_lift'
    assert new.anchor == 'signature' and new.anchor_kind == 'co_motion_v3'
    assert new.claims['gripped']['grip_view_applied'] is False
    assert new.claims['gripped']['grip_view_m2'] == UNSEEN
    assert ('grip_view', {'dark_fraction': .91, 'm2': UNSEEN, 'applied': False}) in new.logs
    assert new.monitor == [('grasp_grip_view', {'frame_id': 7, 'applied': False, **UNSEEN})]


def test_registry_and_records_declare_the_grasp_time_view_log_only(monkeypatch):
    reg = c.registry()
    assert reg['grip_monitor']['grasp_time_view'] == grip.GRASP_TIME_VIEW == rt.GRASP_TIME_VIEW == 'log_only_v98'
    assert 'GRIP_NOT_SEEN' not in reg['grip_monitor']['unchanged_grasp_checks']
    assert any('GRIP_NOT_SEEN' in row for row in reg['grip_monitor']['logged_only'])
    assert "'grasp_time_view': GRASP_TIME_VIEW" in inspect.getsource(rt.Team.records)
    bad = json.loads((ROOT/c.REGISTRY).read_text())
    bad['grip_monitor']['grasp_time_view'] = 'applied'
    read = c.base.read
    monkeypatch.setattr(c.base, 'read', lambda path: bad if str(path).endswith(c.REGISTRY) else read(path))
    with pytest.raises(ValueError, match='registry mismatch'):
        c.registry()
