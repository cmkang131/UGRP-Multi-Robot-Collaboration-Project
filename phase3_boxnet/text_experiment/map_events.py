"""Seeded map-level assignments and the deterministic static reference planner."""
import random
from collections import Counter

EVENT_FILE_VERSION = 3
E2_EVENT_FILE_VERSION = 4
DROPOFF_MODES = ("always", "event")
MAIN_SLOTS = tuple(range(100, 124))
MAIN_SIZES = ((2, 4), (4, 4))
CONFIRM_SLOTS = {(2, 4): tuple(range(200, 328)), (2, 2): tuple(range(200, 232))}
CAUSE_SLOTS = {(2, 4): tuple(range(328, 352))}
STRATIFIED_SLOTS = {"main": dict.fromkeys(MAIN_SIZES, MAIN_SLOTS), "confirm": CONFIRM_SLOTS, "cause": CAUSE_SLOTS}


class NoAdmissibleDestination(ValueError):
    """The assigned stratum has no D satisfying both D0 restrictions."""


def stratified_set(rows, cols, slot):
    for name, sizes in STRATIFIED_SLOTS.items():
        if slot in sizes.get((rows, cols), ()):
            return name
    return None


def event_version(rows, cols, slot, condition):
    if condition == "e2" and stratified_set(rows, cols, slot):
        return E2_EVENT_FILE_VERSION
    return EVENT_FILE_VERSION


def main_design(rows, cols, map_set="main"):
    slots = list(STRATIFIED_SLOTS[map_set][rows, cols])
    prefix = {"main": "chen2d-5", "confirm": "chen2d-7/confirm", "cause": "chen2d-8/cause"}[map_set] + f"/{rows}x{cols}"
    random.Random(f"{prefix}/strata").shuffle(slots)
    half = len(slots) // 2
    design = {}
    for group, stratum in ((slots[:half], "first_column"), (slots[half:], "other_columns")):
        wording = [1, 2] * (half // 2)
        random.Random(f"{prefix}/{stratum}/wording").shuffle(wording)
        design.update({slot: (stratum, w) for slot, w in zip(group, wording)})
    return design


def speech_fields(assignment, rows, cols, slot):
    row, col = map(int, assignment["D"])
    if "wording" in assignment:
        return {k: assignment[k] for k in ("stratum", "member_position", "wording")}
    # Frozen D0 maps use balanced, seeded blocks of four, including Side C (0–3).
    wording = [1, 1, 2, 2]
    random.Random(f"chen2d-5/legacy/{rows}x{cols}/{slot // 4}").shuffle(wording)
    return dict(stratum="first_column" if col == 0 else "other_columns",
                member_position=row * cols + col + 1, wording=wording[slot % 4])


def coordinates(key):
    return tuple(map(float, key.split("_")))


def cell_key(square):
    return "_".join(map(str, square))


def agent_at(square):
    return f"Agent{list(square)}"


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def boxes(state):
    return Counter(item[4:] for items in state.values() for item in items if item.startswith("box_"))


def step_limit(rows, cols):
    return 40 if (rows, cols) == (4, 8) else 30


def reference_plan(state):
    """One action per initially occupied square, all selected from the same state."""
    cells = {coordinates(key): items for key, items in state.items()}
    targets = {}
    for square, items in cells.items():
        for item in items:
            if item.startswith("target_"):
                targets.setdefault(item[7:], []).append(square)
    plan = {}
    for square, items in sorted(cells.items()):
        choices = ((distance(square, dest), box, dest)
                   for box in items if box.startswith("box_") for dest in targets[box[4:]])
        best = min(choices, default=None)
        if best is None:
            continue
        remaining, box, dest = best
        location = "target_" + box[4:]
        if remaining:
            hop = min(p for p in cells if distance(square, p) == 1 and distance(p, dest) < remaining)
            location = f"square{list(hop)}"
        plan[agent_at(square)] = f"move({box}, {location})"
    return plan


def reference_trajectory(state, execute):
    """Yield the state and applied physical actions after each static reference step."""
    steps = 0
    while boxes(state):
        plan = reference_plan(state)
        applied = []
        feedback, state = execute(state, plan, applied)
        if not plan or feedback or len(applied) != len(plan):
            raise ValueError(f"Invalid reference joint action at step {steps + 1}: {plan} {feedback}")
        steps += 1
        yield state, applied


def e2_destination(rng, cells, targets):
    separation = {p: min(distance(p, t) for t in targets) for p in cells}
    threshold = min(2, max(separation.values()))
    return rng.choice([p for p in cells if separation[p] >= threshold])


def map_assignment(state, seed, env_hash, rows, cols, execute, *, stratum=None):
    rng = random.Random(seed)
    cells = sorted(map(coordinates, state))
    colours = sorted(boxes(state))
    if not colours:
        raise ValueError("Event enrolment requires at least one initial box")
    states = [state]
    first_delivery = {}
    for step, (after, actions) in enumerate(reference_trajectory(state, execute), 1):
        states.append(after)
        for _, box, dest in actions:
            if dest == "target_" + box[4:]:
                first_delivery.setdefault(box[4:], step)

    steps = len(states) - 1
    clamped = max(2, min((steps + 1) // 2, step_limit(rows, cols) // 2))
    # The final reference step removes the last box. Step zero is the initial state.
    event_step = min(clamped, steps - 1)
    at_event = states[event_step]
    remaining = boxes(at_event)
    most = max(remaining.values())
    a = rng.choice([c for c in colours if remaining[c] == most])
    no_target = [p for p in cells if "target_" + a not in state[cell_key(p)]]
    destinations = [p for p in no_target if "box_" + a not in at_event[cell_key(p)]]
    if stratum is not None:
        destinations = [p for p in destinations if (p[1] == 0.5) == (stratum == "first_column")]
        if not destinations:
            raise NoAdmissibleDestination(f"No admissible D for seed {seed} in {stratum}")
    d = rng.choice(destinations or no_target or cells)
    a2 = rng.choice([c for c in colours if first_delivery[c] >= 2] or colours)
    targets = [p for p in cells if "target_" + a2 in state[cell_key(p)]]
    d2 = e2_destination(rng, cells, targets)
    leader = rng.choice([p for p in cells if p != d])
    return dict(event_file_version=EVENT_FILE_VERSION, seed=seed, env_sha256=env_hash,
                A=a, D=list(d), S=steps, clamped_event_step=clamped, event_step=event_step,
                event_step_lowered=event_step < clamped,
                reference_boxes_at_event={c: remaining[c] for c in colours},
                reference_box_A_left=remaining[a], reference_first_delivery_steps=first_delivery,
                L=agent_at(leader), M=agent_at(d), A2=a2, D2=list(d2),
                L2=agent_at(rng.choice(cells)), M2=None)


def disjoint_e2(state, base, source_sha):
    """A v4 companion. Keep the enrolled colour and destination whenever they admit a leader."""
    rng = random.Random(f"chen2d-7/e2/{base['env_sha256']}")
    cells = sorted(map(coordinates, state))
    first = base["reference_first_delivery_steps"]
    targets = {c: [p for p in cells if "target_" + c in state[cell_key(p)]] for c in first}
    colour = base["A2"]
    dest = base["D2"]
    redraw = None
    if len(targets[colour]) == len(cells):
        eligible = sorted(c for c in first if len(targets[c]) < len(cells))
        if not eligible:
            raise ValueError("No colour admits an e2 leader outside its initial targets")
        late = [c for c in eligible if first[c] >= 2]
        colour = rng.choice(late or eligible)
        dest = list(e2_destination(rng, cells, targets[colour]))
        redraw = dict(previous_A2=base["A2"], reason="all squares held its initial target",
                      pool="first_delivery_step_2_or_later" if late else "all_eligible_colours")
    leader = rng.choice([p for p in cells if p not in targets[colour]])
    return dict(base, event_file_version=E2_EVENT_FILE_VERSION, source_event_sha256=source_sha,
                A2=colour, D2=dest, L2=agent_at(leader), A2_redraw=redraw)


def event_path(env_path, version=EVENT_FILE_VERSION):
    if version == EVENT_FILE_VERSION:
        return env_path.with_suffix(".event.json")
    if version == E2_EVENT_FILE_VERSION:
        return env_path.with_suffix(".e2-v4.event.json")
    raise ValueError(f"Unknown event file version: {version}")
