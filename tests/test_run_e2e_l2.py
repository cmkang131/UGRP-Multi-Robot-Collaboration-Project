"""CLI dry run: select -> decide (replay) -> evaluate with a fake runner summary."""
import json
import math

import pytest

from scripts import run_e2e_l2 as cli
from test_e2e_l2 import make_case


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv('E2E_L2', 'on_v1')


def test_default_off(monkeypatch, tmp_path):
    monkeypatch.delenv('E2E_L2', raising=False)
    with pytest.raises(SystemExit):
        cli.main(['select', '--cases', str(tmp_path / 'x.json'), '--out', str(tmp_path / 'y.json')])


def test_select_takes_first_admissible_in_seed_order(on, tmp_path):
    cases = [make_case(seed=8344000 + i, yaw=(math.pi / 2 if i in (1, 4) else 0.)) for i in range(9)][::-1]
    (tmp_path / 'c.json').write_text(json.dumps(cases))
    assert cli.main(['select', '--cases', str(tmp_path / 'c.json'), '--out', str(tmp_path / 'base.json')]) == 0
    seeds = [c['plan']['seed'] for c in json.loads((tmp_path / 'base.json').read_text())]
    assert seeds == [8344000, 8344002, 8344003, 8344005, 8344006, 8344007]
    log = json.loads((tmp_path / 'base-admissibility.json').read_text())
    assert [r['seed'] for r in log['log'] if not r['admissible']] == [8344001, 8344004]


def test_live_llm_not_wired(on, tmp_path):
    (tmp_path / 'c.json').write_text(json.dumps([make_case()]))
    with pytest.raises(NotImplementedError):
        cli.main(['decide', '--cases', str(tmp_path / 'c.json'), '--condition', 'no_comm', '--llm', 'live',
                  '--arm', 'student', '--out', str(tmp_path / 'o')])


def test_decide_and_evaluate_dry_run(on, tmp_path, monkeypatch):
    monkeypatch.chdir(cli.Path(cli.__file__).resolve().parents[1])
    cases = [make_case(seed=8344000), make_case(seed=8344001)]
    (tmp_path / 'c.json').write_text(json.dumps(cases))
    r = lambda act: {'need_partner': True, 'act': act, 'message': None}
    replies = {'8344000|r1|1': r('end_west'), '8344000|r2|1': r('end_east'),
               '8344001|r1|1': r('end_west'), '8344001|r2|1': r('end_west')}   # collision
    (tmp_path / 'rep.json').write_text(json.dumps(replies))
    out = tmp_path / 'no_comm'
    cli.main(['decide', '--cases', str(tmp_path / 'c.json'), '--condition', 'no_comm', '--llm', 'replay',
              '--replies', str(tmp_path / 'rep.json'), '--arm', 'student', '--out', str(out)])
    exec_cases = json.loads((out / 'exec-cases.json').read_text())
    assert [c['plan']['seed'] for c in exec_cases] == [8344000]
    assert exec_cases[0]['plan']['roles'] == {'r1': 'teal', 'r2': 'blue'}
    summary = {'student_eval': {'mode': 'pairact_r1_student_eval_v1'},
               'worlds': [{'seed': 8344000, 'carry_success': True, 'teacher_steps': 0}]}
    (out / 'summary.json').write_text(json.dumps(summary))
    cli.main(['evaluate', '--decisions', str(out / 'decisions.json'), '--summary', str(out / 'summary.json'),
              '--out', str(out / 'l2-eval.json')])
    result = json.loads((out / 'l2-eval.json').read_text())
    assert result['aggregate'][0]['report'] == '1/2' and result['llm_note'].startswith('REPLAY')
    assert [s['failure_stage'] for s in result['seeds']] == [None, 'llm']
    with pytest.raises(SystemExit):   # never overwrite
        cli.main(['evaluate', '--decisions', str(out / 'decisions.json'), '--out', str(out / 'l2-eval.json')])


def test_rebind_reuses_decisions_without_llm(on, tmp_path):
    cases = [make_case(seed=8344000)]
    (tmp_path / 'c.json').write_text(json.dumps(cases))
    r = lambda act: {'need_partner': True, 'act': act, 'message': None}
    (tmp_path / 'rep.json').write_text(json.dumps({'8344000|r1|1': r('end_east'), '8344000|r2|1': r('end_west')}))
    cli.main(['decide', '--cases', str(tmp_path / 'c.json'), '--condition', 'no_comm', '--llm', 'replay',
              '--replies', str(tmp_path / 'rep.json'), '--arm', 'student', '--out', str(tmp_path / 's')])
    cli.main(['rebind', '--cases', str(tmp_path / 'c.json'), '--decisions', str(tmp_path / 's' / 'decisions.json'),
              '--arm', 'teacher_fallback', '--out', str(tmp_path / 't')])
    s = json.loads((tmp_path / 's' / 'exec-cases.json').read_text())[0]
    t = json.loads((tmp_path / 't' / 'exec-cases.json').read_text())[0]
    assert s['plan'] == t['plan'] and s['plan']['roles'] == {'r1': 'blue', 'r2': 'teal'}
    assert s['l2_admin']['record_sha256'] == t['l2_admin']['record_sha256']
    assert t['l2_admin']['arm'] == 'teacher_fallback'
    with pytest.raises(SystemExit):   # same arm is refused
        cli.main(['rebind', '--cases', str(tmp_path / 'c.json'), '--decisions', str(tmp_path / 's' / 'decisions.json'),
                  '--arm', 'student', '--out', str(tmp_path / 'u')])
