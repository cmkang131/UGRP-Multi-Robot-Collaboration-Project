"""Offline BoxNet2 reference policies and minimum inter-robot handovers."""
from collections import defaultdict, deque
from functools import lru_cache

from boxnet2 import cells, corners, execute, move_text
from map_events import agent_at, boxes, cell_key, coordinates


@lru_cache(maxsize=64)
def topology(rows, cols):
    incident = defaultdict(list)
    for cell in cells(rows, cols):
        for corner in corners(cell):
            incident[corner].append(cell)
    return dict(incident)


def contents(state):
    positions = {}
    targets = defaultdict(list)
    for key, items in state.items():
        for item in items:
            if item.startswith("box_"):
                positions[coordinates(key)] = item
            elif item.startswith("target_"):
                targets["box_" + item[7:]].append(coordinates(key))
    return positions, targets


def corner_distance(pos, target):
    """Minimum corner-graph hops until the box touches the target cell."""
    return int(max(abs(pos[0] - target[0]), abs(pos[1] - target[1])) - .5)


def min_corner_handovers(state):
    """Minimum over colour-preserving assignments of boxes to individual target slots."""
    positions, targets = contents(state)
    total = 0
    for box, slots in targets.items():
        starts = [p for p, item in positions.items() if item == box]
        if len(starts) != len(slots):
            raise ValueError("Expected balanced boxes and targets")
        costs = [[corner_distance(start, cell) for cell in slots] for start in starts]
        # The five-colour scaled boards have small per-colour multiplicity.
        @lru_cache(maxsize=None)
        def assign(taken):
            i = taken.bit_count()
            if i == len(slots):
                return 0
            return min(costs[i][j] + assign(taken | (1 << j))
                       for j in range(len(slots)) if not taken & (1 << j))
        total += assign(0)
    return total


def independent_plan(rows, cols, state):
    """Each robot chooses from its four corners without reading any other robot's actions or occupancy elsewhere."""
    positions, targets = contents(state)
    plan = {}
    for cell in cells(rows, cols):
        choices, considered = [], set()
        for pos in corners(cell):
            box = positions.get(pos)
            if box is None or box in considered:
                continue
            considered.add(box)  # The colour-only command addresses its first local copy.
            hops = min(corner_distance(pos, target) for target in targets[box])
            for dest in targets[box]:
                if corner_distance(pos, dest) != hops:
                    continue
                if dest == cell:
                    choices.append((0, box, dest, pos, move_text(box, "target_" + box[4:])))
                elif hops:
                    nearer = [p for p in corners(cell) if corner_distance(p, dest) < hops]
                    if nearer:
                        choices.append((hops, box, dest, pos, move_text(box, min(nearer))))
        if choices:
            plan[agent_at(cell)] = min(choices)[-1]
    return plan


def shortest_delivery(start, box, positions, targets, incident):
    """BFS for one physical box with every other box fixed, respecting Chen's first-colour lookup."""
    others = {p: b for p, b in positions.items() if p != start}
    queue = deque([start])
    paths = {start: ()}
    while queue:
        pos = queue.popleft()
        for cell in incident[pos]:
            local = corners(cell)
            if any(others.get(p) == box for p in local[:local.index(pos)]):
                continue
            robot = agent_at(cell)
            if cell in targets:
                return paths[pos] + ((robot, move_text(box, "target_" + box[4:])),)
            for dest in local:
                if dest not in others and dest not in paths:
                    paths[dest] = paths[pos] + ((robot, move_text(box, dest)),)
                    queue.append(dest)
    return ()


def coordinated_plan(rows, cols, state, limit=40):
    """Prioritize the shortest currently feasible single-box delivery; serialize its route and replan."""
    plans = []
    incident = topology(rows, cols)
    while len(plans) < limit:
        positions, targets = contents(state)
        if not positions:
            break
        choices = []
        for pos, box in sorted(positions.items()):
            route = shortest_delivery(pos, box, positions, targets[box], incident)
            if route:
                choices.append((len(route), pos, route))
        if not choices:
            break
        for robot, action in min(choices)[-1][:limit-len(plans)]:
            joint = {robot: action}
            result = execute(state, joint, "fail", len(plans) + 1)
            if result.failed or result.feedback or len(result.applied) != 1:
                raise ValueError("Reference route disagrees with the BoxNet2 executor")
            state = result.state
            plans.append(joint)
    return plans, state


def independent_result(rows, cols, state, limit=40):
    cancelled = 0
    for step in range(1, limit + 1):
        result = execute(state, independent_plan(rows, cols, state), step=step)
        cancelled += len(result.collisions)
        state = result.state
        if not boxes(state):
            return True, step, cancelled
    return False, limit, cancelled


# CHEN2D-22C offline analysis. The policies above are the published 22B reference.
from collections import Counter
from heapq import heappop, heappush
from itertools import permutations, product

from boxnet2 import available_actions, decode_move


def independent_local(rows, cols, state, *, rng=None, cancelled_last=()):
    """Choose from the pre-step board only. Optional randomness belongs to this policy."""
    positions, targets = contents(state)
    plan = {}
    for cell in cells(rows, cols):
        robot = agent_at(cell)
        local = corners(cell)
        choices, considered = [], set()
        for pos in local:
            box = positions.get(pos)
            if box is None or box in considered:
                continue
            considered.add(box)
            distances = {t: corner_distance(pos, t) for t in targets[box]}
            nearest = min(distances.values())
            for target, distance in distances.items():
                if distance != nearest:
                    continue
                if cell == target:
                    choices.append((0, box, target, pos, cell, move_text(box, "target_" + box[4:])))
                elif distance:
                    for dest in local:
                        if dest not in positions and corner_distance(dest, target) < distance:
                            choices.append((distance, box, target, pos, dest, move_text(box, dest)))
        if not choices:
            continue
        if rng is None:
            plan[robot] = min(choices)[-1]
        elif robot not in cancelled_last or rng.random() >= .5:
            distance = min(c[0] for c in choices)
            tied = sorted({c[-1] for c in choices if c[0] == distance})
            plan[robot] = rng.choice(tied) if len(tied) > 1 else tied[0]
    return plan


def parallel_coordinated(rows, cols, state):
    """Pack one step, longest remaining feasible delivery route first; each box moves at most once."""
    incident = topology(rows, cols)
    available = available_actions(rows, cols, state)
    pending = set(contents(state)[0])
    joint, expected, reserved = {}, [], set()
    working = state
    while pending:
        positions, targets = contents(working)
        choices = []
        for pos in pending:
            box = positions[pos]
            route = shortest_delivery(pos, box, positions, targets[box], incident)
            if not route:
                continue
            robot, action = route[0]
            if robot in joint or action not in available[robot]:
                continue
            _, _, dest = decode_move(robot, action)
            if dest not in reserved:
                choices.append((-len(route), pos, robot, action, box, dest))
        if not choices:
            break
        _, pos, robot, action, box, dest = min(choices)
        joint[robot] = action
        expected.append((pos, box, dest))
        trial = execute(state, joint, "fail")
        if trial.failed or trial.feedback or trial.applied != expected:
            raise ValueError("Parallel reservation disagrees with the issued-order executor")
        pending.remove(pos)
        if isinstance(dest, tuple):
            reserved.add(dest)
        working = trial.state
    return joint


def run_boxnet2(rows, cols, state, policy, *, limit=40, rng=None):
    """Execute to completion or the cap; retain evidence for the terminal failure label."""
    if policy not in ("parallel_coordinated", "independent_local", "ignores_occupancy"):
        raise ValueError(f"Unknown BoxNet2 analysis policy: {policy}")
    if rng is not None and policy != "independent_local":
        raise ValueError("Only independent_local uses randomness")
    cancelled = last_change = tail_repeats = 0
    last_cancelled, seen_collisions = set(), set()
    plans = []
    for step in range(1, limit + 1):
        if not boxes(state):
            break
        if policy == "independent_local":
            joint = independent_local(rows, cols, state, rng=rng, cancelled_last=last_cancelled)
        elif policy == "parallel_coordinated":
            joint = parallel_coordinated(rows, cols, state)
        else:
            joint = independent_plan(rows, cols, state)
        result = execute(state, joint, "skip", step)
        if policy == "parallel_coordinated" and (result.collisions or result.feedback):
            raise ValueError("The centralized joint step did not execute cleanly")
        cancelled += len(result.collisions)
        last_cancelled = {c["robot"] for c in result.collisions}
        if result.state != state:
            last_change = step
            seen_collisions.clear()
            tail_repeats = 0
        else:
            # One signature per corner and group of incoming physical moves, once per tick.
            signatures = {(c["corner"], tuple(sorted((m["robot"], m["box_start_corner"], m["source"])
                                                     for m in c["moves"]))) for c in result.collisions}
            tail_repeats += bool(seen_collisions & signatures)
            seen_collisions.update(signatures)
        state = result.state
        plans.append(joint)

    left = sum(boxes(state).values())
    failure = None
    if left:
        rule = {"parallel_coordinated": parallel_coordinated, "independent_local": independent_local,
                "ignores_occupancy": independent_plan}[policy]
        if not rule(rows, cols, state):  # Ask before this policy's optional one-tick wait.
            failure = "deadlock"
        elif tail_repeats:
            failure = "livelock"
        else:
            failure = "progress_timeout"
    return dict(completed=not left, steps=len(plans), cancelled_moves=cancelled, failure=failure,
                remaining_boxes=left, last_change_step=last_change, repeated_collision_steps=tail_repeats), plans


def _delivery_costs(start, box, obstacles, slots, incident):
    """Lexicographic (actions including delivery, robot changes), for each reachable target cell."""
    frontier = [(0, 0, start, ())]
    best = {(start, ()): (0, 0)}
    delivered = {}
    while frontier:
        moves, changes, pos, last_cell = heappop(frontier)
        if best[pos, last_cell] != (moves, changes):
            continue
        for cell in incident[pos]:
            local = corners(cell)
            if any(obstacles.get(p) == box for p in local[:local.index(pos)]):
                continue  # A colour-only command would pick a different physical box.
            cost = (moves + 1, changes + int(bool(last_cell) and last_cell != cell))
            if cell in slots and (cell not in delivered or cost < delivered[cell]):
                delivered[cell] = cost
            for dest in local:
                if dest == pos or dest in obstacles:
                    continue
                key = dest, cell
                if key not in best or cost < best[key]:
                    best[key] = cost
                    heappush(frontier, (*cost, dest, cell))
    return delivered


def _sum_route_costs(costs):
    if any(cost is None for cost in costs):
        return None
    return sum(moves for moves, _ in costs), sum(changes for _, changes in costs)


def _matching_cost(matrix):
    """One slot per box, minimizing total moves then changes. None means no perfect matching."""
    @lru_cache(maxsize=None)
    def assign(mask):
        i = mask.bit_count()
        if i == len(matrix):
            return 0, 0
        feasible = []
        for j, cost in enumerate(matrix[i]):
            if cost is not None and not mask & (1 << j):
                tail = assign(mask | (1 << j))
                if tail is not None:
                    feasible.append((cost[0] + tail[0], cost[1] + tail[1]))
        return min(feasible, default=None)
    return assign(0)


def delivery_difficulty(rows, cols, state):
    """Measure boxes individually and with distinct colour-matched slots, with/without fixed obstacles."""
    positions, targets = contents(state)
    incident = topology(rows, cols)
    inventory = Counter(positions.values())
    if inventory != Counter({box: len(slots) for box, slots in targets.items()}):
        raise ValueError("Expected balanced boxes and targets")
    measures = {"min_corner_handovers": min_corner_handovers(state)}
    for fixed in (False, True):
        nearest, assigned = [], []
        for box, slots in targets.items():
            matrix = []
            for start in sorted(p for p in positions if positions[p] == box):
                obstacles = {p: b for p, b in positions.items() if p != start} if fixed else {}
                costs = _delivery_costs(start, box, obstacles, slots, incident)
                best = min(costs.values(), default=None)
                if fixed:
                    route = shortest_delivery(start, box, positions, slots, incident)
                    if (len(route) or None) != (best[0] if best else None):
                        raise ValueError("Fixed-obstacle cost disagrees with shortest_delivery")
                nearest.append(best)
                matrix.append([costs.get(t) for t in slots])
            assigned.append(_matching_cost(matrix))
        suffix = "_fixed" if fixed else ""
        for mode, costs in (("", nearest), ("_distinct", assigned)):
            total = _sum_route_costs(costs)
            measures["min_box_moves" + suffix + mode] = total[0] if total is not None else None
            measures["min_robot_changes" + suffix + mode] = total[1] if total is not None else None
        if fixed:
            measures["fixed_unreachable_boxes"] = nearest.count(None)
    return measures


def _makespan_lower_bound(state, team_size):
    positions, targets = contents(state)
    if not positions:
        return 0
    work = len(positions) + min_corner_handovers(state)
    load = Counter(cell for slots in targets.values() for cell in slots)
    bound = max((work + team_size - 1) // team_size, max(load.values()))
    # For a unique colour, all robots able to name it this tick touch its initial corner.
    # Even an ordered relay ends at most one corner hop away; delivery needs its own tick
    # once the box first reaches a corner of the target cell.
    for pos, box in positions.items():
        if len(targets[box]) == 1:
            bound = max(bound, 1 + corner_distance(pos, targets[box][0]))
    return bound


def _joint_steps(rows, cols, state, ticks_left):
    """All initially doable joint commands, including orders that affect colour lookup."""
    _, targets = contents(state)
    load = Counter(cell for slots in targets.values() for cell in slots)
    choices = []
    available = available_actions(rows, cols, state)
    for cell in cells(rows, cols):
        robot = agent_at(cell)
        options = []
        for action in dict.fromkeys(available[robot]):
            _, box, dest = decode_move(robot, action)
            delivery = isinstance(dest, str)
            if load[cell] == ticks_left and not delivery:
                continue  # This cell must deliver on every remaining tick.
            distance = -1 if delivery else min(corner_distance(dest, t) for t in targets[box])
            options.append((distance, robot, action, box))
        options.sort()
        if load[cell] < ticks_left:
            options.append(None)
        choices.append(options)

    seen = set()
    for selected in product(*choices):
        moves = [m for m in selected if m is not None]
        if not moves:
            continue
        # Different colours commute before the final occupancy check. Same-colour commands
        # can change which physical box a later robot finds, so include their issue orders.
        orders = (moves,) if len({m[3] for m in moves}) == len(moves) else permutations(moves)
        for order in orders:
            joint = {robot: action for _, robot, action, _ in order}
            result = execute(state, joint, "fail")
            if result.failed or result.feedback or result.state == state:
                continue
            key = tuple(tuple(v) for v in result.state.values())
            if key not in seen:
                seen.add(key)
                yield joint, result.state, key


def exact_joint_plan(rows, cols, state, *, limit=40):
    """Iterative-deepening search over collision-free joint states. None means no plan within limit."""
    team_size = rows * cols
    ruled_out, bounds = {}, {}

    def search(board, key, remaining):
        if key not in bounds:
            bounds[key] = _makespan_lower_bound(board, team_size)
        if bounds[key] == 0:
            return []
        if bounds[key] > remaining or ruled_out.get(key, -1) >= remaining:
            return None
        for joint, after, next_key in _joint_steps(rows, cols, board, remaining):
            tail = search(after, next_key, remaining - 1)
            if tail is not None:
                return [joint, *tail]
        ruled_out[key] = remaining
        return None

    initial = tuple(tuple(v) for v in state.values())
    for depth in range(_makespan_lower_bound(state, team_size), limit + 1):
        solution = search(state, initial, depth)
        if solution is not None:
            return solution
    return None
