"""v98: the own grasp receipt is carried across intermediate HIGH stops (beam kept closed at HIGH).

The frozen ``PairGraspRelook.beam_grasp_confirmed`` holds only while ``receipt['segment'] == seg``. v98 advances
``seg`` at every intermediate HIGH stop without opening, so without the carry the controller (and the pair guard's
``carrying_beam``, which sets ``loaded`` for the sweep certificates) read "not carrying" from leg 1 on.
Record-derived: align_to_carry@1236c63d (receipt minted in segment 0, stops at seg 1 and 2, gripper closed)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import zone_pair_highpose_runtime as rt
from harness.zone_pair_grasp import PairGraspRelook
from harness.zone_pair_guards import PairCommandGuard
from tests import test_highpose_transit as tt
from tests.test_highpose_dr_checkpoint import run_dr

FIXTURE = json.loads((Path(__file__).parent/'fixtures'/'v98_grasp_receipt_segments_1236c63d.json').read_text())


class Ctl:
    """Only what the frozen property and the carry helper read."""
    beam_grasp_confirmed = PairGraspRelook.beam_grasp_confirmed

    def __init__(self, rid, receipt, seg=0, gripper=1500):
        self.rid, self.seg, self.beam_grasp_receipt = rid, seg, receipt
        self.port = SimpleNamespace(own=SimpleNamespace(servo={1: gripper}))
        self.events = []

    def log(self, rid, event, t, **kw):
        self.events.append({'robot_id': rid, 'event': event, 't': t, **kw})


def guard_for(ctl):
    guard = object.__new__(PairCommandGuard)
    guard.ep = SimpleNamespace(controller=ctl)
    return guard


@pytest.mark.parametrize('rid', ['r1', 'r2'])
def test_recorded_segments_lose_the_receipt_without_the_carry_and_keep_it_with_it(rid):
    rows = FIXTURE['robots'][rid]
    minted = next(e for e in rows if e['event'] == 'beam_grasp_confirmed')
    stops = [e for e in rows if e['event'] == 'checkpoint_high_stop']
    assert minted['segment'] == 0 and [e['seg'] for e in stops] == [1, 2] and not any(e['opened'] for e in stops)
    receipt = {k: minted[k] for k in ('segment', 'frame_id', 'sha256', 'observed_at_s', 'closed_command_at_s', 'source')}
    old, new = Ctl(rid, dict(receipt)), Ctl(rid, dict(receipt))
    assert old.beam_grasp_confirmed and new.beam_grasp_confirmed and guard_for(new).carrying_beam
    for stop in stops:
        old.seg = new.seg = stop['seg']                     # what checkpoint() does first
        assert rt.carry_grasp_receipt(new, stop['sim_s'])
        assert not old.beam_grasp_confirmed and not guard_for(old).carrying_beam    # the recorded defect
        assert new.beam_grasp_confirmed and guard_for(new).carrying_beam
        assert new.beam_grasp_receipt['minted_segment'] == 0 and new.beam_grasp_receipt['sha256'] == minted['sha256']
    assert [e['segment'] for e in new.events if e['event'] == rt.GRASP_RECEIPT_CARRIED_EVENT] == [1, 2]


def test_no_receipt_or_a_stale_receipt_is_never_minted():
    none = Ctl('r1', None, seg=1)
    assert not rt.carry_grasp_receipt(none, 1.) and none.beam_grasp_receipt is None and not none.events
    stale = Ctl('r1', {'segment': 0}, seg=2)               # skipped a stop: not continuous, not carried
    assert not rt.carry_grasp_receipt(stale, 1.) and stale.beam_grasp_receipt == {'segment': 0}
    assert not stale.beam_grasp_confirmed


def test_an_open_gripper_still_reads_not_carrying_after_the_carry():
    ctl = Ctl('r1', {'segment': 0}, seg=1, gripper=2000)
    assert rt.carry_grasp_receipt(ctl, 1.)
    assert not ctl.beam_grasp_confirmed and not guard_for(ctl).carrying_beam   # frozen pulse check unchanged


@pytest.fixture(autouse=True)
def short_route(monkeypatch):
    monkeypatch.setattr(tt.legacy, 'build_schedule',
                        lambda rid, t: [(t, t+.2, {'forward': .01, 'left': 0., 'turn': 0.})])


def test_real_high_checkpoint_carries_the_receipt_to_the_next_leg():
    _, ctls = tt.pair(segments=(.1, .1))
    for c in ctls:
        c.beam_grasp_receipt = {'segment': 0, 'frame_id': 1, 'sha256': 'x', 'source': 'test'}
    run_dr(ctls, until=60., sxy={'r1': .0424, 'r2': .0423}, syaw_deg={'r1': 1.38, 'r2': 1.22})
    for c in ctls:
        assert c.failure is None and c.state == 'released'
        stop = next(e for e in c.events if e['event'] == 'checkpoint_high_stop')
        carried = [e for e in c.events if e['event'] == rt.GRASP_RECEIPT_CARRIED_EVENT]
        assert len(carried) == 1 and carried[0]['t'] == stop['t'] and carried[0]['segment'] == stop['seg'] == 1
        assert c.beam_grasp_receipt['segment'] == 1 and c.beam_grasp_receipt['minted_segment'] == 0
