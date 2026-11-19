"""Free communication (study switch --talk free), the leader's binding assignment (--leader-bind) and the election at the start of a free run.

Phase 2 of the leader study (PREREG-PHASE2.md, FREE-TALK-SURVEY.md). Nothing here runs unless TeamBrain(talk="free") is given; with the switch off no
prompt, option, result or record key changes (tools/identity_check.py proves it byte for byte against the frozen planner).

Free talk (CoELA: "send a message" is one entry of the action list; Guo 2024: a receiver can be named, silence is allowed):
  * Every decision (pick, destination, door, report) lists, after the executor's own options, one entry "say to rX: <text>" for every other robot and
    one "say to everyone: <text>". The model answers with an option label (or the option text) and writes its words (see read_say for the shapes read).
  * Words written next to a body option ({"action":"B","say":"r2, ..."}) are a speech too: the decision is the speech, the body option is not done (the dropped
    option is in the decision result `say_with_action` and the event counter `say_with_action`; target: the "to" field, else a leading "rX," / "rX:", else everyone;
    but when the leader's words hold a valid `assign rY:` line for a teammate other than that addressee the speech goes to everyone, so that the line reaches rY:
    `say_with_action.widened_from`, event `say_widened_for_assignments`).
    Only when a say entry is offered; right after its own say a robot has none, and words next to an action are dropped and counted (words_beside_an_action_not_sent).
  * Choosing a say entry takes the place of the body action of that decision: the answer is {option: wait key, sent: [message], wait_s: t_say} and the
    runner lets the robot stand for max(2, wait_s) s (run_team_carry ask(): `turn_used = sent and not sent_with_action`). t_say = 1.45 + 0.0036 * chars.
    /poll answers "nothing new" while the robot speaks, so a new message does not cut the speech short (brain_server).
  * Delivery = start of the say + t_say + msg_delay_s (2 s). A receiver reads its messages one after the other: a message is READABLE at
    max(deliver_at, end of the previous read) + 0.7 + 0.0018 * chars. A message enters a prompt, the /poll "new" test and an assignment only from its
    readable time on (one time, used in all three places).
  * No message budget (MAX_MESSAGES, "Messages left", the draft step and the send question are not used). One limit: a robot that has just spoken is not
    offered a say entry again until a new message has reached it (CoELA LLM.py:496; say_streak_max = 1).
  * The message history of a prompt is bounded by the input bound (see _Planner._prompt in __init__.py): when the prompt would not fit, the oldest shown messages are
    dropped one by one and a line "(N older messages not shown)" says how many (events history_trimmed_prompts, history_messages_dropped). Display only: delivery, the
    reading queue, reported facts and assignments read the stored messages.
  * A message goes to the robots it names (no hub routing in T2: members talk to each other like in T1, see PREREG-PHASE2.md 2).
  * The runner stands the body for max(2, wait_s) after a speech on every path (pick / destination / door question, report, message chance, destination
    re-decision): execution layer scripts/run_team_carry.py talk_stand (commit 87e9d0d on lead2/exec-v39), recognised by say_s in the answer. The ACT grasp and
    the release replay are not paused there. With multi-carry the runner also holds the body on the return, at 'blocked' and while retrying
    'next'. Repeated valid assign lines form a FIFO per member. Only its own completed matching release consumes the head.
    The record keeps say_s of every say.

Leader binding (T2, free talk): the leader says the line `assign rX: <colour> -> <zone>` (any number of them in one say; the existing message table
`assignments` carries it: a valid line is attached to the message as the fact {table: assignments, id: rX, value: {box, zone}}). Once such a message has
become readable to rX, rX's pick and destination lists hold only the assigned colour / zone (+ wait; finish and put_down are taken out). Without an
assignment rX may only wait or speak for hold_s after its first pick decision. A failed first grasp lifts the binding. The leader is never bound.

Star route (T2, free talk, --leader-route star; PREREG-PHASE2.md 8): ALL communication goes through the leader. A member is offered one say entry only, "say to <leader>: <text>"
(no teammate, no "everyone"); the leader keeps every entry (each teammate, everyone) and its assign lines / widening rule. A member's words that address another member or everyone
(a "say to rX:" / "say to everyone:" text, a body label plus words with a "to" field or a leading "rX,") are delivered to the leader only and counted (message field
`redirected_from`, event `member_redirected_to_leader`, record `star`); words beside a body label with no addressee at all go to the leader and are not counted as a redirect;
a say entry chosen to the leader whose words start "rX," is not a redirect either (the leader is its addressee). A target that is the robot itself or no robot of the team stays
`say_to_nobody`. The leader is known before any say entry is built (the election of a free run happens at the first decision, `_ensure_elected`; `_say_entries` repeats it), so
there is no window in which a member could speak to someone else: before the first decision nobody can speak. The prompt tells every robot the rule (STAR_LEADER, STAR_MEMBER).
The leader stays available: every decision answer of the star leader carries `relay: True`; a runner that knows the key keeps the leader in the conversation after its own run is over
(carry delivered, put down or finish) and asks it the point "relay" (options: wait, plus the say entries) whenever /poll reports a new message, until every teammate has finished
(execution layer scripts/run_team_carry.py, phase2/exec-merged). If the leader halts (call cap or fault) the members are told in their next prompt (STAR_MEMBER_DOWN), their only
say entry is "say to everyone" (a speech to anyone goes to everyone) and every such speech is counted: event and record `leader_down_fallback`.
"""
import copy
import math
import re

from .llm import CallLimitError, RealLLM, check_spend_guard
from .planning import _json
from .protocol import COLOURS

SAY_FIX_S, SAY_PER_CHAR_S = 1.45, 0.0036      # PREREG-PHASE2.md 2 (measured on v38 calls: median latency 1.45 s, 0.0112 s per output token, 3.15 chars/token)
READ_FIX_S, READ_PER_CHAR_S = 0.7, 0.0018     # half of the say values (an assumption of the document, not a measurement)
HOLD_S = 75.0                                 # T_hold of PREREG-PHASE2.md
SAY_MAX_CHARS = 600                           # protocol.UTTERANCE_CHARS: a longer text is cut before it is sent
SAY_STREAK_MAX = 1                            # CoELA LLM.py:496: no second say in a row unless a new message came in between

# Sentences shown only in a free-talk run (T1/T2); the other runs never see them.
FREE_RULE = ("Besides acting you may speak: choose a say option to say something to one teammate or to everyone, and write your words yourself. "
             "Speaking uses your turn instead of a body action: you stand still for a few seconds and do nothing else, and your friends need time "
             "to read it, so speak only when it tells them something they need and do not already know.")
FREE_ANSWER = ('Return an action or option label, optionally as {"action":"text"}. To speak, choose a say option instead of a body action and write '
               'your words: {"action":"<say option label>","say":"your words"}. Do not write "say" together with a body action: then only the '
               'words are sent and the action is not done.')
FREE_MERGE = ('\nLet\'s think step by step, then answer. Return {"reasoning":"text","action":"option label"} and, when the action is a say option, also '
              '"say":"your words".')
FREE_FINAL = ("Answer with only one best next action. To speak, give the say option and your words (for example: say to r2: your words). "
              "So the answer is option")
FREE_RETRY = "\nYour last answer could not be matched to an option. Answer with only the option label (a letter)."
# What _choose_free appends to the prompt after _prompt (the merged-call sentence, the label-only retry, the two-step final line): the history bound leaves room for it.
FREE_SUFFIX_BYTES = len((FREE_MERGE + FREE_RETRY + "\nAssistant: " + FREE_FINAL).encode("utf-8"))
CHANCE_FREE = ("A message from my friends has just arrived and I have no decision to make right now. I may reply with a say option, or stay silent "
               "(only reply if I have something to answer or something new to tell them).")
SILENT_TEXT = "stay silent and carry on"
# Leader authority in free talk (the original sentences of --leader-authority speak of message facts, which a say does not have).
FREE_AUTHORITY_LEADER = ("You are the leader: decide which box each robot takes and to which zone, using only what you know and what your friends have "
                         "told you, and tell each robot with a say. Write each assignment as the line \"assign rX: <colour> -> <zone>\" (for example "
                         "\"assign %s: %s -> %s\"), several lines in one say are fine.")
FREE_AUTHORITY_MEMBER = ("The leader decides which robot takes which box to which zone. When the leader tells you which box to take or which zone to "
                         "carry it to, do that instead of your own guess, unless what you see shows that it cannot be done. Where the leader has "
                         "told you nothing, act on what you know.")
BIND_LEADER = (" A robot you assign can then only carry that colour to that zone. A robot you have not assigned can only wait or speak until %d s "
               "after its first decision.")
BIND_MEMBER = (" Until the leader assigns you a box colour and a zone you can only wait or speak (for up to %d s after your first decision); once "
               "the leader has assigned you, you can only carry that colour to that zone.")
# Star route (--leader-route star): the rule is stated to every robot; a member's goal sentence names the leader as the only addressee.
STAR_LEADER = (" All communication goes through you: your teammates can only talk to you (they cannot say anything to each other or to everyone), so tell a teammate "
               "yourself whatever it needs to know from the others. You may say something to any one teammate or to everyone. Even after your own carry is over "
               "you stay here and keep relaying until every teammate has finished.")
STAR_MEMBER = (" You can only talk to the leader %s; the leader relays. You cannot say anything to the other robots or to everyone: what you say reaches only the "
               "leader, and what you learn about the other robots comes through the leader.")
STAR_MEMBER_DOWN = (" The leader %s is no longer available: it cannot read or answer any more, so nothing you say reaches it. You can now say something to "
                    "everyone instead (every other robot still working hears it).")
RELAY_NOTE = ("My own carry is over and my body is done, but I stay here to relay for my teammates while they are still working. A message from "
              "them has just arrived. I may reply with a say option (tell a teammate what it needs to know), or just wait (only speak if I have something to tell).")
FREE_RULE_STAR_MEMBER = ("Besides acting you may speak: choose the say option to say something to the leader, and write your words yourself. "
                         "Speaking uses your turn instead of a body action: you stand still for a few seconds and do nothing else, and the leader needs time "
                         "to read it, so speak only when it tells the leader something it needs and does not already know.")

SAY_TO = re.compile(r"\bsay\s+to\s+(r\d+|everyone|everybody|all)\b[ \t]*[:\-]?[ \t]*(.*)", re.I | re.S)
PLACEHOLDER = re.compile(r"^\W*(?:<\s*)?(?:text|your words|words|\.\.\.)(?:\s*>)?\W*$", re.I)
ASSIGN = re.compile(r"\bassign\s+(r\d+)\s*:\s*<?\s*([A-Za-z]+)(?:\s+box)?\s*>?\s*(?:->|=>|→|to)\s*<?\s*(sign\d+)(?:\s+zone)?\s*>?", re.I)
WORDS_FIELDS = ("say", "text", "message", "words", "content")
ADDRESSEE = re.compile(r"^\s*(r\d+)\s*[,:]", re.I)            # a text that starts "r2, ..." or "r2: ...": the teammate it is spoken to


def say_time(chars, fix=SAY_FIX_S, per_char=SAY_PER_CHAR_S):
    return fix + per_char * chars


def read_time(chars, fix=READ_FIX_S, per_char=READ_PER_CHAR_S):
    return fix + per_char * chars


def _target(raw):
    raw = raw.lower()
    return "everyone" if raw in ("everyone", "everybody", "all") else raw


def _words(text):
    """The words of a say: stripped, without surrounding quotes, '' for the placeholder of the option line."""
    text = str(text).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return "" if PLACEHOLDER.match(text) else text


def _words_field(result):
    """The words an answer wrote in one of its JSON fields ('' when there are none or only the placeholder of the option line)."""
    return next((_words(result[k]) for k in WORDS_FIELDS if isinstance(result.get(k), str) and _words(result[k])), "")


def parse_assign(text):
    """[(robot, colour word as written, zone)] of every `assign rX: <colour> -> <zone>` line of a text, in order."""
    return [(m.group(1).lower(), m.group(2), m.group(3).lower()) for m in ASSIGN.finditer(text)]


def read_say(menu, result, text, label):
    """The say the model chose: None (a body action), or dict(entry=menu text of the say entry or None, target, body).
    Shapes read, in this order (before any body match: the words of a say may contain the text of another option):
      1. 'say to r2: words' / 'say to everyone: words' anywhere in the action text (a JSON `say` / `text` / `message` field supplies the words when the
         text has only the placeholder); a target that is not in the menu (itself, a robot that is not there) gives entry=None;
      2. the label of a say entry ('F', 'F.', 'F: words', 'option F') with the words in the `say` field or after the label."""
    items = [(i, key, skill) for i, (key, skill) in enumerate(menu.items()) if skill["skill"] == "say"]
    if not items:
        return None
    field = next((_words(result[k]) for k in WORDS_FIELDS if isinstance(result.get(k), str) and _words(result[k])), "")
    found = SAY_TO.search(text)
    if found:
        target = _target(found.group(1))
        entry = next((key for _, key, skill in items if skill["target"] == target), None)
        return dict(entry=entry, target=target, body=_words(found.group(2)) or field)
    stripped = text.strip()
    for i, key, skill in items:
        lab = label(i)
        tail = re.match(r"\s*\(?%s\)?(?:[.):]\s*(.*)|\s*)$" % re.escape(lab), stripped, re.S)
        if tail or re.search(r"\b(?:option|Option|action) %s\b" % re.escape(lab), text):
            rest = _words(tail.group(1)) if tail and tail.group(1) else ""
            return dict(entry=key, target=skill["target"], body=field or rest)
    return None


def _is_echo(menu, words):
    """The words are one of the option lines of the prompt copied (with or without its label): not something the robot wants to say."""
    low = re.sub(r"^\(?[A-Z]{1,2}[.):]\s+", "", words.strip()).strip().casefold()
    return any(low == key.strip().casefold() for key in menu)


def read_say_beside_action(menu, result, text, label, roster=None, default="everyone"):
    """The answer {"action":"B","say":"words"}: a body option (or the silence entry of a chance) with words. Speaking is an action that takes the turn
    (PREREG-PHASE2.md 8), so words next to an action make the decision a speech and the body action of that answer is not done. Called after read_say
    found no say entry in the answer; only when the menu offers say entries (a robot that has just spoken is not offered one: the words are then dropped).
    Target: an explicit "to" field ('r2', 'everyone' / 'all', a list that names one teammate or all of them) if it names a robot of the menu, else a text
    that starts "rX," / "rX:" with rX a teammate, else everyone. The words are sent as written. None: no words, only the copy of an option line, or
    no say entry. Otherwise dict(entry, target, body, dropped = the body answer that was not done: its text and, when the answer is a bare label or
    starts with one, the executor key).
    roster / default (star route, a member whose menu has the leader entry only): roster = every other robot of the team (the addressees the answer can name although
    the menu offers one of them), default = the target of words that name nobody (the leader; else everyone). The returned target can then be a robot or `everyone`
    (or "rA,rB" for a "to" list naming several) that the menu has no entry for: entry is None and the caller redirects it. Without roster nothing changes."""
    items = {skill["target"]: key for key, skill in menu.items() if skill["skill"] == "say"}
    words = _words_field(result)
    if not items or not words or _is_echo(menu, words):
        return None
    teammates = {t for t in items if t != "everyone"} if roster is None else set(roster)
    valid = set(items) if roster is None else set(items) | teammates | {"everyone"}
    explicit = result.get("to")
    named = [explicit] if isinstance(explicit, str) else list(explicit) if isinstance(explicit, (list, tuple)) and all(isinstance(x, str) for x in explicit) else []
    named = {_target(x.strip()) for x in named}
    target = None
    if len(named) == 1 and next(iter(named)) in valid:
        target = next(iter(named))
    elif named and named == teammates:
        target = "everyone"
    elif roster is not None and len(named & valid) >= 2:
        target = ",".join(sorted(named & valid))
    if target is None:
        address = ADDRESSEE.match(words)
        target = address.group(1).lower() if address and address.group(1).lower() in teammates else default
    stripped = text.strip()
    dropped = dict(action=stripped[:80], key=None)
    for i, (key, skill) in enumerate(menu.items()):
        if skill["skill"] != "say" and (stripped.strip("().: ") == label(i) or re.match(r"\(?%s[.):]" % re.escape(label(i)), stripped)):
            dropped["key"] = skill.get("key")
            break
    return dict(entry=items.get(target), target=target, body=words, dropped=dropped)


class FreeChoiceMixin:
    """Choice step of a free-talk decision (the planner side; TeamBrain._decide_free calls it). It is PlanningPolicy._choose with say entries in the list."""

    def _note(self, s):
        return self.brain._free_note(s) if self.brain.talk == "free" else ""

    def _free_mock(self, s, body_menu):
        return {"action": self._mock_choice(s, body_menu)}

    def _choose_free(self, s, menu):
        """('say', dict from read_say / read_say_beside_action) or ('act', menu text of a body entry); (None, None) for an empty menu. A say entry that the
        answer chooses without words is returned as ('say', dict with body '') and treated by the brain as a wait."""
        body_menu = {key: skill for key, skill in menu.items() if skill["skill"] != "say"}
        if not menu or not body_menu:
            return None, None
        prompt = self._prompt(s, "choice", menu, FREE_ANSWER)
        if self.merge_calls and self.cot:
            prompt += FREE_MERGE
        elif self.cot:
            result = self._call(s, "reasoning", prompt + ' Let\'s think step by step. Return {"reasoning":"text"}.',
                                lambda: {"reasoning": "Compare the available skills using local memory."})
            prompt += "\nAssistant: " + _json(result) + "\n" + self.brain._free_final(s["rid"])
        result = self._call(s, "choice", prompt, lambda: self._free_mock(s, body_menu))
        text = result.get("action", "")
        text = text if isinstance(text, str) else _json(text)
        say = read_say(menu, result, text, self._label) or read_say_beside_action(menu, result, text, self._label, **self.brain._beside_kw(s["rid"]))
        if say:
            return "say", say
        if any(isinstance(result.get(k), str) and result[k].strip() for k in WORDS_FIELDS):
            self.brain._event("words_beside_an_action_not_sent")      # words next to a body action that cannot be a speech (no say entry is offered right after the robot's own say, an echo of an option line, a placeholder): dropped, counted
        if not self.parser_fix:
            return "act", self._match(s, body_menu, text)
        # parser_fix: a label at the start is read first; an answer that matches nothing is asked once more (a say label in the new answer counts)
        head = re.match(r"\s*\(?([A-Z]{1,2})[.):]\s", text.strip() + " ")
        if head:
            for i, action in enumerate(body_menu):
                if self._label(i) == head.group(1):
                    return "act", action
        found = self._match(s, body_menu, text, allow_random=False)
        if found is not None:
            return "act", found
        self.plan_events.append(dict(robot=s["rid"], time=s["now"], event="parse_retry", plan=None, box=None, zone=None,
                                     reason="answer_matched_no_option", start=None, end=None, change=False))
        again = self._call(s, "choice", prompt + FREE_RETRY, lambda: self._free_mock(s, body_menu))
        text = again.get("action", "")
        text = text if isinstance(text, str) else _json(text)
        say = read_say(menu, again, text, self._label) or read_say_beside_action(menu, again, text, self._label, **self.brain._beside_kw(s["rid"]))
        if say:
            return "say", say
        if any(isinstance(again.get(k), str) and again[k].strip() for k in WORDS_FIELDS):
            self.brain._event("words_beside_an_action_not_sent")
        return "act", self._match(s, body_menu, text)


class TalkMixin:
    """Free talk, leader binding and the free-run election (all methods are used only when self.talk == "free")."""

    # ------------------------------------------------------------------ setup
    def _talk_init(self, talk, say, read, say_streak_max, hold_s, leader_bind, leader_seed, zones, team, protocol, pre_exchange, option_order, route_note,
                   caps_given, leader_authority, leader_route=None):
        if talk not in (None, "free"):
            raise ValueError("talk must be None or 'free'")
        self.talk = talk
        if leader_route not in (None, "star"):
            raise ValueError("leader_route must be None or 'star'")
        if leader_route and (talk != "free" or team != "T2"):
            raise ValueError("leader_route needs team T2 with free talk")
        self.leader_route = leader_route
        self._leader_down_info = None
        self.say_fix_s, self.say_per_char_s, self.read_fix_s, self.read_per_char_s = (float(x) for x in say + read)
        if min(self.say_fix_s, self.say_per_char_s, self.read_fix_s, self.read_per_char_s) < 0:
            raise ValueError("say / read times must be >= 0")
        if isinstance(say_streak_max, bool) or int(say_streak_max) != say_streak_max or say_streak_max < 1:
            raise ValueError("say_streak_max must be a whole number >= 1")
        self.say_streak_max, self.hold_s, self.leader_bind = int(say_streak_max), float(hold_s), bool(leader_bind)
        if self.hold_s < 0:
            raise ValueError("hold_s must be >= 0")
        if leader_seed is not None and (isinstance(leader_seed, bool) or int(leader_seed) != leader_seed or leader_seed < 0):
            raise ValueError("leader_seed must be a whole number >= 0")
        self.leader_seed = None if leader_seed is None else int(leader_seed)
        if talk == "free":
            if team not in ("T1", "T2"):
                raise ValueError("free talk needs a structure that can send messages (T1 or T2)")
            if protocol or pre_exchange or option_order != "forward" or route_note or caps_given:
                raise ValueError("free talk replaces the old message routes: no protocol, pre_exchange, option_order reverse, route_note or message budget with it")
        if self.leader_bind and (talk != "free" or team != "T2"):
            raise ValueError("leader_bind needs team T2 with free talk")
        self.zones = tuple(zones)
        self._seen_zones = set()
        self._busy_until, self._wake_at = {}, {}
        self._first_pick, self._grasp_failed = {}, set()
        self._bind = {}
        self._assign_log = []
        self._talk_events = {}
        self._elected, self._election = False, None

    def _event(self, name, n=1):
        self._talk_events[name] = self._talk_events.get(name, 0) + n

    # ------------------------------------------------------------------ reading queue, poll
    def _readable(self, rid):
        """{message index: readable time} of the messages addressed to rid: a receiver reads one after the other, a message from its arrival on."""
        out, t = {}, -math.inf
        for dat, i in sorted((m["deliver_at"], i) for i, m in enumerate(self._messages) if rid in m["to"] and m["from"] != rid):
            t = max(dat, t) + read_time(self._messages[i].get("chars", 0), self.read_fix_s, self.read_per_char_s)
            out[i] = t
        return out

    def readable_count(self, rid, now_s, decisions_only=False):
        """Messages rid can read by now_s (what brain_server counts for /poll `new`; a reply written at a chance does not count when decisions_only)."""
        ready = self._readable(rid)
        return sum(1 for i, t in ready.items() if t <= now_s and not (decisions_only and self._messages[i].get("via") == "chance"))

    def hold_poll(self, rid, now_s, chance=False):
        """/poll override: False while the robot speaks (a new message must not cut the speech short), True at a wake-up the planner asked for (the end of
        the binding hold of a member), None = the usual test (delivered count against `seen`)."""
        if self.talk != "free":
            return None
        if now_s < self._busy_until.get(rid, -math.inf):
            return False
        wake = self._wake_at.get(rid)
        if wake is not None and now_s >= wake and not chance:
            return True
        return None

    # ------------------------------------------------------------------ election
    def _ensure_elected(self, now_s):
        """A free T2 run with --leader-election: the leader is chosen at the first decision (every robot has been told its orders by then), once.
        Without protocol rounds nothing else elects a leader, and the election is ideal: no time, no loss."""
        if self.talk != "free" or self.team != "T2" or not self.leader_election or self._elected:
            return
        self._elected = True
        alive = self._alive(now_s)
        leader, counts = self._elect(alive)
        top = max(counts.values())
        self.leader = leader
        self._election = dict(counts=counts, leader=leader, tied=sorted(r for r in alive if counts[r] == top), seed=self.leader_seed,
                              rule="most orders known, ties: lowest robot number" if self.leader_seed is None
                              else "most orders known, ties: sorted(tied)[seed % len(tied)]")

    # ------------------------------------------------------------------ prompt sentences and notes
    def _example_assign(self):
        member = next(r for r in self.robots if r != self.leader)
        return member, COLOURS[0], self.zones[0]

    def _free_org_sentence(self, rid):
        """The organization sentence of a free T2 prompt (replaces the --leader-authority sentences, which speak of message facts)."""
        index = self.robots.index(self.leader) + 1
        sentence = "Agent %d is the leader to coordinate the task." % index
        if self.leader_authority or self.leader_bind:
            if rid == self.leader:
                sentence += " " + FREE_AUTHORITY_LEADER % self._example_assign()
                if self.leader_bind:
                    sentence += BIND_LEADER % round(self.hold_s)
                    if self.multi_carry:
                        sentence += (" Give one assign line per carry in trip order. Several lines for the same robot form its queue. "
                                     "New lines append to the queue, so only send a job once.")
            else:
                sentence += " " + FREE_AUTHORITY_MEMBER
                if self.leader_bind:
                    sentence += BIND_MEMBER % round(self.hold_s)
                    if self.multi_carry:
                        sentence += " Carry out the assign lines for you in order. Go back while you have an outstanding assignment."
        if self.leader_route == "star":
            leader_note = STAR_LEADER.replace("your own carry is", "all your own carries are") if self.multi_carry else STAR_LEADER
            sentence += leader_note if rid == self.leader else STAR_MEMBER_DOWN % self.leader if self._member_down(rid) else STAR_MEMBER % self.leader
        return sentence

    # ------------------------------------------------------------------ star route (--leader-route star)
    def _star_member(self, rid):
        return self.leader_route == "star" and rid != self.leader

    def _leader_down(self, now_s):
        """Star route: the leader has halted (call cap, fault) or failed (--fail-robot): it cannot read or answer any more. The first time it is seen is recorded."""
        if self.leader_route != "star":
            return False
        reason = self._halts.get(self.leader) or ("robot_failed" if self._failed(self.leader, now_s) else None) or \
            ("Robot call cap reached" if self._calls_for(self.leader) >= self.max_calls else None)
        if reason and self._leader_down_info is None:
            self._leader_down_info = dict(reason=reason, first_seen_s=float(now_s), leader=self.leader)
        return bool(reason)

    def _member_down(self, rid):
        """A star member whose leader is down (it is then offered `say to everyone` only)."""
        return self._star_member(rid) and self._leader_down(self._states[rid].get("now", 0.0))

    def _free_rule(self, rid):
        """The sentence about speaking that is added to the goal of a free-talk prompt (a star member may speak to the leader only)."""
        return FREE_RULE_STAR_MEMBER if self._star_member(rid) and not self._member_down(rid) else FREE_RULE

    def _free_final(self, rid):
        """The last line of the two-step answer; the example of a star member names its only addressee, the leader (everyone while the leader is down)."""
        if not self._star_member(rid):
            return FREE_FINAL
        return FREE_FINAL.replace("say to r2:", "say to %s:" % ("everyone" if self._member_down(rid) else self.leader))

    def _free_suffix_extra(self, rid):
        """Bytes the line above is longer than FREE_FINAL (a leader named r10 or longer, `everyone`): the input bound of the prompt leaves room for them."""
        return max(0, len(self._free_final(rid).encode("utf-8")) - len(FREE_FINAL.encode("utf-8"))) if self._star_member(rid) else 0

    def _beside_kw(self, rid):
        """Extra arguments of read_say_beside_action for a star member: it can name any robot although its menu has one entry only; no addressee = the leader
        (everyone while the leader is down)."""
        if not self._star_member(rid):
            return {}
        return dict(roster=[r for r in self.robots if r != rid], default="everyone" if self._member_down(rid) else self.leader)

    def _redirect_to_leader(self, rid, menu, picked):
        """A star member's speech to a robot or to everyone (the menu has no such entry: picked["entry"] is None) goes to the leader instead; picked gets
        redirected_from = the addressee as written ("r3", "everyone", "r3,r4") and target = the leader. A speech without words, or to the member itself or to no robot
        of the team, is left as it is (say_to_nobody)."""
        others = {r for r in self.robots if r != rid}
        if not picked["body"] or not all(part == "everyone" or part in others for part in picked["target"].split(",")):
            return
        target = "everyone" if self._member_down(rid) else self.leader          # the leader is down: the speech goes to everyone (the only entry of the menu)
        picked["entry"] = next(key for key, skill in menu.items() if skill["skill"] == "say" and skill["target"] == target)
        picked["redirected_from"], picked["target"] = picked["target"], target

    def _free_note(self, s):
        """A line before the action list: the chance note while the robot is between decisions, else the robot's own binding state (derived from the
        messages it has read and the clock only)."""
        if s.get("point") == "relay":
            return "Note: " + RELAY_NOTE + "\n"
        if s.get("point") == "moving":
            return "Note: " + CHANCE_FREE + "\n"
        bind = s.get("bind")
        if not bind:
            return ""
        if bind["state"] == "held":
            return "Leader's assignment for me: none yet. Until %.0f s I can only wait or speak.\n" % bind["until"]
        note = "Leader's assignment for me: carry a <%s box> to the <%s zone>. I can only do that (or wait or speak).\n" % (bind["box"], bind["zone"])
        if self.multi_carry:
            queue = self._bind[s["rid"]]["pending"]
            if len(queue) > 1:
                note += "After that, in order: " + ", ".join("%s to %s" % (a["box"], a["zone"]) for a in queue[1:]) + ".\n"
        return note

    # ------------------------------------------------------------------ say entries
    def _say_ok(self, rid, now_s):
        s = self._states[rid]
        if s.get("say_streak", 0) < self.say_streak_max:
            return True
        last, ready = s.get("last_say_t", -math.inf), self._readable(rid)
        if self.leader_route == "star":
            # star route: the leader reads the questions of its members one after the other, so a message that arrived before its own say began but became readable only
            # after it began is new to it (with the arrival time the leader could never answer the second of two questions that reached it together)
            return any(t <= now_s and t > last for t in ready.values())
        return any(t <= now_s and self._messages[i]["deliver_at"] > last for i, t in ready.items())

    def _say_entries(self, rid, now_s):
        """[(menu text, skill)] of the say entries offered to rid now: one per other robot, then everyone; none right after its own say."""
        if not self._say_ok(rid, now_s):
            return []
        if self.leader_route == "star":
            self._ensure_elected(now_s)             # the leader is known before the first entry is built (the election of a free run is ideal: no time)
            if rid != self.leader:
                if self._leader_down(now_s):                  # the leader has halted: its members speak to everyone (the leader is no addressee)
                    rest = [r for r in self.robots if r not in (rid, self.leader)]
                    return [("say to everyone: <text>", {"skill": "say", "target": "everyone", "to": rest})] if rest else []
                return [("say to %s: <text>" % self.leader, {"skill": "say", "target": self.leader, "to": [self.leader]})]      # a member: the leader only
        others = [r for r in self.robots if r != rid]
        entries = [("say to %s: <text>" % r, {"skill": "say", "target": r, "to": [r]}) for r in others]
        entries.append(("say to everyone: <text>", {"skill": "say", "target": "everyone", "to": others}))
        return entries

    def _assign_rows(self, rid, body):
        """The `assign rX: <colour> -> <zone>` lines of a text said by rid as rows {to, box, zone, valid[, reason]}; only the leader of a T2 run with authority or
        binding has any (what _speak attaches to the message)."""
        rows = []
        if self.team == "T2" and rid == self.leader and (self.leader_authority or self.leader_bind):
            roster, colours = set(self.robots), set(COLOURS)
            for to, colour, zone in parse_assign(body):
                reason = ("not a robot of the team" if to not in roster else "the leader itself" if to == rid else
                          "colour is not red or blue" if colour.lower() not in colours else "zone is not one of the team's" if zone not in self._zone_set() else None)
                row = dict(to=to, box=colour.lower(), zone=zone, valid=reason is None)
                if reason:
                    row["reason"] = reason
                rows.append(row)
        return rows

    def _reach_assignments(self, rid, menu, picked):
        """The say entry to use for a speech the model wrote as a body label plus words (its addressee was read from a "to" field or a leading "rX,"). A valid
        assign line reaches only the robot it names when the message is delivered to it, so when the leader's words hold a valid line for a teammate other than the
        addressee the speech goes to everyone (recorded: tgt everyone, say_with_action.widened_from, event say_widened_for_assignments). Otherwise the addressee
        stays. A say option the model chose itself is not touched. Returns (entry, widened_from or None)."""
        skill = menu[picked["entry"]]
        if picked.get("dropped") is None or skill["target"] == "everyone":
            return picked["entry"], None
        named = {row["to"] for row in self._assign_rows(rid, picked["body"]) if row["valid"]}
        if not named - {skill["target"]}:
            return picked["entry"], None
        everyone = next(key for key, sk in menu.items() if sk["skill"] == "say" and sk["target"] == "everyone")
        self._event("say_widened_for_assignments")
        return everyone, skill["target"]

    def _speak(self, rid, now_s, entry, body, chance=False, redirected_from=None):
        """Send one say. Returns the recorded message. The message is delivered t_say + msg_delay_s after the start, readable after the receiver's queue."""
        if len(body) > SAY_MAX_CHARS:
            body = body[:SAY_MAX_CHARS]
            self._event("say_cut_at_%d_chars" % SAY_MAX_CHARS)
        assigns = self._assign_rows(rid, body)
        facts = [{"table": "assignments", "id": row["to"], "value": {"box": row["box"], "zone": row["zone"]}} for row in assigns if row["valid"]]
        chars = len(body)
        t_say = say_time(chars, self.say_fix_s, self.say_per_char_s)
        message = self._post(rid, now_s, _json({"message": body, "facts": facts}), via="chance" if chance else "say", to=entry["to"], lag=t_say)
        message.update(chars=chars, say_s=round(t_say, 4), read_s=round(read_time(chars, self.read_fix_s, self.read_per_char_s), 4), tgt=entry["target"])
        if self.leader_route == "star" and rid != self.leader and self._leader_down(now_s):
            message["leader_down"] = True        # the leader has halted: a member's speech goes to everyone (counted)
            self._event("leader_down_fallback")
        if redirected_from:                      # star route: the member addressed someone else; the words went to the leader only (to everyone while the leader is down)
            message["redirected_from"] = redirected_from
            self._event("member_redirected_to_leader" if entry["target"] == self.leader else "member_redirected_to_everyone")
        if assigns:
            message["assign"] = assigns
            for row in assigns:
                self._assign_log.append(dict(time=float(now_s), message=len(self._messages) - 1, **row))
        self._busy_until[rid] = float(now_s) + t_say
        s = self._states[rid]
        s["say_streak"], s["last_say_t"] = s.get("say_streak", 0) + 1, float(now_s)
        s["actions"].append("say to %s" % entry["target"])
        return message

    def _zone_set(self):
        return set(self.zones) | self._seen_zones

    # ------------------------------------------------------------------ leader binding
    def _assignment(self, rid, now_s):
        """One-carry uses the first line of the latest readable assignment message. Multi-carry uses every addressed line in order."""
        rows = []
        for i, t in self._readable(rid).items():
            m = self._messages[i]
            if t > now_s or m["from"] != self.leader:
                continue
            for a in m.get("assign", ()):
                if a["valid"] and a["to"] == rid:
                    rows.append(dict(box=a["box"], zone=a["zone"], readable_at=t, deliver_at=m["deliver_at"], message=i))
        if not self.multi_carry:
            return max(rows, key=lambda a: (a["readable_at"], a["message"]), default=None)
        b = self._bind.get(rid, {})
        b["pending"] = rows[len(b.setdefault("fulfilled", [])):]
        return b["pending"][0] if b["pending"] else None

    def _binding_progress(self, rid, facts):
        """Only the robot's own completed release can fulfill the head. A speech, put-down, lost grasp or repeated report cannot."""
        if facts.get("milestone") == "trip_started":
            self._grasp_failed.discard(rid)
        if facts.get("milestone") != "carry_finished" or facts.get("outcome") != "at_zone":
            return
        b = self._bind.get(rid)
        if not b or not b.get("pending"):
            return
        trip, head = facts.get("trip"), b["pending"][0]
        if (not isinstance(trip, int) or trip <= 0 or (b["fulfilled"] and b["fulfilled"][-1]["trip"] >= trip)
                or (facts.get("box"), facts.get("zone")) != (head["box"], head["zone"])):
            return
        b["fulfilled"].append(dict(trip=trip, **b["pending"].pop(0)))
        b["assignment"] = {k: b["pending"][0][k] for k in ("box", "zone")} if b["pending"] else None

    def _bind_view(self, rid, now_s, point, options, wait_key="wait"):
        """(options the robot may choose from, binding state or None). Only members of a --leader-bind run are touched, only at pick and destination."""
        if not self.leader_bind or rid == self.leader:
            return options, None
        b = self._bind.setdefault(rid, dict(first_arrival_s=None, first_readable_s=None, released=None, decisions=0, bound_decisions=0, held_decisions=0,
                                            infeasible=0, assignment=None))
        if point == "pick":
            self._first_pick.setdefault(rid, float(now_s))
        asg = self._assignment(rid, now_s)
        if asg is not None:
            if b["first_arrival_s"] is None:
                b["first_arrival_s"], b["first_readable_s"] = asg["deliver_at"], asg["readable_at"]
            b["assignment"] = dict(box=asg["box"], zone=asg["zone"])
        if self.multi_carry and point == "next" and asg is not None:
            # Speech entries are appended later. Outstanding work cannot be ended with a body finish.
            b["decisions"] += 1
            b["bound_decisions"] += 1
            return [o for o in options if o["key"] in ("back", "wait")], dict(state="bound", box=asg["box"], zone=asg["zone"])
        if point not in ("pick", "destination"):
            return options, None
        b["decisions"] += 1
        if rid in self._grasp_failed:
            b["released"] = b["released"] or "grasp_failed"
            return options, None
        if asg is None:
            if point == "pick" and rid in self._first_pick and not b.get("fulfilled"):
                end = self._first_pick[rid] + self.hold_s
                if now_s < end:
                    self._wake_at[rid] = end
                    b["held_decisions"] += 1
                    return [o for o in options if o["key"] == wait_key], dict(state="held", until=end)
                b["released"] = b["released"] or "timeout"
            return options, None
        if point == "pick":
            keep = [o for o in options if o["key"] not in ("finish", "none") and (not o["key"].startswith("box:") or
                                                                              re.search(r"<%s box>" % re.escape(asg["box"]), o["text"]))]
            ok = any(o["key"].startswith("box:") for o in keep)
        else:
            keep = [o for o in options if o["key"] not in ("put_down", "none") and (not o["key"].startswith("zone:") or o["key"] == "zone:" + asg["zone"])]
            ok = any(o["key"] == "zone:" + asg["zone"] for o in keep)
        if not ok:
            b["infeasible"] += 1
            b["released"] = b["released"] or "infeasible"
            return options, None
        b["bound_decisions"] += 1
        return keep, dict(state="bound", box=asg["box"], zone=asg["zone"])

    # ------------------------------------------------------------------ decisions
    def _decide_free(self, rid, now_s, point, options, wait):
        """decide() of a free-talk run (T1 / T2). The bookkeeping mirrors decide()."""
        s = self._states[rid]
        before = self._calls_for(rid)
        result = dict(option=wait["key"], wait_s=0.0 if point == "report" else 2.0, sent=[], calls=0)
        self._wake_at.pop(rid, None)
        self._ensure_elected(now_s)
        if self.leader_route == "star" and rid == self.leader:
            result["relay"] = True                  # tells the runner to keep this robot in the conversation after its own run is over (see the module text)
        self._seen_zones |= {o["key"][5:] for o in options if o["key"].startswith("zone:")}
        self._receive(s, rid, now_s)
        try:
            if self._halts[rid]:
                raise CallLimitError(self._halts[rid])
            if self._failed(rid, now_s):
                raise CallLimitError("robot_failed")
            if self._calls_for(rid) >= self.max_calls:
                raise CallLimitError("Robot call cap reached")
            if isinstance(self.client, RealLLM):
                self.client.spend_guard = check_spend_guard()
            shown, bind = self._bind_view(rid, now_s, point, options, wait["key"])
            s["bind"] = bind
            menu = {o["text"]: {"skill": "executor", "key": o["key"]} for o in shown}
            for text, skill in self._say_entries(rid, now_s):
                menu[text] = skill
            kind, picked = self._planner._choose_free(s, menu)
            if bind:
                result["bind"] = dict(bind)
            if kind == "say" and picked["entry"] is None and self._star_member(rid):
                self._redirect_to_leader(rid, menu, picked)
            if kind == "say" and picked["entry"] is not None and picked["body"]:
                entry, widened = self._reach_assignments(rid, menu, picked)
                message = self._speak(rid, now_s, menu[entry], picked["body"], redirected_from=picked.get("redirected_from"))
                result.update(option="wait" if point == "next" else wait["key"], wait_s=message["say_s"], say_s=message["say_s"], sent=[copy.deepcopy(message)])
                if picked.get("dropped") is not None:
                    self._event("say_with_action")                      # the answer was a body option plus words: the words are the decision, the body option is not done
                    result["say_with_action"] = dict(copy.deepcopy(picked["dropped"]), **({"widened_from": widened} if widened else {}))
            elif kind == "say":
                # the answer chose a say entry without words (or a target that is not there): read as wait, counted
                self._event("say_without_text" if picked["entry"] is not None else "say_to_nobody")
                s["actions"].append(wait["text"])
                s["say_streak"] = 0
                result.update(option="wait" if point == "next" else wait["key"], wait_s=0.0 if point == "report" else 2.0, say_failed=True)
            elif kind == "act":
                s["actions"].append(picked)
                s["say_streak"] = 0
                chosen = menu[picked]
                result.update(option=chosen["key"], wait_s=2.0 if point not in ("report", "next") and chosen["key"] == wait["key"] else 0.0)
        except CallLimitError as error:
            self._halts[rid] = str(error)
            result.update(halted=True, reason=self._halts[rid])
        except Exception as error:
            self._halts[rid] = type(error).__name__
            result.update(halted=True, reason=self._halts[rid])
        s["asked_at"] = float(now_s)
        result["calls"] = self._calls_for(rid) - before
        self._decisions[rid].append(dict(time=float(now_s), point=point, options=options, **copy.deepcopy(result)))
        self._write_record()
        return result

    def _chance_free(self, rid, now_s):
        """chance() of a free-talk run: a message has reached the robot and no decision is open; it may answer (a say entry) or stay silent. One model
        call, no cap (there is no budget); only a halted or failed robot gets no further chance."""
        result = dict(sent=[], calls=0, asked=False, final=False)
        if self._failed(rid, now_s) or self._halts[rid]:
            result["final"] = True
            return result
        if not math.isfinite(now_s) or now_s < self._now:
            raise ValueError("Decisions must use nondecreasing simulation time")
        s = self._states[rid]
        entries = self._say_entries(rid, now_s)
        if not entries:
            return result                       # it has just spoken and nothing new has reached it
        self._now = float(now_s)
        s.update(now=float(now_s), point="moving")
        self._ensure_elected(now_s)
        before = self._calls_for(rid)
        self._receive(s, rid, now_s)
        s["bind"] = None
        try:
            if self._calls_for(rid) >= self.max_calls:
                raise CallLimitError("Robot call cap reached")
            if isinstance(self.client, RealLLM):
                self.client.spend_guard = check_spend_guard()
            result["asked"] = True
            menu = {SILENT_TEXT: {"skill": "executor", "key": "silent"}}      # first: the body entries keep the first labels (see _choose_free)
            menu.update(entries)
            kind, picked = self._planner._choose_free(s, menu)
            if kind == "say" and picked["entry"] is None and self._star_member(rid):
                self._redirect_to_leader(rid, menu, picked)
            if kind == "say" and picked["entry"] is not None and picked["body"]:
                entry, widened = self._reach_assignments(rid, menu, picked)
                message = self._speak(rid, now_s, menu[entry], picked["body"], chance=True, redirected_from=picked.get("redirected_from"))
                result.update(sent=[copy.deepcopy(message)], wait_s=message["say_s"], say_s=message["say_s"])
                if picked.get("dropped") is not None:
                    self._event("say_with_action")
                    result["say_with_action"] = dict(copy.deepcopy(picked["dropped"]), **({"widened_from": widened} if widened else {}))
            elif kind == "say":
                self._event("say_without_text" if picked["entry"] is not None else "say_to_nobody")
        except CallLimitError as error:
            result.update(final=True, reason=str(error))
        except Exception as error:
            result.update(final=True, reason=type(error).__name__)
        s["asked_at"] = float(now_s)
        result["calls"] = self._calls_for(rid) - before
        if result["asked"] or result.get("reason"):
            self._chances[rid].append(dict(time=float(now_s), **copy.deepcopy(result)))
            self._write_record()
        return result

    # ------------------------------------------------------------------ record
    def _talk_conditions(self):
        out = dict(talk=dict(mode="free", say_fix_s=self.say_fix_s, say_per_char_s=self.say_per_char_s, read_fix_s=self.read_fix_s,
                             read_per_char_s=self.read_per_char_s, say_streak_max=self.say_streak_max))
        if self.leader_bind:
            out["leader_bind"] = dict(hold_s=self.hold_s)
        if self.leader_seed is not None:
            out["leader_seed"] = self.leader_seed
        if self.leader_route:
            out["leader_route"] = self.leader_route
        return out

    def _talk_record(self):
        """Fields of the record's `talking` entry for a free run: what was said, the election and the binding manipulation check."""
        says = [m for m in self._messages if "say_s" in m]
        out = dict(talk=dict(says=len(says), says_by_robot={r: sum(1 for m in says if m["from"] == r) for r in self.robots},
                             directed=sum(1 for m in says if m["tgt"] != "everyone"), to_everyone=sum(1 for m in says if m["tgt"] == "everyone"),
                             chars=sum(m["chars"] for m in says), say_s=round(sum(m["say_s"] for m in says), 4),
                             read_s=round(sum(m["read_s"] * len(m["to"]) for m in says), 4), events=dict(self._talk_events)))
        if self._election is not None:
            out["election"] = copy.deepcopy(self._election)
        if self.leader_route:
            out["star"] = self._star_record(says)
        if self.leader_bind:
            valid = [a for a in self._assign_log if a["valid"]]
            members = {r: copy.deepcopy(self._bind[r]) for r in self.robots if r in self._bind}
            out["binding"] = dict(
                leader=self.leader, hold_s=self.hold_s, assign_lines=len(self._assign_log), assign_valid=len(valid),
                assign_invalid=len(self._assign_log) - len(valid), valid_rate=(len(valid) / len(self._assign_log)) if self._assign_log else None,
                assignments=copy.deepcopy(self._assign_log), members=members,
                members_assigned=sum(1 for b in members.values() if b["first_arrival_s"] is not None),
                unlocked_by_timeout=sum(1 for b in members.values() if b["released"] == "timeout"),
                unlocked_by_grasp_failed=sum(1 for b in members.values() if b["released"] == "grasp_failed"),
                unlocked_infeasible=sum(1 for b in members.values() if b["released"] == "infeasible"))
        return out

    def _star_record(self, says):
        """Record of a star-route run: who spoke to whom (every addressee of a say counts once; `to` + `lost` = the robots the speaker meant), how often a member's
        words were redirected to the leader, and the load on the leader (the bottleneck: messages and characters it receives and sends)."""
        leader, robots = self.leader, self.robots
        meant = lambda m: list(m["to"]) + list(m.get("lost", []))
        members = [m for m in says if m["from"] != leader]
        inbound = [m for m in says if m["from"] != leader and leader in meant(m)]
        outbound = [m for m in says if m["from"] == leader]
        redirected = [m for m in says if "redirected_from" in m]
        return dict(
            leader=leader,
            says_by_recipient={r: {x: sum(1 for m in says if m["from"] == r and x in meant(m)) for x in robots if x != r} for r in robots},
            says_by_target={r: {tgt: sum(1 for m in says if m["from"] == r and m["tgt"] == tgt) for tgt in sorted({m["tgt"] for m in says if m["from"] == r})} for r in robots},
            received_by_robot={r: sum(1 for m in says if r in meant(m) and m["from"] != r) for r in robots},
            member_messages=len(members), member_chars=sum(m["chars"] for m in members),
            member_messages_to_non_leader=sum(1 for m in members if not m.get("leader_down") and any(x != leader for x in meant(m))),
            redirected=len(redirected), redirected_by_robot={r: sum(1 for m in redirected if m["from"] == r) for r in robots if r != leader},
            redirected_by_addressee={a: sum(1 for m in redirected if m["redirected_from"] == a) for a in sorted({m["redirected_from"] for m in redirected})},
            leader_down=copy.deepcopy(self._leader_down_info) if self._leader_down_info else (
                dict(reason=self._halts[leader], first_seen_s=None, leader=leader) if self._halts.get(leader) else None),
            leader_down_fallback=sum(1 for m in members if m.get("leader_down")),
            relay_decisions=sum(1 for d in self._decisions[leader] if d["point"] == "relay"),
            leader_inbound=dict(messages=len(inbound), chars=sum(m["chars"] for m in inbound), read_s=round(sum(m["read_s"] for m in inbound), 4),
                                by_sender={r: sum(1 for m in inbound if m["from"] == r) for r in robots if r != leader}),
            leader_outbound=dict(messages=len(outbound), chars=sum(m["chars"] for m in outbound), say_s=round(sum(m["say_s"] for m in outbound), 4),
                                 deliveries=sum(len(meant(m)) for m in outbound), directed=sum(1 for m in outbound if m["tgt"] != "everyone"),
                                 to_everyone=sum(1 for m in outbound if m["tgt"] == "everyone")))
