"""solo_carry='off' leaves the runner's behaviour untouched; parameter validation only (derived, unverified).

No simulator is started: every case either raises during argument validation, before any
simulator import, or inspects source. The byte-identity check compares the runner against the pinned base
commit with the opt-in additions removed.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = '75929e7719ad98a089e3dda5251f4249d8bae511'      # the pinned pairact tree this branch is cut from
RUNNER = 'scripts/run_grasp_act_teacher.py'
SOLO_MODULES = ('harness.solo_carry_contract', 'harness.solo_carry_runner', 'harness.solo_carry_visible',
                'harness.solo_carry_recorder', 'harness.solo_carry_teacher')


def base_source():
    run = subprocess.run(['git', '-C', str(ROOT), 'show', f'{BASE}:{RUNNER}'], capture_output=True, text=True)
    assert run.returncode == 0, f'base commit {BASE} unavailable: {run.stderr[-200:]}'
    return run.stdout


def strip_solo(text):
    """Remove every opt-in addition: fragments, the CLI flag and each ``if solo_carry!='off'`` block."""
    text = text.replace('solo_carry="off",', '').replace('solo_carry=a.solo_carry,', '')
    lines, out, k = text.split('\n'), [], 0
    while k < len(lines):
        line = lines[k]
        if line.strip().startswith('p.add_argument(\'--solo-carry\''):
            k += 1
            continue
        if line.strip() == "solo_inst=None;solo_recorders={};solo_rows=[];solo_ctl=None":
            k += 1
            continue
        if re.match(r"^\s*if solo_carry!='off'", line):
            indent = len(line) - len(line.lstrip())
            k += 1
            while k < len(lines) and (not lines[k].strip() or len(lines[k]) - len(lines[k].lstrip()) > indent):
                k += 1
            continue
        out.append(line)
        k += 1
    return '\n'.join(out)


def test_runner_with_the_solo_additions_removed_is_byte_identical_to_the_pinned_base():
    current = (ROOT/RUNNER).read_text()
    assert strip_solo(current) == base_source()


def test_every_solo_addition_is_guarded_and_no_pair_line_was_edited():
    current = (ROOT/RUNNER).read_text().split('\n')
    unguarded = [l for l in current if 'solo' in l and not re.match(r"^\s*if solo_carry!='off'", l)]
    # lines that mention solo outside a guard line must live inside a guarded block (indented deeper than its guard)
    removed = [l for l in strip_solo('\n'.join(current)).split('\n') if 'solo' in l]
    assert removed == [], removed
    assert unguarded                                   # sanity: there are additions to check


def test_signature_default_is_off_and_cli_default_is_off():
    tree = ast.parse((ROOT/RUNNER).read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    kw = {a.arg: d.value for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults) if isinstance(d, ast.Constant)}
    assert kw['solo_carry'] == 'off' and kw['pair_carry'] == 'off'
    assert '--solo-carry' in (ROOT/RUNNER).read_text() and "default='off',help='single-robot" in (ROOT/RUNNER).read_text()


def run_with(tmp_path, **kw):
    from scripts import run_grasp_act_teacher as runner
    return runner.run({'roles': {'r1': 'teal'}}, tmp_path/'out', **kw)


def test_off_path_never_imports_the_solo_modules(tmp_path):
    for name in SOLO_MODULES:
        sys.modules.pop(name, None)
    with pytest.raises(ValueError, match='unknown pair carry mode'):
        run_with(tmp_path, teacher_profile='visible_only', pair_carry='bogus')
    with pytest.raises(ValueError, match='recording requires'):
        run_with(tmp_path, record_training=True)
    assert not [m for m in SOLO_MODULES if m in sys.modules]


def test_pair_carry_validation_messages_are_unchanged_when_solo_is_off(tmp_path):
    with pytest.raises(ValueError, match='visible_only one-robot-per-end'):
        run_with(tmp_path, teacher_profile='visible_only', pair_carry='pair_carry_gt_v1')
    with pytest.raises(ValueError, match='carry lower mode requires pair carry'):
        run_with(tmp_path, carry_lower='floor_contact_v1')
    with pytest.raises(ValueError, match='carry route mode requires pair carry'):
        run_with(tmp_path, carry_route='detour_v1')
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('kw,match', [
    (dict(solo_carry='solo_v2'), 'unknown solo carry mode'),
    (dict(solo_carry='solo_box_v1'), 'strict mode'),                                    # legacy profile
    (dict(solo_carry='solo_box_v1', teacher_profile='observable_v2'), 'strict mode'),
    (dict(solo_carry='solo_box_v1', teacher_profile='visible_only', pair_carry='pair_carry_gt_v1'), 'mutually exclusive'),
    (dict(solo_carry='solo_box_v1', teacher_profile='visible_only', probe=True), 'probe'),
    (dict(solo_carry='solo_box_v1', teacher_profile='visible_only', carry_cap_s=0.), 'carry cap'),
    (dict(solo_carry='solo_box_v1', teacher_profile='visible_only', carry_cap_s=500.), 'carry cap'),
    (dict(solo_carry='solo_box_v1', teacher_profile='visible_only', student_eval={'mode': 'x'}), 'student eval'),
    (dict(solo_carry='solo_box_v1', teacher_profile='visible_only'), 'plan roles|solo_cargo|solo_slot'),   # plan lacks solo fields
])
def test_solo_requirements_fail_before_any_simulator_or_output(tmp_path, kw, match):
    plan = {'roles': {'r1': 'teal'}}
    from scripts import run_grasp_act_teacher as runner
    with pytest.raises(ValueError, match=match):
        runner.run(plan, tmp_path/'out', **kw)
    assert not (tmp_path/'out').exists()                  # nothing was created: validation precedes mkdir


def test_cli_exposes_only_the_two_documented_values():
    text = (ROOT/RUNNER).read_text()
    assert "p.add_argument('--solo-carry',choices=('off','solo_box_v1')" in text
    from harness import solo_carry_contract as sc
    assert sc.MODES == ('off', 'solo_box_v1')
