from unittest.mock import patch

import pytest

from scripts import gcpctl, remote_run


def test_create_command_has_every_cost_and_credential_guard():
    command = gcpctl.create_command('gcp1', 'ssh-ed25519 AAAA test')
    assert command[command.index('--project') + 1] == 'ugrp-act-train-1014'
    for flag in ('--max-run-duration=8h', '--instance-termination-action=STOP', '--no-service-account', '--no-scopes'):
        assert flag in command
    assert any(part.startswith('ssh-keys=') and 'block-project-ssh-keys=true' in part for part in command)
    assert gcpctl.STARTUP.is_file() and 'shutdown -h now' in gcpctl.STARTUP.read_text()
    with pytest.raises(ValueError):
        gcpctl.create_command('gcp2', 'k')


def test_every_gcloud_call_names_the_project():
    with patch.object(gcpctl.subprocess, 'run') as run:
        gcpctl.gcloud('compute', 'instances', 'stop', 'x')
    assert run.call_args.args[0][-2:] == ['--project', 'ugrp-act-train-1014']


def test_stop_defers_while_leases_or_simulations_exist():
    with patch.object(gcpctl, 'status', return_value=('RUNNING', '1.2.3.4', 'n4-highcpu-64')), \
            patch.object(gcpctl, 'guest_busy', return_value=True), patch.object(gcpctl, 'gcloud') as call:
        assert gcpctl.stop('gcp1') == 75
    call.assert_not_called()
    with patch.object(gcpctl, 'status', return_value=('RUNNING', '1.2.3.4', 'n4-highcpu-64')), \
            patch.object(gcpctl, 'guest_busy', return_value=False), patch.object(gcpctl, 'gcloud') as call:
        gcpctl.stop('gcp1')
    assert call.call_args.args[:2] == ('compute', 'instances')


def test_runner_keeps_gcp_evidence_apart_and_keeps_lease_unless_verified(tmp_path):
    with patch.object(remote_run.subprocess, 'run') as run, patch.object(remote_run, 'PRIMARY', tmp_path):
        assert remote_run.fetch('gcp1', 'r1') == str(tmp_path / 'outputs/gcp1-runs/r1')
    assert not any('lifecycle' in str(c) for c in run.call_args_list)
    for archived, removes in ((True, True), (False, False)):
        with patch.object(remote_run, 'ssh') as ssh, patch.object(remote_run.subprocess, 'run') as run:
            remote_run.finish_lease('gcp1', 'r1', 'LEASE', archived)
        assert any('rm -f LEASE' in str(c) for c in ssh.call_args_list) is removes
        assert run.call_args.args[0][-2:] == ['stop', 'gcp1']
