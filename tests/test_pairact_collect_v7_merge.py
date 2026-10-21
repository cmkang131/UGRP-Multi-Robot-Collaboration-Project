"""COLLECT_PREREG v7 merge (dsh/pairact-carry-r1-v7 + v7-1b): reinforcements a / b.

a: the wrapper parser accepts model-input options the core does not hash (--compiled-reference-v1,
--compiled-geometry-312-v1, --damping-ablation-v1, ...).  The core / final gates accept only the options on
pc.EPISODE_OPTION_ALLOWLIST, even when the parser knows the option.  b: a wrapper without parser() is refused
at core / final (no form-only fallback).  CPU only, no simulator import.
"""
import hashlib
from pathlib import Path

import pytest

from harness import pairact_collect as pc
from test_pairact_collect import FAKE_WRAPPER, filled_manifest, recording_dir
from test_pairact_collect_v5 import prereg_core

EXP = Path(__file__).resolve().parents[1] / 'experiments/2026-10-21-pairact-r1'
OPTION = ('--compiled-reference-v1 /abs/compiled-316.json', '--compiled-geometry-312-v1 /abs/geometry.npz',
          '--compiled-reference-v1=/abs/compiled-316.json', '--damping-ablation-v1', '--physics-backend c_pilot_v1',
          '--export-compiled-only')


def _with(m, tpl):
    m['command'].update(episode_template=tpl, episode_template_sha256=hashlib.sha256(tpl.encode()).hexdigest())
    return m


def _gates(tmp_path, tpl):
    """(core error, final error) of the filled manifest carrying ``tpl``; '' when accepted."""
    out = []
    try:
        core = pc.check_run_manifest(_with(filled_manifest(prereg_core()), tpl), stage='core', prereg=prereg_core())
        out.append('')
    except ValueError as e:
        core = None
        out.append(str(e))
    rec, hashes = recording_dir(tmp_path, core=core or 'f' * 64)
    m = _with(filled_manifest(prereg_core(), status='FROZEN', recording=hashes), tpl)
    try:
        pc.check_run_manifest(m, stage='final', prereg=dict(prereg_core(), status='FROZEN'), recording_dir=rec)
        out.append('')
    except ValueError as e:
        out.append(str(e))
    return out


def _base():
    from test_pairact_collect import EP_CMD
    return EP_CMD


def test_allowlisted_command_is_accepted_at_core_and_final(tmp_path):
    assert _gates(tmp_path, _base()) == ['', '']


@pytest.mark.parametrize('extra', OPTION)
def test_model_input_option_known_to_the_parser_is_refused_at_core_and_final(tmp_path, extra):
    name = extra.split()[0].partition('=')[0]
    assert name in pc.wrapper_parser(FAKE_WRAPPER)._option_string_actions        # the parser accepts it
    assert not pc.episode_parse_problems(_base() + ' ' + extra, pc.wrapper_parser(FAKE_WRAPPER))
    core, final = _gates(tmp_path, _base() + ' ' + extra)
    for err in (core, final):
        assert f'{name} is not on the v7 allowlist' in err, err


def test_real_wrapper_options_outside_the_allowlist_are_named():
    """Every option of the real gcp6 wrapper is either allowlisted or refused; the model-input ones are refused."""
    known = set(pc.wrapper_parser(pc.REPO_WRAPPER)._option_string_actions) - {'-h', '--help'}
    refused = known - set(pc.EPISODE_OPTION_ALLOWLIST)
    assert {'--compiled-reference-v1', '--compiled-geometry-312-v1', '--physics-backend',
            '--export-compiled-only', '--initialize-only', '--diagnostic-ticks'} <= refused
    assert set(pc.EPISODE_OPTION_ALLOWLIST) <= known                          # nothing the wrapper would exit 2 on


def test_manifest_draft_command_uses_only_allowlisted_options():
    import json
    tpl = json.loads((EXP / 'RUN_MANIFEST.json').read_text())['command']['episode_template_draft']
    assert pc.episode_allowlist_problems(tpl.replace('$SRC', '/home/ugrp/ugrp-sim/src/pairact-c5')) == []


@pytest.mark.parametrize('flag,bad', [('--out', '/x/out'), ('--cases', '/x/cases.json'), ('--indices', '0,1')])
def test_runner_options_must_carry_their_placeholder(tmp_path, flag, bad):
    tpl = _base().replace(pc.EPISODE_PLACEHOLDER_OPTIONS[flag], bad)
    for err in _gates(tmp_path, tpl):
        assert f'{flag} must be exactly' in err, err


def test_wrapper_without_parser_is_refused_at_core_and_final(tmp_path):
    wrap = tmp_path / 'noparser' / 'wrap.py'
    wrap.parent.mkdir()
    wrap.write_text('# no parser()\n')
    for err in _gates(tmp_path, _base().replace(FAKE_WRAPPER, str(wrap))):
        assert 'has no parser()' in err, err


def test_missing_wrapper_is_refused_at_core_and_final(tmp_path):
    for err in _gates(tmp_path, _base().replace(FAKE_WRAPPER, '/nonexistent/wrap.py')):
        assert 'episode wrapper /nonexistent/wrap.py not found' in err, err


def test_pilot_audit_keeps_the_form_only_fallback(tmp_path):
    """The non-frozen runner audit (no manifest) is unchanged: the strict reading is the core / final gate's."""
    assert pc.episode_command_problems(_base().replace(FAKE_WRAPPER, '/nonexistent/wrap.py')) == []
    assert pc.episode_command_problems(_base().replace(FAKE_WRAPPER, '/nonexistent/wrap.py'), strict=True)
