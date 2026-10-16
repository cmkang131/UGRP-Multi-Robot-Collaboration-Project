from unittest.mock import patch

import pytest

from scripts import gcpctl, remote_run


def test_create_command_has_every_cost_and_credential_guard():
    command = gcpctl.create_command('gcp2', 'ssh-ed25519 AAAA test')
    assert command[command.index('--project') + 1] == 'ugrp-sim-b-1014'
    for flag in ('--max-run-duration=24h', '--instance-termination-action=STOP', '--no-service-account', '--no-scopes'):
        assert flag in command
    assert any(part.startswith('ssh-keys=') and 'block-project-ssh-keys=true' in part for part in command)
    assert command[command.index('--account') + 1] == 'changmin5781@gmail.com'
    assert '--provisioning-model=STANDARD' in command
    assert command[command.index('--boot-disk-size') + 1] == '400GB'
    assert gcpctl.STARTUP.is_file() and 'shutdown -h now' in gcpctl.STARTUP.read_text()
    with pytest.raises(ValueError):
        gcpctl.create_command('unknown', 'k')


def test_every_gcloud_call_names_the_project():
    with patch.object(gcpctl.subprocess, 'run') as run:
        gcpctl.gcloud('compute', 'instances', 'stop', 'x')
    assert run.call_args.args[0][-2:] == ['--project', 'ugrp-sim-b-1014']


def test_gcp3_l4_uses_its_project_gpu_image_and_eight_hour_cap():
    command = gcpctl.create_command('gcp3', 'ssh-ed25519 AAAA test')
    for flag, value in (('--project', 'ugrp-sim-c-1016'), ('--machine-type', 'g2-standard-8'),
                        ('--image-project', 'deeplearning-platform-release'),
                        ('--accelerator', 'type=nvidia-l4,count=1'), ('--boot-disk-size', '140GB')):
        assert command[command.index(flag) + 1] == value
    for flag in ('--max-run-duration=8h', '--instance-termination-action=STOP',
                 '--maintenance-policy=TERMINATE', '--no-service-account', '--no-scopes'):
        assert flag in command
    assert remote_run.wait_budget_s('gcp3') == 7.5 * 3600
    assert remote_run.wait_budget_s('gcp2') == 23.5 * 3600
    assert remote_run.DEFAULT_HOST == gcpctl.DEFAULT_HOST == 'gcp2'
    with patch.object(gcpctl.subprocess, 'run') as run:
        gcpctl.gcloud('compute', 'instances', 'describe', 'x', host='gcp3')
    assert run.call_args.args[0][-4:] == ['--account', 'changmin5781@gmail.com', '--project', 'ugrp-sim-c-1016']


def test_gcp3_stop_is_blocked_by_an_unwrapped_python_or_ffmpeg_job():
    with patch.object(gcpctl.subprocess, 'run') as run:
        run.return_value.returncode = 1
        assert gcpctl.guest_busy('gcp3')
    probe = run.call_args.args[0][-1]
    assert "pgrep -u ugrp -x 'python[0-9.]*|mujoco|ffmpeg'" in probe
    assert 'test -d ~/ugrp-sim/leases' in probe
    assert gcpctl.GCP_HOSTS['gcp3']['identity_file'] == '~/.ssh/ugrp_gcp3'


def test_stop_defers_while_leases_or_simulations_exist():
    with patch.object(gcpctl, 'status', return_value=('RUNNING', '1.2.3.4', 'n4-highcpu-64')), \
            patch.object(gcpctl, 'guest_busy', return_value=True), patch.object(gcpctl, 'gcloud') as call:
        assert gcpctl.stop('gcp2') == 75
    call.assert_not_called()
    with patch.object(gcpctl, 'status', return_value=('RUNNING', '1.2.3.4', 'n4-highcpu-64')), \
            patch.object(gcpctl, 'guest_busy', return_value=False), patch.object(gcpctl, 'gcloud') as call:
        gcpctl.stop('gcp2')
    assert call.call_args.args[:2] == ('compute', 'instances')


def test_runner_keeps_gcp_evidence_apart_and_keeps_lease_unless_verified(tmp_path):
    with patch.object(remote_run.subprocess, 'run') as run, patch.object(remote_run, 'PRIMARY', tmp_path):
        assert remote_run.fetch('gcp1', 'r1') == str(tmp_path / 'outputs/gcp1-runs/r1')
    assert not any('lifecycle' in str(c) for c in run.call_args_list)
    for archived, removes in ((True, True), (False, False)):
        with patch.object(remote_run, 'ssh') as ssh, patch.object(remote_run.subprocess, 'run') as run:
            remote_run.finish_lease('gcp2', 'r1', 'LEASE', archived)
        assert any('rm -f LEASE' in str(c) for c in ssh.call_args_list) is removes
        assert run.call_args.args[0][-2:] == ['stop', 'gcp2']


def test_retired_gcp1_cannot_be_mutated_even_with_force():
    for action in (lambda: gcpctl.start('gcp1'),
                   lambda: gcpctl.stop('gcp1', force=True),
                   lambda: gcpctl.create_command('gcp1', 'public')):
        with patch.object(gcpctl, 'gcloud') as cloud, patch.object(gcpctl, 'status') as status:
            with pytest.raises(RuntimeError, match='lifecycle disabled'):
                action()
            cloud.assert_not_called()
            status.assert_not_called()


def test_ssh_config_uses_separate_key_and_explicit_config(capsys):
    gcpctl.main(['ssh-config'])
    block = capsys.readouterr().out
    assert 'Host gcp2' in block
    assert '~/.ssh/ugrp_gcp2' in block
    assert 'UGRP_GCP_CONFIG=' in block


def test_retired_gcp1_finisher_never_removes_lease():
    with patch.object(remote_run, 'ssh') as ssh, patch.object(remote_run.subprocess, 'run') as run:
        with pytest.raises(RuntimeError, match='lifecycle disabled'):
            remote_run.finish_lease('gcp1', 'old', 'LEASE', True)
        ssh.assert_not_called()
        run.assert_not_called()
