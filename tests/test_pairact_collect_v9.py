"""COLLECT_PREREG v9 (dsh/pairact-carry-r1-v9): the threat model is accidental inconsistency, not an attacker.

g: a stale PYTHONPATH / PYTHONHOME in the shell that starts the collector would change the episode imports
(the wrapper inserts its stack paths itself), so a strict pin refuses it, the gate reports it once with a clean
message, and a strict launch drops it from the exec env even for a hand-built pin.  h: the v8 gate checked the
teacher / adapter / root checkouts only before the first launch, so a multi-hour run kept launching against a
checkout edited after the gate; the observed stack is now bound into the launch binding and re-observed after
every episode, and consumers refuse a difference.  subprocess.call is a stub (no teacher / simulator).  CPU only.
"""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import pairact_collect as pc
from test_pairact_collect import EP_CMD, EP_PYTHON, FAKE_WRAPPER, filled_manifest, runner
from test_pairact_collect_v5 import _repo, prereg_core

CORE = 'c' * 64
BIND = dict(stage='core', core=CORE, manifest_sha256='m' * 64)
ROLES = ('teacher', 'adapter', 'root')


def _env(**kw):
    """The exec env without the variables v9 controls or the stack check reads."""
    e = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME', 'WARP_SOURCE_ROOT')}
    e.update(kw)
    return e


@pytest.fixture
def calls(monkeypatch):
    """subprocess.call stub of the runner: records (argv, env, cwd); ``calls.during`` runs inside the 'teacher'."""
    seen = []

    def call(argv, env=None, cwd=None, **kw):
        seen.append(dict(argv=list(argv), env=dict(env or {}), cwd=cwd))
        if getattr(calls_obj, 'during', None):
            calls_obj.during()
        return 0
    calls_obj = type('Calls', (), {})()
    calls_obj.seen = seen
    monkeypatch.setattr(runner.subprocess, 'call', call)
    return calls_obj


def _stack3(tmp_path):
    """Three real git checkouts pinned in a filled manifest + the template that names them."""
    roots = {r: tmp_path / 'src' / r for r in ROLES}
    m = filled_manifest(prereg_core())
    for r, path in roots.items():
        m['stack'][r]['sha'] = _repo(path)
    tpl = (f"WARP_SOURCE_ROOT={roots['root']} {EP_PYTHON} {FAKE_WRAPPER} --flow beampair --adapter-source "
           f"{roots['adapter']} --teacher-source {roots['teacher']} --cases {{cases}} --indices {{indices}} "
           f"--cap-s 60 --rejection-table /abs/table.json --out {{out}}")
    m['command'].update(episode_template=tpl, episode_template_sha256=hashlib.sha256(tpl.encode()).hexdigest())
    return m, roots, tpl


def _raw(out):
    raw = Path(out) / 'world-000' / 'raw'
    raw.mkdir(parents=True)
    return raw


# ------------------------------------------------------------ g: PYTHONPATH / PYTHONHOME

def test_g_pythonpath_in_the_exec_env_is_refused_by_a_strict_pin_only(tmp_path):
    for key in pc.EPISODE_ENV_UNBOUND:
        with pytest.raises(pc.EpisodePinError, match=key):
            pc.episode_pin(EP_CMD, cwd=str(tmp_path), env=_env(**{key: '/stale/site-packages'}))
    pin = pc.episode_pin(EP_CMD, cwd=str(tmp_path), env=_env(PYTHONPATH='/stale'), strict=False)   # pilot
    assert pin['strict'] is False
    clean = pc.episode_pin(EP_CMD, cwd=str(tmp_path), env=_env())
    assert clean['strict'] is True and clean['wrapper_sha256'] == pc.file_sha256(FAKE_WRAPPER)


def test_g_launch_refuses_when_pythonpath_appears_after_the_gate(tmp_path, calls, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pin = pc.episode_pin(EP_CMD, cwd=os.getcwd(), env=_env())
    with pytest.raises(pc.EpisodePinError, match='episode not launched'):
        runner.shell_episode(EP_CMD, _env(PYTHONPATH='/stale'), BIND, pin)(tmp_path / 'c.json', [0], tmp_path / 'o')
    assert calls.seen == []                                            # nothing ran with the changed imports


def test_g_pinned_exec_drops_unbound_env_for_strict_pins_only(tmp_path):
    clean = pc.episode_pin(EP_CMD, cwd=str(tmp_path), env=_env())
    argv = [EP_PYTHON, FAKE_WRAPPER]
    _, env = pc.pinned_exec(clean, argv, _env(PYTHONPATH='/stale', PYTHONHOME='/home'), {})
    assert 'PYTHONPATH' not in env and 'PYTHONHOME' not in env
    pilot = pc.episode_pin(EP_CMD, cwd=str(tmp_path), env=_env(PYTHONPATH='/stale'), strict=False)
    _, env = pc.pinned_exec(pilot, argv, _env(PYTHONPATH='/stale', PYTHONHOME='/home'), {})
    assert env['PYTHONPATH'] == '/stale'                               # the pilot keeps the shell it was started in


def test_g_gate_reports_pythonpath_once_with_the_command_name(tmp_path):
    m = filled_manifest(prereg_core())
    m['assets']['wrapper_sha256'] = pc.file_sha256(FAKE_WRAPPER)
    path = tmp_path / 'RUN_MANIFEST.json'
    path.write_text(json.dumps(m))
    a = SimpleNamespace(command='probe-episode', episode_cmd=EP_CMD, run_manifest=path)
    with pytest.raises(SystemExit) as e:
        runner.gate_pin(a, _env(PYTHONPATH='/stale'))
    assert 'probe-episode: episode pin refused: PYTHONPATH is set' in str(e.value)
    assert runner.gate_pin(a, _env())['wrapper_sha256'] == pc.file_sha256(FAKE_WRAPPER)   # clean env still passes


# ------------------------------------------------------------ h: the stack observed before and after each launch

def test_h_stack_changed_during_the_episode_refuses_the_output(tmp_path, calls, monkeypatch):
    m, roots, tpl = _stack3(tmp_path)
    stack = pc.observe_stack(roots)
    assert pc.stack_manifest_problems(stack, m) == []                   # control: the gate sees the manifest pins
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'out'
    calls.during = lambda: (roots['teacher'] / 'f.txt').write_text('edited during the run\n')
    assert runner.shell_episode(tpl, _env(), dict(BIND, stack=stack), None,
                                lambda: pc.observe_stack(roots))(tmp_path / 'c.json', [0], out) == 0
    rec = json.loads(pc.launch_binding_path(out).read_text())
    assert rec['stack']['teacher']['dirty'] is False and rec['stack_post']['teacher']['dirty'] is True
    assert 'episode stack teacher changed while the teacher ran' in \
        pc.launch_binding_problems(_raw(out), CORE, ('core',))[0]       # v8: this run looked like any other
    assert calls.seen[0]['argv'][:2] == [EP_PYTHON, FAKE_WRAPPER]


def test_h_a_clean_run_is_accepted_with_pin_and_stack_posts(tmp_path, calls, monkeypatch):
    m, roots, tpl = _stack3(tmp_path)
    stack = pc.observe_stack(roots)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'out'
    assert runner.shell_episode(tpl, _env(), dict(BIND, stack=stack), None,
                                lambda: pc.observe_stack(roots))(tmp_path / 'c.json', [0], out) == 0
    rec = json.loads(pc.launch_binding_path(out).read_text())
    assert rec['pin'] == rec['pin_post'] and rec['stack'] == rec['stack_post'] == stack
    assert pc.launch_binding_problems(_raw(out), CORE, ('core',)) == []


def test_h_binding_without_a_stack_pin_or_a_post_stack_is_refused(tmp_path):
    out = tmp_path / 'out'
    (out / 'w').mkdir(parents=True)
    pin = pc.episode_pin(EP_CMD, cwd=str(tmp_path), env=_env())
    rec = pc.launch_binding(stage='core', core=CORE, manifest_sha256='m' * 64, template=EP_CMD, argv=['x'],
                            cwd=tmp_path, out=out, pin=pin)
    pc.launch_binding_path(out).write_text(json.dumps(dict(rec, pin_post=pin)))    # v8-shaped: pin only
    assert 'has no stack pin' in pc.launch_binding_problems(out / 'w', CORE, ('core',))[0]
    stack = dict(teacher=dict(path='/s/t', head='a' * 40, dirty=False),
                 adapter=dict(path='/s/a', head='b' * 40, dirty=False),
                 root=dict(path='/s/r', head='c' * 40, dirty=False))
    rec2 = pc.launch_binding(stage='core', core=CORE, manifest_sha256='m' * 64, template=EP_CMD, argv=['x'],
                             cwd=tmp_path, out=out, pin=pin, stack=stack)
    pc.launch_binding_path(out).write_text(json.dumps(dict(rec2, pin_post=pin)))   # crashed runner: no stack_post
    assert 'has no post-run stack' in pc.launch_binding_problems(out / 'w', CORE, ('core',))[0]


def test_h_unreadable_post_run_stack_is_refused(tmp_path, calls, monkeypatch):
    m, roots, tpl = _stack3(tmp_path)
    stack = pc.observe_stack(roots)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'out'

    def gone():
        raise ValueError(f'stack teacher checkout {roots["teacher"]} is not a git checkout')
    assert runner.shell_episode(tpl, _env(), dict(BIND, stack=stack), None, gone)(tmp_path / 'c.json', [0], out) == 0
    assert 'post-run stack unreadable' in pc.launch_binding_problems(_raw(out), CORE, ('core',))[0]


def test_h_stack_gate_binds_the_manifest_pins_and_sees_a_later_edit(tmp_path):
    m, roots, tpl = _stack3(tmp_path)
    a = SimpleNamespace(command='collect', dependency_root=roots['teacher'], adapter_root=roots['adapter'],
                        frozen_root=roots['root'])
    stack, stack_now = runner.stack_gate(a, m, env={})
    assert [stack[r]['head'] for r in ROLES] == [m['stack'][r]['sha'] for r in ROLES]
    assert stack_now() == stack
    (roots['root'] / 'f.txt').write_text('edited\n')
    assert pc.stack_changed(stack, stack_now()) == ['root']
    assert 'has tracked changes' in pc.stack_manifest_problems(stack_now(), m)[0]
    (roots['root'] / 'f.txt').write_text('root')                       # reverted: the observed state is clean again
    assert pc.stack_changed(stack, stack_now()) == []


def test_h_stack_manifest_problems_reports_a_wrong_head(tmp_path):
    m, roots, _ = _stack3(tmp_path)
    observed = pc.observe_stack(roots)
    m['stack']['adapter']['sha'] = 'f' * 40
    assert 'RUN_MANIFEST pins' in pc.stack_manifest_problems(observed, m)[0]


# ------------------------------------------------------------ i: the executed wrapper is the pinned wrapper

def test_i_pinned_exec_refuses_a_wrapper_other_than_the_pin(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _wrapper(tmp_path / 'w' / 'wrap.py')
    pin = pc.episode_pin(_rel_template(), cwd=os.getcwd(), env=_env(), strict=False)
    argv, _ = pc.pinned_exec(pin, [EP_PYTHON, 'w/wrap.py'], _env(), {})    # pilot: relative name, same file
    assert argv[1] == 'w/wrap.py'
    with pytest.raises(pc.EpisodePinError, match='is not the pinned'):
        pc.pinned_exec(pin, [EP_PYTHON, 'w/other.py'], _env(), {})
    strict = pc.episode_pin(EP_CMD, cwd=str(tmp_path), env=_env())
    with pytest.raises(pc.EpisodePinError, match='is not the pinned'):
        pc.pinned_exec(strict, [EP_PYTHON, FAKE_WRAPPER + '.bak'], _env(), {})
    ok, _ = pc.pinned_exec(strict, [EP_PYTHON, FAKE_WRAPPER], _env(), {})
    assert ok == [EP_PYTHON, FAKE_WRAPPER]


def _wrapper(path):
    from test_pairact_collect import FAKE_WRAPPER_SOURCE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FAKE_WRAPPER_SOURCE)
    return path


def _rel_template():
    return EP_CMD.replace(FAKE_WRAPPER, 'w/wrap.py', 1)
