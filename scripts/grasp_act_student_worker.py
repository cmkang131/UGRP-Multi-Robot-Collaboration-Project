"""Isolated CPU policy process: serialized own inputs in, action chunk out."""
import argparse
import base64
import json

import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.grasp_act_policy import GraspActor


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--threads', type=int, choices=(1, 2, 4, 8, 16), default=1)
    a = p.parse_args()
    import torch
    torch.set_num_threads(a.threads)
    if a.threads != 1:
        torch.set_num_interop_threads(1)
    actor = GraspActor.load(a.model, device='cpu')
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        if set(request) != {'observation', 'jpegs'}:
            raise ValueError('worker request whitelist mismatch')
        jpegs = [base64.b64decode(s, validate=True) for s in request['jpegs']]
        chunk = actor.predict(request['observation'], jpegs)
        print(json.dumps({'chunk': chunk}, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
