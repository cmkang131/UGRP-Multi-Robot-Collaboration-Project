"""Bounded, discrete-event plumbing check; not a physics experiment.

Default: prompt-only mock clients for T0/T1/T2. --real opts into the brain's
default client and its shared call ledger; this runner never creates a client
or changes its spend guard. The parent owns the campaign-wide 60-call budget.
"""

import argparse
import heapq
import json
import math
from pathlib import Path
import re
import sys
import traceback


ROOT = Path(__file__).resolve().parent
ZONES = ("orange", "blue", "purple")
ROBOTS = ("r1", "r2")
ORDERS = {"red": "blue", "blue": "purple"}
SIM_CAP = 900.0
DECISION_CAP = 32


def json_values(text):
    """Read embedded JSON, including JSON carried inside message strings."""
    decoder = json.JSONDecoder()
    offset = 0
    while offset < len(text):
        match = re.search(r"[\[{]", text[offset:])
        if match is None:
            break
        start = offset + match.start()
        try:
            value, size = decoder.raw_decode(text[start:])
        except ValueError:
            offset = start + 1
            continue
        yield value
        offset = start + size


def walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)
    elif isinstance(value, str):
        for item in json_values(value):
            yield from walk(item)


class MockClient:
    """Stateless response double: all choices derive exclusively from prompt."""

    def call(self, prompt, response_format=None):
        progress_match = re.search(r"^Progress:\s*(.*)$", prompt, re.M)
        if not progress_match:
            raise ValueError("Mock requires the planning.py JSON Progress field")
        progress = json.loads(progress_match.group(1))
        own = list(walk(progress))
        rid = next((v[k] for v in own if isinstance(v, dict)
                    for k in ("robot", "rid") if v.get(k) in ROBOTS), None)
        if rid is None:
            raise ValueError("Progress must identify the acting robot")
        own_orders = {}
        holding = None
        for value in own:
            if isinstance(value, dict):
                if "holding" in value:
                    holding = value["holding"]
                if isinstance(value.get("orders"), dict):
                    own_orders.update(value["orders"])

        if "Available actions:" not in prompt:
            message = json.dumps({"robot": rid, "orders": own_orders})
            return {"raw_output": json.dumps({"message": message})}

        menu_text = prompt.split("Available actions:", 1)[1].split("\nAnswer:", 1)[0]
        menu = re.findall(r"^([A-Z]+)\.\s*(.+)$", menu_text, re.M)
        if not menu:
            raise ValueError("Mock requires the planning.py lettered action menu")
        previous_match = re.search(r"^Previous actions:\s*(.*)$", prompt, re.M)
        previous = previous_match.group(1).lower() if previous_match else ""
        times = [v[k] for v in own if isinstance(v, dict)
                 for k in ("time", "now_s")
                 if isinstance(v.get(k), (int, float))]
        sent_before = bool(re.search(r"send|message", previous)) or max(times, default=0) >= 2
        messages = [(label, text) for label, text in menu
                    if "send" in text.lower() and "message" in text.lower()]
        if messages and not sent_before:
            return {"raw_output": messages[0][0]}

        known_orders = dict(own_orders)
        for root in json_values(prompt):
            for value in walk(root):
                if isinstance(value, dict) and isinstance(value.get("orders"), dict):
                    known_orders.update(value["orders"])
        tasks = [(label, text) for label, text in menu
                 if "wait" not in text.lower()
                 and not ("send" in text.lower() and "message" in text.lower())]
        chosen = None
        destination = known_orders.get(holding)
        if destination:
            chosen = next((label for label, text in tasks
                           if "destination" in text.lower()
                           and f"<{destination}>" in text), None)
        if chosen is None:
            chosen = tasks[0][0] if tasks else menu[0][0]
        # A letter also works for the intermediate CoT response; no secret state.
        return {"raw_output": chosen}


def run(team, *, real=False, log_dir=None):
    directory = Path(log_dir) if log_dir else ROOT / "evidence" / f"mock-{team}"
    directory.mkdir(parents=True, exist_ok=True)
    brain = None
    now = 0.0
    decisions = 0
    door_until = 0.0
    queue = [(0.0, index, rid, "ready") for index, rid in enumerate(ROBOTS)]
    heapq.heapify(queue)
    serial = len(queue)
    boxes = {color: {"owner": None, "transported": False, "placed": None}
             for color in ORDERS}
    robots = {rid: {"point": "pick", "holding": None, "destination": None,
                    "done": False} for rid in ROBOTS}
    events = []
    reason = "incomplete"
    error = None
    report = None

    def schedule(rid, kind, when):
        nonlocal serial
        serial += 1
        heapq.heappush(queue, (when, serial, rid, kind))

    try:
        from brain import TeamBrain

        brain = TeamBrain(team, list(ROBOTS),
                          "Transport the red and blue boxes through the single door "
                          "and place each in its privately ordered zone. Share orders "
                          "when communication is available. Each robot carries one box.",
                          client=None if real else MockClient(), log_dir=str(directory))
        brain.max_calls = 26 if real else 120
        for rid, color in zip(ROBOTS, ("blue", "red")):
            brain.tell(rid, {"robot": rid, "orders": {color: ORDERS[color]},
                             "visible_boxes": ["red", "blue"], "zones": list(ZONES),
                             "durations_s": {"pick": 58, "transport": 102,
                                             "place": 9, "message": 2}})
        while queue:
            when, _, rid, kind = heapq.heappop(queue)
            if when > SIM_CAP:
                now = SIM_CAP
                reason = "simulation_clock_cap"
                break
            now = when
            state = robots[rid]
            if kind == "picked":
                state["point"] = "destination"
                brain.tell(rid, {"robot": rid, "holding": state["holding"],
                                 "event": "grasp_completed", "time": now})
            elif kind == "transported":
                boxes[state["holding"]]["transported"] = True
                events.append({"time": now, "robot": rid, "event": kind,
                               "box": state["holding"]})
                brain.tell(rid, {"event": "transport_completed", "time": now})
                schedule(rid, "placed", now + 9)
                continue
            elif kind == "placed":
                boxes[state["holding"]]["placed"] = state["destination"]
                state["done"] = True
                events.append({"time": now, "robot": rid, "event": kind,
                               "box": state["holding"], "zone": state["destination"]})
                brain.tell(rid, {"event": "place_completed", "time": now,
                                 "placed_zone": state["destination"]})
                if all(s["done"] for s in robots.values()):
                    reason = "completed"
                continue

            if decisions >= DECISION_CAP:
                reason = "decision_cap"
                break
            point = state["point"]
            if point == "pick":
                options = [{"key": f"box:{color}",
                            "text": f"go grasp target object <{color}>"}
                           for color, box in boxes.items() if box["owner"] is None]
            elif point == "destination":
                options = [{"key": f"zone:{zone}",
                            "text": f"choose destination <{zone}>"} for zone in ZONES]
            else:
                options = [{"key": "door:go", "text": "transport held box through single door"}]
            options.append({"key": "wait", "text": "wait here"})
            brain.tell(rid, {"robot": rid, "time": now, "holding": state["holding"],
                             "point": point, "door_busy_until": door_until,
                             "selected_destination": state["destination"]})
            decisions += 1
            result = brain.decide(rid, now, point, options)
            events.append({"time": now, "robot": rid, "point": point,
                           "options": options, "decision": result})
            if result.get("halted"):
                reason = "brain_halted"
                break
            option = result["option"]
            if option not in {entry["key"] for entry in options}:
                raise ValueError(f"Brain returned unavailable option: {option!r}")
            if option == "wait":
                delay = float(result.get("wait_s", 0))
                if not math.isfinite(delay) or delay < 0:
                    raise ValueError("Invalid wait_s")
                if result.get("sent"):
                    delay = max(2.0, delay)
                elif point == "door" and door_until > now:
                    delay = max(delay, door_until - now)
                else:
                    future = [event[0] for event in queue if event[0] > now]
                    delay = max(delay, min(future) - now if future else 10.0)
                schedule(rid, "ready", now + delay)
            elif point == "pick":
                color = option.split(":", 1)[1]
                boxes[color]["owner"] = rid
                state["holding"] = color
                schedule(rid, "picked", now + 58)
            elif point == "destination":
                state["destination"] = option.split(":", 1)[1]
                state["point"] = "door"
                schedule(rid, "ready", now)
            elif door_until > now:
                events.append({"time": now, "robot": rid, "event": "door_rejected_busy",
                               "retry_at": door_until})
                brain.tell(rid, {"event": "door_rejected_busy", "time": now,
                                 "retry_at": door_until})
                # Rejection consumes no transport; retry only when the door frees.
                schedule(rid, "ready", door_until)
            else:
                door_until = now + 102
                events.append({"time": now, "robot": rid, "event": "transport_started",
                               "door_release_at": door_until})
                schedule(rid, "transported", door_until)
    except Exception:
        reason = "exception"
        error = traceback.format_exc()
    finally:
        try:
            report = brain.record() if brain is not None else {"unavailable": "constructor failed"}
        except Exception:
            report = {"record_error": traceback.format_exc()}
            error = (error or "") + report["record_error"]
            reason = "record_failed"
        transported = sum(box["transported"] for box in boxes.values())
        placed = sum(box["placed"] is not None for box in boxes.values())
        correct = sum(box["placed"] == ORDERS[color] for color, box in boxes.items())
        summary = {"team": team, "real": real, "reason": reason, "error": error,
                   "sim_time_s": now, "decisions": decisions, "max_calls": brain.max_calls if brain else None,
                   "total_boxes": 2, "excluded": 0,
                   "transport_completed": transported, "placed": placed,
                   "correct_placement": correct, "transport_coverage": transported / 2,
                   "correct_placement_rate": correct / 2,
                   "success": reason == "completed" and correct == 2 and error is None,
                   "boxes": boxes, "events": events}
        # Preserve the module's report verbatim; runner scoring is a separate file.
        (directory / "brain-record.json").write_text(json.dumps(report, indent=2) + "\n")
        (directory / "runner-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true", help="Use the real default brain client")
    parser.add_argument("--team", choices=("T0", "T1", "T2"))
    parser.add_argument("--log-dir", type=Path)
    args = parser.parse_args()
    if args.real and args.team is None:
        parser.error("--real requires --team; the parent owns the 60-call campaign cap")
    teams = [args.team] if args.team else ["T0", "T1", "T2"]
    results = []
    for team in teams:
        directory = args.log_dir
        if directory is not None and len(teams) > 1:
            directory = directory / team
        if directory is None:
            directory = ROOT / "evidence" / f"{'real' if args.real else 'mock'}-{team}"
        result = run(team, real=args.real, log_dir=directory)
        results.append(result)
        print(json.dumps({k: v for k, v in result.items() if k not in ("events", "boxes")}))
    # Wrong placement is an observed task failure, not an executor crash.
    return 0 if all(r["reason"] == "completed" and r["error"] is None for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
