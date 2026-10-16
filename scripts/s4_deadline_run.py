"""Run one owned DEV process group with an absolute UTC deadline on x86."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def run(argv, root, deadline, source_sha):
    root = Path(root).resolve()
    if not root.is_relative_to(Path.home()/'ugrp-sim/runs'):
        raise ValueError('persistent run directory required')
    if not 5 < deadline-time.time() <= 86400:
        raise ValueError('expired or nonfinite absolute deadline')
    # Reserve the five-second graceful-exit window BEFORE the user's hard cap.
    effective = min(deadline-5., time.time()+10800)
    meta = dict(**{'class': 'dev', 'pr': 425}, research_result=False,
        source_sha=source_sha, deadline_utc=datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
        deadline_unix=deadline, effective_deadline_unix=effective, argv=argv)
    with (root/'RUN_META.json').open('x') as f: json.dump(meta, f, indent=2)
    child = subprocess.Popen(argv, start_new_session=True)
    (root/'deadline-driver.json').write_text(json.dumps(dict(pid=child.pid, pgid=child.pid, **meta)))
    timed_out = False
    try:
        while child.poll() is None:
            remaining = effective-time.time()
            if remaining <= 0:
                timed_out = True; break
            try: child.wait(timeout=min(1., remaining))
            except subprocess.TimeoutExpired: pass
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.wait()
    if timed_out:
        (root/'deadline-stop.json').write_text(json.dumps(dict(classification='HOST_ERROR',
            reason='USER_ABSOLUTE_HARD_CAP', deadline_unix=deadline, stopped_unix=time.time())))
    return 124 if timed_out else child.returncode


def main():
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, required=True)
    p.add_argument('--deadline-utc', required=True); p.add_argument('--source-sha', required=True)
    p.add_argument('argv', nargs=argparse.REMAINDER); a=p.parse_args()
    dt=datetime.fromisoformat(a.deadline_utc.replace('Z', '+00:00'))
    if dt.tzinfo is None: raise ValueError('explicit timezone required')
    argv=a.argv[1:] if a.argv[:1] == ['--'] else a.argv
    if not argv: raise ValueError('command required')
    def stop(signum, frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    return run(argv, a.root, dt.timestamp(), a.source_sha)


if __name__ == '__main__': raise SystemExit(main())
