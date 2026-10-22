"""COLLECT_PREREG v8 (dsh/pairact-carry-r1-v8): Codex v7 4th review -- the wrapper the gates checked (parser,
sha256) was not necessarily the file that ran.

a: relative wrapper token resolved at the gate cwd vs the exec cwd; b: a missing named wrapper was read through
the repository copy (REPO_WRAPPER) while the named path ran; c: a symlink in any wrapper path component, and the
wrapper changed between gate and launch (or while running); d: bare ``python`` resolved through the exec PATH;
e: WARP_SOURCE_ROOT token vs env; f: the normal command is still accepted end to end.  subprocess.call is a stub
(no teacher / simulator runs).  CPU only.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

from harness import pairact_collect as pc
from test_pairact_collect import EP_CMD, EP_PYTHON, FAKE_WRAPPER, FAKE_WRAPPER_SOURCE, filled_manifest, runner
from test_pairact_collect_v5 import _repo, prereg_core

CORE = 'c' * 64
BIND = dict(stage='core', core=CORE, manifest_sha256='m' * 64)


def _tpl(wrapper=FAKE_WRAPPER, python=EP_PYTHON, root=None):
    t = EP_CMD.replace(FAKE_WRAPPER, str(wrapper)).replace(EP_PYTHON, python, 1)
    return t if root is None else f'WARP_SOURCE_ROOT={root} {t}'


def _core_gate(tpl, **kw):
    m = filled_manifest(prereg_core())
    m['command'].update(episode_template=tpl, episode_template_sha256=hashlib.sha256(tpl.encode()).hexdigest())
    try:
        pc.check_run_manifest(m, stage='core', prereg=prereg_core(), **kw)
    except ValueError as e:
        return str(e)
    return ''


def _wrapper(path, extra=''):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FAKE_WRAPPER_SOURCE + extra)
    return path


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


# ------------------------------------------------------------ a: relative wrapper + cwd difference

def test_a_relative_wrapper_is_refused_by_the_gate_and_the_launch(tmp_path, monkeypatch, calls):
    gate_cwd, run_cwd = tmp_path / 'A', tmp_path / 'B'
    _wrapper(gate_cwd / 'w' / 'wrap.py')
    _wrapper(run_cwd / 'w' / 'wrap.py', "\nOTHER = 1\n")          # another file under the same relative name
    tpl = _tpl('w/wrap.py')
    monkeypatch.chdir(gate_cwd)
    assert 'episode wrapper must be an absolute path' in _core_gate(tpl)         # v7: accepted (hashes A)
    monkeypatch.chdir(run_cwd)
    with pytest.raises(pc.EpisodePinError, match='absolute path'):
        runner.shell_episode(tpl, dict(os.environ), BIND)(tmp_path / 'c.json', [0], tmp_path / 'out')
    assert calls.seen == []                                                     # v7: ran B


# ------------------------------------------------------------ b: no REPO_WRAPPER stand-in at core / final

def test_b_missing_named_wrapper_is_not_read_through_the_repository_copy(tmp_path, calls):
    named = tmp_path / 'vm' / pc.REPO_WRAPPER.name                                # gcp6 name, file absent
    named.parent.mkdir()
    tpl = _tpl(named) + ' --adapter-source /s/adapter --teacher-source /s/teacher --vm-hourly-usd 1.096'
    err = _core_gate(tpl)    # (options the real gcp6 parser requires, so v7 read it through REPO_WRAPPER)
    assert f'episode wrapper {named} not found' in err, err                      # v7: passed via REPO_WRAPPER
    named.write_text('import os\n# a different program under the checked name\n')
    assert 'has no parser()' in _core_gate(tpl)                                   # the named file itself is read
    with pytest.raises(pc.EpisodePinError):
        runner.shell_episode(tpl, dict(os.environ), BIND, pc.episode_pin(_tpl(), cwd=os.getcwd()))(
            tmp_path / 'c.json', [0], tmp_path / 'out')
    assert calls.seen == []


# ------------------------------------------------------------ c: symlinks and gate -> launch changes

@pytest.mark.parametrize('where', ['file', 'parent', 'ancestor'])
def test_c_symlink_in_any_wrapper_path_component_is_refused(tmp_path, where, calls):
    real = _wrapper(tmp_path / 'real' / 'd' / 'wrap.py')
    if where == 'file':
        link = tmp_path / 'real' / 'd' / 'link.py'
        link.symlink_to(real)
    elif where == 'parent':
        (tmp_path / 'real' / 'ld').symlink_to(tmp_path / 'real' / 'd')
        link = tmp_path / 'real' / 'ld' / 'wrap.py'
    else:
        (tmp_path / 'lr').symlink_to(tmp_path / 'real')
        link = tmp_path / 'lr' / 'd' / 'wrap.py'
    assert link.is_file()
    assert 'is not its own realpath' in _core_gate(_tpl(link))                   # v7: accepted
    with pytest.raises(pc.EpisodePinError, match='realpath'):
        runner.shell_episode(_tpl(link), dict(os.environ), BIND)(tmp_path / 'c.json', [0], tmp_path / 'out')
    assert calls.seen == []


def test_c_dotdot_component_is_refused(tmp_path):
    _wrapper(tmp_path / 'd' / 'wrap.py')
    assert 'is not its own realpath' in _core_gate(_tpl(f'{tmp_path}/x/../d/wrap.py'))


@pytest.mark.parametrize('swap', ['content', 'symlink_target', 'replace_with_symlink'])
def test_c_wrapper_changed_after_the_gate_is_not_launched(tmp_path, swap, calls, monkeypatch):
    wrap = _wrapper(tmp_path / 'w' / 'wrap.py')
    tpl = _tpl(wrap)
    monkeypatch.chdir(tmp_path)
    pin = pc.episode_pin(tpl, cwd=os.getcwd())                                    # what the gate checked
    if swap == 'content':
        wrap.write_text(FAKE_WRAPPER_SOURCE + '\nimport os; os.system("echo other")\n')
    else:
        other = _wrapper(tmp_path / 'evil' / 'wrap.py', '\nEVIL = 1\n')
        wrap.unlink()
        wrap.symlink_to(other)
    with pytest.raises(pc.EpisodePinError, match='episode not launched'):
        runner.shell_episode(tpl, dict(os.environ), BIND, pin)(tmp_path / 'c.json', [0], tmp_path / 'out')
    assert calls.seen == []                                                      # v7: ran the new file


def test_c_wrapper_changed_while_running_refuses_the_output(tmp_path, calls, monkeypatch):
    wrap = _wrapper(tmp_path / 'w' / 'wrap.py')
    tpl = _tpl(wrap)
    monkeypatch.chdir(tmp_path)
    pin = pc.episode_pin(tpl, cwd=os.getcwd())
    calls.during = lambda: wrap.write_text(FAKE_WRAPPER_SOURCE + '\nSWAPPED = 1\n')
    out = tmp_path / 'out'
    assert runner.shell_episode(tpl, dict(os.environ), BIND, pin)(tmp_path / 'c.json', [0], out) == 0
    rec = json.loads(pc.launch_binding_path(out).read_text())
    assert rec['pin']['wrapper_sha256'] == pin['wrapper_sha256'] != rec['pin_post']['wrapper_sha256']
    raw = out / 'world-000' / 'raw'
    raw.mkdir(parents=True)
    assert 'wrapper_sha256 changed while the teacher ran' in pc.launch_binding_problems(raw, CORE, ('core',))[0]


def test_c_binding_without_post_pin_or_pin_is_refused(tmp_path):
    out = tmp_path / 'out'
    (out / 'w').mkdir(parents=True)
    rec = pc.launch_binding(stage='core', core=CORE, manifest_sha256='m' * 64, template=EP_CMD, argv=['x'],
                            cwd=tmp_path, out=out)                                 # v7-shaped: no pin
    pc.launch_binding_path(out).write_text(json.dumps(rec))
    assert 'no strict episode pin' in pc.launch_binding_problems(out / 'w', CORE, ('core',))[0]
    pin = pc.episode_pin(EP_CMD, cwd=str(tmp_path))
    pc.launch_binding_path(out).write_text(json.dumps(dict(rec, pin=pin)))     # crashed runner: no pin_post
    assert 'no post-run pin' in pc.launch_binding_problems(out / 'w', CORE, ('core',))[0]


# ------------------------------------------------------------ d: interpreter through PATH

def test_d_bare_python_is_refused_at_core_and_at_a_frozen_launch(tmp_path, calls, monkeypatch):
    tpl = _tpl(python='python')
    assert "episode python 'python' must be an absolute path" in _core_gate(tpl)   # v7: accepted
    fake = tmp_path / 'bin' / 'python'
    fake.parent.mkdir()
    fake.write_text('#!/bin/sh\necho not the checked interpreter\n')
    fake.chmod(0o755)
    env = dict(os.environ, PATH=f'{fake.parent}:{os.environ.get("PATH", "")}')
    with pytest.raises(pc.EpisodePinError, match='absolute path'):
        runner.shell_episode(tpl, env, BIND)(tmp_path / 'c.json', [0], tmp_path / 'out')
    assert calls.seen == []                                                      # v7: ran tmp/bin/python


def test_d_pilot_bare_python_runs_the_path_resolved_once(tmp_path, calls):
    fake = tmp_path / 'bin' / 'python'
    fake.parent.mkdir()
    fake.write_text('#!/bin/sh\n')
    fake.chmod(0o755)
    env = dict(os.environ, PATH=f'{fake.parent}:/usr/bin')
    runner.shell_episode(_tpl(python='python'), env)(tmp_path / 'c.json', [0], tmp_path / 'out')
    assert calls.seen[0]['argv'][0] == str(fake)                                  # absolute, not re-looked-up


def test_d_interpreter_swapped_after_the_gate_is_not_launched(tmp_path, calls, monkeypatch):
    py = tmp_path / 'py' / 'python3'
    py.parent.mkdir()
    py.write_bytes(b'#!/bin/sh\n')
    monkeypatch.chdir(tmp_path)
    tpl = _tpl(python=str(py))
    pin = pc.episode_pin(tpl, cwd=os.getcwd())
    py.write_bytes(b'#!/bin/sh\necho swapped\n')
    with pytest.raises(pc.EpisodePinError, match='python_sha256'):
        runner.shell_episode(tpl, dict(os.environ), BIND, pin)(tmp_path / 'c.json', [0], tmp_path / 'out')
    assert calls.seen == []


# ------------------------------------------------------------ e: WARP_SOURCE_ROOT token vs env

def _stack3(tmp_path, root_token):
    roots = {r: tmp_path / 'src' / r for r in ('teacher', 'adapter', 'root')}
    m = filled_manifest(prereg_core())
    for r, path in roots.items():
        m['stack'][r]['sha'] = _repo(path)
    tpl = (f"WARP_SOURCE_ROOT={root_token} {EP_PYTHON} {FAKE_WRAPPER} --flow beampair --adapter-source "
           f"{roots['adapter']} --teacher-source {roots['teacher']} --cases {{cases}} --indices {{indices}} "
           f"--cap-s 60 --rejection-table /abs/table.json --out {{out}}")
    m['command'].update(episode_template=tpl, episode_template_sha256=hashlib.sha256(tpl.encode()).hexdigest())
    return m, roots, tpl


def test_e_root_token_and_env_disagreeing_is_refused(tmp_path, calls, monkeypatch):
    m, roots, tpl = _stack3(tmp_path, tmp_path / 'src' / 'root')
    assert pc.check_stack_heads(m, roots, env={})['root'] == m['stack']['root']['sha']          # control
    other = dict(WARP_SOURCE_ROOT=str(tmp_path / 'elsewhere'))
    with pytest.raises(pc.EpisodePinError, match='WARP_SOURCE_ROOT token'):
        pc.check_stack_heads(m, roots, env=other)                                 # v7: template won silently
    monkeypatch.chdir(tmp_path)
    with pytest.raises(pc.EpisodePinError, match='WARP_SOURCE_ROOT token'):
        runner.shell_episode(tpl, dict(os.environ, **other), BIND)(tmp_path / 'c.json', [0], tmp_path / 'out')
    assert calls.seen == []


def test_e_exec_env_carries_the_pinned_root_realpath(tmp_path, calls, monkeypatch):
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src' / 'real-root').mkdir()
    (tmp_path / 'src' / 'root-link').symlink_to(tmp_path / 'src' / 'real-root')
    tpl = _tpl(root=tmp_path / 'src' / 'root-link')
    monkeypatch.chdir(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != 'WARP_SOURCE_ROOT'}
    runner.shell_episode(tpl, env, BIND)(tmp_path / 'c.json', [0], tmp_path / 'out')
    assert calls.seen[0]['env']['WARP_SOURCE_ROOT'] == str(tmp_path / 'src' / 'real-root')
    # no root named anywhere: an inherited value cannot sneak into the exec env
    runner.shell_episode(_tpl(), env, BIND)(tmp_path / 'c.json', [0], tmp_path / 'out2')
    assert 'WARP_SOURCE_ROOT' not in calls.seen[1]['env']


def test_e_root_changed_after_the_gate_is_not_launched(tmp_path, calls, monkeypatch):
    for d in ('r1', 'r2'):
        (tmp_path / d).mkdir()
    (tmp_path / 'root').symlink_to(tmp_path / 'r1')
    tpl = _tpl(root=tmp_path / 'root')
    monkeypatch.chdir(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != 'WARP_SOURCE_ROOT'}
    pin = pc.episode_pin(tpl, cwd=os.getcwd(), env=env)
    (tmp_path / 'root').unlink()
    (tmp_path / 'root').symlink_to(tmp_path / 'r2')
    with pytest.raises(pc.EpisodePinError, match='root'):
        runner.shell_episode(tpl, env, BIND, pin)(tmp_path / 'c.json', [0], tmp_path / 'out')
    assert calls.seen == []


# ------------------------------------------------------------ f: the normal command is accepted

def test_f_normal_command_passes_the_gate_and_runs_the_pinned_values(tmp_path, calls, monkeypatch):
    assert _core_gate(EP_CMD) == ''
    monkeypatch.chdir(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != 'WARP_SOURCE_ROOT'}
    pin = pc.episode_pin(EP_CMD, cwd=os.getcwd(), env=env)
    assert pin['wrapper'] == FAKE_WRAPPER and pin['wrapper_sha256'] == pc.file_sha256(FAKE_WRAPPER)
    assert pin['python'] == EP_PYTHON and pin['python_realpath'] == os.path.realpath(EP_PYTHON)
    out = tmp_path / 'out'
    assert runner.shell_episode(EP_CMD, env, BIND, pin)(tmp_path / 'c.json', [0, 1], out) == 0
    (call,) = calls.seen
    assert call['argv'][:2] == [EP_PYTHON, FAKE_WRAPPER] and call['cwd'] == str(tmp_path)
    rec = json.loads(pc.launch_binding_path(out).read_text())
    assert rec['pin'] == rec['pin_post'] == pin
    raw = out / 'world-000' / 'raw'
    raw.mkdir(parents=True)
    assert pc.launch_binding_problems(raw, CORE, ('core',)) == []


def test_f_verify_assets_hashes_the_pinned_wrapper(tmp_path):
    """The gate's assets.wrapper_sha256 check reads the same resolver the runner pins."""
    assert pc.resolve_episode_wrapper(EP_CMD)[0] == dict(path=FAKE_WRAPPER, sha256=pc.file_sha256(FAKE_WRAPPER))
    err = _core_gate(EP_CMD, verify_assets=True)
    assert 'assets.wrapper_sha256 differs' in err                       # filled manifest carries a dummy hash
    m = filled_manifest(prereg_core())
    m['assets']['wrapper_sha256'] = pc.file_sha256(FAKE_WRAPPER)
    try:
        pc.check_run_manifest(m, stage='core', prereg=prereg_core(), verify_assets=True)
    except ValueError as e:
        assert 'wrapper_sha256' not in str(e)
