"""Only changed Azure lifecycle paths: no live cloud, simulation or SSH calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import Mock, patch

import pytest

from scripts import azure_shutdown as shutdown
from scripts import azure_idle_guard as guard
from scripts import remote_run, remote_run_finish, azctl, azure_safety_setup


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / 'runs').mkdir()
    (tmp_path / 'leases').mkdir()
    (tmp_path / 'arm').mkdir()
    monkeypatch.setattr(shutdown, 'boot_id', lambda: 'boot-one')
    monkeypatch.setattr(shutdown, 'run_processes', lambda run: set())
    monkeypatch.setattr(shutdown.os, 'sync', lambda: None, raising=False)
    return tmp_path


def run(root, name='one'):
    folder = root / 'runs' / name
    folder.mkdir()
    (folder / 'EXIT').write_text('0\n')
    (folder / 'raw').write_bytes(b'flushed original')
    (root / 'leases' / name).touch()
    return folder


def copy_rsync(call, **kwargs):
    if call[1] == '-ac':
        shutil.copytree(call[-2], call[-1], dirs_exist_ok=True)
    return subprocess.CompletedProcess(call, 0, stdout='')


def test_eight_hour_stops_even_with_live_lease_and_archive_failure(root, monkeypatch):
    folder = run(root)
    report = {'failed': ['one'], 'archived': []}
    monkeypatch.setattr(guard, 'lifecycle', Mock(return_value=report))
    monkeypatch.setattr(guard, 'deallocate', Mock())
    guard.stop(guard.reason(28800, 0))
    guard.lifecycle.assert_called_once_with('stop', 'eight_hour_cap')
    guard.deallocate.assert_called_once()
    assert folder.exists() and (root / 'leases/one').exists()


def test_cost_stop_still_deallocates_if_flush_helper_raises(monkeypatch):
    monkeypatch.setattr(guard, 'lifecycle', Mock(side_effect=OSError('disk error')))
    monkeypatch.setattr(guard, 'deallocate', Mock())
    with pytest.raises(OSError):
        guard.stop('eight_hour_cap')
    guard.deallocate.assert_called_once()


def test_exit_only_and_stale_failed_lease_block_ordinary_stop(root):
    run(root)
    os.utime(root / 'leases/one', (0, 0))
    assert shutdown.blockers(root)['unarchived'] == ['one']
    assert shutdown.blockers(root)['leases'] == []


def test_idle_guard_keeps_exit_only_evidence_busy(root, monkeypatch):
    run(root)
    monkeypatch.setattr(guard, 'ROOT', root)
    with patch.object(guard.Path, 'iterdir', return_value=iter([])):
        # Avoid mocking the real pending scan as well.
        monkeypatch.setattr(guard, 'blockers', lambda root: {'unarchived': ['one']})
        assert guard.active()


def test_failed_archive_is_recorded_preserves_lease_and_closes_admission(root, monkeypatch):
    folder = run(root)
    monkeypatch.setattr(shutdown, 'signal_runs', lambda root: [{'run': 'one', 'pid': 123}])
    monkeypatch.setattr(shutdown, 'bounded_archive', lambda *args: False)
    result = shutdown.lifecycle('stop', 'credit_cap', root, grace=0.01)
    assert result['failed'] == ['one'] and not result['archived']
    assert result['signalled'] == [{'run': 'one', 'pid': 123}]
    assert result['elapsed_seconds'] < 1
    assert folder.joinpath('raw').read_bytes() == b'flushed original'
    assert (root / 'leases/one').exists()
    assert shutdown.admission_closed(root)
    record = json.loads(next((root / 'lifecycle/events').iterdir()).read_text())
    assert record['failed'] == ['one']


def test_archive_retry_then_next_boot_recovers_failed_raw(root, monkeypatch):
    folder = run(root)
    monkeypatch.setattr(shutdown.os.path, 'ismount', lambda path: True)
    monkeypatch.setattr(shutdown.shutil, 'disk_usage', lambda path: Mock(free=100 * 2**30))
    monkeypatch.setattr(shutdown.subprocess, 'run', copy_rsync)
    attempts = []
    def archive(*args):
        attempts.append(1)
        if len(attempts) == 1:
            return False
        shutdown.archive_one(root, folder)
        return True
    monkeypatch.setattr(shutdown, 'bounded_archive', archive)
    monkeypatch.setattr(shutdown.time, 'sleep', lambda delay: None)
    shutdown.write_json(root / 'lifecycle/STOPPING.json', {'boot_id': 'old-boot', 'reason': 'cap'})
    result = shutdown.lifecycle('recover', 'boot_recovery', root, grace=1)
    assert result['archived'] == ['one'] and result['attempts']['one'] == 2
    assert folder.joinpath('raw').exists()  # No deletion of original evidence.
    assert not (root / 'leases/one').exists()
    assert shutdown.archived(root, folder)
    assert not shutdown.admission_closed(root)
    assert shutdown.blockers(root)['unarchived'] == []
    marker = json.loads((root / 'lifecycle/archives/one.json').read_text())
    assert marker['inventory']['raw']['sha256'] == shutdown.inventory(folder)['raw']['sha256']


@pytest.mark.parametrize('action', ['recover', 'stop', 'daily'])
def test_archive_failure_cli_returns_nonzero_and_preserves_evidence(root, monkeypatch, action):
    folder = run(root)
    monkeypatch.setattr(shutdown, 'bounded_archive', lambda *args: False)
    # Daily can race with a newly pending run after its initial blocker scan.
    monkeypatch.setattr(shutdown, 'blockers', lambda root: {})
    monkeypatch.setattr(sys, 'argv', ['guard', action, '--root', str(root), '--grace-seconds', '0.01'])
    assert shutdown.main() == 74
    assert folder.joinpath('raw').read_bytes() == b'flushed original'
    assert (root / 'leases/one').exists()
    record = json.loads(next((root / 'lifecycle/events').iterdir()).read_text())
    assert record['failed'] == ['one']


def test_recover_cli_success_returns_zero(root, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['guard', 'recover', '--root', str(root)])
    assert shutdown.main() == 0


def test_start_recovery_archive_failure_refuses_admission(root, monkeypatch):
    run(root)
    monkeypatch.setattr(shutdown, 'bounded_archive', lambda *args: False)
    monkeypatch.setattr(azctl.subprocess, 'run', lambda *args, **kw: subprocess.CompletedProcess([], 0))
    def guest(action):
        monkeypatch.setattr(sys, 'argv', ['guard', 'recover', '--root', str(root), '--grace-seconds', '0.01'])
        return subprocess.CompletedProcess([], shutdown.main())
    monkeypatch.setattr(azctl, 'guest', guest)
    fetch = Mock()
    monkeypatch.setattr(remote_run, 'fetch_lifecycle', fetch)
    with pytest.raises(RuntimeError, match='new execution refused'):
        azctl.recover()
    fetch.assert_not_called()


def test_failed_rsync_resumes_incoming_and_never_overwrites_published(root, monkeypatch):
    folder = run(root)
    monkeypatch.setattr(shutdown.os.path, 'ismount', lambda path: True)
    monkeypatch.setattr(shutdown.shutil, 'disk_usage', lambda path: Mock(free=100 * 2**30))
    with patch.object(shutdown.subprocess, 'run', side_effect=subprocess.CalledProcessError(23, 'rsync')):
        with pytest.raises(subprocess.CalledProcessError):
            shutdown.archive_one(root, folder)
    assert (root / 'arm/.incoming-shutdown-one').exists()
    assert (root / 'leases/one').exists()
    monkeypatch.setattr(shutdown.subprocess, 'run', copy_rsync)
    shutdown.archive_one(root, folder)
    assert shutdown.archived(root, folder)
    folder.joinpath('raw').write_bytes(b'changed')
    assert not shutdown.archived(root, folder)
    with pytest.raises(RuntimeError, match='no overwrite'):
        shutdown.archive_one(root, folder)


def test_archive_checksum_mismatch_is_not_success(root, monkeypatch):
    folder = run(root)
    monkeypatch.setattr(shutdown.os.path, 'ismount', lambda path: True)
    monkeypatch.setattr(shutdown.shutil, 'disk_usage', lambda path: Mock(free=100 * 2**30))
    def bad_copy(call, **kwargs):
        answer = copy_rsync(call, **kwargs)
        if call[1] == '-ac':
            Path(call[-1], 'raw').write_bytes(b'wrong bytes')
        return answer
    monkeypatch.setattr(shutdown.subprocess, 'run', bad_copy)
    with pytest.raises(RuntimeError, match='checksum mismatch'):
        shutdown.archive_one(root, folder)
    assert not (root / 'lifecycle/archives/one.json').exists()
    assert (root / 'leases/one').exists()


def test_arm_reserve_and_flushing_run_refuse_archive(root, monkeypatch):
    folder = run(root)
    monkeypatch.setattr(shutdown.os.path, 'ismount', lambda path: True)
    monkeypatch.setattr(shutdown.shutil, 'disk_usage', lambda path: Mock(free=25 * 2**30))
    with pytest.raises(RuntimeError, match='reserve'):
        shutdown.archive_one(root, folder)
    monkeypatch.setattr(shutdown, 'run_processes', lambda run: {55})
    with pytest.raises(RuntimeError, match='flushing'):
        shutdown.archive_one(root, folder)


def test_recovery_without_exit_records_host_error_before_archive(root, monkeypatch):
    folder = run(root)
    folder.joinpath('EXIT').unlink()
    monkeypatch.setattr(shutdown.os.path, 'ismount', lambda path: True)
    monkeypatch.setattr(shutdown.shutil, 'disk_usage', lambda path: Mock(free=100 * 2**30))
    monkeypatch.setattr(shutdown.subprocess, 'run', copy_rsync)
    shutdown.archive_one(root, folder)
    assert folder.joinpath('EXIT').read_text() == '74\n'
    assert json.loads(folder.joinpath('HOST_ERROR.json').read_text())['reason'] == 'interrupted_before_exit'
    assert shutdown.archived(root, folder)


def test_daily_active_lease_is_skipped_and_persisted(root, monkeypatch, capsys):
    run(root)
    monkeypatch.setattr(sys, 'argv', ['guard', 'daily', '--root', str(root)])
    assert shutdown.main() == 75
    record = json.loads(next((root / 'lifecycle/events').iterdir()).read_text())
    assert record['result'] == 'skipped' and record['blockers']['leases'] == ['one']
    assert not (root / 'lifecycle/STOPPING.json').exists()


def test_runner_archive_failure_keeps_lease_and_mac_pending_record(root, monkeypatch):
    monkeypatch.setattr(remote_run, 'PRIMARY', root)
    calls = []
    monkeypatch.setattr(remote_run, 'ssh', lambda host, cmd: calls.append(cmd))
    monkeypatch.setattr(remote_run.subprocess, 'run', lambda *args, **kw: None)
    remote_run.finish_lease('azure', 'one', '$HOME/ugrp-sim/leases/one', False)
    assert calls == ['touch $HOME/ugrp-sim/leases/one']
    record = json.loads((root / 'outputs/azure-lifecycle/pending/one.json').read_text())
    assert record['lease'] == 'retained' and record['archive'] == 'pending'


def test_runner_verified_archive_releases_own_lease(root, monkeypatch):
    calls = []
    monkeypatch.setattr(remote_run, 'ssh', lambda host, cmd: calls.append(cmd))
    monkeypatch.setattr(remote_run.subprocess, 'run', lambda *args, **kw: None)
    remote_run.finish_lease('azure', 'one', 'lease', True)
    assert calls == ['rm -f lease']


def test_ordinary_azctl_stop_defers_on_guest_exit75(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['azctl', 'stop'])
    arm = Mock()
    arm.request.return_value = {'statuses': [{'code': 'PowerState/running'}]}
    monkeypatch.setattr(azctl, 'Arm', lambda: arm)
    monkeypatch.setattr(azctl, 'guest', lambda action: subprocess.CompletedProcess([], 75, '{"unarchived":["one"]}'))
    monkeypatch.setattr(remote_run, 'fetch_lifecycle', lambda: None)
    monkeypatch.setattr(azctl, 'az', Mock())
    azctl.main()
    azctl.az.assert_not_called()


def test_start_runs_recovery_before_return(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['azctl', 'start'])
    monkeypatch.setattr(azctl, 'EXPIRY', __import__('datetime').datetime.max.replace(tzinfo=__import__('datetime').timezone.utc))
    monkeypatch.setattr(azctl, 'Arm', Mock())
    monkeypatch.setattr(azctl, 'safety', lambda arm: 1)
    calls = []
    monkeypatch.setattr(azctl, 'az', lambda *args: calls.append('start'))
    monkeypatch.setattr(azctl, 'recover', lambda: calls.append('recover'))
    azctl.main()
    assert calls == ['start', 'recover']


def test_runbook_only_updates_content_and_publish(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['setup', '--runbook-only'])
    arm = Mock()
    arm.request.side_effect = [{}, {}, azure_safety_setup.runbook_content(), {'properties': {'state': 'Published'}}]
    monkeypatch.setattr(azure_safety_setup, 'Arm', lambda: arm)
    azure_safety_setup.main()
    assert [call.args[:2] for call in arm.request.call_args_list] == [
        ('PUT', azure_safety_setup.RUNBOOK + '/draft/content' + azure_safety_setup.API),
        ('POST', azure_safety_setup.RUNBOOK + '/publish' + azure_safety_setup.API),
        ('GET', azure_safety_setup.RUNBOOK + '/content' + azure_safety_setup.API),
        ('GET', azure_safety_setup.RUNBOOK + azure_safety_setup.API)]
    content = arm.request.call_args_list[0].args[2]
    assert '__UGRP_SHUTDOWN_SOURCE__' not in content
    assert 'GRACE_SECONDS = 600' in content and 'asyncExecution=$true' in content


def test_lifecycle_deployment_scopes_commands_to_own_vm_without_webhook_rotation(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['setup', '--lifecycle-only'])
    arm = Mock()
    setup = azure_safety_setup
    def request(method, path, *args, **kwargs):
        if method == 'GET':
            if path == setup.ACCOUNT + setup.API:
                return {'identity': {'principalId': 'automation'}, 'properties': {'state': 'Published'}}
            if path == setup.VM_ID + '?api-version=2024-11-01':
                return {'identity': {'principalId': 'self-vm'}}
            if path == setup.RUNBOOK + '/content' + setup.API:
                return setup.runbook_content()
            if path == setup.RUNBOOK + setup.API:
                return {'properties': {'state': 'Published'}}
            pytest.fail('Unexpected read: ' + path)
        return {}
    arm.request.side_effect = request
    monkeypatch.setattr(setup, 'Arm', lambda: arm)
    setup.main()
    writes = [c for c in arm.request.call_args_list if c.args[0] in ('PUT', 'POST', 'DELETE')]
    for call in writes:
        assert call.args[1].startswith('/subscriptions/' + setup.SUB + '/')
        assert not any(word in call.args[1] for word in ('webhooks', 'actionGroups', '/start', '/deallocate'))
    roles = [c for c in writes if '/roleDefinitions/' in c.args[1]]
    assert len(roles) == 1
    props = roles[0].args[2]['properties']
    assert props['assignableScopes'] == [setup.BASE]
    assert props['permissions'][0]['actions'] == [
        'Microsoft.Compute/virtualMachines/runCommands/write', 'Microsoft.Compute/virtualMachines/runCommands/read']
    assignments = [c for c in writes if '/roleAssignments/' in c.args[1]]
    assert len(assignments) == 2
    assert {c.args[2]['properties']['principalId'] for c in assignments} == {'automation', 'self-vm'}
    assert all(c.args[1].startswith(setup.VM_ID + '/') for c in assignments)
    daily = next(c for c in writes if '/schedules/daily-backup-kst?' in c.args[1]).args[2]['properties']
    assert daily['timeZone'] == 'Asia/Seoul' and daily['isEnabled']
    assert daily['startTime'].endswith('T00:00:00+09:00')
    link = next(c for c in writes if '/jobSchedules/' in c.args[1]).args[2]['properties']
    assert link['parameters'] == {'Mode': 'Daily'}
    old = next(c for c in writes if '/Microsoft.DevTestLab/' in c.args[1]).args[2]['properties']
    assert old['status'] == 'Disabled' and old['targetResourceId'] == setup.VM_ID


@pytest.mark.parametrize('mode,scenario,deallocate', [
    ('Force', 'success', True), ('Force', 'archive_failed', True),
    ('Force', 'dispatch_failed', True), ('Force', 'timeout', True),
    ('Daily', 'busy', False), ('Daily', 'success', True),
    ('Daily', 'dispatch_failed', False), ('Daily', 'timeout', False),
    ('Cost', 'credit_cap', True), ('Cost', 'below_credit', False),
    ('Daily', 'expired', True), ('Force', 'view_failed', True),
])
def test_powershell_runbook_mocked_vm_lifecycle(tmp_path, mode, scenario, deallocate):
    pwsh = os.environ.get('UGRP_TEST_PWSH') or shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell parser/runtime unavailable; no Azure calls')
    content = azure_safety_setup.runbook_content()
    if scenario == 'timeout':
        content = content.replace('UtcNow.AddSeconds(600)', 'UtcNow.AddSeconds(0)')
    if scenario == 'expired':
        content = content.replace('2026-11-18T15:00:00Z', '2000-01-01T00:00:00Z')
    else:
        # Clock-independent test of daily-vs-expiry precedence.
        content = content.replace('2026-11-18T15:00:00Z', '2999-01-01T00:00:00Z')
    book = tmp_path / 'runbook.ps1'
    book.write_text(content)
    harness = tmp_path / 'harness.ps1'
    harness.write_text(r'''
param([string]$Book,[string]$Mode,[string]$Scenario)
$ErrorActionPreference='Stop'
$global:MockScenario=$Scenario
$global:MockEvents=[System.Collections.Generic.List[string]]::new()
function Disable-AzContextAutosave { param($Scope) }
function Connect-AzAccount { param([switch]$Identity) }
function Get-AzAccessToken { param($ResourceUrl) return @{Token='mock-token'} }
function Start-Sleep { param($Seconds) }
function Invoke-AzRestMethod {
    param($Method,$Path)
    if ($Path -match '/deallocate\?') {
        $global:MockEvents.Add('deallocate')
        return @{StatusCode=202;Content='{}'}
    }
    if ($Path -match '/instanceView\?') {
        if ($global:MockScenario -eq 'view_failed') { throw 'mock view unavailable' }
        return @{StatusCode=200;Content='{"statuses":[{"code":"PowerState/running"}]}'}
    }
    $vm=@{id='/subscriptions/mock/resourceGroups/mock/providers/Microsoft.Compute/virtualMachines/mock';location='koreacentral'}
    $values=if ($Path -match '88b7ee7f') { @($vm) } else { @() }
    return @{StatusCode=200;Content=(@{value=$values}|ConvertTo-Json -Depth 8 -Compress)}
}
function Invoke-WebRequest {
    param([switch]$UseBasicParsing,$Uri,$Method,$Body,$ContentType,$Headers,$TimeoutSec)
    if ($Uri -notmatch '/runCommands/' -and $Method -eq 'GET') {
        return Invoke-AzRestMethod -Method $Method -Path $Uri
    }
    if ($Uri -match '/query\?') {
        $usd=if ($global:MockScenario -eq 'below_credit') { 0 } elseif ($Uri -match '88b7ee7f') { 160 } else { 0 }
        return @{StatusCode=200;Content=(@{properties=@{columns=@(@{name='CostUSD'});rows=@(,@($usd))}}|ConvertTo-Json -Depth 8 -Compress)}
    }
    if ($Method -eq 'PUT') {
        $global:MockEvents.Add('graceful')
        $data=$Body|ConvertFrom-Json
        if (-not $data.properties.asyncExecution -or $data.properties.timeoutInSeconds -gt 600 -or $data.properties.source.script -notmatch 'SIGINT') { throw 'invalid guest payload' }
        if ($global:MockScenario -eq 'dispatch_failed') { throw 'mock command unavailable' }
        return @{StatusCode=202;Content='{}'}
    }
    $code=if ($global:MockScenario -eq 'busy') { 75 } elseif ($global:MockScenario -eq 'archive_failed') { 1 } else { 0 }
    $state=if ($code -eq 0) { 'Succeeded' } else { 'Failed' }
    return @{StatusCode=200;Content=(@{properties=@{instanceView=@{executionState=$state;exitCode=$code;output='{"archived":[],"failed":["one"]}'}}}|ConvertTo-Json -Depth 8 -Compress)}
}
$tokens=$null; $parseErrors=$null
[System.Management.Automation.Language.Parser]::ParseFile($Book,[ref]$tokens,[ref]$parseErrors)|Out-Null
if ($parseErrors.Count) { throw ($parseErrors|Out-String) }
& $Book -Mode $Mode
Write-Output ('MOCK_EVENTS='+($global:MockEvents|ConvertTo-Json -Compress -AsArray))
''')
    result = subprocess.run([pwsh, '-NoLogo', '-NoProfile', '-File', str(harness),
                             '-Book', str(book), '-Mode', mode, '-Scenario', scenario],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr + result.stdout
    events = json.loads(result.stdout.split('MOCK_EVENTS=')[1].strip() or '[]')
    assert ('deallocate' in events) == deallocate, result.stdout
    if deallocate:
        assert events.index('graceful') < events.index('deallocate')
    if mode == 'Daily' and not deallocate:
        assert 'DAILY_SKIPPED' in result.stdout


def test_command_signal_flushes_before_records_exit_and_hashes(root, monkeypatch):
    folder = run(root)
    folder.joinpath('EXIT').unlink()
    source = root / 'src/source'; source.mkdir(parents=True)
    monkeypatch.setattr(shutdown, 'process_start', lambda pid: 'ticks')
    handlers = {}
    monkeypatch.setattr(remote_run_finish.signal, 'signal', lambda sig, func: handlers.__setitem__(sig, func))
    child = Mock(pid=345)
    child.poll.return_value = None
    def wait():
        handlers[remote_run_finish.signal.SIGINT](2, None)
        folder.joinpath('raw').write_bytes(b'final flushed raw')
        return 130
    child.wait.side_effect = wait
    monkeypatch.setattr(remote_run_finish.subprocess, 'Popen', Mock(return_value=child))
    monkeypatch.setattr(remote_run_finish.os, 'killpg', Mock())
    def collect_after_flush(source, run):
        assert run.joinpath('raw').read_bytes() == b'final flushed raw'
        assert not run.joinpath('EXIT').exists()
        return []
    monkeypatch.setattr(remote_run_finish, 'collect', collect_after_flush)
    assert remote_run_finish.execute(source, folder, ['mock-sim']) == 130
    remote_run_finish.os.killpg.assert_called_once_with(345, remote_run_finish.signal.SIGINT)
    assert folder.joinpath('EXIT').read_text() == '130\n'
    assert 'raw' in folder.joinpath('SHA256SUMS').read_text()
    assert json.loads(folder.joinpath('HOST_ERROR.json').read_text())['reason'] == 'cost_stop_signal'


def test_archive_timeout_kills_only_own_copy_process_group(root, monkeypatch):
    folder = run(root)
    child = Mock(pid=456)
    child.wait.side_effect = [subprocess.TimeoutExpired('archive-one', 0.01), 0]
    monkeypatch.setattr(shutdown.subprocess, 'Popen', Mock(return_value=child))
    monkeypatch.setattr(shutdown.os, 'killpg', Mock())
    assert not shutdown.bounded_archive(root, folder, 0.01)
    shutdown.os.killpg.assert_called_once_with(456, shutdown.signal.SIGKILL)
    assert folder.joinpath('raw').exists()
    assert 'ARCHIVE_TIMEOUT' in next((root / 'lifecycle/archive-attempts').iterdir()).read_text()


def test_eight_hour_whole_grace_deadline_is_bounded(root, monkeypatch):
    run(root)
    monkeypatch.setattr(guard, 'ROOT', root)
    child = Mock(pid=999)
    child.wait.side_effect = [subprocess.TimeoutExpired('grace', 600), 0]
    monkeypatch.setattr(guard.subprocess, 'Popen', Mock(return_value=child))
    monkeypatch.setattr(guard.os, 'killpg', Mock())
    monkeypatch.setattr(guard, 'deallocate', Mock())
    guard.stop('eight_hour_cap')
    guard.deallocate.assert_called_once()
    guard.os.killpg.assert_called_once_with(999, guard.signal.SIGKILL)
    assert child.wait.call_args_list[0].kwargs == {'timeout': 600}
    record = json.loads(next((root / 'lifecycle/events').iterdir()).read_text())
    assert record['status'] == 'deadline_exceeded' and record['failed_or_unconfirmed'] == ['one']
