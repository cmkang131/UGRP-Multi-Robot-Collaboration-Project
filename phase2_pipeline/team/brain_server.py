"""Serve one TeamBrain for one physical run over localhost HTTP (the simulator host reaches it through a forwarded port).

The model key stays on this host. One process = one run. Written by the main session (not part of the brain module).
"""
import argparse, json, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brain import MAX_MESSAGES, RULES_GOAL, TeamBrain
from brain.llm import HARD_EPISODE_CALLS, RealLLM
from brain.protocol import ZONES
from brain.talk import HOLD_S, READ_FIX_S, READ_PER_CHAR_S, SAY_FIX_S, SAY_PER_CHAR_S, SAY_STREAK_MAX

GOAL = ("Transport each box to the zone named in its order. Orders were given to the robots separately, so a robot "
        "may not know every order. In this task each robot makes one carry: it carries one box, and once that box is set down its run ends. Only one robot at a time fits through the "
        "door between the box room and the zone room. "
        "Orders are for the whole team; a count is the team total, not per robot. "
        "Moving a box that no order asks for counts as an error. Other robots may hold orders you do not know, so do not stop "
        "just because you cannot do your own order: use what you know and see to make your best guess about which box "
        "and zone help the team. Finish only if no box you can grasp could plausibly be wanted.")


# --idle-option (default off, GOAL above is then unchanged): the last sentences of the goal say that doing nothing is a good choice when the
# robot cannot tell which box and zone help; the pick menu's finish entry is reworded by TeamBrain(idle_option=True).
GOAL_TAIL = ("Moving a box that no order asks for counts as an error. Other robots may hold orders you do not know, so do not stop "
             "just because you cannot do your own order: use what you know and see to make your best guess about which box "
             "and zone help the team. Finish only if no box you can grasp could plausibly be wanted.")
GOAL_IDLE_TAIL = ("Moving a box that no order asks for counts as an error, and a wrongly placed box cancels a correctly placed one. "
                  "Other robots may hold orders you do not know: use what you know and what your friends have told you to judge "
                  "which box and zone help the team. If you cannot tell which box and zone would help, choose the do-nothing action "
                  "(finish): a robot that stays still never causes an error.")
assert GOAL.count(GOAL_TAIL) == 1
GOAL_IDLE = GOAL.replace(GOAL_TAIL, GOAL_IDLE_TAIL)
ONE_CARRY = "In this task each robot makes one carry: it carries one box, and once that box is set down its run ends."
MULTI_CARRY = ("A robot carries one box at a time. After setting it down, choose whether to return for another box or finish. "
               "Use the orders, completed deliveries and messages you know when choosing your next box and zone.")
assert GOAL.count(ONE_CARRY) == 1

# --map-doors (default off, GOAL and GOAL_IDLE above are then unchanged): a generated map scene (maps branch) has several doors, and the bridge keeps one queue per
# door for the reference plan; the planner is told the same thing, so it does not wait for a robot that uses another door (the wording of the maps branch,
# a work record).
DOOR_SENTENCE = "Only one robot at a time fits through the door between the box room and the zone room. "
DOORS_SENTENCE = ("Only one robot at a time fits through a door. There are several doors and each robot carries through the door nearest to it, "
                  "so robots that use different doors do not hold each other up. ")


def with_several_doors(goal):
    if goal.count(DOOR_SENTENCE) != 1:
        raise ValueError('the door sentence is not in the goal text exactly once')
    return goal.replace(DOOR_SENTENCE, DOORS_SENTENCE)


def run_ceiling(per_robot, n_robots):
    """Paid-call ceiling of the whole run: the per-robot cap times the roster, never above the hard episode cap."""
    return min(HARD_EPISODE_CALLS, per_robot * n_robots)


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--team', required=True)
    p.add_argument('--robots', default='r1,r2')
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--log-dir', type=Path, required=True)
    p.add_argument('--max-calls', type=int, default=150,
                   help='cap PER ROBOT; the run total is capped by the hard episode limit (600) in brain/llm.py')
    p.add_argument('--leader', choices=tuple('r%d' % i for i in range(1, 17)), default='r1', help='T2 leader (ignored by T0/T1; r1..r16)')
    p.add_argument('--model', default='z-ai/glm-5.3-flash', help='planner model id (second-model runs use another id)')
    p.add_argument('--option-order', choices=('forward', 'reverse'), default='forward',
                   help='experiment condition: order in which every action list is shown to the model (reverse = the whole '
                        'list reversed, letters follow the shown order); default forward = unchanged')
    p.add_argument('--temperature', type=float, default=0.7,
                   help='sampling temperature, same for every structure (frozen 0.7, Fable review 2026-11-15 D1: at 0.0 the '
                        'same prompt gave the same choice in 18/18 groups, so repeats measured no planner variation)')
    p.add_argument('--pre-exchange', action='store_true',
                   help='experiment condition (T1/T2 only): every robot writes one message before its first pick decision and '
                        'waits until the messages already sent to it have arrived; default off')
    p.add_argument('--max-messages', type=int, default=None,
                   help='experiment condition (T1/T2 only): message cap of every robot (default %d, the main experiment; the prompt and the '
                        'record show it)' % MAX_MESSAGES)
    p.add_argument('--leader-max-messages', type=int, default=None,
                   help='experiment condition (T2 only): message cap of the leader alone (the others keep --max-messages); default = same cap')
    p.add_argument('--robot-max-messages', default=None, metavar='rid=cap[,rid=cap]',
                   help='experiment condition (T1/T2 only): message cap of single robots, e.g. r2=4,r3=6 (the others keep --max-messages)')
    p.add_argument('--leader-authority', action='store_true',
                   help='experiment condition (T2 only): the leader assigns which robot takes which box to which zone and the members follow it '
                        '(two sentences in the organization line of every prompt; no new information is given); default off')
    p.add_argument('--idle-option', action='store_true',
                   help='experiment condition: the do-nothing action (finish) is worded as a good choice when the robot cannot tell what helps '
                        '(goal tail sentence and the pick menu text of the finish entry); default off')
    p.add_argument('--protocol', choices=('peer-roco', 'hub-hmas2'), default=None,
                   help='experiment condition: the team talks like the prior work (T1 peer-roco: RoCo / Chen DMAS dialog; T2 hub-hmas2: Chen HMAS-2 '
                        'leader proposes, members review). No message budget. Default off = the main experiment\'s messages')
    p.add_argument('--hub-rounds', type=int, default=3, help='hub-hmas2: review rounds before the latest plan runs (Chen code 3; 0 = CMAS, no review)')
    p.add_argument('--peer-max-calls', type=int, default=10, help='peer-roco: dialogue calls per round (RoCo code 10)')
    p.add_argument('--leader-election', action='store_true',
                   help='T2: the leader is the robot that knows the most orders (every robot is assumed to have announced its count at the start; '
                        'ties: lowest robot number) instead of --leader')
    p.add_argument('--msg-delay-s', type=float, default=2.0, help='delivery delay of every message in simulated seconds (main experiment 2.0)')
    p.add_argument('--msg-loss', type=float, default=0.0, help='probability that one recipient does not get a message (seeded per message and recipient)')
    p.add_argument('--msg-seed', type=int, default=0, help='seed of the message loss draws')
    p.add_argument('--fail-robot', default=None, help='robot that fails (halted: no decisions, no messages sent or heard) from --fail-at-s')
    p.add_argument('--fail-at-s', type=float, default=None, help='simulated time of the failure')
    p.add_argument('--parser-fix', action='store_true', help='answers {"action":..} followed by text are read; an unreadable answer is asked again once before the random fallback')
    p.add_argument('--merge-calls', action='store_true', help='reasoning and choice in one model call')
    p.add_argument('--options-v2', action='store_true', help='wait is worded as stand-by (asked again later) and finish as ending the run')
    p.add_argument('--route-note', action='store_true', help='T2: the prompts say who hears whose messages')
    # ---- phase 2 of the leader study (PREREG-PHASE2.md): free talk, the leader's binding assignment, the election seed, N robots, the rule sentence. All default off.
    p.add_argument('--multi-carry', action='store_true', help="allow another trip after release; use --multi-carry on the runner too")
    p.add_argument('--talk', choices=('free',), default=None,
                   help='T1/T2: a say ("say to rX: <text>" / "say to everyone: <text>") is one entry of every action list; it takes the place of the body action, costs '
                        'simulated time (--say-*) and the receiver reads it after a reading time (--read-*); no message budget; no protocol. Default off = the main experiment\'s messages')
    p.add_argument('--no-message-budget', action='store_true', help='with --talk free: there is no message budget (free talk never has one; the flag makes the manifest say so)')
    p.add_argument('--say-fix-s', type=float, default=SAY_FIX_S, help='--talk free: fixed part of the time a robot stands while it speaks (default %g s)' % SAY_FIX_S)
    p.add_argument('--say-per-char-s', type=float, default=SAY_PER_CHAR_S, help='--talk free: seconds per character spoken (default %g)' % SAY_PER_CHAR_S)
    p.add_argument('--read-fix-s', type=float, default=READ_FIX_S, help='--talk free: fixed part of the time a receiver needs to read one message (default %g s)' % READ_FIX_S)
    p.add_argument('--read-per-char-s', type=float, default=READ_PER_CHAR_S, help='--talk free: seconds per character read (default %g)' % READ_PER_CHAR_S)
    p.add_argument('--say-streak', type=int, default=SAY_STREAK_MAX,
                   help='--talk free: consecutive says without a new message in between (default %d: no second say in a row, CoELA LLM.py:496)' % SAY_STREAK_MAX)
    p.add_argument('--leader-binding', '--leader-bind', dest='leader_bind', action='store_true',
                   help='T2 with --talk free: the leader\'s line "assign rX: <colour> -> <zone>" binds that member (its pick and destination lists hold only that); a member '
                        'without an assignment may only wait or speak for --hold-s. With --multi-carry, repeat a member\'s line for each trip, in order. Default off')
    p.add_argument('--leader-route', choices=('star',), default=None,
                   help='T2 with --talk free: ALL communication goes through the leader. A member can only say to the leader (no teammate, no everyone); words it addresses to another '
                        'member or to everyone are delivered to the leader only and counted (member_redirected_to_leader); the leader may say to any one robot or to everyone. '
                        'The prompts state the rule. Default off = members talk to anyone (PREREG-PHASE2.md 8)')
    p.add_argument('--hold-s', type=float, default=None, help='--leader-binding: seconds after its first pick decision that a member without an assignment may only wait or speak (default %g)' % HOLD_S)
    p.add_argument('--leader-seed', type=int, default=None,
                   help='with --leader-election: a tie of the election goes to sorted(tied)[seed %% len(tied)] (the manifest gives crc32("elect|scene|rep") %% 2^31) instead of the lowest number')
    p.add_argument('--zones', default=None, metavar='sign11,sign12,...',
                   help='the zone names of the scene (assignment check, plan examples); default: --scene-file\'s scene, else sign11..sign13 (sign11..sign(10+N) for N > 3)')
    p.add_argument('--scene-file', type=Path, default=None,
                   help='the scene file the runner uses (the planner reads only the scene\'s `constraints`, `orders` and `arena.signs`); with --scene-id. A scene with a rule tells it to '
                        'its `known_by` robots and adds one sentence to the goal; a scene without one changes nothing. The file is read when the server starts, not by --help or parsing')
    p.add_argument('--scene-id', default=None, help='scene of --scene-file')
    p.add_argument('--max-input-bytes', type=int, default=None,
                   help='the planner\'s mandatory-context bound in bytes (default 12000 = the main experiment; a larger team needs more, e.g. 24000; the client\'s own bound is 71024)')
    p.add_argument('--map-doors', action='store_true',
                   help='the scene has several doors (maps branch; one robot at a time fits through each): the goal says so (the bridge gets a generated map scene). Default off = unchanged')
    p.add_argument('--leader-policy', default=None,
                   help='label only (recorded in brain-record conditions): how the manifest chose the leader, e.g. most / least / seat; '
                        'changes no behaviour')
    a = p.parse_args(argv)
    a.robot_caps = None
    if a.robot_max_messages is not None:
        try:
            a.robot_caps = {k: int(v) for k, v in (x.split('=') for x in a.robot_max_messages.split(','))}
        except ValueError:
            p.error('--robot-max-messages must look like r2=4,r3=6')
        unknown = sorted(set(a.robot_caps) - set(a.robots.split(',')))
        if unknown:
            p.error('--robot-max-messages names robots that are not in --robots: %s' % unknown)
    for flag, value in (('--max-messages', a.max_messages), ('--leader-max-messages', a.leader_max_messages),
                        ('--robot-max-messages', a.robot_max_messages)):
        if value is not None and a.team not in ('T1', 'T2'):
            p.error('%s needs --team T1 or T2 (T0 robots cannot send messages)' % flag)
    if a.protocol and (a.max_messages is not None or a.leader_max_messages is not None or a.robot_max_messages is not None):
        p.error('--protocol has no message budget')
    if a.protocol and (a.team, a.protocol) not in (('T1', 'peer-roco'), ('T2', 'hub-hmas2')):
        p.error('--protocol peer-roco goes with --team T1 and hub-hmas2 with --team T2')
    if (a.leader_election or a.route_note) and a.team != 'T2':
        p.error('--leader-election and --route-note need --team T2')
    if (a.fail_robot is None) != (a.fail_at_s is None):
        p.error('--fail-robot and --fail-at-s go together')
    if a.fail_robot is not None and a.fail_robot not in a.robots.split(','):
        p.error('--fail-robot %s is not in --robots %s' % (a.fail_robot, a.robots))
    if (a.msg_loss or a.msg_delay_s != 2.0) and a.team not in ('T1', 'T2'):
        p.error('--msg-loss and --msg-delay-s need --team T1 or T2')
    if a.leader_authority and a.team != 'T2':
        p.error('--leader-authority needs --team T2 (only T2 has a leader)')
    if a.leader_max_messages is not None and a.team != 'T2':
        p.error('--leader-max-messages needs --team T2 (only T2 has a leader)')
    if a.leader_max_messages is not None and a.robot_caps and a.leader in a.robot_caps:
        p.error('--leader-max-messages and --robot-max-messages both set the cap of the leader %s' % a.leader)
    if a.pre_exchange and a.team not in ('T1', 'T2'):
        p.error('--pre-exchange needs --team T1 or T2 (T0 robots cannot send messages)')
    if a.leader not in a.robots.split(','):
        p.error('--leader %s is not in --robots %s' % (a.leader, a.robots))
    free_only = [f for f, v in (('--no-message-budget', a.no_message_budget), ('--say-fix-s', a.say_fix_s != SAY_FIX_S), ('--say-per-char-s', a.say_per_char_s != SAY_PER_CHAR_S),
                                ('--read-fix-s', a.read_fix_s != READ_FIX_S), ('--read-per-char-s', a.read_per_char_s != READ_PER_CHAR_S),
                                ('--say-streak', a.say_streak != SAY_STREAK_MAX), ('--leader-binding', a.leader_bind), ('--leader-route', a.leader_route is not None)) if v]
    if a.talk is None and free_only:
        p.error('%s need --talk free' % ', '.join(free_only))
    if a.talk == 'free':
        if a.team not in ('T1', 'T2'):
            p.error('--talk free needs --team T1 or T2 (T0 robots cannot send messages)')
        for flag, value in (('--protocol', a.protocol), ('--pre-exchange', a.pre_exchange), ('--route-note', a.route_note), ('--max-messages', a.max_messages),
                            ('--leader-max-messages', a.leader_max_messages), ('--robot-max-messages', a.robot_max_messages), ('--option-order reverse', a.option_order == 'reverse')):
            if value:
                p.error('--talk free replaces the old message routes and has no message budget: it cannot be combined with %s' % flag)
    if a.leader_bind and a.team != 'T2':
        p.error('--leader-binding needs --team T2 (only T2 has a leader)')
    if a.leader_route is not None and a.team != 'T2':
        p.error('--leader-route needs --team T2 (only T2 has a leader)')
    if a.hold_s is not None and not a.leader_bind:
        p.error('--hold-s needs --leader-binding')
    a.hold_s = HOLD_S if a.hold_s is None else a.hold_s
    if a.hold_s < 0 or min(a.say_fix_s, a.say_per_char_s, a.read_fix_s, a.read_per_char_s) < 0 or a.say_streak < 1:
        p.error('--hold-s, --say-* and --read-* must be >= 0 and --say-streak >= 1')
    if a.leader_seed is not None and not a.leader_election:
        p.error('--leader-seed needs --leader-election (it only breaks the ties of the election)')
    if a.leader_seed is not None and a.leader_seed < 0:
        p.error('--leader-seed must be >= 0')
    if a.max_input_bytes is not None and a.max_input_bytes <= 1024:
        p.error('--max-input-bytes must exceed 1024')
    if (a.scene_file is None) != (a.scene_id is None):
        p.error('--scene-file and --scene-id go together')
    if a.zones is not None:
        names = a.zones.split(',')
        if len(set(names)) != len(names) or not all(re.fullmatch(r'sign\d+', n) for n in names):
            p.error('--zones must look like sign11,sign12,sign13 (distinct names)')
    return a


def load_scene(scene_file, scene_id):
    doc = json.loads(Path(scene_file).read_text())
    scene = next((s for s in (doc['scenes'] if isinstance(doc, dict) else doc) if s['id'] == scene_id), None)
    if scene is None:
        raise ValueError('scene %s not in %s' % (scene_id, scene_file))
    return scene


def rule_text(scene, c):
    """The sentence the rule's robots are told (colour and zone of both orders; identical to precedence/gen_s3.py rule_text)."""
    o = {x['id']: x for x in scene['orders']}
    p, q = c['orders']
    return ("Rule of this task, given to every robot: the <%s box> for the <sign%d zone> must be set down at its zone BEFORE the <%s box> "
            "for the <sign%d zone> is set down at its zone. A box set down earlier than that does not count as delivered."
            % (o[p]['colour'], o[p]['sign'], o[q]['colour'], o[q]['sign']))


def scene_rules(scene_file, scene_id):
    """{robot: rule text} of the scene's `constraints` (type 'order' only; any other type is an error); {} when the scene has none.
    A robot is told every rule whose `known_by` lists it (phase-2 scenes list every robot in every rule: every robot is told every rule), one text
    per rule, in the order of the scene's `constraints`. The value is the bare string when the robot holds one rule (the S3 scenes: unchanged) and a
    list of strings when it holds several (phase-2 N=9 scenes have 3 rules).
    (a work record, the rule sentence part; several rules per scene are new.)"""
    scene = load_scene(scene_file, scene_id)
    held = {}
    for c in scene.get('constraints') or []:
        if c.get('type') != 'order':
            raise ValueError('unknown constraint type %r' % (c.get('type'),))
        text = rule_text(scene, c)
        for rid in dict.fromkeys(c['known_by']):               # a robot named twice in one rule still hears it once
            held.setdefault(rid, []).append(text)
    return {rid: (texts[0] if len(texts) == 1 else texts) for rid, texts in held.items()}


def scene_zones(scene_file, scene_id):
    """The zone names of a scene: the numbers of its arena's wall signs (generated map scenes), else sign11..sign13 plus the signs its orders name."""
    scene = load_scene(scene_file, scene_id)
    signs = (scene.get('arena') or {}).get('signs')
    numbers = sorted({int(s['number']) for s in signs}) if signs else sorted({int(x[4:]) for x in ZONES} | {int(o['sign']) for o in scene['orders']})
    return tuple('sign%d' % n for n in numbers)


def main():
    a = parse_args()
    a.log_dir.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parent / 'evidence'
    robots = a.robots.split(',')
    ceiling = run_ceiling(a.max_calls, len(robots))
    if ceiling < a.max_calls * len(robots):
        print('note: run ceiling %d is below %d x %d robots (hard episode cap)' % (ceiling, a.max_calls, len(robots)),
              file=sys.stderr, flush=True)
    client = RealLLM(ceiling, a.log_dir / 'llm-calls.jsonl', model=a.model, max_output_tokens=2048,
                     temperature=a.temperature, campaign_log_path=a.log_dir / 'run-campaign-calls.jsonl', campaign_max_calls=ceiling, budget_usd=1.0)
    # one ledger per run: two runs sharing one ledger blocked each other (2026-11-15 01:03); the guard file still caps the total
    rules = scene_rules(a.scene_file, a.scene_id) if a.scene_file is not None else {}
    zones = tuple(a.zones.split(',')) if a.zones else (scene_zones(a.scene_file, a.scene_id) if a.scene_file is not None else None)
    goal = GOAL_IDLE if a.idle_option else GOAL
    if a.multi_carry:
        goal = goal.replace(ONE_CARRY, MULTI_CARRY)
    if a.map_doors:
        goal = with_several_doors(goal)
    if rules:
        goal += RULES_GOAL
    brain = TeamBrain(a.team, robots, goal, client=client, log_dir=a.log_dir, leader=a.leader,
                      option_order=a.option_order, pre_exchange=a.pre_exchange, max_messages=a.max_messages,
                      leader_max_messages=a.leader_max_messages, robot_max_messages=a.robot_caps, leader_policy=a.leader_policy,
                      leader_authority=a.leader_authority, idle_option=a.idle_option, protocol=a.protocol, hub_rounds=a.hub_rounds,
                      peer_max_calls=a.peer_max_calls, leader_election=a.leader_election, msg_delay_s=a.msg_delay_s, msg_loss=a.msg_loss,
                      msg_seed=a.msg_seed, fail_robot=a.fail_robot, fail_at_s=a.fail_at_s, parser_fix=a.parser_fix,
                      merge_calls=a.merge_calls, options_v2=a.options_v2, route_note=a.route_note,
                      talk=a.talk, say=(a.say_fix_s, a.say_per_char_s), read=(a.read_fix_s, a.read_per_char_s), say_streak_max=a.say_streak, leader_bind=a.leader_bind,
                      hold_s=a.hold_s, leader_seed=a.leader_seed, zones=zones, max_input_bytes=a.max_input_bytes, order_rules=rules,
                      leader_route=a.leader_route, multi_carry=a.multi_carry)
    brain.max_calls = a.max_calls
    seen = {r: 0 for r in brain.robots}            # messages the robot has read at its last decision or chance (re-decision / waiting poll)
    seen_chance = {r: 0 for r in brain.robots}     # the same, not counting replies written at a chance (the poll that opens a chance)

    def delivered(rid, now, decisions_only=False):
        """Messages delivered to rid by `now`. decisions_only: not the replies written at a message chance (via='chance')."""
        if brain.talk == 'free':
            return brain.readable_count(rid, now, decisions_only)      # a message counts from the time its receiver can read it (the same time its prompt shows it from)
        return sum(1 for m in brain._messages if rid in m['to'] and m['deliver_at'] <= now
                   and not (decisions_only and m.get('via') == 'chance'))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            if self.path == '/tell':
                brain.tell(body['rid'], body['facts']); out = {}
            elif self.path == '/decide':
                out = brain.decide(body['rid'], body['now_s'], body['point'], body['options'])
                seen[body['rid']] = delivered(body['rid'], body['now_s'])
                seen_chance[body['rid']] = delivered(body['rid'], body['now_s'], True)
            elif self.path == '/chance':
                # a reply chance between decisions (offered by the bridge when /poll said a message is new): a chance is a planner
                # contact like a decision, so it moves `seen` too and the same message is answered once. (Before 2026-11-15 'chance on
                # new message' it left `seen` alone and the bridge offered chances every 15 s.) The bridge asks /poll (chance=true) again
                # right after the chance and turns the robot's chances off when it is still new (a host that does not do this).
                out = brain.chance(body['rid'], body['now_s'])
                seen[body['rid']] = delivered(body['rid'], body['now_s'])
                seen_chance[body['rid']] = delivered(body['rid'], body['now_s'], True)
            elif self.path == '/poll':
                held = brain.hold_poll(body['rid'], body['now_s'], bool(body.get('chance')))     # free talk only: None = the usual test below
                if held is not None:
                    out = {'new': held}
                    if body.get('chance'):
                        out['chance'] = True
                elif body.get('chance'):
                    # the bridge asks whether a message written at a teammate's DECISION POINT has reached the robot since its last
                    # planner contact (a decision or a chance): only those open a message chance. A reply written at a chance
                    # (via='chance') does not, so a chain of replies stops after one reply per teammate. The echo tells the bridge the
                    # host knows the flag (an older host answers without it and the bridge turns the robot's chances off).
                    out = {'new': delivered(body['rid'], body['now_s'], True) > seen_chance[body['rid']], 'chance': True}
                else:
                    # the re-decision / waiting poll: every delivered message counts, replies written at a chance too
                    out = {'new': delivered(body['rid'], body['now_s']) > seen[body['rid']]}
            elif self.path == '/record':
                out = brain.record()
            else:
                self.send_error(404); return
            data = json.dumps(out).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

    HTTPServer(('127.0.0.1', a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
