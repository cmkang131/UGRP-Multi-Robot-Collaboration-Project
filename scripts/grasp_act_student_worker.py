"""Isolated policy process: own serialized inputs in, action chunk out."""
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
    p.add_argument('--server-url', help='opt-in private L4 inference; CPU remains default')
    p.add_argument('--serve-bind', help='private L4 server; never a simulation owner')
    p.add_argument('--serve-port', type=int, default=18796)
    p.add_argument('--serve-report', type=Path)
    a = p.parse_args()
    if a.server_url and a.serve_bind:p.error('client and server modes are exclusive')
    if a.server_url:
        from harness.grasp_act_inference import RemoteActor
        actor=RemoteActor(a.model,a.server_url)
        print(json.dumps({'ready':True}),flush=True)
        for line in sys.stdin:
            chunk=actor.predict_request(json.loads(line))
            print(json.dumps({'chunk':chunk},allow_nan=False),flush=True)
        return
    if a.serve_bind:
        if not a.serve_report:p.error('--serve-report required')
        import os
        # PyTorch's deterministic cuBLAS requirement, before CUDA initialization.
        os.environ['CUBLAS_WORKSPACE_CONFIG']=':4096:8'
    import torch
    torch.set_num_threads(a.threads)
    if a.threads != 1:
        torch.set_num_interop_threads(1)
    if a.serve_bind:
        from harness.grasp_act_inference import serve
        serve(a.model,a.serve_bind,a.serve_port,a.serve_report)
        return
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
