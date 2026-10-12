import datetime as dt
import subprocess
from unittest.mock import patch

import pytest

from scripts import azctl, remote_run
from scripts.azure_api import SUB, VM, vm_target
from scripts.remote_reverse_tunnel import validate_deadline


def test_default_and_explicit_targets_cannot_cross_machines():
    assert vm_target() == (VM, 'azure')
    assert vm_target(host='azure2') == ('ugrp-sim-azure2', 'azure2')
    assert vm_target(vm='ugrp-sim-azure2') == ('ugrp-sim-azure2', 'azure2')
    for vm, host in [('ugrp-sim-azure', 'azure2'), ('other', None), (None, 'other')]:
        with pytest.raises(ValueError):
            vm_target(vm, host)


def test_vm2_status_is_explicitly_scoped():
    with patch('sys.argv', ['azctl', 'status', '--host', 'azure2']), patch.object(azctl, 'az') as call:
        azctl.main()
    args = call.call_args.args
    assert args[args.index('-n') + 1] == 'ugrp-sim-azure2'
    with patch.object(subprocess, 'run') as run:
        azctl.az(*args)
    assert run.call_args.args[0][-3:] == ['--subscription', SUB, '--only-show-errors']


def test_stop_vm2_checks_vm2_guest_and_retrieves_vm2_records():
    with patch('sys.argv', ['azctl', 'stop', '--vm', 'ugrp-sim-azure2']), \
            patch.object(azctl, 'Arm') as arm, patch.object(azctl, 'guest') as guest, \
            patch.object(remote_run, 'fetch_lifecycle') as fetch, patch.object(azctl, 'az') as call:
        arm.return_value.request.return_value = {'statuses': []}
        guest.return_value = subprocess.CompletedProcess([], 0, '')
        azctl.main()
    guest.assert_called_once_with('status', 'azure2')
    fetch.assert_called_once_with('azure2')
    assert call.call_args.args[-1] == 'ugrp-sim-azure2'
    assert '/ugrp-sim-azure2/instanceView' in arm.return_value.request.call_args.args[1]


def test_failed_vm2_archive_does_not_drop_lease_or_stop_vm1(tmp_path):
    with patch.object(remote_run, 'PRIMARY', tmp_path), patch.object(remote_run, 'ssh') as ssh, \
            patch.object(subprocess, 'run') as run:
        remote_run.finish_lease('azure2', 'run', '$HOME/lease', False)
    ssh.assert_called_once_with('azure2', 'touch $HOME/lease')
    assert run.call_args.args[0][-3:] == ['stop', '--host', 'azure2']
    assert (tmp_path / 'outputs/azure2-lifecycle/pending/run.json').is_file()


def test_lifecycle_records_are_isolated_and_checksum_verified(tmp_path):
    with patch.object(remote_run, 'PRIMARY', tmp_path), patch.object(subprocess, 'run') as run, \
            patch.object(subprocess, 'check_output', return_value='') as verify:
        result = remote_run.fetch_lifecycle('azure2')
    assert result.endswith('outputs/azure2-lifecycle')
    assert 'azure2:~/ugrp-sim/lifecycle/' in run.call_args.args[0]
    assert 'azure2:~/ugrp-sim/lifecycle/' in verify.call_args.args[0]


def test_long_relay_requires_explicit_finite_cap():
    deadline = dt.datetime.fromtimestamp(7 * 3600, tz=dt.timezone.utc)
    with pytest.raises(ValueError):
        validate_deadline(deadline, now=0)
    validate_deadline(deadline, 7.5, now=0)
    with pytest.raises(ValueError):
        validate_deadline(deadline, 8, now=0)
