"""Real ACT15 own-RGB -> command -> MJWarp smoke, not a task success claim."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from warp_act_rpc import Client


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    for key in ('physics-python', 'qualified-source', 'teacher-source', 'qualification', 'references',
                'compiled-reference', 'compiled-geometry', 'plans', 'actor-source', 'checkpoint', 'out'):
        p.add_argument('--'+key, type=Path, required=True)
    a = p.parse_args()
    if not a.enabled: p.error('student smoke is default OFF')
    import platform
    if platform.system() != 'Linux': p.error('Linux gcp2 only')
    model = a.checkpoint/'model.safetensors'
    expected = 'd90a2b545709df6cd1a5972874db2e20c264007f9a798888f1bdccac22882ed1'
    if hashlib.sha256(model.read_bytes()).hexdigest() != expected: p.error('exact ACT15 checkpoint required')
    sys.path.insert(0, str(a.actor_source))
    from harness.grasp_act_policy import GraspActor, ChunkExecutor
    from harness.grasp_act_contract import validate_observation
    actor = GraspActor.load(a.checkpoint, device='cuda')
    plans = json.loads(a.plans.read_text())['episodes']
    chunks = [ChunkExecutor(actor.predict) for _ in plans]
    client = Client(python=a.physics_python, qualified_source=a.qualified_source, teacher_source=a.teacher_source,
        qualification=a.qualification, references=a.references, compiled_reference=a.compiled_reference,
        compiled_geometry=a.compiled_geometry, out=a.out, nworld=len(plans), enabled=True)
    report = dict(status='running', passed=False, checkpoint_sha256=expected,
                  scope='two own-RGB ACT policy steps only; no full student task score or training')
    try:
        client.reset(plans)
        actions_log = []
        # Two steps verify a real inference plus world-local chunk continuation;
        # this is an API transaction count, not a new success/time threshold.
        for _ in range(2):
            actions = []
            for i, chunk in enumerate(chunks):
                obs, jpgs = client.read_actor(i); validate_observation(obs)
                command, done = chunk.step(obs, jpgs)
                actions.append(dict(command=command, done=done))
            client.step(actions); actions_log.append(actions)
        try: client.read_training(0)
        except RuntimeError: pass
        else: raise RuntimeError('training lane exposed to actor evaluator')
        report.update(status='complete', passed=True, actions=actions_log, terminal=client.terminal,
                      actor_schema=client.read_actor(0)[0]['schema'], actual_inference=True,
                      native_camera='640x480/10Hz; four own JPEG history lags, model resize224x224')
    except BaseException as error:
        report.update(status='HOST_ERROR', error=repr(error)); raise
    finally:
        client.close()
        (a.out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__': main()
