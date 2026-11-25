"""Shared writing instructions, board partitions and history for matched planning."""
import json
from dataclasses import dataclass
from functools import lru_cache

from env1_create import state_update_func
from map_events import agent_at
from prompt_env1 import AfterHistoryPrompt, OWN_DIALOGUE, state_action_history

REPAIRS_PER_WRITER = 2
PLAN_NOTES = ("none", "continue")
FAILED_WRITERS = ("drop", "fail", "idle")
CUT_ANSWERS = ("discard", "prefix")
DEFAULT_STALLED_ROUNDS = 3
DEFAULT_ENV_STEPS = 30
DEFAULT_PLANNING_ROUNDS = 30
STATE_HEADING = "Current board and doable actions:"
HISTORY_HEADING = "Earlier executed state and action pairs:"
GOAL = "Match all boxes to their color-coded targets."
DROPOFF_RULE = ("The dropoff is only for boxes whose order has been changed to the dropoff. "
                "Putting any other box into the dropoff counts as a wrong delivery, and a wrong delivery cannot be undone.")
TASK = ("Each robot occupies a 1x1 square identified by its center coordinates. It can move one box "
        "in its square to a neighboring square or to a matching target in its square. "
        "Each square can contain multiple boxes and targets.")
ACTION_EXAMPLES = "Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue)."
BREVITY = "Respond concisely."
JOINT_WRITER = "Write a joint entry for every step, choosing the actions of all robots."
OWN_WRITER = "Write an individual entry for every step, choosing only the action of {speaker}."
GROUP_WRITER = "Write a joint entry for every step, choosing actions only for {robots}."
GROUP_CALL_FIELDS = ("framework", "group_size", "callers_per_round", "assigned_robots",
                     "robots_assigned", "assigned_robots_with_doable_actions")
# Keep the non-shape instruction common, but make the shape itself unambiguous
# for the writer which is actually answering.
FORMAT = "Assume the earlier entries have been executed. Return only the list."
JOINT_FORMAT = "Each list entry is a joint object mapping acting Agent[row, col] names to action strings. Use {} for an idle step."
OWN_FORMAT = "Each list entry is your own action string or the JSON literal null for a wait."
EMPTY_PEER_NOTE = "In the earlier lists, [] means that robot has no usable entries yet."
REPAIR_INSTRUCTION = "Revise your list using the same board and writer assignment."
UNREADABLE = "The reply could not be read in the requested JSON format."
INVALID_ACTIONS = "First-step actions outside the current doable lists: "


def validate_writer_options(protocol, plan_note, failed_writer="drop", max_stalled_rounds=None, cut_answer="discard"):
    if cut_answer not in CUT_ANSWERS or (cut_answer == "prefix" and protocol != "matched"):
        raise ValueError("--cut-answer must be discard or, with --protocol matched, prefix")
    if plan_note not in PLAN_NOTES or failed_writer not in FAILED_WRITERS:
        raise ValueError("Unknown --plan-note or --failed-writer setting")
    if protocol != "matched" and (plan_note != "none" or failed_writer != "drop"):
        if failed_writer == "idle":
            raise ValueError("--failed-writer idle requires --protocol matched")
        raise ValueError("--plan-note continue and --failed-writer fail require --protocol matched")
    if max_stalled_rounds is not None:
        if failed_writer != "idle":
            raise ValueError("--max-stalled-rounds requires --failed-writer idle")
        if type(max_stalled_rounds) is not int or max_stalled_rounds < 1:
            raise ValueError("--max-stalled-rounds must be a positive integer")


def block_shapes(rows, cols):
    """Map each permitted writer size to one aligned, repeatable rectangle (rows, columns)."""
    shapes = {}
    for height in range(1, rows + 1):
        for width in range(1, cols + 1):
            if rows % height or cols % width:
                continue
            size = height * width
            shape = height, width
            if size != rows * cols and size in (4, 8) and shape != (2, size // 2):
                continue
            prior = shapes.get(size)
            if prior is None or (abs(height - width), height) < (abs(prior[0] - prior[1]), prior[0]):
                shapes[size] = shape
    return shapes


@dataclass(frozen=True)
class GroupPartition:
    group_size: int
    shape: tuple
    blocks: tuple

    @property
    def writer_framework(self):
        if len(self.blocks) == 1:
            return "CMAS"
        return "OWN" if self.group_size == 1 else "GROUP"

    def record(self):
        return dict(framework="GROUP", group_size=self.group_size, callers_per_round=len(self.blocks),
                    block_shape=list(self.shape), blocks=[list(block) for block in self.blocks])

    def call_scope(self, members, available):
        return dict(framework="GROUP", group_size=self.group_size, callers_per_round=len(self.blocks),
                    assigned_robots=list(members), robots_assigned=len(members),
                    assigned_robots_with_doable_actions=sum(bool(available[name]) for name in members))


@lru_cache(maxsize=128, typed=True)
def group_partition(rows, cols, size):
    shapes = block_shapes(rows, cols)
    if type(size) is not int or size not in shapes:
        valid = ", ".join(map(str, sorted(shapes)))
        raise ValueError(f"--group-size {size} does not tile {rows}x{cols}. Valid sizes: {valid}")
    height, width = shapes[size]
    blocks = tuple(tuple(agent_at((i + .5, j + .5))
                         for i in range(top, top + height) for j in range(left, left + width))
                   for top in range(0, rows, height) for left in range(0, cols, width))
    return GroupPartition(size, (height, width), blocks)


def build_prompt(rows, cols, state, responses, states, *, horizon, history_method, history_window,
                 state_position, robot=None, block=None, earlier=None, step_offset=0, strip_style=False,
                 announcement="", dropoff_rule=False, returned_only=False, plan_note="none", failed_writer="drop",
                 env="boxnet1"):
    """robot is a zero-based grid index. The history budget is independent of the reader."""
    if state_position not in ("before", "after") or horizon < 1 or history_window < 0:
        raise ValueError("Invalid matched prompt settings")
    validate_writer_options("matched", plan_note, failed_writer)
    if not states or states[-1] != state or len(states) != len(responses) + 1:
        raise ValueError("Expected one source state for each step, including the current state")
    if history_method in ("none", "_wo_any_dialogue_history"):
        history_window = 0
    elif history_method not in ("authors", "dialogue", "_w_only_state_action_history", "_w_all_dialogue_history"):
        raise ValueError("Unknown history method")
    # Matched history contains public executed state/actions for either nonempty method.
    past = state_action_history(responses, states, history_window, step_offset=step_offset)
    history = HISTORY_HEADING + "\n" + past
    if env == "boxnet2":
        import boxnet2
        observation = boxnet2.board_text(rows, cols, state)
        task, example = boxnet2.TASK, boxnet2.EXAMPLES
    else:
        observation = state_update_func(rows, cols, state, returned_only)
        task, example = TASK, ACTION_EXAMPLES
    board = announcement + STATE_HEADING + "\n" + observation
    goal = GOAL + (" " + DROPOFF_RULE if dropoff_rule in (True, "on") else "")
    intro = [goal, task]
    if not strip_style:
        intro.append(example)
    if env == "boxnet2":
        intro.append(boxnet2.COLLISION_RULE)
    intro = "\n".join(intro) + "\n\n"
    if block is not None:
        writer = GROUP_WRITER.format(robots=json.dumps(block))
    elif robot is None:
        writer = JOINT_WRITER
    else:
        speaker = agent_at((robot[0] + .5, robot[1] + .5))
        writer = OWN_WRITER.format(speaker=speaker)
    # Every matched role sees the same peer-list slot; it is empty for the
    # central writer before any submissions, and fills only as writers answer.
    writer += "\n" + OWN_DIALOGUE + json.dumps(earlier or {})
    layout = [board, history] if state_position == "before" else [history, board]
    shape = OWN_FORMAT if robot is not None else JOINT_FORMAT
    if failed_writer == "idle" and earlier and [] in earlier.values():
        shape += " " + EMPTY_PEER_NOTE
    output = [writer, f"Return a JSON list for the next {horizon} steps in execution order."]
    if plan_note == "continue":
        if horizon == 1:
            note = ("The job may need more than 1 step: plan only the next 1 step; "
                    "after it is executed, another planning round continues from the new state.")
        else:
            note = (f"The job may need more than {horizon} steps: plan only the next {horizon} steps; "
                    "after they are executed, another planning round continues from the new state.")
        output.append(note)
    output.extend((shape, FORMAT))
    if not strip_style:
        output.append(BREVITY)
    prompt = AfterHistoryPrompt(intro + "\n".join(layout) + "\n" + "\n".join(output))
    prompt.state_offset = len(intro) + (len(history) + 1 if state_position == "after" else 0) + len(announcement)
    return prompt
