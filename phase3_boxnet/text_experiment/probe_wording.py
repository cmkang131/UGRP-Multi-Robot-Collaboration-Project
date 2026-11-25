"""Probe wording ablations and fixed peer lists for paired first-round writer prompts."""
import json
import re
from dataclasses import dataclass
from itertools import islice

from env1_create import action_from_response
from map_events import agent_at, reference_trajectory
from matched_protocol import ACTION_EXAMPLES, BREVITY, build_prompt, group_partition
from plan_parse import speaker_coordinates


@dataclass(frozen=True)
class FirstWriter:
    framework: str
    index: int
    role: str
    speaker: str
    members: tuple
    earlier: dict
    scope: dict

    def prompt(self, saved, horizon, note, position, strip_style):
        robot = None
        if self.role == "own":
            robot = tuple(int(float(v) - .5) for v in speaker_coordinates(self.speaker))
        prompt = build_prompt(saved.rows, saved.cols, saved.state, [], [saved.state], horizon=horizon,
                              history_method="authors", history_window=0, state_position=position, robot=robot,
                              block=self.members if self.role == "group" else None, earlier=self.earlier,
                              dropoff_rule=saved.record["dropoff_rule"], plan_note=note, strip_style=strip_style)
        metadata = dict(robot=self.speaker, writer_role=self.role, writer_index=self.index, peer_lists=self.earlier,
                        state_position=position, env_seed=saved.record["env_seed"], env_sha256=saved.record["env_sha256"],
                        map_set=saved.record["map_set"], box_count=saved.record["box_count"], **self.scope)
        return prompt, metadata


def joint_moves(applied):
    step = {}
    for origin, box, dest in applied:
        site = f"square{list(dest)}" if isinstance(dest, (tuple, list)) else dest
        step[agent_at(origin)] = f"move({box}, {site})"
    return step


def first_round_writers(saved, frameworks, group_size, horizon, allowed):
    """Freeze row-major predecessors from the same static reference moves for both note arms."""
    reference = [joint_moves(actions) for _, actions in
                 islice(reference_trajectory(saved.state, action_from_response), horizon)]
    reference.extend({} for _ in range(horizon - len(reference)))
    for framework in frameworks:
        size = {"CMAS": saved.rows * saved.cols, "GROUP": group_size, "OWN": 1}[framework]
        partition = group_partition(saved.rows, saved.cols, size)
        role = {"CMAS": "central", "GROUP": "group", "OWN": "own"}[partition.writer_framework]
        earlier = {}
        for index, members in enumerate(partition.blocks):
            speaker = saved.record["L"] if role == "central" else members[0]
            scope = partition.call_scope(members, allowed)
            scope["framework"] = framework
            if framework != "GROUP":
                del scope["group_size"]
            yield FirstWriter(framework, index, role, speaker, members, earlier.copy(), scope)
            earlier[speaker] = ([step.get(speaker) for step in reference] if role == "own" else
                                [{name: step[name] for name in members if name in step} for step in reference])

LEADER_EXAMPLE = ('Specify your action plan in this format: {"Agent[0.5, 0.5]":"move(box_blue, square[0.5, 1.5])", '
                  '"Agent[1.5, 0.5]":"move...}.')
LEADER_INTRO = (
    " in a grid-like field to move colored boxes",
    "Each agent is assigned to a 1x1 square and can only interact with objects in its area.",
    "Agents can move a box to a neighboring square or a same-color target.",
    "The squares are identified by their center coordinates, e.g., square[0.5, 0.5].",
    "Actions are like: move(box_red, target_red) or move(box_red, square[0.5, 0.5]).",
    "After each move, agents provide updates for the next sequence of actions.",
    "Your job is to coordinate the agents optimally.",
)
OWN_INTRO = (
    ", stationed on a 1x1 square in a grid playground",
    "You can only interact with objects in your square.",
    "Squares are denoted by their center coordinates (e.g., square[0.5, 0.5]), and actions involve moving boxes "
    "to targets or nearby squares, represented by colors (e.g., move(box_red, target_red)).",
    "All the agents coordinate with others together to come out a plan and ",
)
OWN_OUT = ("only ", ", using the move syntax above", "Write null as the unquoted JSON literal.",
           "Do not name an agent or write actions for others.", "Your response:")


def style_spans(caller, horizon):
    if caller == "leader":
        cue = "Now, plan the next step:" if horizon == 1 else f"Now, plan the next {horizon} steps:"
        return LEADER_INTRO, (LEADER_EXAMPLE, cue)
    example = json.dumps(["move(box_blue, square[0.5, 1.5])"] + [None] * (horizon - 1))
    return OWN_INTRO, (*OWN_OUT, "Example#1: " + example)


def strip_nonstructural_style(prompt, caller, horizon=1):
    """Only inspect template copy on either side of all board, history and peer data."""
    context = re.search(r"^\s*(?:Hence, the current state is|The current state and possible actions of yourself are:|"
                        r"The previous state and action pairs at each step are:|Change of orders \(announced)", prompt, re.M)
    tail = prompt.rindex(LEADER_EXAMPLE if caller == "leader" else "\nAvoid conflicts with these lists.")
    intro, material, output = prompt[:context.start()], prompt[context.start():tail], prompt[tail:]
    intro_spans, output_spans = style_spans(caller, horizon)
    for span in intro_spans:
        if span not in intro:
            raise ValueError(f"Unrecognized probe introduction for {caller}")
        intro = intro.replace(span, "", 1)
    for span in output_spans:
        if span not in output:
            raise ValueError(f"Unrecognized probe output wording for {caller}")
        if span == "only ":
            output = output.replace("Output only a JSON list", "Output a JSON list", 1)
        else:
            output = output.replace(span, "", 1)
    return intro + material + output


SOURCE_MAPPING = (
    "State N is the saved board before step N. Public history uses saved states and the source's issued joint "
    "response for each earlier executed transition, with original step numbers. For peer lists and repeats, "
    "the physical executor's applied_actions are authoritative. Each applied (origin, box, destination) becomes "
    "one move for Agent[origin], with coordinates rendered as square[row, col]. Every row-major predecessor "
    "gets that move or null at entry one and H − 1 trailing nulls. A final actionable board with no executed "
    "next step gives every predecessor null. own_first uses the same robot with {}."
)


def fairness_report(horizon=1):
    lines = [
        "#### Wording audit and the optional style ablation", "",
        "These are the literal deletion spans in the rendered prompts. The short fragments occur inside role, "
        "goal or output sentences. All board observations, history pairs and peer data keep their original text. "
        "The single-step CMAS example ends with the malformed `move...}.` in the original. Removing it also "
        "removes the leader's only worked JSON example at H1.", "",
    ]
    for caller in ("leader", "own_first"):
        lines.extend([f"**{'Leader' if caller == 'leader' else 'OWN (both callers)'}**, H={horizon}", "", "```text"])
        intro, output = style_spans(caller, horizon)
        lines.extend((*intro, *output, "```", ""))
    lines.extend([
        "The final leader cue at H>1 is `Now, plan the next H steps:`. The OWN example contains one blue move "
        "and H − 1 nulls. The two deletion lists above instantiate both strings for the specified horizon.", "",
        "Three other differences matter when reading the legacy comparison.", "",
        "- The role and goal are written as “You are a central planner directing agents in a grid-like field to move "
        "colored boxes.” and “Your task is to instruct each agent to match all boxes to their color-coded targets.” "
        "OWN reads “You're a box-moving agent in a multi-agent system, stationed on a 1x1 square in a grid playground.” "
        "and “All the agents coordinate with others together to come out a plan and achieve the goal: match each box "
        "with its color-coded target.” The ablation retains the writer identity and delivery goal.", 
        "- CMAS repeats a raw board dictionary in “Hence, the current state is {board}, with the possible actions:”. "
        "OWN labels “The current state and possible actions of yourself are: {local}.” and “The current states and possible "
        "actions of all other agents are: {others}.” Native observation lines use “I am in”, “I can observe”, “I can do” "
        "for the whole board, and “in”, “can observe”, “can do” for the local OWN observation. These data-bearing blocks "
        "and native newlines stay in the style ablation. Matched uses the same row-major board for both.", 
        "- CMAS keeps “Include an agent only if it has a task next.” At H>1 it requests a list of joint objects, allows "
        "an empty object and early completion, and assumes earlier steps executed. OWN keeps its earlier-list heading, "
        "“Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.” "
        "and the JSON-list length, action-string and idle-null contract. The full output-format sentences appear in the "
        "unaltered prompts below. Both callers use “Please learn from previous steps. Not purely repeat the actions but "
        "learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.”", "",
        "The D2 review measured DMAS. Its “Think step-by-step about the task and the previous dialogue history. "
        "Carefully check and correct them if they made a mistake.” and “Respond very concisely but informatively, "
        "and do not repeat what others have said. Discuss with others to come up with the best plan.” are replaced by "
        "the OWN output instruction before rendering. Neither probe caller receives them or the two DMAS EXECUTE examples. "
        "OWN's “Output only a JSON list” is its remaining explicit output-only instruction. The probe preserves the JSON "
        "type/length and removes the output-only qualifier in the stripped OWN prompt.", "",
        "In matched mode both callers receive the same examples and brevity instruction. The corresponding style "
        "ablation removes exactly these two shared sentences.", "", "```text", ACTION_EXAMPLES, BREVITY, "```", "",
        SOURCE_MAPPING, "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    from probe_reading import main, parser
    try:
        main()
    except ValueError as exc:
        parser().error(str(exc))
