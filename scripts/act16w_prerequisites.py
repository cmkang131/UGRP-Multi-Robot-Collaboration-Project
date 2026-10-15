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


def snapshot(alert):
    raw = alert.read_bytes()
    return {"checked_at": datetime.now(timezone.utc).isoformat(),
            "ops_alert_sha256": hashlib.sha256(raw).hexdigest(), **signals(raw.decode())}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ops-alert", type=Path, required=True)
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
        row = snapshot(a.ops_alert)
        state.update(checks=state["checks"] + 1, latest=row,
                     elapsed_s=time.time() - state["started_epoch"], status=row["status"])
        with (a.out / "prerequisite-checks.jsonl").open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if state["elapsed_s"] >= state["max_wait_s"] and row["status"] != "INSPECT_QUEUE":
            state["status"] = "WAIT_EXPIRED"
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"check": state["checks"], "status": state["status"],
                          "checked_at": row["checked_at"], "warp1": row["warp1"],
                          "scene_decision": row["scene_decision"]}, ensure_ascii=False), flush=True)
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
