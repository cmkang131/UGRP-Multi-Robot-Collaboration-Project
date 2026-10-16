"""Finite task-owned scheduler; resume paused groups without changing SIM state."""
import datetime
import json
import os
from pathlib import Path
import signal
import time

ROOT=Path('/home/ugrp/ugrp-sim/runs/warp3')
LEASE=Path('/home/ugrp/ugrp-sim/leases/warp3.json')
END=datetime.datetime.fromisoformat('2026-10-16T05:57:25.154+00:00')


def read(path):
    try:return json.loads(path.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return {}


def owns(group,pid):
    try:args=[s.decode() for s in Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0') if s]
    except FileNotFoundError:return False
    return '--out' in args and args[args.index('--out')+1]==str(ROOT/f'teacher-r1-group{group}')


def main():
    active={0,2,3};pending=[4,1,5,6];events=[]
    pids={g:read(ROOT/f'teacher-r1-group{g}-receipt.json')['pid'] for g in range(7)}
    while datetime.datetime.now(datetime.timezone.utc)<END:
        complete={g for g in range(7) if read(ROOT/f'teacher-r1-group{g}/summary.json').get('status') not in (None,'running')}
        active-=complete
        while len(active)<3 and pending:
            group=pending.pop(0)
            if group in complete:continue
            pid=pids[group]
            if not owns(group,pid):raise RuntimeError(f'cannot resume missing/mismatched own group{group} PID{pid}')
            os.kill(pid,signal.SIGCONT);active.add(group)
            events.append(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),group=group,pid=pid,signal='SIGCONT'))
        state=dict(task='warp3',scheduler_pid=os.getpid(),active_groups=sorted(active),pending_groups=pending,
            completed_groups=sorted(complete),events=events)
        (ROOT/'gate-schedule-state.json').write_text(json.dumps(state,indent=2)+'\n')
        lease=read(LEASE)
        if lease.get('task')!='warp3':raise RuntimeError('own lease lost')
        lease.update(scheduler_pid=os.getpid(),active_pids=[pids[g] for g in sorted(active)],paused_pids=[pids[g] for g in pending])
        LEASE.write_text(json.dumps(lease,indent=2)+'\n')
        if len(complete)==7:return
        time.sleep(20)
    # Administrative resource cap, not a teacher action or task-score decision.
    for group,pid in pids.items():
        if not owns(group,pid):continue
        out=ROOT/f'teacher-r1-group{group}'
        (out/'SUPERVISOR_STOP.json').write_text(json.dumps(dict(category='cap_end',reason='warp3_resource_8h_cap'))+'\n')
        os.kill(pid,signal.SIGCONT);os.kill(pid,signal.SIGINT)


if __name__=='__main__':main()
