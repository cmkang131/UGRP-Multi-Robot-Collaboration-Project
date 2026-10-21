"""pairact P1: world-run ledger from fake OUT_ROOT summaries (pure)."""
import importlib.util
import json
from pathlib import Path

import pytest

_D = Path(__file__).resolve().parents[1]/'experiments/2026-10-21-pairact-p1'
_spec = importlib.util.spec_from_file_location('p1_ledger', _D/'p1_ledger.py')
m = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(m)
PREREG = _D/'PAIRACT_P1_PREREG_DRAFT.json'


def _setup(tmp_path, excluded=(37,)):
    d = json.loads(PREREG.read_text())
    d['static_exclusion']['tournament']['excluded_worlds'] = list(excluded)
    pre = tmp_path/'prereg.json'; pre.write_text(json.dumps(d))
    cases = tmp_path/'cases.json'
    cases.write_text(json.dumps([dict(plan={'seed': 8420000 + i}, candidate='beamact5_r13') for i in range(40)]))
    return pre, cases


def _summary(out, arm, *, indices, fail=(), status='complete', HOST_ERROR=0):
    (out/arm).mkdir(parents=True)
    worlds = [dict(world=k, seed=8420000 + i, success=i not in fail, sim_s=50., cap_end=False)
              for k, i in enumerate(indices)]
    (out/arm/'summary.json').write_text(json.dumps(dict(status=status, HOST_ERROR=HOST_ERROR,
                                                        world_indices=indices, worlds=worlds)))


def test_rows_cover_every_index_with_status(tmp_path):
    pre, cases = _setup(tmp_path)
    out = tmp_path/'tournament'
    idx = [i for i in range(40) if i not in (15, 37)]
    _summary(out, 'r13', indices=idx, fail=(27,))
    _summary(out, 'c1', indices=idx, status='HOST_ERROR', HOST_ERROR=1)
    # c1 HOST_ERROR after 10 worlds: keep only the first 10 world results
    s = json.loads((out/'c1/summary.json').read_text()); s['worlds'] = s['worlds'][:10]
    (out/'c1/summary.json').write_text(json.dumps(s))
    (out/'c2b').mkdir()                      # started, no summary -> HOST_ERROR
    rows = m.ledger(pre, 'tournament', out, cases, ['r13', 'c1', 'c2b', 'c3'])
    head, world = rows[0], rows[1:]
    assert head['prereg_sha256'] == m._sha(pre) and head['excluded_worlds'] == [37] and head['not_executed'] == [15]
    assert head['summary_sha256']['c3'] is None and head['summary_sha256']['c2b'] is None
    by = {}
    for r in world:
        by.setdefault(r['arm'], {})[r['world']] = r
    assert set(by) == {'r13', 'c1', 'c2b'} and all(len(v) == 40 for v in by.values())
    assert by['r13'][15]['status'] == 'not_executed' and by['r13'][37]['status'] == 'excluded'
    assert by['r13'][27]['success'] is False and sum(r.get('success') is True for r in by['r13'].values()) == 37
    st = [r['status'] for r in by['c1'].values()]
    assert st.count('complete') == 10 and st.count('HOST_ERROR') == 28
    assert all(r['status'] in ('HOST_ERROR', 'not_executed', 'excluded') for r in by['c2b'].values())
    assert by['c2b'][0]['host_error_reason'] == 'no summary.json' and by['c2b'][0]['seed'] == 8420000


def test_seed_mismatch_and_unrecorded_exclusion_refused(tmp_path):
    pre, cases = _setup(tmp_path)
    out = tmp_path/'t'
    _summary(out, 'r13', indices=[0, 1])
    s = json.loads((out/'r13/summary.json').read_text()); s['worlds'][1]['seed'] = 1
    (out/'r13/summary.json').write_text(json.dumps(s))
    with pytest.raises(ValueError, match='seed'):
        m.ledger(pre, 'tournament', out, cases, ['r13'])
    with pytest.raises(ValueError, match='excluded_worlds not recorded'):
        m.ledger(PREREG, 'confirmation', out, cases, ['r13'])


def test_main_writes_once(tmp_path):
    pre, cases = _setup(tmp_path, excluded=())
    out = tmp_path/'t'
    _summary(out, 'r13', indices=[i for i in range(40) if i != 15])
    m.main([str(pre), 'tournament', str(out), str(cases), 'r13'])
    lines = (out/'p1-ledger.jsonl').read_text().splitlines()
    assert len(lines) == 41 and json.loads(lines[0])['type'] == 'header'
    with pytest.raises(SystemExit):
        m.main([str(pre), 'tournament', str(out), str(cases), 'r13'])


def test_prereg_and_runner_carry_no_rerun_rule():
    d = json.loads(PREREG.read_text())
    assert '재실행하지 않는다' in d['host_error']['rule'] and 'p1_ledger.py' in d['ledger']['writer']
    sh = (_D/'run_p1.sh').read_text()
    assert 'p1_ledger.py' in sh and 'started arms are not re-run' in sh
