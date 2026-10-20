"""Isolated pairact-r1 student process: own camera + own issued command in, commands out.

JSON lines on stdin/stdout (one request -> one response):
  {"op": "reset", "roles": {...}, "episode_id": str, "initial": {rid: command}}
  {"op": "propose", "t": float, "robots": {rid: {"jpeg": b64, "issued": command}}}
      -> {"robots": {rid: {"ready", "observation", "rgb_path", "stage"}}}
  {"op": "issue", "t": float, "permits": {rid: bool}}
      -> {"robots": {rid: {"command", "done", "stage", "segment", "permit", "blocked"}}, "finished": bool}
  {"op": "summary"} -> controller summary
No simulator, truth, teacher or partner pose is importable through this protocol.
"""
import argparse
import base64
import json
import sys

OPS = {'reset': {'op', 'roles', 'episode_id', 'initial'}, 'propose': {'op', 't', 'robots'},
       'issue': {'op', 't', 'permits'}, 'summary': {'op'}}


def serve(predict, lines, write, *, config):
    from harness.pairact_r1_student import PairStudentController
    controller = None
    for line in lines:
        request = json.loads(line)
        op = request.get('op')
        if op not in OPS or set(request) != OPS[op]:
            raise ValueError('worker allowlist mismatch')
        if op == 'reset':
            controller = PairStudentController(predict, request['roles'], request['episode_id'], request['initial'],
                                               done_recovery=config['done_recovery'], place_sync=config['place_sync'],
                                               deadband=config['issued_clock_deadband'])
            result = {'ok': True}
        elif op == 'propose':
            robots = {rid: {'jpeg': base64.b64decode(v['jpeg'], validate=True), 'issued': v['issued']}
                      for rid, v in request['robots'].items()}
            result = {'robots': controller.propose(float(request['t']), robots)}
        elif op == 'issue':
            result = {'robots': controller.issue(float(request['t']), request['permits']),
                      'finished': controller.finished}
        else:
            result = controller.summary()
        write(json.dumps(result, allow_nan=False))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--config', required=True, help='PAIRACT_R1 train config (done_recovery, place_sync, deadband)')
    p.add_argument('--device', default='cuda')
    a = p.parse_args()
    from harness.pairact_r1 import PairActActor, load_config
    config = load_config(a.config)
    actor = PairActActor.load(a.model, device=a.device)
    print(json.dumps({'ready': True, 'mode': 'pairact_r1_student_eval_v1'}), flush=True)
    serve(actor.predict_staged, sys.stdin, lambda s: print(s, flush=True), config=config)


if __name__ == '__main__':
    main()
