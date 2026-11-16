"""Serve one TeamBrain for one physical run over localhost HTTP (the simulator host reaches it through a forwarded port).

The model key stays on this host. One process = one run. Written by the main session (not part of the brain module).
"""
import argparse, json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brain import TeamBrain
from brain.llm import HARD_EPISODE_CALLS, RealLLM

GOAL = ("Transport each box to the zone named in its order. Orders were given to the robots separately, so a robot "
        "may not know every order. In this task each robot makes one carry: it carries one box, and once that box is set down its run ends. Only one robot at a time fits through the "
        "door between the box room and the zone room. "
        "Orders are for the whole team; a count is the team total, not per robot. "
        "Moving a box that no order asks for counts as an error. Other robots may hold orders you do not know, so do not stop "
        "just because you cannot do your own order: use what you know and see to make your best guess about which box "
        "and zone help the team. Finish only if no box you can grasp could plausibly be wanted.")


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
                   help='cap PER ROBOT; the run total is capped by the hard episode limit (300) in brain/llm.py')
    p.add_argument('--leader', choices=('r1', 'r2', 'r3'), default='r1', help='T2 leader (ignored by T0/T1)')
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
    a = p.parse_args(argv)
    if a.pre_exchange and a.team not in ('T1', 'T2'):
        p.error('--pre-exchange needs --team T1 or T2 (T0 robots cannot send messages)')
    if a.leader not in a.robots.split(','):
        p.error('--leader %s is not in --robots %s' % (a.leader, a.robots))
    return a


def main():
    a = parse_args()
    a.log_dir.mkdir(parents=True, exist_ok=False)
    root = Path(os.environ.get('UGRP_BRAIN_EVIDENCE_DIR', 'outputs/team-brain'))
    robots = a.robots.split(',')
    ceiling = run_ceiling(a.max_calls, len(robots))
    if ceiling < a.max_calls * len(robots):
        print('note: run ceiling %d is below %d x %d robots (hard episode cap)' % (ceiling, a.max_calls, len(robots)),
              file=sys.stderr, flush=True)
    client = RealLLM(ceiling, a.log_dir / 'llm-calls.jsonl', model=a.model, max_output_tokens=2048,
                     temperature=a.temperature, campaign_log_path=a.log_dir / 'run-campaign-calls.jsonl', campaign_max_calls=ceiling, budget_usd=1.0)
    # one ledger per run: two runs sharing one ledger blocked each other (2026-11-15 01:03); the guard file still caps the total
    brain = TeamBrain(a.team, robots, GOAL, client=client, log_dir=a.log_dir, leader=a.leader,
                      option_order=a.option_order, pre_exchange=a.pre_exchange)
    brain.max_calls = a.max_calls
    seen = {r: 0 for r in brain.robots}            # messages the robot has read at its last decision or chance (re-decision / waiting poll)
    seen_chance = {r: 0 for r in brain.robots}     # the same, not counting replies written at a chance (the poll that opens a chance)

    def delivered(rid, now, decisions_only=False):
        """Messages delivered to rid by `now`. decisions_only: not the replies written at a message chance (via='chance')."""
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
                if body.get('chance'):
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
