import copy
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import run_s3_x86_probe as probe


def test_x86_archive_guard_and_immutable_output(tmp_path, monkeypatch):
    sha='a'*40; root=tmp_path/sha; root.mkdir(); monkeypatch.chdir(root)
    monkeypatch.setattr(probe,'ROOT',root)
    parent=root/'outputs/test'; parent.mkdir(parents=True); (parent/'SOURCE_SHA').write_text(sha)
    monkeypatch.setenv('MUJOCO_GL','osmesa')
    monkeypatch.setattr(probe.platform,'system',lambda:'Linux')
    monkeypatch.setattr(probe.platform,'machine',lambda:'x86_64')
    monkeypatch.setattr(probe.os,'getpriority',lambda *a:0)
    monkeypatch.setattr(probe.shutil,'disk_usage',lambda p:SimpleNamespace(free=20*1024**3))
    probe.archive_guard(sha,Path('outputs/test/raw'))
    monkeypatch.setattr(probe.platform,'machine',lambda:'aarch64')
    with pytest.raises(ValueError,match='x86'): probe.archive_guard(sha,Path('outputs/test/raw'))


def test_six_paired_conditions_remain_setup_only_and_preserve_contract():
    original=probe.setup_record(None,'pair')
    for case in ('pair','cyan'):
        for i in range(6):
            b=probe.bundle('0'*40,case,condition=i)
            assert b['host']=='oracle-x86' and b['seed']==14201+i
            assert b['case_cap_s']==60 and b['alignment_entry']==probe.OPTION
            assert b['controller_config']['options']['heading_mode']=='path_tangent_v1'
            assert b['controller_config']['options']['s3_dev_light']=='continue_estimate_v1'
            setup=probe.varied_setup(case,i)
            assert setup['offset_body_m_rad']==list(probe.OFFSETS[i])
            assert setup['checkpoint'] is False
            assert b['known_start_information'] is False
    assert probe.setup_record(None,'pair')==original
    assert probe.varied_setup('pair',0)['robots']==original['robots']


def test_cli_plan_cannot_launch_physics(tmp_path,capsys):
    assert probe.main(['--expected-source-sha','0'*40,'--output',str(tmp_path/'unused')])==0
    assert 'oracle-x86' in capsys.readouterr().out
    assert not (tmp_path/'unused').exists()
