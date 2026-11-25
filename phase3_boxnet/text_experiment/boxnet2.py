"""Chen BoxNet2 corner geometry, seeded placement and step execution (upstream MIT)."""
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

from map_events import agent_at, cell_key, coordinates
from plan_parse import CORNER_MOVES, PLAN_AGENT

TASK = ("Each robot occupies a 1x1 square identified by its center coordinates. It can move one box "
        "on a corner of its square to one of the other three corners or to a matching target in its square. "
        "Each square can contain multiple targets.")
EXAMPLES = "Example actions are move(box_blue, position[0.0, 1.0]) and move(box_blue, target_blue)."
# prompt_env2.py:15, including the authors' brackets and punctuation.
COLLISION_RULE = ("[Do remember that each corner can only contain at most one box! Hence, you need to avoid "
                  "the collision of boxes. Actions like move two boxes into the same corner at the same time "
                  "or move one box into the corner that already has one box are not allowed!]")


@lru_cache(maxsize=1024)
def corners(cell):
    x, y = cell
    return ((x - .5, y - .5), (x - .5, y + .5), (x + .5, y - .5), (x + .5, y + .5))


def cells(rows, cols):
    return tuple((i + .5, j + .5) for i in range(rows) for j in range(cols))


def create_board(rows, cols, counts, rng):
    """env2_create.py:190–215, retaining target and corner order on a full-cell redraw."""
    if rows < 1 or cols < 1 or any(type(n) is not int or n < 0 for n in counts.values()):
        raise ValueError("Invalid dimensions or colour counts")
    capacity = (rows + 1) * (cols + 1)
    if sum(counts.values()) > capacity:
        raise ValueError(f"{sum(counts.values())} boxes exceed {capacity} distinct BoxNet2 corners")
    squares = cells(rows, cols)
    board = {cell_key(p): [] for p in squares}
    for i in range(rows + 1):
        for j in range(cols + 1):
            board[cell_key((float(i), float(j)))] = []
    redraws = 0
    for colour, count in counts.items():
        for _ in range(count):
            cell = rng.choice(squares)
            target = rng.choice(squares)
            order = [2, 0, 1, 3]  # (1,0), (0,0), (0,1), (1,1) before Chen's shuffle.
            rng.shuffle(order)
            while True:
                positions = corners(cell)
                free = next((positions[k] for k in order if not board[cell_key(positions[k])]), None)
                if free is not None:
                    break
                cell = rng.choice(squares)
                redraws += 1
            board[cell_key(free)].append("box_" + colour)
            board[cell_key(target)].append("target_" + colour)
    return board, redraws


def move_text(box, dest):
    site = dest if isinstance(dest, str) else f"position{list(dest)}"
    return f"move({box}, {site})"


def square_actions(state, cell):
    result = []
    for pos in corners(cell):
        items = state[cell_key(pos)]
        if len(items) == 1:
            box, = items
            result.extend(move_text(box, other) for other in corners(cell) if other != pos)
            target = "target_" + box[4:]
            if target in state[cell_key(cell)]:
                result.append(move_text(box, target))
    return result


def available_actions(rows, cols, state):
    return {agent_at(p): square_actions(state, p) for p in cells(rows, cols)}


def board_text(rows, cols, state):
    # Show absolute corner contents: colour-only actions cannot identify the starting corner.
    lines = []
    for cell in cells(rows, cols):
        positions = {cell_key(p): state[cell_key(p)] for p in corners(cell)}
        lines.append(f"{agent_at(cell)}: I am in square{list(cell)}, I can observe {state[cell_key(cell)]}, "
                     f"my corners contain {positions}, I can do {square_actions(state, cell)}\n")
    return "".join(lines)


def decode_move(name, action):
    agent = PLAN_AGENT.fullmatch(name) if isinstance(name, str) else None
    move = CORNER_MOVES.strict.fullmatch(action) if isinstance(action, str) else None
    if agent and move:
        box, target, row, col = move.groups()
        return tuple(map(float, agent.groups())), box, target or (float(row), float(col))
    return None


def check_plan(plan, available):
    bad, seen = {}, set()
    for robot, action in plan.items():
        decoded = decode_move(robot, action)
        if decoded:
            cell, box, dest = decoded
            name = agent_at(cell)
            if name not in seen and move_text(box, dest) in available.get(name, ()):
                seen.add(name)
                continue
        bad[robot] = action
    return ("Actions outside the current doable lists: " + str(bad) if bad else ""), bad


@dataclass
class Step:
    state: dict
    applied: list
    robots: list
    feedback: str
    collisions: list
    failed: bool


def _trial(state, proposals, bindings):
    """Source-order colour lookup on the first pass. A rollback keeps each surviving move bound to its box."""
    board = {key: items.copy() for key, items in state.items()}
    # Parallel lists track physical boxes even when equal colours temporarily share a corner.
    ids = {key: [(key, i) for i in range(len(items))] for key, items in state.items()}
    moves, feedback, resolved = [], [], {}
    for robot, action in proposals.items():
        decoded = decode_move(robot, action)
        if not decoded:
            continue
        cell, box, dest = decoded
        local = corners(cell)
        if bindings is None:
            origin = next((p for p in local if box in board.get(cell_key(p), ())), None)
            index = board[cell_key(origin)].index(box) if origin is not None else None
        else:
            origin, token = bindings.get(robot, (None, None))
            occupants = ids[cell_key(origin)] if origin is not None else []
            index = occupants.index(token) if token in occupants else None
        target_key = cell_key(cell)
        deliver = dest == "target_" + box[4:] and dest in board.get(target_key, ())
        if index is None or (dest not in local and not deliver):
            feedback.append(f"Your assigned task for {target_key} is not in the doable action list; ")
            continue
        origin_key = cell_key(origin)
        token = ids[origin_key].pop(index)
        board[origin_key].pop(index)
        if deliver:
            board[target_key].remove(dest)
        else:
            dest_key = cell_key(dest)
            board[dest_key].append(box)
            ids[dest_key].append(token)
        moves.append((robot, origin, box, dest))
        resolved[robot] = origin, token
    return board, moves, "".join(feedback), resolved


def execute(state, plan, collision="skip", step=1):
    """Detect final occupancy. Skip rolls back conflicting arrivals and retries the surviving proposals."""
    if collision not in ("skip", "fail"):
        raise ValueError("Unknown BoxNet2 collision policy")
    proposals = dict(plan)
    events, bindings = [], None
    pass_number = 0
    while True:
        pass_number += 1
        board, moves, feedback, resolved = _trial(state, proposals, bindings)
        if bindings is None:
            bindings = resolved
        crowded = {coordinates(k) for k, v in board.items() if len(v) > 1 and v[0].startswith("box_")}
        if not crowded:
            return Step(board, [(src, box, dest) for _, src, box, dest in moves],
                        [robot for robot, *_ in moves], feedback, events, False)
        arrivals = defaultdict(list)
        for robot, src, box, dest in moves:
            if dest in crowded:
                start_key, _ = bindings[robot][1]
                arrivals[dest].append(dict(robot=robot, box=box, box_start_corner=coordinates(start_key),
                                           source=src, corner=dest))
        held = defaultdict(list)
        for previous in events:
            held[previous["source"]].append({k: previous[k] for k in ("robot", "source", "box", "corner")})
        for dest, incoming in arrivals.items():
            for move in incoming:
                events.append(dict(event="collision", step=step, pass_number=pass_number, **move, moves=incoming,
                                   cancelled_departures=held[dest],
                                   initial_occupants=state[cell_key(dest)].copy(),
                                   final_occupants=board[cell_key(dest)].copy()))
                del proposals[move["robot"]]
        if collision == "fail":
            return Step(board, [(src, box, dest) for _, src, box, dest in moves],
                        [robot for robot, *_ in moves], feedback, events, True)
        if not arrivals:
            raise ValueError("BoxNet2 skip requires a collision-free initial board")
