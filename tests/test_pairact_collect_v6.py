"""COLLECT_PREREG v6 fixes (dsh/pairact-carry-r1-v6): Codex v5 re-review (collect-v5-review-20261021).

3 (remaining): the gates read the episode command's options with a first-match reader while the wrapper's
argparse keeps the last one -- a duplicated --teacher-source passed stack / verify_assets / CORE / final with
the wrapper running the other path.  New: the first merge trusted attempt.bin over the planned slot's bin.
Each test is the Codex counterexample (duplicate-source-proof.json, bin-merge-results.json).  CPU only.
"""
import argparse
import json
import shlex

import pytest

from harness import pairact_collect as pc
from test_pairact_collect import PREREG, FakeEpisode, result, runner
from test_pairact_collect_v5 import _stack, prereg_core


@pytest.fixture
def prereg():
    return json.loads(PREREG.read_text())


# ------------------------------------------------------------ 3. one reading of the episode options

def test_episode_option_refuses_what_argparse_would_resolve_differently():
    tok = shlex.split
    assert pc.episode_option(tok('w.py --teacher-source /a --out x'), '--teacher-source') == '/a'
    assert pc.episode_option(tok('w.py --teacher-source=/a --out x'), '--teacher-source') == '/a'
    assert pc.episode_option(tok('w.py --out x'), '--teacher-source') is None
    for cmd, match in (('w.py --teacher-source /a --teacher-source /b', '2 times'),
                       ('w.py --teacher-source /a --teacher-source=/b', '2 times'),
                       ('w.py --teacher-source=/a --teacher-source=/b', '2 times'),
                       ('w.py --teacher-sour /b', 'abbreviates'),
                       ('w.py --teacher-sour=/b --teacher-source /a', 'abbreviates'),
                       ('w.py --teacher-source', 'no value')):
        with pytest.raises(ValueError, match=match):
            pc.episode_option(tok(cmd), '--teacher-source')


def test_accepted_option_is_the_value_argparse_runs():
    """Whatever episode_option accepts, a wrapper-style argparse parser resolves to the same value."""
    p = argparse.ArgumentParser()
    for flag in pc.EPISODE_VALUE_FLAGS:
        p.add_argument(flag)
    p.add_argument('--out')
    for cmd in ('--teacher-source /a --adapter-source /b --cap-s 60 --out o',
                '--teacher-source=/a --adapter-source=/b --cap-s=60 --out o',
                '--adapter-source /b --teacher-source=/a --rejection-table /t.json --out o'):
        ns = vars(p.parse_args(shlex.split(cmd)))
        for flag in pc.EPISODE_VALUE_FLAGS:
            assert pc.episode_option(shlex.split(cmd), flag) == ns[flag[2:].replace('-', '_')], (cmd, flag)


def _dup(template, flag, last):
    """Codex duplicate-source-proof: keep the checked first value, append the value argparse would run."""
    i = template.index(' --out ')
    return template[:i] + f' {flag} {last}' + template[i:]


def _with(m, tpl):
    import hashlib
    m['command'].update(episode_template=tpl, episode_template_sha256=hashlib.sha256(tpl.encode()).hexdigest())
    return m


@pytest.mark.parametrize('flag', ['--teacher-source', '--adapter-source'])
def test_duplicate_episode_source_is_refused_by_stack_check(tmp_path, flag):
    env = dict(WARP_SOURCE_ROOT=str(tmp_path / 'src' / 'root'))
    m, roots = _stack(tmp_path)
    assert pc.check_stack_heads(m, roots, env=env)['teacher'] == m['stack']['teacher']['sha']     # control
    _with(m, _dup(m['command']['episode_template'], flag, f'/nonexistent/review-{flag[2:]}'))
    with pytest.raises(ValueError, match=f'names {flag} 2 times'):
        pc.check_stack_heads(m, roots, env=env)


def test_duplicate_warp_source_root_is_refused(tmp_path):
    m, roots = _stack(tmp_path, warp_root_in_template=True)
    assert pc.check_stack_heads(m, roots, env={})['root'] == m['stack']['root']['sha']
    _with(m, 'WARP_SOURCE_ROOT=/nonexistent/review-root ' + m['command']['episode_template'])
    with pytest.raises(ValueError, match='WARP_SOURCE_ROOT more than once'):
        pc.check_stack_heads(m, roots, env={})


def _gate(m, **kw):
    try:
        pc.check_run_manifest(m, prereg=prereg_core(), **kw)
    except ValueError as e:
        return str(e)
    return ''


@pytest.mark.parametrize('stage', ['core', 'final'])
@pytest.mark.parametrize('flag,last', [('--teacher-source', '/nonexistent/review-teacher'),
                                       ('--adapter-source', '/nonexistent/review-adapter'),
                                       ('--rejection-table', '/nonexistent/review-table.json'),
                                       ('--canonical-xml', '/nonexistent/review-scene.xml'),
                                       ('--per-world-model-references-v1', '/nonexistent/review-refs.json'),
                                       ('--cap-s', '90')])
def test_duplicate_episode_option_is_refused_by_core_and_final(tmp_path, stage, flag, last):
    """The static manifest gate refuses the duplicate at every stage, with or without verify_assets."""
    m, _ = _stack(tmp_path)
    tpl = m['command']['episode_template'].replace(
        ' --out ', ' --canonical-xml /abs/scene.xml --per-world-model-references-v1 /abs/refs.json --out ')
    _with(m, tpl)
    assert 'times; give it once' not in _gate(m, stage=stage)                       # control: single values
    _with(m, _dup(tpl, flag, last))
    for kw in ({}, dict(verify_assets=True)):
        assert f'names {flag} 2 times' in _gate(m, stage=stage, **kw)


def test_episode_cmd_audit_reads_the_same_single_value():
    base = 'python /w/wrap.py --cases {cases} --indices {indices} --cap-s 60 --rejection-table /t.json --out {out}'
    assert pc.episode_cmd_audit(base)['rejection_table_input'] == '/t.json'
    assert pc.episode_cmd_audit(base.replace('--cap-s 60', '--cap-s=60'))['cap_s'] == 60.0
    for bad in (base + ' --rejection-table=/other.json', base.replace('--cap-s 60', '--cap-s 60 --cap-s 90')):
        with pytest.raises(ValueError, match='2 times'):
            pc.episode_cmd_audit(bad)


# ------------------------------------------------------------ new: attempt bin = planned slot bin

def test_attempt_bin_must_be_the_planned_slot_bin(prereg):
    plan = dict(type='batch_planned', batch=0, split='train', bin='B0',
                slots=[dict(seed=1, bin='B0', split='train', slot=0, requeue=False)])
    att = lambda b: dict(type='attempt', batch=0, slot=0, seed=1, split='train', bin=b, requeue=False)
    hdr = pc.header('sha', mode='training', noise='off', batch_size=20)
    assert pc.check_attempt_identity(pc.replay(prereg, [hdr, plan, att('B0')])) == 1
    with pytest.raises(ValueError, match='planned slot'):
        pc.check_attempt_identity(pc.replay(prereg, [hdr, plan, att('B5')]))


def test_first_merge_refuses_a_relabelled_bin(tmp_path, prereg):
    """bin-merge-results: v5 merged one attempt changed B0->B5 as N40 finished=true."""
    from test_pairact_collect_shard import run_cooperative
    eps = {i: FakeEpisode(lambda s, c: result()) for i in range(2)}
    run_cooperative(tmp_path, prereg, 2, eps, mode='measurement')
    led = runner.shard_dir(tmp_path, 0) / 'ledger.jsonl'
    rows = pc.read_ledger(led)
    k = next(i for i, r in enumerate(rows) if r.get('type') == 'attempt')
    other = next(b for b in pc.bin_ids(prereg) if b != rows[k]['bin'])
    rows[k] = dict(rows[k], bin=other)
    led.write_text(''.join(json.dumps(r, sort_keys=True, allow_nan=False) + '\n' for r in rows))
    with pytest.raises(ValueError, match='planned slot'):
        runner.merge(tmp_path, prereg, 'sha', 2)
    assert not (tmp_path / 'merged' / 'report.json').exists()
