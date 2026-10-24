"""Isolated solo-carry student process: own camera + own issued command in, commands out.

DERIVED / UNVERIFIED (solo-e2e/20261024): never run against a checkpoint.

JSON lines on stdin/stdout (one request -> one response), the pair worker's protocol for one robot:
  {"op": "reset", "robot_id": "r1", "episode_id": str, "initial": command}
  {"op": "propose", "t": float, "robots": {"r1": {"jpeg": b64, "issued": command}}}
      -> {"robots": {"r1": {"ready", "observation", "rgb_path", "stage"}}}
  {"op": "issue", "t": float, "permits": {"r1": bool}}
      -> {"robots": {"r1": {"command", "done", "stage", "segment", "permit", "blocked"}}, "finished": bool}
  {"op": "summary"} -> controller summary
Any other op or key set is rejected. No simulator, truth, teacher or partner pose is importable through
this protocol; the only inputs are a JPEG and the applied command.
"""
import argparse
import base64
import json
import sys

OPS = {'reset': {'op', 'robot_id', 'episode_id', 'initial'}, 'propose': {'op', 't', 'robots'},
       'issue': {'op', 't', 'permits'}, 'summary': {'op'}}


def serve(predict, lines, write, *, config, executor_factory=None, barrier_factory=None):
    from harness.pairact_solo_student import SoloStudentController
    controller = None
    for line in lines:
        request = json.loads(line)
        op = request.get('op')
        if op not in OPS or set(request) != OPS[op]:
            raise ValueError('worker allowlist mismatch')
        if op != 'reset' and controller is None:
            raise ValueError('reset required first')
        if op == 'reset':
            controller = SoloStudentController(predict, request['episode_id'], request['initial'],
                                               robot_id=request['robot_id'], executor_factory=executor_factory,
                                               barrier_factory=barrier_factory,
                                               deadband=config['issued_clock_deadband'])
            result = {'ok': True}
        elif op == 'propose':
            from harness.pairact_solo_student import REQUEST_KEYS
            if any(set(v) != REQUEST_KEYS for v in request['robots'].values()):
                raise ValueError('own camera + own issued command only')     # checked BEFORE the dict is rebuilt
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
    p.add_argument('--config', required=True, help='train config with issued_clock_deadband')
    p.add_argument('--device', default='cuda')
    a = p.parse_args()
    from harness.pairact_r1 import PairActActor, load_config   # dsh/pairact-r1-dryrun; not in this tree
    config = load_config(a.config)
    actor = PairActActor.load(a.model, device=a.device)
    print(json.dumps({'ready': True, 'mode': 'pairact_solo_student_eval_v1'}), flush=True)
    serve(actor.predict_staged, sys.stdin, lambda s: print(s, flush=True), config=config)


if __name__ == '__main__':
    main()
