"""CPU DEVICE actor load/readback only; no predict, episodes or simulator."""
import json
import os
from pathlib import Path
import sys
import time

os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
sys.dont_write_bytecode = True
here = Path(__file__).resolve().parent
ref = json.loads((here / 'baseline-reference.json').read_text())
sys.path.insert(0, ref['aliases']['S'])
result = dict(device_requested='cpu', gpu_episodes=0, training_runs=0, evaluation_runs=0,
              policy_forward_calls=0, cpu_load_attempted=True)
start = time.monotonic()
try:
    import torch
    torch.set_num_threads(1)
    from harness.pairact_r1 import PairActActor
    actor = PairActActor.load(ref['aliases']['ACTOR'], device='cpu')
    devices = sorted({str(v.device) for v in actor.policy.state_dict().values()})
    result.update(status='PASS', devices=devices, cpu_only=devices == ['cpu'],
        state_dict_entries=len(actor.policy.state_dict()),
        parameter_count=sum(p.numel() for p in actor.policy.parameters()),
        cuda_initialized=torch.cuda.is_initialized(), actor_meta_keys=sorted(actor.meta))
    assert result['cpu_only'] and not result['cuda_initialized']
except Exception as error:
    result.update(status='UNAVAILABLE', reason=type(error).__name__ + ': ' + str(error),
        fallback='full artifact/source/provenance SHA-256 comparison; not equivalent to successful model load')
result.update(wall_s=time.monotonic() - start,
    simulator_modules=[m for m in sys.modules if m == 'mujoco' or m == 'warp'])
print(json.dumps(result, indent=2))
