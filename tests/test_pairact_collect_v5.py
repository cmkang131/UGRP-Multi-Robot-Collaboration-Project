"""COLLECT_PREREG v5 fixes (dsh/pairact-carry-r1-v5): Codex v4 re-review 1-5 + collector carry_success.

Each test is the counterexample of collect-v4-review-20261021 (admission-probe.py / sharding-probe.py) moved
into the suite, plus the carry_success record_error of the gcp2 shard smoke (2026-10-21).  CPU fakes only.
"""
import copy
import json
from pathlib import Path

import pytest

from harness import pairact_collect as pc
from test_pairact_collect import PREREG, TABLE, FakeEpisode, result, runner

FIX = Path(__file__).resolve().parent / 'fixtures' / 'pairact_c5_shardsmoke_20261021'


@pytest.fixture
def prereg():
    return json.loads(PREREG.read_text())


# ------------------------------------------------------------ 6. summary worlds[].carry_success

def _smoke_world(tmp_path, i, carry=None):
    """A real gcp2 -c5 shard-smoke summary world (no carry_success key) + the gcp6 raw of the same seed."""
    s = json.loads((FIX / 'summary-worlds.json').read_text())
    w = dict(s['worlds'][i])
    raw = tmp_path / f'world-{i:03d}' / 'raw'
    raw.mkdir(parents=True)
    r = json.loads((FIX / w['raw']).read_text())
    if carry is not None:
        r['carry_eval'] = dict(r['carry_eval'], success=carry, failure=None if carry else r['carry_eval']['failure'])
        r['carry_success'] = carry
    (raw / 'result.json').write_text(json.dumps(r))
    w['raw'] = str(raw)
    return w, r, dict(status=s['status'], HOST_ERROR=s['HOST_ERROR'], worlds=[w], rejection_table=TABLE)


def _judge(w, summary, seed):
    case = dict(plan=dict(seed=seed, roles=['r1', 'r2']))
    return runner.judge_world(dict(seed=seed, slot=0), case, w, summary, mode='measurement', clean=True,
                              read_rows=pc.read_jsonl)[0]


def test_smoke_summary_without_carry_success_is_not_a_record_error(tmp_path):
    """gcp2 shard smoke: the gcp6 wrapper summary has no worlds[].carry_success -> 25 record_error (v4)."""
    s = json.loads((FIX / 'summary-worlds.json').read_text())
    assert all('carry_success' not in w for w in s['worlds'])
    for i in (0, 1):
        w, r, summary = _smoke_world(tmp_path / 'f', i)
        assert r['carry_eval']['success'] is False
        j = _judge(w, summary, w['seed'])
        assert j['category'] == 'behavior' and j['outcome'] == 'failure' and j['failure_stage'] == 'carry', j
    w, r, summary = _smoke_world(tmp_path / 's', 0, carry=True)
    j = _judge(w, summary, w['seed'])
    assert j['outcome'] == 'success' and j['admitted'], j          # 16 such worlds were record_error in v4


def test_summary_carry_success_that_disagrees_is_still_a_record_error(tmp_path):
    w, r, summary = _smoke_world(tmp_path, 0, carry=True)
    for bad in (False, None):
        j = _judge(dict(w, carry_success=bad), summary, w['seed'])
        assert j['outcome'] == 'record_error' and 'carry_success disagree' in j['reason']
        # v4 left success/admitted True on this record_error: report ks.admitted 16 vs A.text 0/7 (smoke)
        assert j['success'] is False and j['admitted'] is False
    assert _judge(dict(w, carry_success=True), summary, w['seed'])['outcome'] == 'success'


class NoCarryKeyEpisode(FakeEpisode):
    """Root-runner layout as the gcp6 wrapper writes it: worlds[] without carry_success."""

    def __call__(self, cases_path, indices, out):
        code = super().__call__(cases_path, indices, out)
        path = Path(out) / 'summary.json'
        s = json.loads(path.read_text())
        for w in s.get('worlds', []):
            w.pop('carry_success', None)
        path.write_text(json.dumps(s))
        return code


def test_gcp6_wrapper_summary_writes_carry_success_like_the_c5_root():
    src = (Path(__file__).resolve().parents[1] / 'experiments/2026-10-17-beamact5/teacher/'
           'run_warp_flow_teacher_gcp6.py').read_text()
    block = src[src.index('worlds.append(dict(world=i'):]
    block = block[:block.index("raw=str(a.out/f'world-{i:03d}'/'raw')))")]
    assert "carry_success=(raw.get('carry_eval') or {}).get('success')" in block
    assert "carry_failure=(raw.get('carry_eval') or {}).get('failure')" in block


def test_collect_without_summary_carry_success_admits_from_the_result(tmp_path, prereg):
    from test_pairact_collect import make
    ok = lambda s, c: result() if s % 2 else result(success=False)
    runner.run(tmp_path, prereg, 'sha', mode='measurement', noise='off', batch_size=20, max_batches=1,
               make_cases=make(prereg), run_episode=NoCarryKeyEpisode(ok))
    rows = [r for r in pc.read_ledger(tmp_path / 'ledger.jsonl') if r.get('type') == 'attempt']
    assert len(rows) == 20 and not [r for r in rows if r['outcome'] == 'record_error']
    assert sum(r['success'] for r in rows) == sum(r['seed'] % 2 for r in rows) > 0
    assert all(r['summary_carry_success'] is None for r in rows)


# ------------------------------------------------------------ 4. ledger: one committed prefix

def _shard0(tmp_path):
    sdir = runner.shard_dir(tmp_path, 0)
    sdir.mkdir(parents=True)
    led = sdir / 'ledger.jsonl'
    pc.append(led, pc.header('sha', mode='measurement', noise='off', batch_size=20,
                             shard=dict(index=0, count=2, vm='A')))
    return led


PLAN0 = dict(type='batch_planned', batch=0, split='pilot',
             slots=[dict(seed=8343000, bin='B0', split='pilot', slot=0, requeue=False)])


def test_repaired_torn_tail_then_append_merges_again(tmp_path, prereg):
    """sharding-probe repair_after_merge: v4 sealed the torn 8 bytes and refused the repaired ledger."""
    led = _shard0(tmp_path)
    with led.open('a') as f:
        f.write('{"type":')                                   # 8 bytes, no newline (crash mid-append)
    runner.merge(tmp_path, prereg, 'sha', 2)
    meta = json.loads((tmp_path / 'merged' / 'merge.json').read_text())
    assert meta['shard_ledger_bytes']['s00'] == len(led.read_bytes()) - 8      # committed prefix only
    assert pc.repair_ledger(led) == 8
    pc.append(led, PLAN0)
    rep, meta = runner.merge(tmp_path, prereg, 'sha', 2)
    assert meta['planned'] == [0] and meta['shard_ledger_bytes']['s00'] == len(led.read_bytes())


def test_committed_prefix_change_is_still_refused(tmp_path, prereg):
    led = _shard0(tmp_path)
    pc.append(led, PLAN0)
    with led.open('a') as f:
        f.write('{"type": "attempt"')                          # uncommitted tail, ignored by the seal
    runner.merge(tmp_path, prereg, 'sha', 2)
    data = led.read_bytes()
    led.write_bytes(data.replace(b'8343000', b'8343001', 1))  # rewritten committed row
    with pytest.raises(ValueError, match='append-only'):
        runner.merge(tmp_path, prereg, 'sha', 2)
    led.write_bytes(data[:len(data) - 30])                    # shorter than the sealed prefix
    with pytest.raises(ValueError, match='append-only'):
        runner.merge(tmp_path, prereg, 'sha', 2)


def test_valid_json_without_newline_is_uncommitted_for_reader_and_repair(tmp_path):
    """sharding-probe uncommitted_valid_row: v4 read_ledger showed the row, repair_ledger deleted it."""
    h = pc.header('sha', mode='measurement', noise='off', batch_size=20, shard=dict(index=0, count=2, vm='A'))
    torn = tmp_path / 'torn.jsonl'
    torn.write_text(json.dumps(h) + '\n' + json.dumps(PLAN0))
    before = pc.read_ledger(torn)
    assert before == [h]
    assert pc.shard_view({0: before, 1: []}, 2, 1) is None          # batch 0 not planned yet for the view
    pc.repair_ledger(torn)
    assert pc.read_ledger(torn) == before
    pc.append(torn, PLAN0)
    assert pc.read_ledger(torn) == [h, PLAN0]
