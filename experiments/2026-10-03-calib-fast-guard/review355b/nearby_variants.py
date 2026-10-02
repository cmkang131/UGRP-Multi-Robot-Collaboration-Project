"""Independent scoped re-review variants; copy into the target archive's tests/."""
import json
import os
import pytest
from scripts import agent_lock as legacy, agent_sim_slots as slots


def physics(root, owner, timing=False):
    return legacy.acquire(root, owner=owner, branch=owner+'/exclusive', purpose='test',
                          pid=os.getpid(), expected_minutes=1, timing_sensitive=timing)


def slot(root, owner, name='sim-one', pid=None):
    return slots.acquire_sim_slot(root, slot=name, owner=owner, branch=owner+'/review',
        purpose='test', pid=os.getpid() if pid is None else pid, expected_minutes=1)


@pytest.mark.parametrize('holder', ['claude', 'codex', 'kiro'])
@pytest.mark.parametrize('entrant', ['claude', 'codex', 'kiro'])
@pytest.mark.parametrize('timing', [False, True])
def test_all_owner_timing_combinations(tmp_path, holder, entrant, timing):
    physics(tmp_path, holder, timing)
    before=(tmp_path/'physics/owner.json').read_bytes()
    if holder == entrant and not timing:
        slot(tmp_path, entrant)
        slots.release(tmp_path, owner=entrant, name='sim-one')
    else:
        with pytest.raises(RuntimeError):
            slot(tmp_path, entrant)
        assert slots.sim_holders(tmp_path) == []
    assert (tmp_path/'physics/owner.json').read_bytes() == before


@pytest.mark.parametrize('owner', ['claude', 'codex', 'kiro'])
@pytest.mark.parametrize('reverse', [False, True])
def test_empty_host_first_last_slot_lifetime(tmp_path, owner, reverse):
    slot(tmp_path, owner)
    slot(tmp_path, owner, 'sim-two')
    first, last = ('sim-two','sim-one') if reverse else ('sim-one','sim-two')
    reservation=(tmp_path/'physics/owner.json').read_bytes()
    slots.release(tmp_path, owner=owner, name=first)
    assert (tmp_path/'physics/owner.json').read_bytes() == reservation
    for entrant in ('claude','codex','kiro'):
        for timing in (False,True):
            with pytest.raises(RuntimeError):
                physics(tmp_path, entrant, timing)
    slots.release(tmp_path, owner=owner, name=last)
    assert legacy.status(tmp_path) is None
    physics(tmp_path, owner)


@pytest.mark.parametrize('timing', [False, True])
def test_other_live_coordinator_is_refused(tmp_path, monkeypatch, timing):
    physics(tmp_path, 'codex', timing)
    # Only liveness is synthetic. No source/hash mutation is used.
    monkeypatch.setattr(legacy, '_alive', lambda pid: True)
    with pytest.raises(RuntimeError):
        slot(tmp_path, 'codex', pid=os.getpid()+100000)
    assert slots.sim_holders(tmp_path) == []


def test_two_dead_slots_require_both_explicit_releases(tmp_path, monkeypatch):
    slot(tmp_path, 'codex')
    slot(tmp_path, 'codex', 'sim-two')
    for owner in ('codex','claude'):
        with pytest.raises(RuntimeError):
            slots.release(tmp_path, owner=owner, name='sim-one', stale=True)
    monkeypatch.setattr(legacy, '_alive', lambda pid: False)
    for name in ('sim-one','sim-two'):
        with pytest.raises(ValueError):
            slots.require_sim_slot(tmp_path, slot=name, owner='codex', branch='codex/review')
    slots.release(tmp_path, owner='claude', name='sim-two', stale=True)
    with pytest.raises(RuntimeError):
        physics(tmp_path, 'kiro')
    assert legacy.status(tmp_path) is not None
    slots.release(tmp_path, owner='claude', name='sim-one', stale=True)
    assert legacy.status(tmp_path) is None
    monkeypatch.undo()
    slot(tmp_path, 'kiro')


def test_distinct_slot_outputs_and_cross_slot_duplicate_refusal(tmp_path, monkeypatch):
    from tests.test_zone_final_pair_fast import fake_host, args
    from harness import zone_final_pair_fast as v91
    from scripts import run_final_pair_fast as run
    fake_host(tmp_path, monkeypatch)
    slots.release(tmp_path/'locks', owner='codex', name='sim-second')
    slots.acquire_sim_slot(tmp_path/'locks', slot='sim-second', owner='codex',
        branch='codex/fast-test', purpose='test', pid=os.getpid(), expected_minutes=1)
    one, two = tmp_path/'outputs/one', tmp_path/'outputs/two'
    flags=['--execute','--lock-owner','codex','--sim-slot']
    assert run.main(args(one,v91.MAPS[0])+flags+['sim-first']) == 0
    saved={str(p.relative_to(one)):p.read_bytes() for p in one.rglob('*') if p.is_file()}
    with pytest.raises(FileExistsError):
        run.main(args(one,v91.MAPS[1])+flags+['sim-second'])
    assert run.main(args(two,v91.MAPS[1])+flags+['sim-second']) == 0
    assert saved == {str(p.relative_to(one)):p.read_bytes() for p in one.rglob('*') if p.is_file()}
    for out,name,map_id in ((one,'sim-first',v91.MAPS[0]),(two,'sim-second',v91.MAPS[1])):
        assert json.loads((out/'plan.json').read_text())['sim_slot'] == name
        assert json.loads((out/map_id/'bundle.json').read_text())['map_id'] == map_id


def test_exclusive_runner_still_works_when_no_slots(tmp_path, monkeypatch):
    from tests.test_zone_final_pair_fast import fake_host, args
    from harness import zone_final_pair_fast as v91
    from scripts import run_final_pair_fast as run
    fake_host(tmp_path, monkeypatch)
    for name in ('sim-first','sim-second'):
        slots.release(tmp_path/'locks', owner='codex', name=name)
    legacy.acquire(tmp_path/'locks', owner='codex', branch='codex/fast-test', purpose='test',
                   pid=os.getpid(), expected_minutes=1)
    out=tmp_path/'outputs/exclusive'
    assert run.main(args(out,v91.MAPS[0])+['--execute','--lock-owner','codex']) == 0
    assert json.loads((out/'plan.json').read_text())['lock_mode'] == 'exclusive'
