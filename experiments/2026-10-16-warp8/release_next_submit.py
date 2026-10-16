"""Submit one remaining group on gcp3 after verified no-cap startup; no cloud credentials."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time

ROOT = Path('/home/ugrp/ugrp-sim')
OPS = ROOT / 'ops-reviews/warp8'
SOURCE = '175281c8922453465f8bf32707e22988e78b8812'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tag', required=True)
    p.add_argument('--driver', type=Path, required=True)
    p.add_argument('--driver-sha256', required=True)
    a = p.parse_args()
    assert socket.gethostname().split('.')[0] == 'ugrp-act-l4-gcp3'
    assert a.driver.is_absolute() and digest(a.driver) == a.driver_sha256
    plan = json.loads((OPS / 'release-batch-plan-current.json').read_text())
    assert plan['source_sha'] == SOURCE
    group = next(g for g in plan['groups'] if g['tag'] == a.tag)
    before = plan['groups'][:plan['groups'].index(group)]
    # All prior groups must be terminal and audited. A failed first30 blocks
    # new submissions; finishing before30 is explicitly assessed by the operator.
    for prior in before:
        run = ROOT / 'runs/warp8' / prior['tag']
        receipt = json.loads(run.with_suffix('.receipt.json').read_text())
        check = json.loads((OPS / (prior['tag'] + '-admission.json')).read_text())
        assert receipt['exit_code'] == 0 and check['continue_authorized'] is True
        assert check['raw_summary_sha256'] == digest(run / 'summary.json')
    session = json.loads((OPS / 'host-start-nocap.json').read_text())
    assert session['project'] == 'ugrp-sim-c-1016'
    assert session['account'] == 'changmin5781@gmail.com'
    assert session['vm'] == 'ugrp-act-l4-gcp3'
    assert session['max_run_duration_s'] is None and session['supervisor_wall_deadline'] is None
    assert session['clear_verified'] is True and session['started_without_cap_flags'] is True
    assert session['budget_stop_verified'] is True
    lock = (ROOT / 'leases/.warp9-claim.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert not list((ROOT / 'leases').glob('*.json'))
        assert not subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid',
            '--format=csv,noheader'], text=True).strip()
        assert subprocess.run(['pgrep', '-f', '[n]vidia-cuda-mps'], capture_output=True).returncode == 1
        assert subprocess.check_output(['systemctl', 'is-active', 'ugrp-idle-guard.timer'], text=True).strip() == 'active'
        src = ROOT / 'src' / SOURCE
        assert subprocess.check_output(['git', '-C', str(src), 'rev-parse', 'HEAD'], text=True).strip() == SOURCE
        assert not subprocess.check_output(['git', '-C', str(src), 'status', '--porcelain', '--untracked-files=no'])
        table, cases, refs = [Path(plan[k]) for k in ('rejection_table', 'cases')] + [Path(group['references'])]
        assert table.is_absolute() and table.is_file()
        assert digest(cases) == plan['cases_sha256'] and digest(refs) == group['references_sha256']
        assert group['N'] == len(group['indices']) == len(group['seeds'])
        assert not (ROOT / 'runs/warp8' / a.tag).exists()
        cmd = ['python3', str(a.driver), '--source-sha', SOURCE, '--tag', a.tag,
            '--flow', 'release', '--cases', str(cases), '--indices', ','.join(map(str, group['indices'])),
            '--references', str(refs), '--canonical-xml', group['canonical_xml'],
            '--rejection-table', str(table), '--full-active-dof-workspace-v1']
        with (OPS / (a.tag + '.driver.log')).open('x') as log:
            child = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True)
        lease = ROOT / 'leases' / ('warp8-' + a.tag + '.json')
        # This bounds only the resource launch handshake, not task execution.
        until = time.monotonic() + 10
        while not lease.exists() and child.poll() is None and time.monotonic() < until:
            time.sleep(.1)
        assert lease.exists() and child.poll() is None
        record = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), group=group,
            driver_PID=child.pid, lease=json.loads(lease.read_text()), actual_command=cmd,
            driver_sha256=a.driver_sha256, submitter_sha256=digest(Path(__file__)),
            source_sha=SOURCE, session=session, GPU_before_launch='none', MPS='off')
        with (OPS / (a.tag + '-submit.json')).open('x') as f:
            json.dump(record, f, indent=2)
        print(json.dumps(record), flush=True)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


if __name__ == '__main__':
    main()
