#!/usr/bin/env python3
"""Offline shortfall-cause decomposition for team runs (standard library only).

Reads the same run directories as compare.py plus planner records
(brain-record.json, llm-calls.jsonl). Never runs a simulation or an LLM.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re

from compare import PUT_DOWN, analyze_run, decisions, markdown, read_json, sign

EPS = 1e-6          # tolerance for exact (unrounded) event times
LOOSE = 0.051       # tolerance when only 0.1 s rounded times exist
MATCH = 0.051       # decision matching window, same as compare.py
STRUCTURES = ("T0", "T1", "T2")
# not_sent_cap is an analysis-only side tag (2026-11-16): a refinement of not_sent, never a primary cause (not in PRIMARY_ORDER).
TAGS = ("not_sent", "late", "ignored", "guess_wrong", "no_info_T0", "dropped_needed", "other", "not_sent_cap")
PRIMARY_ORDER = ("no_info_T0", "ignored", "late", "not_sent", "guess_wrong", "dropped_needed", "other")
PUT_KINDS = ("decoy", "duplicate", "lost")   # put-down of a box whose colour is not ordered / already covered / still needed
LABELS = ("own_order", "message", "guess", "conflicts_message", "unknown")
SUCCESS_CLASSES = ("guess_correct", "message_grounded", "own_only", "other_or_unknown")
SIGN_RE = re.compile(r"sign\s*(\d+)", re.I)
NEGATED = re.compile(r"\b(?:not|instead of|rather than)\s+sign\s*\d+", re.I)
ADDRESSED = re.compile(r"\b(?:please|you|your|could|can you|take the|grab the|go ahead)\b", re.I)
FIRST_PERSON = re.compile(r"^\W*(?:i|i'm|i've|i'll|we|my)\b", re.I)


# ---------------------------------------------------------------- messages
def norm_sign(value):
    text = sign(value) if value is not None else None
    match = SIGN_RE.search(text) if isinstance(text, str) else None
    return "sign" + match[1] if match else None


def colour_of(value, colours):
    if not isinstance(value, str):
        return None
    value = value.lower()
    if value in colours:
        return value
    match = re.fullmatch(r"([a-z]+?)_?\d*", value)
    return match[1] if match and match[1] in colours else None


def message_pairs(text, colours):
    """Return (pairs, facts_ok). Each pair: pair, kind, robot, src."""
    pairs, payload = [], None
    try:
        payload = json.loads(text) if isinstance(text, str) else text
    except ValueError:
        payload = None
    body = text if isinstance(text, str) else ""
    if isinstance(payload, dict):
        body = str(payload.get("message", ""))
        for fact in payload.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            value = fact.get("value") if isinstance(fact.get("value"), dict) else {}
            colour = (colour_of(value.get("box") or value.get("colour"), colours)
                      or colour_of(fact.get("id"), colours))
            zone = norm_sign(value.get("delivered") or value.get("zone") or value.get("dest"))
            if not colour or not zone:
                continue
            table = fact.get("table")
            kind = "delivered" if "delivered" in value else (
                "assignment" if table == "assignments" else "order" if table == "orders" else "info")
            pairs.append({"pair": (colour, zone), "kind": kind,
                          "robot": value.get("robot"), "src": "fact"})
    for sentence in re.split(r"[.;!?\n]", NEGATED.sub("", body)):
        found = [(m.start(), m[0].lower()) for c in colours
                 for m in re.finditer(r"\b" + re.escape(c) + r"\b", sentence, re.I)]
        signs = [(m.start(), "sign" + m[1]) for m in SIGN_RE.finditer(sentence)]
        if not found or not signs:
            continue
        kind = "text_directive" if ADDRESSED.search(sentence) and not FIRST_PERSON.match(
            sentence.strip()) else "text_self"
        distinct = {c for _, c in found}
        for position, zone in signs:
            if len(distinct) == 1:
                colour = found[0][1]
            else:
                before = [f for f in found if f[0] < position]
                colour = (before[-1] if before else min(found, key=lambda f: abs(f[0] - position)))[1]
            pairs.append({"pair": (colour, zone), "kind": kind, "robot": None, "src": "text"})
    return pairs, isinstance(payload, dict)


def recipients(message, robots):
    to = message.get("to")
    if isinstance(to, str):
        to = [] if to in ("all", "*", "broadcast") else [to]
    to = to or [r for r in robots if r != message.get("from")]
    return set(to)


def load_messages(team, brain, robots, colours):
    if isinstance(brain.get("messages"), list):
        raw = brain["messages"]
    else:
        rows = decisions(team.get("decisions"))
        if rows and all("sent" in d for d in rows):
            raw = [dict(m, **{"from": m.get("from", d.get("rid"))}) for d in rows for m in d["sent"]]
        else:
            return None
    result = []
    for m in raw:
        pairs, facts_ok = message_pairs(m.get("text"), colours)
        send = m.get("time")
        result.append({"from": m.get("from"), "to": recipients(m, robots), "send": send,
                       "deliver": m.get("deliver_at", send), "pairs": pairs,
                       "facts_ok": facts_ok, "via": m.get("via")})
    return result


def message_stats(messages, brain, team, robots):
    """Analysis-only message labels (2026-11-16): where each message came from (planner record key `via`: "chance" = a reply
    written between decisions, no key = written at a decision point) and whether a robot reached the per-robot cap.
    The cap is read from the record (`max_messages_per_robot`, T1/T2 only); without it cap_reached is None (NA), never 0.
    cap_times[rid] = send time of that robot's cap-th message. Warnings: counts disagree with the record's own tallies, or the
    `via` marks disagree with the recorded chances (a planner older than brain-v3 does not write `via`, so its chance messages
    read as decision messages)."""
    out = {"via_decision": None, "via_chance": None, "chance_recorded": None, "cap": None, "cap_reached": None,
           "cap_robots": [], "cap_times": {}, "sent_by_robot": {}, "warnings": []}
    if messages is None:
        return out
    out["via_chance"] = sum(m["via"] == "chance" for m in messages)
    out["via_decision"] = len(messages) - out["via_chance"]
    out["sent_by_robot"] = {r: sum(m["from"] == r for m in messages) for r in robots}
    recorded = brain.get("chances") if isinstance(brain.get("chances"), dict) else None
    if recorded is not None:
        out["chance_recorded"] = sum(len(c.get("sent") or []) for rows in recorded.values() for c in rows if isinstance(c, dict))
    elif isinstance(team.get("chances"), list):
        out["chance_recorded"] = sum(len(c.get("sent") or []) for c in team["chances"] if isinstance(c, dict))
    if out["chance_recorded"] is not None and out["chance_recorded"] != out["via_chance"]:
        out["warnings"].append("via marks %d chance messages but the chance record holds %d (older planner without `via`?)"
                               % (out["via_chance"], out["chance_recorded"]))
    cap = brain.get("max_messages_per_robot")
    if isinstance(cap, int) and not isinstance(cap, bool) and cap > 0:
        out["cap"] = cap
        for rid in robots:
            times = sorted(m["send"] for m in messages if m["from"] == rid and m["send"] is not None)
            if len(times) >= cap:
                out["cap_robots"].append(rid)
                out["cap_times"][rid] = times[cap - 1]
        out["cap_reached"] = bool(out["cap_robots"])
        tally = brain.get("messages_by_robot")
        if isinstance(tally, dict) and any(tally.get(r) != out["sent_by_robot"][r] for r in robots):
            out["warnings"].append("messages_by_robot %s differs from the message list %s" % (tally, out["sent_by_robot"]))
    return out


def received(rid, time, eps, messages):
    return [m for m in messages if rid in m["to"] and m["from"] != rid
            and m["deliver"] is not None and m["deliver"] <= time + eps]


# ----------------------------------------------------------------- prompts
def load_calls(path):
    """Action prompts keyed by (robot, point, time); one entry per decision."""
    calls = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        prompt = row.get("raw_prompt") or ""
        if row.get("event") != "finish" or "choose the best available action" not in prompt:
            continue
        match = re.search(r"^Progress: (\{.*\})$", prompt, re.M)
        try:
            progress = json.loads(match[1])
        except (TypeError, ValueError):
            continue
        facts = progress.get("own_facts") or []
        orders = {(f_["box"], norm_sign(f_["zone"])) for f in facts if isinstance(f, dict)
                  for f_ in f.get("orders", []) if isinstance(f_, dict) and "box" in f_}
        holding = [f["holding"] for f in facts if isinstance(f, dict) and f.get("holding")]
        seen = None
        section = re.search(r"Dialogue history:(.*?)\n(?:Previous actions|Available actions|Note):",
                            prompt, re.S)
        if section:
            seen = set()
            for part in reversed(section[1].strip().splitlines()):
                if part.startswith("["):
                    try:
                        seen = {(d.get("from"), round(float(d.get("time", 0)), 1))
                                for d in json.loads(part)}
                    except (ValueError, TypeError):
                        pass
                    break
        calls.append({"call_index": row.get("call_index"), "robot": progress.get("robot"),
                      "point": progress.get("point"), "time": progress.get("time"),
                      "orders": orders, "holding": holding[-1] if holding else None, "seen": seen})
    return calls


def find_call(calls, rid, point, time):
    for call in calls or []:
        if (call["robot"] == rid and call["point"] == point and call["time"] is not None
                and time is not None and abs(call["time"] - time) < MATCH):
            return call
    return None


# ----------------------------------------------------------------- grounding
def classify(kind, colour, zone, own, received_msgs, rid, known):
    """Independent flags first; the label is derived from them."""
    if colour is None or own is None or not known or (kind == "destination" and zone is None):
        return {"label": "unknown", "in_own": None, "support": None, "strong": None, "weak": None}
    support, strong, weak = False, False, False
    for m in received_msgs:
        for p in m["pairs"]:
            if p["kind"] == "assignment" and p["robot"] not in (None, rid, m["from"]):
                continue  # about a third robot
            role = ("directive" if p["kind"] == "assignment" and p["robot"] == rid
                    else "info" if p["kind"] in ("order", "info", "text_directive") else "self")
            if role == "self":
                # A first-person / sender-intent / report pair still names a team-goal pair: the same
                # (colour, zone) supports a destination (HAN rule fix 2026-11-15). It never conflicts
                # and never supports a pick (the sender covers that colour already).
                support |= kind == "destination" and p["pair"] == (colour, zone)
                continue
            pc, ps = p["pair"]
            if kind == "pick":
                support |= pc == colour
            elif pc == colour and ps == zone:
                support = True
            elif pc == colour:
                weak = True
                strong |= role == "directive" and p["src"] == "fact"
    in_own = colour in {c for c, _ in own} if kind == "pick" else (colour, zone) in own
    if kind == "pick":
        label = "own_order" if in_own else "message" if support else "guess"
    elif strong:
        label = "conflicts_message"
    elif in_own:
        label = "own_order"
    elif support:
        label = "message"
    elif weak:
        label = "conflicts_message"
    else:
        label = "guess"
    return {"label": label, "in_own": in_own, "support": support, "strong": strong, "weak": weak}


def option_colour(decision, brain_rows):
    options = decision.get("options") or []
    if not any(isinstance(o, dict) for o in options):
        time = decision.get("t", decision.get("time", 0))
        found = [d for d in brain_rows if d.get("rid") == decision.get("rid")
                 and d.get("point") == decision.get("point") and d.get("option") == decision.get("option")
                 and abs(d.get("time", d.get("t", 0)) - time) < MATCH]
        options = found[0].get("options", []) if len(found) == 1 else []
    for entry in options:
        if isinstance(entry, dict) and entry.get("key") == decision.get("option"):
            match = re.search(r"<([^<>]+) box>", entry.get("text", ""))
            return entry.get("colour") or (match[1] if match else None)
    return decision.get("colour") if decision.get("colour") else None


def own_orders(team, scene, rid):
    knows = (team.get("knows") or {}).get(rid)
    if knows is None:
        return None
    table = {o["id"]: (o["colour"], norm_sign(o.get("dest") or "sign" + str(o.get("sign"))))
             for o in (scene or {}).get("orders", [])}
    table.update({o["id"]: (o["colour"], norm_sign(o["dest"])) for o in team.get("orders") or []
                  if isinstance(o, dict) and o.get("dest")})
    return {table[i] for i in knows if i in table}


def choice_events(team, brain, robots, scene, messages, calls, structure):
    """Every non-wait pick and destination decision with its grounding."""
    primary = decisions(team.get("decisions"))
    detailed = decisions(brain.get("decisions"))
    rows = primary if primary else detailed
    events = []
    known = messages is not None or structure == "T0"
    for rid in robots:
        own_rows = sorted((d for d in rows if d.get("rid") == rid),
                          key=lambda d: d.get("t", d.get("time", 0)))
        own = own_orders(team, scene, rid)
        last_colour = None
        for d in own_rows:
            point, option = d.get("point"), str(d.get("option", ""))
            is_pick = point == "pick" and option not in ("wait", "none")
            is_dest = point == "destination" and option.startswith(("zone:", "zone_", "sign"))
            is_put = option == PUT_DOWN        # any point (destination question or door question)
            if not (is_pick or is_dest or is_put):
                continue
            rounded = d.get("t", d.get("time"))
            exact = [b for b in detailed if b.get("rid") == rid and b.get("point") == point
                     and b.get("option") == d.get("option")
                     and abs(b.get("time", b.get("t", 0)) - rounded) < MATCH]
            time, eps, source = rounded, LOOSE, "team.json(rounded)"
            if len(exact) == 1:
                time, eps, source = exact[0].get("time", exact[0].get("t")), EPS, "brain-record"
            call = find_call(calls, rid, point, time)
            if call:
                time, eps, source = call["time"], EPS, "llm-calls"
            colour = option_colour(d, detailed) if is_pick else (
                call["holding"] if call and call["holding"] else last_colour)
            if is_pick:
                last_colour = colour
            got = received(rid, time, eps, messages or [])
            flags = ({"label": "put_down", "in_own": None, "support": None, "strong": None, "weak": None} if is_put else
                     classify("pick" if is_pick else "destination", colour,
                              sign(d.get("option")) if is_dest else None, own, got, rid, known))
            mismatch = None
            if call and call["seen"] is not None and messages is not None:
                timed = {(m["from"], round(m["send"], 1)) for m in got}
                mismatch = timed != {s for s in call["seen"] if s[0] != rid}
            events.append(dict(flags, rid=rid, kind="pick" if is_pick else "destination" if is_dest else "put_down",
                               t=time, option=option, colour=colour,
                               zone=sign(option) if is_dest else None,
                               call_index=call["call_index"] if call else None,
                               time_source=source, eps=eps, n_received=len(got),
                               received=got, prompt_mismatch=mismatch,
                               orders_prompt_mismatch=(None if not call or own is None
                                                       else call["orders"] != own)))
    return events


# -------------------------------------------------------------------- causes
def scene_pairs(scene):
    required = Counter()
    for o in scene["orders"]:
        required[(o["colour"], "sign" + str(o["sign"]))] += o["count"]
    return required


def classify_put_downs(team, scene, robots, last):
    """Put-downs (final choice dest == 'put_down') of one run, each as decoy / duplicate / lost.
    decoy: no order of the held box's colour in the scene. Otherwise the colour is ordered: the pairs still missing
    after the last plan (put-downs are empty assignments) decide. lost: a pair of that colour is still missing (one
    missing pair is charged to one put-down, robots in id order); duplicate: nothing of that colour is missing.
    A lost put-down says whether the robot itself knew the missing order (own_order) or only a teammate did (team_only;
    unknown when team.json has no `knows`)."""
    choices = team.get("choices") or {}
    puts = [r for r in sorted(robots) if isinstance(choices.get(r), dict) and sign(choices[r].get("dest")) == PUT_DOWN]
    if not puts or scene is None:
        return []
    required = scene_pairs(scene)
    missing = required - Counter(p for rows in last.values() for p in rows or [])
    out = []
    for rid in puts:
        colour = choices[rid].get("picked")
        entry = {"rid": rid, "colour": colour, "kind": "unknown", "knew": None, "pair": None}
        wanted = sorted(pair for pair in missing if pair[0] == colour and missing[pair] > 0)
        if colour is None:
            pass
        elif colour not in {c for c, _ in required}:
            entry["kind"] = "decoy"
        elif not wanted:
            entry["kind"] = "duplicate"
        else:
            own = own_orders(team, scene, rid)
            pair = next((w for w in wanted if own and w in own), wanted[0])
            missing[pair] -= 1
            entry.update(kind="lost", pair=list(pair), knew="unknown" if own is None else
                         "own_order" if pair in own else "team_only")
        out.append(entry)
    return out


def info_status(rid, time, eps, informative, messages, structure):
    if structure == "T0":
        return "no_info_T0", []
    if messages is None:
        return "other", []
    hits = [(m, p) for m in messages if rid in m["to"] and m["from"] != rid
            for p in m["pairs"] if p["pair"] in informative]
    before = [h for h in hits if h[0]["deliver"] is not None and h[0]["deliver"] <= time + eps]
    ref = lambda h: {"from": h[0]["from"], "sent_s": h[0]["send"], "deliver_s": h[0]["deliver"],
                     "sent_before_decision": h[0]["send"] is not None and h[0]["send"] <= time + eps,
                     "pair": list(h[1]["pair"]), "kind": h[1]["kind"], "src": h[1]["src"]}
    if before:
        return "ignored", [ref(h) for h in before]
    if hits:
        return "late", [ref(h) for h in hits]
    return "not_sent", []


def run_causes(row, team, scene, messages, events, robots, cap_times=None):
    """Tags and evidence for a run whose last-plan coverage failed.
    cap_times (analysis-only, 2026-11-16): {robot: send time of its cap-th message}. `not_sent_cap` is added next to `not_sent`
    when the needed fact never reached the candidate and a peer that held the fact (knew a needed order itself, or chose a needed
    pair) had already sent its cap-th message by the candidate's final decision time: the peer could not send it any more."""
    required = scene_pairs(scene)
    last = row["last_assignments"]
    chosen = {rid: (last[rid][0] if last.get(rid) else None) for rid in robots}
    actual = Counter(p for p in chosen.values() if p)
    surplus, missing = actual - required, required - actual
    candidates = [rid for rid in robots if (chosen[rid] is None and missing)
                  or (chosen[rid] is not None and chosen[rid] in surplus)]
    puts = {p["rid"]: p for p in classify_put_downs(team, scene, robots, last)}
    tags, evidence = [], []
    structure = row["structure"]

    def add(tag, **info):
        if tag not in tags:
            tags.append(tag)
        evidence.append(dict(info, tag=tag))

    for rid in candidates:
        own = own_orders(team, scene, rid) or set()
        mine = [e for e in events if e["rid"] == rid]
        final = next((e for e in reversed(mine) if e["kind"] == "destination"
                      and chosen[rid] and e["zone"] == chosen[rid][1]), None)
        if final is None and chosen[rid]:
            final = next((e for e in reversed(mine) if e["kind"] == "destination"), None)
        picks = [e for e in mine if e["kind"] == "pick"]
        put_event = next((e for e in reversed(mine) if e["kind"] == "put_down"), None)
        decided = final or put_event or (picks[-1] if picks else None)
        time = decided["t"] if decided else 0.0
        eps = decided["eps"] if decided else EPS
        base = {"robot": rid, "chosen": list(chosen[rid]) if chosen[rid] else None,
                "decided_s": time, "call_index": decided["call_index"] if decided else None}
        put = puts.get(rid)
        if put and put["kind"] == "lost":
            add("dropped_needed", reason="put down a box whose order is still missing (%s)" % put["knew"],
                knew=put["knew"], pair=put["pair"], **base)
            if put["knew"] == "own_order":
                continue                      # the robot knew the order itself: a judgement error, no information gap
        elif chosen[rid] is None and own & set(missing):
            add("other", reason="owner of a missing order made no choice", **base)
            continue
        # Needed facts: a missing pair (somebody must carry it) and, if a peer chose the same pair,
        # that peer's claim; with nothing missing (surplus only), the pairs peers already cover.
        peers = {p for r, p in chosen.items() if r != rid and p}
        informative = set(missing) | ({chosen[rid]} & peers if chosen[rid] else set())
        if not missing:
            informative |= peers & set(required)
        status, hits = info_status(rid, time, eps, informative, messages, structure)
        if status == "other":
            add("other", reason="communication record unavailable", **base)
        else:
            add(status, reason="needed fact status", messages=hits, **base)
            if status == "not_sent" and cap_times:
                holders = [p for p in robots if p != rid and p in cap_times and cap_times[p] <= time + eps
                           and ((own_orders(team, scene, p) or set()) & informative or chosen[p] in informative)]
                if holders:
                    add("not_sent_cap", reason="needed fact never sent; the robot holding it had reached the message cap",
                        holders={p: cap_times[p] for p in holders}, **base)
        if chosen[rid]:
            label = final["label"] if final else "unknown"
            if label == "guess":
                add("guess_wrong", reason="destination not in own orders or messages", **base)
            elif label == "unknown":
                add("other", reason="grounding unknown (missing record)", **base)
            elif label == "message":
                add("other", reason="followed a message whose pair was wrong", **base)
            elif chosen[rid][1] is None:
                add("other", reason="pick without destination", **base)
        if final and final["prompt_mismatch"]:
            add("other", reason="delivery timing and prompt dialogue disagree", **base)
    if not tags:
        add("other", reason="no candidate robot identified")
    primary = next(t for t in PRIMARY_ORDER if t in tags)
    if any(e["reason"].startswith("delivery timing") for e in evidence):
        primary = "other"   # inconsistent records: do not blame the agent
    return tags, primary, evidence


def success_class(row, events, robots):
    finals = {}
    for e in events:
        if e["kind"] == "destination":
            finals[e["rid"]] = e["label"]
    labels = [finals.get(rid) for rid in robots if row["last_assignments"].get(rid)]
    if any(label == "guess" for label in labels):
        return "guess_correct"
    if labels and all(label == "own_order" for label in labels):
        return "own_only"
    if any(label == "message" for label in labels) and all(
            label in ("own_order", "message") for label in labels):
        return "message_grounded"
    return "other_or_unknown"


def analyze_causes(path, scenes, brain_root=None, suffix=None):
    row = analyze_run(path, scenes, brain_root, suffix)
    out = {"run": row["run"], "structure": row["structure"], "scene": row["scene"],
           "excluded": row["excluded"], "plan_cover": row.get("plan_cover"),
           "physical_success": row.get("physical_success"), "tags": [], "primary": "",
           "success_class": "", "evidence": [], "events": [], "put_downs": [], "msg_total": 0,
           "msg_with_fact_pair": 0, "msg_with_text_pair": 0, "msg_no_pair": 0,
           "msg_via_decision": None, "msg_via_chance": None, "cap": None, "cap_reached": None, "cap_robots": [],
           "msg_warnings": [], "planner": None,
           "scene_type": (scenes.get(row["scene"]) or {}).get("type", "unknown"),
           "warnings": row.get("warnings", "")}
    if row["excluded"] or row.get("plan_cover") is None or row["structure"] not in STRUCTURES:
        out["skip"] = row["excluded"] or ("plan NA" if row.get("plan_cover") is None
                                          else "not an LLM team structure")
        return out
    path = Path(path)
    team = read_json(path / "team.json")
    brain = team.get("brain", {})
    if isinstance(brain, str):
        try:
            brain = json.loads(brain)
        except ValueError:
            brain = {}
    external = Path(brain_root or "") / row["run"] / "brain-record.json"
    if brain_root and external.exists():
        try:
            brain = read_json(external)
        except (OSError, ValueError):
            pass
    brain = brain if isinstance(brain, dict) else {}
    robots = team.get("robots", ["r1", "r2"])
    scene = scenes[row["scene"]]
    colours = {b["colour"] for b in scene["boxes"]} | {o["colour"] for o in scene["orders"]}
    messages = load_messages(team, brain, robots, colours)
    if row["structure"] == "T0" and messages is None:
        messages = []
    calls = load_calls(Path(brain_root) / row["run"] / "llm-calls.jsonl") if brain_root else None
    events = choice_events(team, brain, robots, scene, messages, calls, row["structure"])
    out["events"] = events
    out["put_downs"] = classify_put_downs(team, scene, robots, row["last_assignments"])
    for m in messages or []:
        out["msg_total"] += 1
        facts = any(p["src"] == "fact" for p in m["pairs"])
        text = any(p["src"] == "text" for p in m["pairs"])
        out["msg_with_fact_pair"] += facts
        out["msg_with_text_pair"] += text
        out["msg_no_pair"] += not m["pairs"]
    out["comm_known"] = messages is not None
    stats = message_stats(messages, brain, team, robots)
    out.update(msg_via_decision=stats["via_decision"], msg_via_chance=stats["via_chance"], cap=stats["cap"],
               cap_reached=stats["cap_reached"], cap_robots=stats["cap_robots"], msg_warnings=stats["warnings"],
               planner=brain.get("planner"))
    if row["plan_cover"]:
        out["success_class"] = success_class(row, events, robots)
    else:
        out["tags"], out["primary"], out["evidence"] = run_causes(
            row, team, scene, messages, events, robots, stats["cap_times"])
    return out


# ------------------------------------------------------------------- outputs
def ref_text(reference):
    return json.dumps(reference, ensure_ascii=False, sort_keys=True, default=str)


def write_outputs(results, out):
    out.mkdir(parents=True, exist_ok=True)
    used = [r for r in results if not r.get("skip")]
    event_rows = []
    for r in used:
        finals = {}
        for e in r["events"]:
            if e["kind"] == "destination":
                finals[e["rid"]] = id(e)
        for e in r["events"]:
            event_rows.append({
                "run": r["run"], "structure": r["structure"], "scene": r["scene"], "rid": e["rid"],
                "kind": e["kind"], "t": e["t"], "time_source": e["time_source"],
                "option": e["option"], "colour": e["colour"], "zone": e["zone"],
                "label": e["label"], "in_own_orders": e["in_own"], "msg_support": e["support"],
                "msg_conflict_directive": e["strong"], "msg_conflict_info": e["weak"],
                "messages_received": e["n_received"], "call_index": e["call_index"],
                "prompt_mismatch": e["prompt_mismatch"],
                "orders_prompt_mismatch": e["orders_prompt_mismatch"],
                "final_destination": finals.get(e["rid"]) == id(e)})
    columns = list(event_rows[0]) if event_rows else ["run"]
    with (out / "choices.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(event_rows)
    run_columns = ["run", "structure", "scene", "scene_type", "plan_cover", "physical_success",
                   "tags", "primary_cause", "success_class", "msg_total", "msg_with_fact_pair",
                   "msg_with_text_pair", "msg_no_pair", "evidence", "warnings", "skipped"]
    with (out / "causes.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=run_columns)
        writer.writeheader()
        for r in results:
            writer.writerow({"run": r["run"], "structure": r["structure"], "scene": r["scene"],
                             "scene_type": r["scene_type"], "plan_cover": r["plan_cover"],
                             "physical_success": r["physical_success"], "tags": "|".join(r["tags"]),
                             "primary_cause": r["primary"], "success_class": r["success_class"],
                             "msg_total": r["msg_total"], "msg_with_fact_pair": r["msg_with_fact_pair"],
                             "msg_with_text_pair": r["msg_with_text_pair"],
                             "msg_no_pair": r["msg_no_pair"], "evidence": ref_text(r["evidence"]),
                             "warnings": r["warnings"], "skipped": r.get("skip", "")})
    (out / "causes.md").write_text(render(results), encoding="utf-8")


def cause_table(group_key, keys, used):
    rows = []
    for key in keys:
        for structure in STRUCTURES:
            group = [r for r in used if group_key(r) == key and r["structure"] == structure]
            failing = [r for r in group if not r["plan_cover"]]
            covered = [r for r in group if r["plan_cover"]]
            rows.append([key, structure, len(group), len(covered), len(failing)]
                        + [sum(t in r["tags"] for r in failing) for t in TAGS]
                        + [sum(r["primary"] == t for r in failing) for t in PRIMARY_ORDER])
    return rows


def render(results):
    used = [r for r in results if not r.get("skip")]
    skipped = [r for r in results if r.get("skip")]
    head = ["n plan-known", "P1 covered", "P0 failed"] + ["tag " + t for t in TAGS] \
        + ["primary " + t for t in PRIMARY_ORDER]
    text = ["# Shortfall causes\n",
            f"Runs listed {len(results)}; analysed {len(used)} (plan known, LLM structure); "
            f"skipped {len(skipped)} (excluded, plan NA or not T0/T1/T2).\n",
            "Denominator of every tag cell is the P0 column of the same row; empty cells are 0/0, "
            "not failed runs. Tags are multi-label; `primary` is a single-label partition using "
            "precedence " + " > ".join(PRIMARY_ORDER) + ".\n\n## Cause counts per structure\n",
            markdown(["structure"] + head,
                     [[s] + cause_table(lambda r: "all", ["all"], used)[i][2:]
                      for i, s in enumerate(STRUCTURES)]),
            "\n## Cause counts per scene type\n",
            markdown(["scene type", "structure"] + head,
                     cause_table(lambda r: r["scene_type"], sorted({r["scene_type"] for r in used}),
                                 used)),
            "\n## Cause counts per scene\n",
            markdown(["scene", "structure"] + head,
                     cause_table(lambda r: r["scene"], sorted({r["scene"] for r in used}), used)),
            "\n## Plan-covered runs by grounding (guess-correct is NOT communication evidence)\n"]
    rows = []
    for structure in STRUCTURES:
        covered = [r for r in used if r["structure"] == structure and r["plan_cover"]]
        rows.append([structure, len(covered), sum(bool(r["physical_success"]) for r in covered)]
                    + [sum(r["success_class"] == c for r in covered) for c in SUCCESS_CLASSES]
                    + [sum(r["success_class"] == c and bool(r["physical_success"]) for r in covered)
                       for c in SUCCESS_CLASSES])
    text.append(markdown(["structure", "P1 covered", "physical success"]
                         + ["P1 " + c for c in SUCCESS_CLASSES]
                         + ["S1 " + c for c in SUCCESS_CLASSES], rows))
    text.append("\n## Plan-covered runs by grounding per scene type\n")
    rows = []
    for stype in sorted({r["scene_type"] for r in used}):
        for structure in STRUCTURES:
            covered = [r for r in used if r["scene_type"] == stype
                       and r["structure"] == structure and r["plan_cover"]]
            rows.append([stype, structure, len(covered)]
                        + [sum(r["success_class"] == c for r in covered) for c in SUCCESS_CLASSES]
                        + [sum(r["success_class"] == c and bool(r["physical_success"])
                               for r in covered) for c in SUCCESS_CLASSES])
    text.append(markdown(["scene type", "structure", "P1 covered"]
                         + ["P1 " + c for c in SUCCESS_CLASSES]
                         + ["S1 " + c for c in SUCCESS_CLASSES], rows))
    labels = Counter((r["structure"], e["kind"], e["label"])
                     for r in used for e in r["events"])
    text.append("\n## Choice grounding (every non-wait pick/destination decision)\n")
    text.append(markdown(["structure", "kind"] + list(LABELS),
                         [[s, k] + [labels[(s, k, label)] for label in LABELS]
                          for s in STRUCTURES for k in ("pick", "destination")]))
    total = sum(r["msg_total"] for r in used)
    text.append("\n## Message parsing coverage\n")
    text.append(markdown(["messages", "with fact pair", "with text pair", "no pair parsed"],
                         [[total, sum(r["msg_with_fact_pair"] for r in used),
                           sum(r["msg_with_text_pair"] for r in used),
                           sum(r["msg_no_pair"] for r in used)]]))
    text.append("\n## Failed runs (P0) with evidence\n")
    text.append(markdown(["run", "tags", "primary", "S", "evidence"],
                         [[r["run"], ",".join(r["tags"]), r["primary"], r["physical_success"],
                           ref_text(r["evidence"])] for r in used if not r["plan_cover"]]))
    text.append("\n## Skipped runs\n")
    text.append(markdown(["run", "scene", "structure", "reason"],
                         [[r["run"], r["scene"], r["structure"], r["skip"]] for r in skipped]))
    flagged = [[r["run"], e["rid"], e["kind"], e["t"]] for r in used for e in r["events"]
               if e["prompt_mismatch"]]
    text.append("\n## Delivery timing vs prompt dialogue disagreements\n")
    text.append(markdown(["run", "robot", "kind", "t"], flagged))
    return "\n".join(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path)
    parser.add_argument("--scenes", type=Path, default=Path("data/scenes18b.json"))
    parser.add_argument("--brain", type=Path)
    parser.add_argument("--out", type=Path, default=Path("out/causes"))
    args = parser.parse_args()
    if not args.runs.is_dir():
        parser.error("runs directory does not exist")
    workspace = Path(__file__).resolve().parent
    target = args.out.resolve()
    if workspace not in target.parents or workspace / "data" == target or workspace / "data" in target.parents:
        parser.error("output must be inside this workspace and outside data/")
    scenes = {s["id"]: s for s in read_json(args.scenes)["scenes"]}
    suffix = {"team-llm26": "h", "team-llm25": "g", "team-llm23": "c"}.get(args.runs.name)
    results = [analyze_causes(p, scenes, args.brain, suffix)
               for p in sorted(args.runs.iterdir()) if p.is_dir()]
    write_outputs(results, args.out)
    used = [r for r in results if not r.get("skip")]
    print(f"runs={len(results)} analysed={len(used)} "
          f"failed_plan={sum(not r['plan_cover'] for r in used)} out={args.out}")


if __name__ == "__main__":
    main()
