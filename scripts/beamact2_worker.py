"""Isolated CPU ACT: strict own observation JSON in, chunk out; no simulator."""
import argparse
import base64
import json
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    from harness.beamact_pair_student import STAGE_MODE
    p.add_argument('--stage-mode', choices=('off', STAGE_MODE), default='off')
    a = p.parse_args()
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    from harness.beamact3 import load_actor
    from harness.grasp_act_rollout import InputAudit
    if a.stage_mode == STAGE_MODE:
        from harness.beamact4_policy import Beam4Actor
        actor = Beam4Actor.load(a.model, device='cpu')
    else:
        actor = load_actor(a.model, device='cpu')
    audit = InputAudit()
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        if set(request) != {'observation', 'jpegs'}:
            raise ValueError('worker allowlist mismatch')
        observation = audit.accept(request['observation'])
        jpegs = [base64.b64decode(s, validate=True) for s in request['jpegs']]
        result = actor.predict_staged(observation, jpegs) if a.stage_mode == STAGE_MODE else {
            'chunk': actor.predict(observation, jpegs)}
        print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
