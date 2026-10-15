"""Read-only prerequisite watcher; no cloud, simulator or model imports.

The watcher never launches work. It ends when both coordinator signals exist,
then a caller must inspect the scene and validate the actual queue/table files.
Five-minute polling and ten-hour maximum come directly from the user request.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time


def signals(text, upstream_job='warp1'):
    if upstream_job not in ('warp1', 'warp3'):
        raise ValueError('unknown upstream job')
    # Do not accept our own act16w report mentioning the missing signal names.
    warp = [s for s in text.splitlines() if re.search(r"(?:^|\s)" + upstream_job + r":\s*", s)
            and not re.search(r"(?:^|\s)act16w(?:-\w+)?:", s)]
    scene = [s for s in text.splitlines() if "SCENE_DECISION:" in s
             and not re.search(r"(?:^|\s)act16w(?:-\w+)?:", s)]
    latest_warp = warp[-1] if warp else None
    latest_scene = scene[-1] if scene else None
    not_ready = bool(latest_warp and re.search(r"\bNOT_READY\b", latest_warp))
    ready = bool(latest_warp and latest_scene and not not_ready
                 and re.search(r"\bREADY(?:_HOLD_SCENE)?\b", latest_warp))
    extra = {}
    if upstream_job == 'warp3':
        # Coordinator handoff (2026-10-16 07:0x): warp1 ended NOT_READY.
        # These receipts only trigger inspection, never recording by themselves.
        distinct = [s for s in warp if re.search(r'\bDISTINCT_STARTS\b', s)]
        gates = [s for s in warp if re.search(r'\bTEACHER_GATE\b', s)]
        api = [s for s in warp if re.search(r'\bRECORD_API_READY\b', s)]
        counts = re.search(r'\bTEACHER_GATE\s+(?:(PASS|READY|COMPLETE|RUNNING|FAIL|PENDING)\s+)?'
                           r'(\d+)\s*/\s*(\d+)\b', gates[-1]) if gates else None
        n, N = map(int, counts.groups()[1:]) if counts else (0, 0)
        gate_pass = (N >= 40 and 0 <= n <= N and n / N >= .95
                     and counts.group(1) not in ('RUNNING', 'FAIL', 'PENDING')
                     and 'NOT_READY' not in gates[-1])
        distinct_pass = bool(distinct and re.search(r'\bPASS\b', distinct[-1])
                             and 'NOT_READY' not in distinct[-1])
        api_pass = bool(api and 'NOT_READY' not in api[-1])
        ready = bool(latest_scene and not not_ready and gate_pass and distinct_pass and api_pass)
        extra = {'distinct_starts': distinct[-1] if distinct else None,
                 'teacher_gate': gates[-1] if gates else None,
                 'record_api': api[-1] if api else None,
                 'record_api_pass': api_pass,
                 'teacher_success_n': n, 'teacher_attempts_N': N}
    return {"warp1": latest_warp if upstream_job == 'warp1' else None,
            "upstream_job": upstream_job, "upstream_signal": latest_warp,
            "scene_decision": latest_scene, **extra,
            "warp_not_ready": not_ready, "signals_present": bool(latest_warp and latest_scene),
            "ready_for_queue_inspection": ready,
            "status": "INSPECT_QUEUE" if ready else "WAIT_NOT_READY" if not_ready else "WAIT_SIGNALS"}


def snapshot(alert, teacher_queue=None, upstream_job='warp1'):
    raw = alert.read_bytes()
    row = {"checked_at": datetime.now(timezone.utc).isoformat(),
           "ops_alert_sha256": hashlib.sha256(raw).hexdigest(),
           "watcher_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           **signals(raw.decode(), upstream_job)}
    if teacher_queue is not None:
        row['teacher_queue'] = str(teacher_queue.resolve())
        if not teacher_queue.is_file():
            row.update(status='WAIT_QUEUE', ready_for_queue_inspection=False)
        else:
            try:
                queue_raw = teacher_queue.read_bytes()
                queue = json.loads(queue_raw)
                table = Path(queue.get('rejection_table') or '__missing__')
                row.update(queue_sha256=hashlib.sha256(queue_raw).hexdigest(),
                    queue_backend_readiness=queue.get('backend_readiness'),
                    queue_status=queue.get('status'), queue_blockers=queue.get('blockers', []),
                    rejection_table_exists=table.is_absolute() and table.is_file())
                if queue.get('backend_readiness') == 'NOT_READY':
                    row.update(status='WAIT_NOT_READY', ready_for_queue_inspection=False)
                elif not row['rejection_table_exists']:
                    row.update(status='WAIT_REJECTION_TABLE', ready_for_queue_inspection=False)
                elif queue.get('backend_readiness') not in ('READY', 'READY_HOLD_SCENE'):
                    row.update(status='WAIT_QUEUE_READINESS', ready_for_queue_inspection=False)
                elif (row['signals_present'] and not row['warp_not_ready']
                      and (upstream_job == 'warp1' or row['ready_for_queue_inspection'])):
                    # The user requires a warp1 line plus its ready queue, not
                    # an exact spelling of READY in the progress alert itself.
                    row.update(status='INSPECT_QUEUE', ready_for_queue_inspection=True)
            except (ValueError, TypeError, AttributeError, OSError) as error:
                row.update(status='WAIT_QUEUE_INVALID', queue_error=str(error),
                           ready_for_queue_inspection=False)
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ops-alert", type=Path, required=True)
    p.add_argument('--upstream-job', choices=('warp1', 'warp3'), default='warp1')
    p.add_argument("--teacher-queue", type=Path,
                   help='actual warp1 queue once published; require its readiness and real rejection table')
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--watch", action="store_true")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    state_file = a.out / "wait-state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
    else:
        state = {"started_epoch": time.time(), "max_wait_s": 36000, "poll_s": 300,
                 "ops_alert": str(a.ops_alert.resolve()), "checks": 0, "status": "WAIT_SIGNALS"}
    while True:
        row = snapshot(a.ops_alert, a.teacher_queue, a.upstream_job)
        state.update(checks=state["checks"] + 1, latest=row,
                     upstream_job=a.upstream_job,
                     elapsed_s=time.time() - state["started_epoch"], status=row["status"])
        if a.teacher_queue:
            state['teacher_queue'] = str(a.teacher_queue.resolve())
        else:
            state.pop('teacher_queue', None)
        with (a.out / "prerequisite-checks.jsonl").open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if state["elapsed_s"] >= state["max_wait_s"] and row["status"] != "INSPECT_QUEUE":
            state["status"] = "WAIT_EXPIRED"
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"check": state["checks"], "status": state["status"],
                          "checked_at": row["checked_at"], "warp1": row["warp1"],
                          "upstream_signal": row['upstream_signal'],
                          "teacher_success_n": row.get('teacher_success_n'),
                          "teacher_attempts_N": row.get('teacher_attempts_N'),
                          "record_api_ready": row.get('record_api_pass', False),
                          "scene_decision": row["scene_decision"],
                          "queue_backend_readiness": row.get('queue_backend_readiness'),
                          "rejection_table_exists": row.get('rejection_table_exists')}, ensure_ascii=False), flush=True)
        if not a.watch or state["status"] in ("INSPECT_QUEUE", "WAIT_EXPIRED"):
            break
        # Short individual waits keep the interactive tool responsive. Heartbeats
        # are informational only; the prerequisite file is reread every 300 s.
        deadline = min(time.time() + state["poll_s"], state["started_epoch"] + state["max_wait_s"])
        while time.time() < deadline:
            time.sleep(min(30, max(0, deadline - time.time())))
            print(json.dumps({"heartbeat": datetime.now(timezone.utc).isoformat(),
                              "status": state["status"]}), flush=True)


if __name__ == "__main__":
    main()
