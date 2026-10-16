"""v98 approach no_fix travel gate (simulator-free).

Record-derived (coordinator practice 2026-10-04): the nine ``no_fix`` looks of r2 in the v98 raise_high probe at
1f7fb800 are fed with the own provider estimate at each look tick and the own estimate at the previous ``look_done``
(replay of the real v98 provider + real GuardedPairApproach on the recorded r2 frames/commands, matching every
recorded command 10.1-151.2 s). No ground truth is used by the rule or by these tests.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from harness import zone_pair_highpose_approach_looks as al
from harness import zone_own_driver as zd
from harness.owncam_drive import LOADED_LOOK_EVERY_M
from harness.zone_pair_guards import GuardedPairApproach

RECORD = Path(__file__).with_name('fixtures')/'v98_r2_approach_no_fix_looks_1f7fb800.json'


def driver(cls, *, loaded=False, last_look_xy=None):
    d = object.__new__(cls)
    d.loaded, d.last_look_xy = loaded, last_look_xy
    d.door, d.checkpoints_done = (-100., 0.), set()        # far west: no door checkpoint in these tests
    return d


def est(x=0., y=0., *, fix_age=5., sxy=.01, syaw=.005):
    return {'initialized': True, 'x': x, 'y': y, 'std_xy_m': sxy, 'std_yaw_rad': syaw, 'fix_age_s': fix_age}


GATED = al.adopt(GuardedPairApproach)


def test_adopt_is_stable_and_keeps_the_driver_mro():
    assert al.adopt(GuardedPairApproach) is GATED
    assert GATED.__mro__[1] is al.TravelGatedNoFix and issubclass(GATED, GuardedPairApproach)


def test_no_fix_without_travel_is_skipped_and_with_travel_kept():
    assert driver(GuardedPairApproach, last_look_xy=(0., 0.))._needs_look(est(.05), 1.) == 'no_fix'
    assert driver(GATED, last_look_xy=(0., 0.))._needs_look(est(.05), 1.) is None
    assert driver(GATED, last_look_xy=(0., 0.))._needs_look(est(LOADED_LOOK_EVERY_M+.01), 1.) == 'no_fix'
    assert driver(GATED, last_look_xy=(0., 0.))._needs_look(est(LOADED_LOOK_EVERY_M), 1.) is None   # <= gate


def test_first_look_and_other_reasons_are_untouched():
    assert driver(GATED)._needs_look(est(), 1.) == 'no_fix'                                   # no look yet
    g = driver(GATED, last_look_xy=(0., 0.))
    assert g._needs_look(est(sxy=.2), 1.) == 'uncertain'
    assert g._needs_look({'initialized': False}, 1.) == 'not_initialized'
    assert g._needs_look(est(fix_age=zd.LOOK_IF_NO_FIX_S-.1), 1.) is None


def test_loaded_driver_is_unchanged():
    cases = [est(x, fix_age=f) for x in (0., .1, .34, .36, .5, 1., 2.) for f in (None, 1., 5., 30.)]
    for e in cases:
        base, gated = driver(GuardedPairApproach, loaded=True, last_look_xy=(0., 0.)), driver(GATED, loaded=True, last_look_xy=(0., 0.))
        assert gated._needs_look(e, 1.) == base._needs_look(e, 1.)
    assert any(driver(GuardedPairApproach, loaded=True, last_look_xy=(0., 0.))._needs_look(e, 1.) == 'travel' for e in cases)


def _recorded():
    return json.loads(RECORD.read_text())


def test_recorded_r2_no_fix_looks_were_all_taken_by_the_old_rule():
    rec = _recorded()
    raw = Path(rec['source']['raw_commands'])
    if raw.exists():                                              # primary outputs present: the source is unchanged
        import hashlib
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == rec['source']['raw_commands_sha256']
    assert len(rec['looks']) == 9
    for look in rec['looks']:
        d = driver(GuardedPairApproach, last_look_xy=look['last_look_xy'] and tuple(look['last_look_xy']))
        assert d._needs_look(look['estimate'], look['t']) == 'no_fix', look['t']


def test_recorded_r2_no_fix_looks_under_the_gate():
    kept, skipped = [], []
    for look in _recorded()['looks']:
        d = driver(GATED, last_look_xy=look['last_look_xy'] and tuple(look['last_look_xy']))
        (kept if d._needs_look(look['estimate'], look['t']) == 'no_fix' else skipped).append(look['t'])
        if look['last_look_xy'] is not None:
            e = look['estimate']
            moved = math.hypot(e['x']-look['last_look_xy'][0], e['y']-look['last_look_xy'][1])
            assert (look['t'] in kept) == (moved > LOADED_LOOK_EVERY_M)
    assert kept == [22.4, 80.8]                                    # first look; 0.442 m after the 76.6 s look
    assert skipped == [31.3, 40.2, 58.7, 67.9, 91.2, 100.7, 110.2]  # 0.0-0.077 m since the previous look


def test_mutation_without_the_gate_takes_every_recorded_look(monkeypatch):
    monkeypatch.setattr(al.TravelGatedNoFix, '_needs_look', lambda self, e, now: super(al.TravelGatedNoFix, self)._needs_look(e, now))
    taken = [look['t'] for look in _recorded()['looks']
             if driver(GATED, last_look_xy=look['last_look_xy'] and tuple(look['last_look_xy']))._needs_look(look['estimate'], look['t']) == 'no_fix']
    assert len(taken) == 9


def test_record_entry():
    r = al.record()
    assert r['id'] == al.ID and r['new_threshold'] is False


def test_runtime_wiring():
    root = Path(__file__).resolve().parents[1]
    src = (root/'harness'/'zone_pair_highpose_runtime.py').read_text()
    assert 'ctl.driver.__class__ = approach_looks.adopt(type(ctl.driver))' in src and "'approach_looks': approach_looks.record()" in src
