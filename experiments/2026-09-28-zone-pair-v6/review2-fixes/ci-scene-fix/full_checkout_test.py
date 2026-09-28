"""Diagnostic only: original HEAD prepare tests with every tracked file present."""
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[4]
BASE = '19b3a7b242ccecf63ac5087ba122b1cb559d0991'


@pytest.mark.parametrize('run', ['dev09', 'dev10'])
def test_original_prepare_with_full_file_presence(tmp_path, run):
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    assert all((ROOT / path).exists() for path in tracked if path)
    source = subprocess.check_output(['git', 'show', BASE + ':tests/test_zone_pair_v5.py'], cwd=ROOT)
    scope = {'__name__': 'original_v5_test', '__file__': str(ROOT / 'tests/test_zone_pair_v5.py')}
    exec(compile(source, scope['__file__'], 'exec'), scope)
    # This retains the original unconditionally successful validate_scene call.
    # macOS + full file presence still passes; omitted files do not cause the CI mismatch.
    scope['test_v5_prepare_copies_frozen_registration_without_physics_or_models'](
        tmp_path, run, 'current_source_fixture')
