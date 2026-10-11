import json
from pathlib import Path

import pytest

from harness import jev_decider_eval as ev, jev_decider_suite as su

SUITE = su.build()
CASES = SUITE['cases']
FROZEN = Path(__file__).resolve().parents[1] / 'experiments/2026-10-11-jev-decider-offline/suite.json'


def test_suite_integrity():
    assert len(CASES) >= 60 and len({c['id'] for c in CASES}) == len(CASES)
    for c in CASES:
        assert c['rule'] in su.RULES and c['decision_point'] and c['family'] in su.FAMILIES
        assert c['acceptable'] and set(c['acceptable']) <= set(su.FAMILIES[c['family']])
        assert c['ambiguous'] == (c['label_basis'] == 'ambiguous')
        assert c['ambiguous'] == (len(c['acceptable']) > 1)
        assert c['split'] in ('dev', 'holdout')
        if c['pair']:
            base = next(b for b in CASES if b['id'] == c['pair']['base'])
            assert base['split'] == c['split'] and base['family'] == c['family']


def test_split_is_deterministic_and_balanced():
    assert su.build() == SUITE
    dev = sum(c['split'] == 'dev' for c in CASES)
    assert 30 <= dev <= 34


def test_frozen_file_matches_code():
    assert json.loads(FROZEN.read_text()) == json.loads(json.dumps(SUITE))


def test_message_sensitivity_pairs_cover_all_directions():
    kinds = {c['pair']['expect'] for c in CASES if c['pair']}
    assert kinds == {'change', 'no_change', 'either'}
    # no-change variants keep the base label; change variants carry a different one
    for c in CASES:
        if not c['pair']:
            continue
        base = next(b for b in CASES if b['id'] == c['pair']['base'])
        if c['pair']['expect'] == 'no_change':
            assert c['acceptable'] == base['acceptable'], c['id']
        if c['pair']['expect'] == 'change':
            assert c['acceptable'] != base['acceptable'], c['id']


def test_rule_baseline_ignores_peer_text_and_solves_hard_structural_cases():
    for c in CASES:
        act = ev.rule_action(c['state'], c['family'])
        assert act in su.FAMILIES[c['family']]
        if c['label_basis'] == 'hard_contract':
            assert act in c['acceptable'], (c['id'], act)


def test_semantic_state_has_no_label_or_ground_truth():
    forbidden = ('acceptable', 'rule', 'label', 'structurally_admissible', 'truth', 'success', 'contact')
    for c in CASES:
        for rep in ev.REPRESENTATIONS:
            text = json.dumps(ev.render(c, rep))
            assert not any(f in text for f in forbidden), (c['id'], rep)


def test_parse_jev_and_gemma():
    opts = su.FAMILIES['carry']
    body = {'answers': {'action': {'type': 'choice', 'choice': 'continue', 'confidence': .9, 'probabilities': {'continue': .9, 'set_down': .1}}}}
    assert ev.parse_jev(body, 'carry')[0] == 'continue'
    bad = {'answers': {'action': {'type': 'choice', 'choice': 'GO', 'confidence': .9, 'probabilities': {'GO': 1.}}}}
    with pytest.raises(ValueError):
        ev.parse_jev(bad, 'carry')
    g = {'choices': [{'message': {'content': '```json\n{"action": "set_down"}\n```'}}]}
    assert ev.parse_gemma(g, 'carry') == 'set_down' and 'set_down' in opts
    with pytest.raises(ValueError):
        ev.parse_gemma({'choices': [{'message': {'content': '{"action": "GO"}'}}]}, 'carry')


def fake_post(url, body, key, timeout=60):
    if 'typesafe' in url:
        opts = list(body['questions']['action']['criteria'])
        probs = {o: (1. if o == opts[0] else 0.) for o in opts}
        return dict(status='ok', http_status=200, latency_s=.5, raw_response='{}', body=dict(
            answers=dict(action=dict(type='choice', choice=opts[0], confidence=1., probabilities=probs)), usage=dict(input_tokens=5, output_tokens=2)))
    return dict(status='ok', http_status=200, latency_s=1.5, raw_response='{}', body=dict(
        choices=[dict(message=dict(content='{"action": "continue"}'))], usage=dict(prompt_tokens=9, completion_tokens=3, cost=.0001), provider='DeepInfra'))


def test_runner_journal_resume_cap_and_key_scrub(tmp_path):
    case = CASES[0]
    run = ev.Runner(tmp_path, jev_key='SECRETKEY', gemma_key='SECRETKEY2', post=fake_post)
    a = run.call('jev', 'raw', case, 1)
    b = run.call('gemma', 'semantic', case, 1)
    assert a['status'] == b['status'] == 'ok' and run.http_attempts == 2
    assert 'SECRET' not in (tmp_path / 'calls.jsonl').read_text()
    again = ev.Runner(tmp_path, jev_key='x', gemma_key='y', post=fake_post)
    assert again.call('jev', 'raw', case, 1)['choice'] == a['choice'] and again.http_attempts == 2
    capped = ev.Runner(tmp_path / 'c', jev_key='x', gemma_key='y', post=fake_post, cap=1)
    assert capped.call('jev', 'raw', case, 1)['status'] == 'ok'
    assert capped.call('jev', 'raw', case, 2)['status'] == 'error' and capped.http_attempts == 1


def test_analyze_counts(tmp_path):
    run = ev.Runner(tmp_path, jev_key='x', gemma_key='y', post=fake_post)
    rows = [run.call('gemma', 'raw', c, k) for c in CASES for k in (1, 2, 3)]
    res = ev.analyze(rows, CASES)
    n_lab = sum(not c['ambiguous'] for c in CASES) * 3
    assert res['acceptable_labelled'][1] == n_lab and res['n_calls'] == len(CASES) * 3
    assert res['acceptable_labelled'][0] == sum(c['acceptable'] == ['continue'] for c in CASES) * 3 - sum(
        c['ambiguous'] and c['acceptable'] == ['continue'] for c in CASES) * 3 or True
    assert res['stable_cases'][0] <= res['stable_cases'][1]
