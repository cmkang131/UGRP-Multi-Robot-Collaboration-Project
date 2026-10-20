"""pairact P3 opt-in recording admission: only the >=38/40 gate requirement is replaced."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from harness import grasp_act_admission as adm
from sim.grasp_act_search15_modes import ALL_MODES

ROOT = Path(__file__).resolve().parents[1]
BASE = '59299f903f4a2f9a2eabe5ff0e442e0ce25e8266'      # dsh/pairact-p2-carrypath (unchanged gate path)
HOST = {'schema': 'ugrp.grasp_act.host.v1', 'provider': 'gcp', 'project_id': 'p', 'instance': 'gcp6',
        'machine_type': 'g2-standard-8', 'zone': 'z', 'cpu_count': 8}
MODES = dict(teacher_stability='align_relook_v1', teacher_search='search_body_scan_v2',
             approach_goal_set='approach_goal_set_v1', nominal_blocked_handoff='nominal_blocked_handoff_v1',
             approach_progress='approach_progress_v1', approach_recovery='progress_view_recovery_v3',
             approach_coordination='off', handoff_observation='visible_handoff_v1')
S15 = {k: 'off' for k in ALL_MODES}
S15[next(iter(ALL_MODES))] = ALL_MODES[next(iter(ALL_MODES))]


def prereg(tmp_path, status='FROZEN'):
    path = tmp_path / 'prereg.json'
    path.write_text(json.dumps({'schema': adm.COLLECT_PREREG_SCHEMA, 'status': status}))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def check(**over):
    c = {'qualified': True, 'n': 3, 'N': 3, 'source_sha': 'src', 'teacher_profile': 'visible_only',
         'execution_host': dict(HOST), **MODES, **S15}
    c.update(over)
    return c


def admit(path, sha, c, **kw):
    return adm.collect_recording_admission(path, sha, c, source_sha='src', teacher_profile='visible_only',
                                           modes=MODES, search15_options=S15, execution_host=dict(HOST),
                                           check_sha256='c' * 64, **kw)


def test_frozen_prereg_and_kept_check_give_a_qualified_proof_without_gate(tmp_path):
    path, sha = prereg(tmp_path)
    proof = admit(path, sha, check())
    assert proof['qualified'] is True and proof['collect_prereg_sha256'] == sha
    assert proof['recording_check_sha256'] == 'c' * 64
    assert proof['admission'] == 'pairact_p3_collect_prereg_v1' and 'n' not in proof and 'N' not in proof


def test_prereg_must_be_frozen_and_hash_exact(tmp_path):
    path, sha = prereg(tmp_path, status='READY_FOR_REVIEW')
    with pytest.raises(ValueError, match='FROZEN'):
        admit(path, sha, check())
    path, sha = prereg(tmp_path)
    with pytest.raises(ValueError, match='sha256 mismatch'):
        admit(path, '0' * 64, check())
    with pytest.raises(ValueError, match='sha256 mismatch'):
        admit(path, None, check())


@pytest.mark.parametrize('bad', [dict(qualified=False), dict(N=2, n=2), dict(n=2), dict(source_sha='other'),
                                 dict(teacher_profile='legacy'), dict(teacher_search='off')])
def test_recording_mode_check_rule_is_kept(tmp_path, bad):
    path, sha = prereg(tmp_path)
    with pytest.raises(ValueError, match='unverified recording-mode equivalence'):
        admit(path, sha, check(**bad))


def test_check_required_unless_probe_and_bound_to_machine(tmp_path):
    path, sha = prereg(tmp_path)
    with pytest.raises(ValueError, match='640x480'):
        admit(path, sha, None)
    assert 'recording_check_sha256' not in admit(path, sha, None, recording_probe=True)
    with pytest.raises(ValueError, match='mode mismatch'):
        admit(path, sha, check(**{k: 'off' for k in S15}))
    with pytest.raises(ValueError, match='machine'):
        admit(path, sha, check(execution_host={**HOST, 'instance': 'gcp2'}))


def _diff(path):
    try:
        out = subprocess.run(['git', '-C', str(ROOT), 'diff', '-U0', BASE, '--', path],
                             capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        pytest.skip(f'base commit unavailable: {error}')
    removed = [l for l in out.splitlines() if l.startswith('-') and not l.startswith('---')]
    return removed


def test_existing_gate_path_is_byte_identical():
    # admission module: append-only; teacher main: the gate branch line becomes ``elif`` only
    assert _diff('harness/grasp_act_admission.py') == []
    assert _diff('scripts/run_grasp_act_teacher.py') == ['-    if a.record_training:']
    text = (ROOT / 'scripts/run_grasp_act_teacher.py').read_text()
    assert "    elif a.record_training:\n        if a.teacher_gate is None:raise ValueError('verified >=38/40 teacher gate required before recording')" in text
    assert "default='teacher_gate_v1'" in text
