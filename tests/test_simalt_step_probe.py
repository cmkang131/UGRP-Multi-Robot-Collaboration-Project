"""The dense diagnostic must never start native physics on the Mac."""
import subprocess
import sys
from pathlib import Path
import pytest
from scripts import simalt_step_probe


def test_dense_probe_denies_mac_before_simulator_import(monkeypatch, tmp_path):
    monkeypatch.setattr(simalt_step_probe.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(sys, 'argv', ['probe', '--enabled', '--fixture', str(tmp_path),
        '--out', str(tmp_path/'out'), '--engine', 'warp', '--case', 'grip',
        '--sha', 'test', '--capacity-reference', str(tmp_path/'ref')])
    with pytest.raises(SystemExit, match='2'):
        simalt_step_probe.main()
    assert not (tmp_path/'out').exists()
