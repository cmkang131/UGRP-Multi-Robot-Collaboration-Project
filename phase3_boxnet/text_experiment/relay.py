"""One private forwarding decision per eligible robot at the event boundary."""
import re
import string
import unicodedata

from env1_create import state_update_func_local_agent
from matched_protocol import STATE_HEADING
from prompt_env1 import message_construct_func

SPEECH_RULES = ("authors", "auto", "choice", "free")
RELAY_TIMINGS = ("immediate", "turn")
RELAY_DISPLAYS = ("persistent", "once")
HEADER = "Messages received from robots:\n"
STATE_HEADERS = {"central": "Hence, the current state is", "local": "The current state and possible actions of yourself are:"}
AUDIENCE = {"CMAS": "the central planner", "HMAS-2": "the central planner", "DMAS": "all other robots", "OWN": "all other robots",
            "HMAS-1": "the central planner and all other robots"}
CHOICE = {1: "You may forward this notice to {recipient}. Reply SEND or PASS.",
          2: "You may keep this notice or forward it to {recipient}. Reply PASS or SEND."}
FREE = ("You may send one short message to {recipient}, or reply PASS to send nothing. "
        "Reply with the message text alone, or PASS.")


def check_relay_options(speech, framework, timing, display):
    if timing is None and display is None:
        return
    if speech != "auto":
        raise ValueError("--relay-timing and --relay-display require --speech auto only")
    if (timing is not None and timing not in RELAY_TIMINGS) or (display is not None and display not in RELAY_DISPLAYS):
        raise ValueError(f"Invalid relay timing or display: {timing}, {display}")
    if timing == "turn" and framework not in ("DMAS", "HMAS-1", "OWN", "GROUP"):
        raise ValueError(f"--relay-timing turn is undefined for {framework}. It requires robot dialogue.")


def relay_cell(record):
    """Auto in archived runs always used immediate, persistent forwarding."""
    if record.get("speech") != "auto":
        return "-", "-"
    return record.get("relay_timing", "immediate"), record.get("relay_display", "persistent")


def parse_reply(rule, reply, notice):
    text = reply.strip()
    token = text
    while token and (token[-1].isspace() or token[-1] in string.punctuation
                     or unicodedata.category(token[-1]).startswith("P")):
        token = token[:-1]
    if rule == "choice":
        words = set(re.findall(r"\b(?:SEND|PASS)\b", token.upper()))
        if words == {"SEND"}:
            return "SEND", notice, False
        if words == {"PASS"}:
            return "PASS", None, False
    elif token.upper() == "PASS":
        return "PASS", None, False
    elif text:
        return "message", reply[:400], len(reply) > 400
    return "relay_format_error", None, False


def free_checks(text, event):
    colour = re.search(r"(?<![a-z0-9])" + re.escape(event["A"]) + r"(?![a-z0-9])", text, re.I)
    site = re.search(r"(?<![a-z0-9])drop[-\s_‐‑]*off(?![a-z0-9])", text, re.I)
    pairs = re.findall(r"(?<![\d.\-])(\d+(?:\.\d+)?)\s*[, _]\s*(\d+(?:\.\d+)?)(?!\d|\.\d)", text)
    coords = any([float(x), float(y)] == event["D"] for x, y in pairs)
    return dict(names_colour=bool(colour), names_dropoff=bool(site), names_coordinates=coords,
                names_destination=bool(site) or coords)


class Relay:
    def __init__(self, spec, wording):
        self.rule, self.framework, self.wording = spec.speech, getattr(spec, "writer_framework", spec.framework), wording
        if self.framework == "GROUP":
            self.framework = "OWN"  # Sub-team leaders read the inbox of their own square.
        self.matched = getattr(spec, "protocol", None) == "matched"
        self.timing = spec.relay_timing or "immediate"
        self.display = spec.relay_display or "persistent"
        self.records = []
        self.deliveries = {}
        self.seen = set()  # (sender, recipient) for once-only display

    def prepare(self, told, robots, leader, step):
        for sender in told:
            if self.framework in ("CMAS", "HMAS-2"):
                recipients = [leader]
            else:
                recipients = [r for r in robots if r != sender or (self.framework == "HMAS-1" and r == leader)]
            if self.rule == "authors":
                status = "authors"
            elif not any(r != sender for r in recipients):
                status = "relay_skipped_self"
            else:
                status = "not_reached"
            self.records.append(dict(sender=sender, after_step=step, status=status, call_made=False,
                                     call_number=None, reply_class=None, delivered_text=None, cut=False,
                                     names_colour=None, names_dropoff=None, names_coordinates=None,
                                     names_destination=None, intended_recipients=recipients, recipients=[]))

    def forward(self, episode, *, after_speaker=None, position=0):
        if self.timing == "turn" and after_speaker is None:
            return
        notice = episode.event["announcement"]
        for record in self.records:
            if record["status"] != "not_reached" or (after_speaker is not None and record["sender"] != after_speaker):
                continue
            if self.rule == "auto":
                decision, text, cut = "SEND", notice, False
                self.deliveries[record["sender"]] = dict(
                    iteration=episode.session.step if after_speaker else record["after_step"] + 1,
                    speaker_position=position, round=episode.session.round if after_speaker else 0,
                    after_call=episode.session.cursor)
            else:
                sender = record["sender"]
                row, col = divmod(episode.robots.index(sender), episode.spec.cols)
                local, _ = state_update_func_local_agent(episode.spec.rows, episode.spec.cols, row, col,
                                                         episode.state, episode.condition == "e2")
                instruction = FREE if self.rule == "free" else CHOICE[self.wording]
                prompt = local + notice + "\n" + instruction.format(recipient=AUDIENCE[self.framework])
                messages = message_construct_func([prompt], [], "_w_all_dialogue_history")
                session = episode.session
                session.step, session.round = record["after_step"], 0
                session.speaker, session.role, session.told = sender, "relay", True
                cursor = session.cursor
                record["status"] = "call_stopped"
                try:
                    scope = episode.spec.partition.call_scope((), {}) if episode.spec.framework == "GROUP" else None
                    reply, _ = session.call(messages, scope=scope)
                finally:
                    if session.cursor > cursor:
                        call = session.records[cursor]
                        record.update(call_number=call["number"], call_made=bool(call["api_calls"]))
                decision, text, cut = parse_reply(self.rule, reply, notice)
            record.update(status="delivered" if text is not None else decision,
                          reply_class=decision, delivered_text=text, cut=cut)
            if text is not None:
                record["recipients"] = record["intended_recipients"].copy()
                if self.rule == "free":
                    record.update(free_checks(text, episode.event))

    def inbox(self, robot, *, consume=False):
        lines = []
        for record in self.records:
            key = record["sender"], robot
            if robot not in record["recipients"] or (consume and key in self.seen):
                continue
            lines.append(f"[{record['sender']}, after step {record['after_step']}]: {record['delivered_text']}\n")
            if consume:
                self.seen.add(key)
        return HEADER + "".join(lines) if lines else ""

    def in_prompt(self, prompt, robot, role):
        marker = STATE_HEADING if self.matched else STATE_HEADERS["central" if role == "central" else "local"]
        if self.timing == "turn" or self.display == "once":
            # The producer may be an earlier proposal, before later sends or reads.
            return any(f"[{r['sender']}, after step {r['after_step']}]: {r['delivered_text']}\n" + marker in prompt
                       for r in self.records if robot in r["recipients"])
        block = self.inbox(robot)
        if not block:
            return False
        return block + marker in prompt

    def insert(self, prompt, robot, role):
        # Called once per regular turn. Repairs and central revisions reuse the built prompt.
        block = self.inbox(robot, consume=self.display == "once")
        if not block:
            return str(prompt)
        marker = STATE_HEADING if self.matched else STATE_HEADERS["central" if role == "central" else "local"]
        offset = getattr(prompt, "state_offset", None)
        if offset is None:
            offset = prompt.find(marker)
        if offset < 0 or not prompt.startswith(marker, offset):
            raise ValueError("Current-state heading missing from addressed prompt")
        return prompt[:offset] + block + prompt[offset:]
