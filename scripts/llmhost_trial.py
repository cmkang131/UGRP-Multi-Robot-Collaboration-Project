"""One approval-gated command: start -> tunnel -> health -> 40 -> stop owned unit."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

from scripts import llmhost_ctl as ctl
from scripts.llmhost_common import ROOT, check_alerts, settings, write_json
from scripts.llmhost_benchmark import benchmark, load_corpus


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', choices=settings()['models'], required=True)
    p.add_argument('--corpus', type=Path, required=True)
    p.add_argument('--coordinator-approval', type=Path, required=True)
    p.add_argument('--queue', type=Path, default=ROOT/'experiments/2026-10-16-llmhost/queue.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--hourly-usd', type=float, required=True); p.add_argument('--rate-source', required=True)
    a = p.parse_args()
    if a.hourly_usd <= 0: p.error('positive whole-VM hourly USD required')
    queue = json.loads(a.queue.read_text())
    rejection_table = Path(queue['rejection_table'])
    if not rejection_table.is_absolute() or not rejection_table.is_file():
        raise ValueError('existing_absolute_rejection_table_required')
    load_corpus(a.corpus); check_alerts(); ctl.approval(a.coordinator_approval, a.candidate)
    a.output.mkdir(parents=True, exist_ok=False)
    c = settings(); tunnel = None; owned = False; began = time.monotonic()
    try:
        ctl.start(a.candidate, a.coordinator_approval); owned = True
        tunnel = subprocess.Popen(['gcloud', 'compute', 'ssh', 'ugrp@'+c['instance'],
            '--zone', c['zone'], '--account', c['account'], '--project', c['project'], '--',
            '-N', '-o', 'ExitOnForwardFailure=yes', '-L', '127.0.0.1:18080:127.0.0.1:8000'])
        # Uses the existing user-mandated idle 20 min as startup watchdog, no restart.
        deadline = time.monotonic() + c['idle_seconds']
        while True:
            if tunnel.poll() is not None: raise ValueError('tunnel_failed')
            if time.monotonic() >= deadline: raise ValueError('cap_end_startup_20min')
            try:
                with urlopen('http://127.0.0.1:18080/health', timeout=5) as response:
                    if response.status == 200: break
            except OSError: pass
            time.sleep(5)
        benchmark(a.corpus, a.output/'benchmark', a.candidate, a.hourly_usd, a.rate_source)
    except BaseException as exc:
        write_json(a.output/'host-error.json', dict(status='cap_end' if 'cap_end' in str(exc) else 'HOST_ERROR',
            reason_category=type(exc).__name__, detail=str(exc), blocked_object='not_applicable_serving',
            minimum_gap='not_measured_serving', research_result=False))
        raise
    finally:
        if tunnel is not None:
            tunnel.terminate(); tunnel.wait(timeout=15)
        if owned:
            ctl.guest('sudo systemctl stop ugrp-llmhost')
            write_json(a.output/'lifecycle.json', dict(allocation_wall_s=time.monotonic()-began,
                compute_usd=(time.monotonic()-began)*a.hourly_usd/3600,
                whole_vm_hourly_usd=a.hourly_usd, rate_source=a.rate_source,
                vm_stop_requested=False, idle_guard_and_budget_stop_unchanged=True))


if __name__ == '__main__': main()
