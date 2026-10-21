"""CLI dry run: select -> decide (replay / fake-Planner live) -> rebind -> evaluate."""
import hashlib
import json
import math

import pytest

from harness import e2e_l2 as l2
from scripts import run_e2e_l2 as cli
from test_e2e_l2 import FakeHTTP, JPEG, make_case


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv('E2E_L2', 'on_v1')
    for k in list(__import__('os').environ):
        if any(m in k.upper() for m in l2.CREDENTIAL_ENV_MARKERS):
            monkeypatch.delenv(k)


def r(act):
    return {'act': act, 'message': None}


def test_default_off(monkeypatch, tmp_path):
    monkeypatch.delenv('E2E_L2', raising=False)
    with pytest.raises(SystemExit):
        cli.main(['select', '--cases', str(tmp_path / 'x.json'), '--out', str(tmp_path / 'y.json')])


def test_select_reports_ns_exclusions(on, tmp_path):
    cases = [make_case(seed=8344000 + i, yaw=(math.pi / 2 if i in (1, 4) else 0.)) for i in range(9)][::-1]
    (tmp_path / 'c.json').write_text(json.dumps(cases))
    cli.main(['select', '--cases', str(tmp_path / 'c.json'), '--out', str(tmp_path / 'base.json')])
    seeds = [c['plan']['seed'] for c in json.loads((tmp_path / 'base.json').read_text())]
    assert seeds == [8344000, 8344002, 8344003, 8344005, 8344006, 8344007]
    adm = json.loads((tmp_path / 'base-admissibility.json').read_text())
    assert adm['excluded_ns_n'] == 2 and adm['excluded_seeds'] == [8344001, 8344004] and adm['scanned_n'] == 8


def write_frames(tmp_path, cases_path, n):
    run = tmp_path / 'frames'
    run.mkdir()
    (run / 'summary.json').write_text(json.dumps({'cases_sha256': hashlib.sha256(cases_path.read_bytes()).hexdigest(),
                                                  'world_indices': list(range(n))}))
    for i in range(n):
        for rid in l2.ROBOTS:
            f = run / f'world-{i:03d}' / 'review-2hz' / rid / '000000.jpg'
            f.parent.mkdir(parents=True)
            f.write_bytes(JPEG[rid])
    return run


def test_live_decide_with_fake_planner(on, tmp_path, monkeypatch):
    cases = [make_case(seed=8344000)]
    cp = tmp_path / 'c.json'
    cp.write_text(json.dumps(cases))
    frames = write_frames(tmp_path, cp, 1)
    http = FakeHTTP([r('end_teal'), r('end_blue')])
    monkeypatch.setattr(l2, 'check_relay', lambda url: {'upstream': dict(l2.PLANNER_PIN), 'alerts': []})
    real = l2.make_planners
    monkeypatch.setattr(l2, 'make_planners', lambda *a, **k: real(*a, **k, http_open=http))
    out = tmp_path / 'no_comm'
    cli.main(['decide', '--cases', str(cp), '--frames-run', str(frames), '--condition', 'no_comm', '--llm', 'live',
              '--relay-url', 'http://127.0.0.1:9/v1/chat/completions', '--arm', 'student', '--out', str(out)])
    d = json.loads((out / 'decisions.json').read_text())
    rec = d['records'][0]
    assert rec['success_eligible'] and rec['frames_sha256']['r1'] == hashlib.sha256(JPEG['r1']).hexdigest()
    assert rec['planner_ledger']['r2'][0]['accepted'] and d['planner_pin']['provider'] == 'CoreWeave'
    assert (out / 'llm' / 'world-00' / 'r1' / '00001.response.json').exists()
    # the image sent is the frame-run JPEG; no geometry in any request
    assert all(l2.input_leaks(json.loads(q['messages'][1]['content'])) == [] for q in http.requests)


def test_live_requires_frames_and_relay(on, tmp_path):
    (tmp_path / 'c.json').write_text(json.dumps([make_case()]))
    with pytest.raises(SystemExit):
        cli.main(['decide', '--cases', str(tmp_path / 'c.json'), '--condition', 'no_comm', '--llm', 'live',
                  '--arm', 'student', '--out', str(tmp_path / 'o')])


def test_frames_from_other_case_file_rejected(on, tmp_path):
    cp = tmp_path / 'c.json'
    cp.write_text(json.dumps([make_case()]))
    frames = write_frames(tmp_path, cp, 1)
    cp.write_text(json.dumps([make_case(seed=8344001)]))
    with pytest.raises(SystemExit):
        cli.load_frames(frames, cp, json.loads(cp.read_text()))


def test_replay_decide_rebind_evaluate(on, tmp_path):
    cases = [make_case(seed=8344000), make_case(seed=8344001)]
    cp = tmp_path / 'c.json'
    cp.write_text(json.dumps(cases))
    replies = {'8344000|r1|1': r('end_blue'), '8344000|r2|1': r('end_teal'),
               '8344001|r1|1': r('end_teal'), '8344001|r2|1': r('end_teal')}   # swap, collision
    (tmp_path / 'rep.json').write_text(json.dumps(replies))
    out = tmp_path / 's'
    cli.main(['decide', '--cases', str(cp), '--condition', 'no_comm', '--llm', 'replay',
              '--replies', str(tmp_path / 'rep.json'), '--arm', 'student', '--out', str(out)])
    ex = json.loads((out / 'exec-cases.json').read_text())
    assert [c['plan']['seed'] for c in ex] == [8344000] and ex[0]['plan']['roles'] == {'r1': 'blue', 'r2': 'teal'}
    cli.main(['rebind', '--cases', str(cp), '--decisions', str(out / 'decisions.json'),
              '--arm', 'teacher_fallback', '--out', str(tmp_path / 't')])
    t = json.loads((tmp_path / 't' / 'exec-cases.json').read_text())
    assert t[0]['plan'] == ex[0]['plan'] and t[0]['l2_admin']['record_sha256'] == ex[0]['l2_admin']['record_sha256']
    with pytest.raises(SystemExit):
        cli.main(['rebind', '--cases', str(cp), '--decisions', str(out / 'decisions.json'),
                  '--arm', 'student', '--out', str(tmp_path / 'u')])
    (out / 'summary.json').write_text(json.dumps({'student_eval': {'mode': 'x'},
                                                  'worlds': [{'seed': 8344000, 'carry_success': True, 'teacher_steps': 0}]}))
    (tmp_path / 'adm.json').write_text(json.dumps({'scanned_n': 7, 'selected_n': 6, 'excluded_ns_n': 1,
                                                   'excluded_seeds': [1], 'rule': 'x'}))
    cli.main(['evaluate', '--decisions', str(out / 'decisions.json'), '--summary', str(out / 'summary.json'),
              '--admissibility', str(tmp_path / 'adm.json'), '--out', str(out / 'l2-eval.json')])
    res = json.loads((out / 'l2-eval.json').read_text())
    assert res['aggregate'][0]['report'] == '1/2' and res['llm_note'].startswith('REPLAY')
    assert res['pre_run_exclusion']['excluded_ns_n'] == 1
    assert [s['failure_stage'] for s in res['seeds']] == [None, 'llm']
    assert res['seeds'][0]['llm']['assignment_match'] is False   # swapped, executed as decided
    with pytest.raises(SystemExit):
        cli.main(['evaluate', '--decisions', str(out / 'decisions.json'), '--out', str(out / 'l2-eval.json')])


def test_prereg_cap_references_p5_and_is_empty():
    d = json.loads((cli.Path(cli.__file__).resolve().parents[1] / 'experiments/2026-11-05-e2e-l2/E2E_L2_PREREG_DRAFT.json').read_text())
    cap = d['episode_cap_sim_s']
    assert cap['value'] is None and 'PAIRACT_R1_EVAL_PREREG_DRAFT.json' in cap['rule']
    assert d['seeds']['candidate_range'] == {'first': 8344000, 'last': 8344099}
    assert 'excluded_ns_n' in d['seeds']['exclusion_report']
    assert 'distance' not in d['task']['llm_input'].split('No ')[0]
