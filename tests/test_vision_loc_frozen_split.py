"""VIS3 pinned files stay byte-identical; VIS4 PF/CLI live in versioned files (2026-09-28, #216).

No model, renderer or physics: hashes, Git blobs and imports only.
"""
import hashlib
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'experiments'/'2026-09-26-vision-loc'
sys.path.insert(0, str(HERE))

import record_verify as rv  # noqa: E402

VIS4_COMMIT = '137ba742493b1f09c68238525cfc44a57054ae48'
VIS4_PF_SHA256 = '97a207dbda2fe31df32809b48baa4db1859ef0e1f30a196f5810b338c955b8f7'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_vis3_student_files_match_registration():
    frozen = json.loads((HERE/'prereg_v3.json').read_text())['student']['frozen_files_sha256']
    for name in ('vision_pf.py', 'vision_loc_cli.py', 'vision_loc.py'):
        assert sha(HERE/name) == frozen[name], name


def test_vis4_pf_is_the_137ba742_blob_byte_for_byte():
    blob = rv.git_blob(VIS4_COMMIT, 'experiments/2026-09-26-vision-loc/vision_pf.py')
    assert hashlib.sha256(blob).hexdigest() == VIS4_PF_SHA256
    assert (HERE/'vision_pf_v4.py').read_bytes() == blob


def test_vis4_cli_uses_vis4_pf_and_vis3_names_stay_vis3():
    import vision_loc_cli
    import vision_loc_cli_v4
    import vision_pf
    import vision_pf_v4
    assert vision_loc_cli_v4.vision_pf is vision_pf_v4
    assert vision_loc_cli.vision_pf is vision_pf and vision_pf is not vision_pf_v4
    assert 'motion_v4' not in inspect.signature(vision_pf.make_robust_pf).parameters
    assert {'motion_v4', 'sigma_v4'} <= set(inspect.signature(vision_pf_v4.make_robust_pf).parameters)


def test_recorded_sources_are_checked_against_the_recording_commit(tmp_path):
    other_worktree = '/elsewhere/ugrp-wt/any/experiments/2026-09-26-vision-loc/vision_pf.py'
    record = {other_worktree: VIS4_PF_SHA256}
    assert rv.blob_mismatches(record, VIS4_COMMIT) == []
    # The working-tree vision_pf.py is VIS3 again, so the same record fails on the current bytes.
    assert sha(HERE/'vision_pf.py') != VIS4_PF_SHA256
    assert rv.blob_mismatches({other_worktree: '0'*64}, VIS4_COMMIT) == [other_worktree]
    assert rv.blob_mismatches({str(tmp_path/'x.py'): VIS4_PF_SHA256}, VIS4_COMMIT) == [str(tmp_path/'x.py')]
    missing = '/w/experiments/2026-09-26-vision-loc/no_such_file.py'
    assert rv.blob_mismatches({missing: VIS4_PF_SHA256}, VIS4_COMMIT) == [missing]
