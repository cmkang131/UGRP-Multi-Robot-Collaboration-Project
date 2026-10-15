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


def signals(text):
    # Do not accept our own act16w report mentioning the missing signal names.
    warp = [s for s in text.splitlines() if re.search(r"(?:^|\s)warp1:\s*", s)
            and not re.search(r"(?:^|\s)act16w(?:-\w+)?:", s)]
    scene = [s for s in text.splitlines() if "SCENE_DECISION:" in s
             and not re.search(r"(?:^|\s)act16w(?:-\w+)?:", s)]
    latest_warp = warp[-1] if warp else None
    latest_scene = scene[-1] if scene else None
    not_ready = bool(latest_warp and re.search(r"\bNOT_READY\b", latest_warp))
    ready = bool(latest_warp and latest_scene and not not_ready
                 and re.search(r"\bREADY(?:_HOLD_SCENE)?\b", latest_warp))
    return {"warp1": latest_warp, "scene_decision": latest_scene,
            "warp_not_ready": not_ready, "signals_present": bool(latest_warp and latest_scene),
            "ready_for_queue_inspection": ready,
            "status": "INSPECT_QUEUE" if ready else "WAIT_NOT_READY" if not_ready else "WAIT_SIGNALS"}


def snapshot(alert, teacher_queue=None):
    raw = alert.read_bytes()
    row = {"checked_at": datetime.now(timezone.utc).isoformat(),
           "ops_alert_sha256": hashlib.sha256(raw).hexdigest(),
           "watcher_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           **signals(raw.decode())}
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
                elif row['signals_present'] and not row['warp_not_ready']:
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
        row = snapshot(a.ops_alert, a.teacher_queue)
        state.update(checks=state["checks"] + 1, latest=row,
                     elapsed_s=time.time() - state["started_epoch"], status=row["status"])
        if a.teacher_queue:
            state['teacher_queue'] = str(a.teacher_queue.resolve())
        with (a.out / "prerequisite-checks.jsonl").open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if state["elapsed_s"] >= state["max_wait_s"] and row["status"] != "INSPECT_QUEUE":
            state["status"] = "WAIT_EXPIRED"
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"check": state["checks"], "status": state["status"],
                          "checked_at": row["checked_at"], "warp1": row["warp1"],
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
