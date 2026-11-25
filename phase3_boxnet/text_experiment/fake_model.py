"""Deterministic offline scripts. The solver sees only the authors' messages."""
import ast
import json
import re
from decimal import Decimal

SCRIPTS = ("correct", "wrong", "non-json", "endless", "invalid", "repair", "feedback", "relay-pass", "relay-invalid")
COST = Decimal("0.001")


class CutReply(str):
    """A scripted physical attempt whose provider finish reason is length."""


OBSERVATION = re.compile(
    r'Agent\[(\d+\.5), (\d+\.5)\]: (?:I am in|in) square\[[^\]]+\], '
    r'(?:I can|can) observe (\[[^\]\n]*\])'
)


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def observed_state(prompt):
    state = {(float(x), float(y)): ast.literal_eval(items) for x, y, items in OBSERVATION.findall(prompt)}
    if not state:
        raise ValueError("Fake script could not find the current observations")
    return state


def plan_for_state(state, prompt, obey):
    e1 = re.search(r'(?:Change of orders \(announced after step \d+\): the order for boxes|Reroute boxes)'
                   r' of colour (\w+) ', prompt)
    e2 = re.search(r'Change of orders \(announced after step \d+\): the box of colour (\w+) '
                   r'that was just delivered(?: at square(\[[\d., ]+\]))? was not accepted', prompt)
    if not e2:
        e2 = re.search(r'Reroute the rejected box of colour (\w+) from square(\[[\d., ]+\])', prompt)
    diverted = "box_" + e1[1] if obey and e1 else None
    returned = f"box_{e2[1]}_returned" if obey and e2 else None
    neutral = any("dropoff" in items for items in state.values())
    return_square = None
    if returned and neutral and e2[2]:
        return_square = tuple(ast.literal_eval(e2[2]))
        returned = "box_" + e2[1]
        copies = sum(items.count(returned) for items in state.values())
    plan = {}
    for square, items in sorted(state.items()):
        choices = []
        for box in items:
            if not box.startswith("box_"):
                continue
            colour = box[4:]
            site = "target_" + colour
            if box == returned and return_square is not None and copies > 1:
                # Leave the rejected copy at X while ordinary copies go to their targets.
                if square == return_square and items.count(box) == 1:
                    continue
            elif box in (diverted, returned):
                site = "dropoff" if neutral else "dropoff_" + colour.removesuffix("_returned")
            for dest, contents in state.items():
                if site in contents:
                    choices.append((distance(square, dest), box, dest, site))
        if not choices:
            continue
        remaining, box, dest, site = min(choices)
        if remaining:
            neighbour = min(p for p in state if distance(p, square) == 1
                            and distance(p, dest) < remaining)
            site = f"square{list(neighbour)}"
        plan[f"Agent{list(square)}"] = f"move({box}, {site})"
    return plan


def plan_from_text(prompt, obey):
    return json.dumps(plan_for_state(observed_state(prompt), prompt, obey))


def corner_sequence(prompt, script, horizon, own, repair):
    """Reconstruct only the visible current board and project a deterministic plan onto this writer's scope."""
    from boxnet2_planning import coordinated_plan
    from map_events import cell_key
    from matched_protocol import GROUP_WRITER

    observed = observed_state(prompt)
    state = {cell_key(pos): items for pos, items in observed.items()}
    size = tuple(int(max(pos[i] for pos in observed)) + 1 for i in (0, 1))
    for raw in re.findall(r"my corners contain (\{[^}\n]*\}), I can do", prompt):
        state.update(ast.literal_eval(raw))
    speaker = re.search(r"choosing only the action of (Agent\[[\d., ]+\])\.", prompt) if own else None
    group_prefix = GROUP_WRITER.split("{robots}")[0]
    group_line = next((line for line in prompt.splitlines() if line.startswith(group_prefix)), None)
    block = json.JSONDecoder().raw_decode(group_line[len(group_prefix):])[0] if group_line else None
    if script == "invalid" or (script == "repair" and not repair):
        bad = "move(box_missing, target_missing)"
        return json.dumps([bad] if own else [{block[0] if block else "Agent[0.5, 0.5]": bad}])
    plans, _ = coordinated_plan(*size, state, limit=horizon)
    plans.extend({} for _ in range(horizon - len(plans)))
    if own:
        return json.dumps([joint.get(speaker[1]) for joint in plans])
    if block:
        return json.dumps([{r: a for r, a in joint.items() if r in block} for joint in plans])
    return json.dumps(plans)


def sequence_reply(messages, script, horizon, own):
    # The offline model predicts from visible text, including earlier speakers' lists.
    from env1_create import action_from_response
    from map_events import cell_key, coordinates
    from matched_protocol import GROUP_WRITER
    from prompt_env1 import OWN_DIALOGUE

    prompt = messages[1]["content"]
    if "my corners contain " in prompt:
        return corner_sequence(prompt, script, horizon, own, len(messages) > 2)
    # A matched repair now gives a concrete H-length example.  Preserve the
    # old short first submission, but make the fake honour that explicit repair
    # contract after its simulated board is solved.
    matched_repair = ("Return a JSON list for the next" in prompt and len(messages) > 2 and
                       "Expected shape:" in messages[-1].get("content", ""))
    state = observed_state(prompt)
    returned_only = any(item.endswith("_returned") for items in state.values() for item in items)
    speaker = None
    peers = {}
    group_prefix = GROUP_WRITER.split("{robots}")[0]
    block_line = next((line for line in prompt.splitlines() if line.startswith(group_prefix)), None)
    block = json.JSONDecoder().raw_decode(block_line[len(group_prefix):])[0] if block_line else None
    if own:
        assignment = re.search(r"choosing only the action of (Agent\[[\d., ]+\])\.", prompt)
        if assignment:
            speaker = assignment[1]
        else:
            x, y = OBSERVATION.search(prompt).groups()[:2]
            speaker = f"Agent[{x}, {y}]"
    if own or block:
        source = next(m["content"] for m in reversed(messages) if m["role"] == "user" and OWN_DIALOGUE in m["content"])
        dialogue = source.rsplit(OWN_DIALOGUE, 1)[-1]
        peers, _ = json.JSONDecoder().raw_decode(dialogue)
    invalid = script == "invalid" or (script == "repair" and len(messages) == 2)
    if invalid:
        bad = "move(box_missing, target_missing)"
        return json.dumps([bad] + [None] * (horizon - 1) if own else [{block[0] if block else "Agent[0.5, 0.5]": bad}])

    entries = []
    for i in range(horizon):
        proposal = plan_for_state(state, prompt, obey=script != "wrong")
        if own:
            action = proposal.get(speaker)
            entries.append(action)
            moves = {s: actions[i] for s, actions in peers.items() if actions and i < len(actions) and actions[i] is not None}
            if action is not None:
                moves[speaker] = action
        elif block:
            entry = {name: proposal[name] for name in block if name in proposal}
            entries.append(entry)
            moves = {}
            for earlier in peers.values():
                if earlier and i < len(earlier):
                    moves.update((name, move) for name, move in earlier[i].items() if isinstance(move, str))
            moves.update(entry)
        else:
            if not proposal:
                break
            entries.append(proposal)
            moves = proposal
        _, after = action_from_response({cell_key(p): items for p, items in state.items()}, moves, returned_only=returned_only)
        state = {coordinates(key): items for key, items in after.items()}
    if matched_repair and not own:
        entries.extend({} for _ in range(horizon - len(entries)))
    return json.dumps(entries or [{}])


def reply(messages, script):
    if script.startswith("cut:"):
        return CutReply(script[4:])
    prompt = messages[1]["content"]
    last = prompt.splitlines()[-1].strip()
    if last.startswith(("You may forward this notice", "You may keep this notice", "You may send one short message")):
        if script == "relay-pass":
            return "PASS"
        if script == "relay-invalid":
            return "SEND or PASS"
        if last.startswith("You may send one short message"):
            notice = prompt.splitlines()[-2]
            colour = re.search(r'of colour (\w+)', notice)[1]
            squares = re.findall(r'square(\[[\d., ]+\])', notice)
            subject = (f"the rejected box of colour {colour} from square{squares[0]}"
                       if "not accepted" in notice else f"boxes of colour {colour}")
            return f"Reroute {subject} to the dropoff at square{squares[-1]}."
        return "SEND"
    if script == "non-json":
        return "This answer contains no plan."
    matched = re.search(r"Return a JSON list for the next (\d+) steps in execution order\.", prompt)
    if matched:
        return sequence_reply(messages, script, int(matched[1]), "Write an individual entry for every step" in prompt)
    if "Please evaluate the given plan." in prompt:
        return "I Agree." if script == "feedback" else "I Agree"
    leader = re.search(r"Now, plan the next (\d+) steps:\s*$", prompt)
    if not leader and prompt.lstrip().startswith("You are a central planner directing agents."):
        leader = re.search(r"Plan the next (\d+) steps at once:", prompt)
    if leader:
        return sequence_reply(messages, script, int(leader[1]), False)
    if "[Own Action Output Instruction]" in prompt:
        horizon = re.search(r"Output (?:only )?a JSON list of (\d+) entries", prompt)[1]
        return sequence_reply(messages, script, int(horizon), True)
    dialogue = "[Action Output Instruction]" in prompt and len(messages) == 2
    if script == "endless" and dialogue:
        return "PROCEED"
    multi = re.search(r"Propose your own actions for the next (\d+) steps at the current round", prompt)
    if multi:
        sequence = sequence_reply(messages, script, int(multi[1]), False)
        return "EXECUTE\n" + sequence if dialogue else sequence
    if script == "invalid" or (script == "repair" and len(messages) == 2):
        plan = '{"Agent[0.5, 0.5]":"move(box_missing, target_missing)"}'
    else:
        plan = plan_from_text(prompt, obey=script != "wrong")
    return "EXECUTE\n" + plan if dialogue else plan
