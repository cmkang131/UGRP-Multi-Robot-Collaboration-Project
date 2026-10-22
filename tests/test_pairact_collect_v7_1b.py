"""COLLECT_PREREG v7-1b (dsh/pairact-carry-r1-v7-1b): Codex v6 re-review (collect-v6-review-20261021).

risk 2: the gates read template tokens while the runner handed the string to ``shell=True`` -- a standalone
``--``, a value-less option or ``--unknown`` passed the gate but the wrapper parser exits 2, and env / cwd
shell syntax was never compared.  1b: a teacher run outside the collector (PAIRACT_P3_* env set by hand) was
not bound to the manifest core.  XML: the teacher compiles --canonical-xml from a string, so relative names
resolve against the process cwd, not the XML directory.  CPU only, no simulator import.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from harness import pairact_collect as pc
from test_pairact_collect import runner
from test_pairact_collect_v5 import _stack, prereg_core

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / 'experiments/2026-10-21-pairact-r1'
BASE = ('python /w/wrap.py --flow beampair --adapter-source /s/adapter --teacher-source /s/teacher '
        '--cases {cases} --indices {indices} --cap-s 60 --rejection-table /abs/table.json --out {out}')


def _draft_template():
    """RUN_MANIFEST episode_template_draft with $SRC expanded (the real gcp6 wrapper command)."""
    m = json.loads((EXP / 'RUN_MANIFEST.json').read_text())
    return m['command']['episode_template_draft'].replace('$SRC', '/home/ugrp/ugrp-sim/src/pairact-c5').replace('$PY', '/venv/bin/python')


def _with(m, tpl):
    import hashlib
    m['command'].update(episode_template=tpl, episode_template_sha256=hashlib.sha256(tpl.encode()).hexdigest())
    return m


def _gate(m, **kw):
    try:
        pc.check_run_manifest(m, prereg=prereg_core(), **kw)
    except ValueError as e:
        return str(e)
    return ''


# ------------------------------------------------------------ risk 2: one explicit command form

@pytest.mark.parametrize('bad,match', [
    ('env -i ' + BASE, 'must start with python'),
    ('cd /tmp && ' + BASE, 'shell operators'),
    ('cd /tmp; ' + BASE, 'shell operators'),
    (BASE + ' ; true', 'shell operators'),
    (BASE + ' && true', 'shell operators'),
    (BASE + ' | tee log', 'shell operators'),
    (BASE + ' > log', 'shell operators'),
    (BASE + ' &', 'shell operators'),
    ('(' + BASE + ')', 'shell operators'),
    ('sh -c ' + repr(BASE), 'must start with python'),
    ('exec ' + BASE, 'must start with python'),
    ('nohup ' + BASE, 'must start with python'),
    ('PYTHONPATH=/x ' + BASE, 'may only set'),
    ('WARP_SOURCE_ROOT=rel/root ' + BASE, 'must be absolute'),
    ('WARP_SOURCE_ROOT=/a WARP_SOURCE_ROOT=/b ' + BASE, 'may only set'),
    (BASE.replace('python /w/wrap.py', 'python -I /w/wrap.py'), 'no interpreter options'),
    (BASE.replace('python /w/wrap.py', 'python -c pass'), 'no interpreter options'),
    (BASE.replace(' --out ', ' -- --out '), 'standalone --'),
    (BASE.replace(' --cap-s 60', ' -x --cap-s 60'), 'short options'),
    (BASE + ' $(true)', r'\$'),
    (BASE + ' `true`', 'backtick'),
])
def test_episode_command_form_refuses_shell_syntax(bad, match):
    assert pc.episode_command_form(BASE)[2] == '/w/wrap.py'                          # control
    assert pc.episode_command_form('WARP_SOURCE_ROOT=/r python3.12 ' + BASE[7:])[0] == dict(WARP_SOURCE_ROOT='/r')
    with pytest.raises(ValueError, match=match):
        pc.episode_command_form(bad)
    with pytest.raises(ValueError):
        pc.episode_cmd_audit(bad)


def test_real_wrapper_parser_accepts_the_manifest_draft_command():
    """The gcp6 wrapper's own parser() reads the RUN_MANIFEST draft command; gate values == parser values."""
    tpl = _draft_template()
    assert pc.episode_command_problems(tpl) == []
    p = pc.wrapper_parser(pc.REPO_WRAPPER)
    assert '--canonical-xml' in p._option_string_actions
    assert pc.episode_cmd_audit(tpl)['cap_s'] == 60.0


@pytest.mark.parametrize('edit,match', [
    (lambda t: t.replace(' --cap-s 60', ' --cap-s'), 'wrapper parser refuses'),             # value-less option
    (lambda t: t.replace(' --teacher-source ', ' --teacher-source --unknown '), 'not a wrapper option'),
    (lambda t: t + ' --unknown', 'not a wrapper option'),
    (lambda t: t + ' --unknown=1', 'not a wrapper option'),
    (lambda t: t.replace('--batch-per-world-speed-v1', '--batch-per-world'), 'not a wrapper option'),  # abbrev
    (lambda t: t + ' stray', 'unread'),
    (lambda t: t.replace(' --cap-s 60', ' --cap-s sixty'), 'wrapper parser refuses'),
    (lambda t: t.replace(' --flow beampair', ''), 'wrapper parser refuses'),                 # required missing
])
def test_real_wrapper_parser_refuses_what_the_wrapper_would_exit_2_on(edit, match):
    """Codex v6 risk 1/2: the gate accepted these, the wrapper's argparse exits 2."""
    bad = edit(_draft_template())
    assert any(match in p for p in pc.episode_command_problems(bad)), pc.episode_command_problems(bad)
    with pytest.raises(ValueError):
        pc.episode_cmd_audit(bad)


@pytest.mark.parametrize('stage', ['core', 'final'])
@pytest.mark.parametrize('edit,match', [
    (lambda t: t.replace(' --out ', ' -- --out '), 'standalone --'),
    (lambda t: 'env -i ' + t, 'must start with python'),
    (lambda t: 'cd /tmp && ' + t, 'shell operators'),
    (lambda t: t + ' ; true', 'shell operators'),
])
def test_manifest_gate_refuses_form_violations_at_core_and_final(tmp_path, stage, edit, match):
    m, _ = _stack(tmp_path)
    assert 'episode command' not in _gate(m, stage=stage)                           # control
    _with(m, edit(m['command']['episode_template']))
    for kw in ({}, dict(verify_assets=True)):
        assert match in _gate(m, stage=stage, **kw)


CHILD = '''import json, os, sys
from pathlib import Path
out = Path(sys.argv[sys.argv.index('--out') + 1])
binding = out.parent / (out.name + '.pairact-binding.json')
out.mkdir(parents=True)
(out / 'seen.json').write_text(json.dumps(dict(argv=sys.argv[1:], cwd=os.getcwd(),
    root=os.environ.get('WARP_SOURCE_ROOT'), binding_at_start=binding.is_file())))
'''


def test_runner_executes_the_checked_argv_without_a_shell(tmp_path, monkeypatch):
    child = tmp_path / 'child.py'
    child.write_text(CHILD)
    tpl = (f'WARP_SOURCE_ROOT=/frozen/root {sys.executable} {child} --cases {{cases}} --indices {{indices}} '
           "--note 'a b;c' --out {out}")
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'o u t'
    assert runner.shell_episode(tpl, dict(os.environ))(tmp_path / 'c.json', [0, 2], out) == 0
    seen = json.loads((out / 'seen.json').read_text())
    _, argv = pc.episode_argv(tpl, tmp_path / 'c.json', [0, 2], out)
    assert seen['argv'] == argv[2:] and 'a b;c' in seen['argv'] and str(out) in seen['argv']
    assert seen['cwd'] == str(tmp_path) and seen['root'] == '/frozen/root' and seen['binding_at_start'] is False


# ------------------------------------------------------------ 1b: teacher output bound to the gate

CORE = 'c' * 64


def test_launch_binding_is_written_before_the_teacher_starts(tmp_path, monkeypatch):
    child = tmp_path / 'child.py'
    child.write_text(CHILD)
    tpl = f'{sys.executable} {child} --cases {{cases}} --indices {{indices}} --out {{out}}'
    monkeypatch.chdir(tmp_path)
    out = tmp_path / 'probe'
    bind = dict(stage='core', core=CORE, manifest_sha256='m' * 64)
    assert runner.shell_episode(tpl, dict(os.environ), bind)(tmp_path / 'c.json', [0], out) == 0
    assert json.loads((out / 'seen.json').read_text())['binding_at_start'] is True
    raw = out / 'world-000' / 'raw'
    raw.mkdir(parents=True)
    assert pc.launch_binding_problems(raw, CORE, ('core',)) == []
    assert 'core' in pc.launch_binding_problems(raw, 'd' * 64, ('core',))[0]        # another core
    assert 'stage' in pc.launch_binding_problems(raw, CORE, ('final',))[0]          # probe != training launch


def test_direct_teacher_run_with_pairact_env_is_refused_downstream(tmp_path, monkeypatch):
    """Counterexample 1b: run the wrapper argv by hand with the collector's training env -> it runs, but
    check-rows / convert-input refuse its raws (no launch binding)."""
    child = tmp_path / 'child.py'
    child.write_text(CHILD)
    out = tmp_path / 'manual'
    env = runner.collect_env('training', runner.ROOT / 'experiments/2026-10-21-pairact-r1/COLLECT_PREREG_DRAFT.json',
                             's' * 64, probe=True, prereg_core=CORE)
    subprocess.check_call([sys.executable, str(child), '--out', str(out)], env=dict(os.environ, **env))
    raw = out / 'world-000' / 'raw'
    raw.mkdir(parents=True)
    assert 'no launch binding' in pc.launch_binding_problems(raw, CORE, ('core',))[0]
    with pytest.raises(SystemExit, match='check-rows'):
        runner.require_launch_bindings([raw], CORE, ('core',), 'check-rows')


def test_copied_launch_binding_is_refused(tmp_path):
    good = tmp_path / 'good'
    rec = pc.launch_binding(stage='final', core=CORE, manifest_sha256='m' * 64, template=BASE, argv=['x'],
                            cwd=tmp_path, out=good)
    other = tmp_path / 'other'
    (other / 'world-000').mkdir(parents=True)
    pc.launch_binding_path(other).write_text(json.dumps(rec))                       # copied next to another out
    assert 'is not for' in pc.launch_binding_problems(other / 'world-000', CORE, ('final',))[0]
    with pytest.raises(ValueError):
        pc.launch_binding(stage='final', core=None, manifest_sha256=None, template=BASE, argv=[], cwd='.', out=good)


# ------------------------------------------------------------ XML: string compile resolves at the cwd

def test_canonical_xml_relative_names_resolve_at_the_episode_cwd(tmp_path):
    scene = tmp_path / 'runs' / 'export'
    scene.mkdir(parents=True)
    xml = scene / 'canonical-scene.xml'
    xml.write_text('<mujoco><compiler texturedir="sim/assets/t" meshdir="m"/>'
                   '<asset><texture name="g" type="2d" file="floor.png"/><mesh name="a" file="a.stl"/></asset>'
                   '<worldbody><flexcomp name="f" type="mesh" file="cloth.obj"/></worldbody></mujoco>')
    src = tmp_path / 'src'
    for rel in ('sim/assets/t/floor.png', 'm/a.stl', 'm/cloth.obj'):
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_bytes(b'x')
    at_cwd = {str(src / r) for r in ('sim/assets/t/floor.png', 'm/a.stl', 'm/cloth.obj')}
    assert set(pc.xml_dependencies(xml, base=src)) == at_cwd
    file_relative = {str(scene / r) for r in ('sim/assets/t/floor.png', 'm/a.stl', 'm/cloth.obj')}
    assert set(pc.xml_dependencies(xml)) == file_relative                       # from_xml_path meaning (v5)
    assert pc.episode_xml_problems(xml, {p: 'h' for p in at_cwd}, src) == []
    probs = pc.episode_xml_problems(xml, {p: 'h' for p in file_relative}, src)  # registered the file-relative set
    assert any('misses' in p for p in probs) and any('does not reference' in p for p in probs)
    (src / 'm/a.stl').unlink()
    assert any('missing at the episode cwd' in p for p in pc.episode_xml_problems(xml, {p: 'h' for p in at_cwd}, src))


def test_repository_scene_export_resolves_its_texture_only_at_the_repository_root():
    """Real exported scene (sim/natural_scene_texture.py writes texturedir relative to the repo scene root):
    the floor texture exists only at the repository cwd, the mesh is an absolute VM path (VM needed)."""
    xml = ROOT / 'experiments/2026-10-17-egonav/raw/far-diag-range-01/scene.xml'
    at_root = pc.xml_dependencies(xml, base=ROOT)
    assert str(ROOT / 'sim/assets/floor_light_textured_v1/floor.png') in at_root
    local = [p for p in at_root if not p.startswith('/home/ugrp/')]
    assert sum(map(os.path.isfile, local)) >= 30                                  # textures found at the repo cwd
    assert any(p.startswith('/home/ugrp/') for p in at_root)                     # VM-only mesh (VM needed)
    beside = pc.xml_dependencies(xml)
    assert not any(map(os.path.isfile, beside))                                   # XML-dir reading finds none
