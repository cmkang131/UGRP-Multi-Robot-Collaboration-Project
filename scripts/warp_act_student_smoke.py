"""Real ACT15 own-RGB -> command -> MJWarp smoke, not a task success claim."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

from warp_act_rpc import Client


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--full-evaluation', action='store_true', help='opt-in90SIMs with exact ACT15 SoloSequence, including release')
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
    from harness.grasp_act_rollout import SoloSequence, SoloScore
    actor = GraspActor.load(a.checkpoint, device='cuda')
    plans = json.loads(a.plans.read_text())['episodes']
    chunks = [ChunkExecutor(actor.predict) for _ in plans]
    sequences = [SoloSequence(with_release=True) for _ in plans]
    client = Client(python=a.physics_python, qualified_source=a.qualified_source, teacher_source=a.teacher_source,
        qualification=a.qualification, references=a.references, compiled_reference=a.compiled_reference,
        compiled_geometry=a.compiled_geometry, out=a.out, nworld=len(plans), enabled=True,
        on_reset=lambda indices: [chunks[i].reset() for i in indices])
    report = dict(status='running', passed=False, checkpoint_sha256=expected,
                  scope='two own-RGB ACT policy steps only; no full student task score or training')
    try:
        client.reset(plans)
        actions_log = []
        report['actions'] = actions_log  # preserve completed prefix on errors
        # Two steps verify a real inference plus world-local chunk continuation;
        # this is an API transaction count, not a new success/time threshold.
        for step in range(900 if a.full_evaluation else 2):  # existing90SIMs /0.1SIMs
            if step == 1 and not a.full_evaluation:
                other_pending = deepcopy(chunks[1].pending)
                other_input = client.read_actor(1)
                fresh = deepcopy(plans[0]); fresh['spawns']['r1'] = deepcopy(plans[1]['spawns']['r1'])
                fresh['episode_id'] += '-student-reset'
                client.reset([fresh], indices=[0])
                if chunks[0].pending or chunks[1].pending != other_pending or client.read_actor(1) != other_input:
                    raise RuntimeError('partial reset changed another actor or retained reset actor chunk')
                report['world_local_chunk_reset_verified'] = True
            actions = []
            skills = []
            for i, chunk in enumerate(chunks):
                if client.terminal[i]:
                    obs, _ = client.read_actor(i)
                    actions.append(dict(command=dict(obs['issued'][-1], t=obs['t']), done=True))
                    skills.append(sequences[i].skill)
                    continue
                if a.full_evaluation and client.read_actor(i)[0]['skill'] != sequences[i].skill:
                    client.instruct(i, sequences[i].skill); chunk.reset()
                obs, jpgs = client.read_actor(i); validate_observation(obs)
                command, done = chunk.step(obs, jpgs)
                skills.append(obs['skill'])
                terminal = sequences[i].update(obs['t'], done) if a.full_evaluation else done
                actions.append(dict(command=command, done=terminal))
            client.step(actions); actions_log.append(dict(actions=actions, skills=skills))
            if all(client.terminal): break
        try: client.read_training(0)
        except RuntimeError: pass
        else: raise RuntimeError('training lane exposed to actor evaluator')
        report.update(status='complete', passed=True, actions=actions_log, terminal=client.terminal,
                      actor_schema=client.read_actor(0)[0]['schema'], actual_inference=True,
                      native_camera='640x480/10Hz; four own JPEG history lags, model resize224x224')
        if a.full_evaluation:
            # Evaluation truth is read ONLY after all policy actions. Reuse the
            # checkpoint's exact evaluator; the owner's teacher Score is a
            # separate diagnostic, not silently substituted as student score.
            scores = [SoloScore() for _ in plans]
            for line in (a.out/'owner/evaluation-only.jsonl').read_text().splitlines():
                ev = json.loads(line)
                if 'min_z' not in ev: continue
                i = ev['world']; index = max(0, round(ev['elapsed_sim_s']/.1)-1)
                skill = actions_log[min(index, len(actions_log)-1)]['skills'][i]
                scores[i].add(ev['t'], skill=skill, linear_speed=ev['speed'], clearance=ev['min_z'],
                              tilt=ev['tilt_deg'], forces=ev['finger_forces'], weld=ev['weld_active'])
            report['student_scores'] = []
            for i, (plan, score, seq) in enumerate(zip(plans, scores, sequences)):
                result = json.loads((a.out/'owner'/f'world-{i:03d}'/'result.json').read_text())
                report['student_scores'].append(dict(seed=plan['seed'], cap_end=result['cap_end'],
                    issued_sequence_complete=result['issued_done'], **score.record(seq.done_times, with_release=True)))
            report['scope'] = 'ACT15 full grasp/release evaluation on MJWarp; no teacher actions, no GT policy inputs'
    except BaseException as error:
        report.update(status='HOST_ERROR', error=repr(error)); raise
    finally:
        try: client.close('evaluation_end' if a.full_evaluation else 'smoke_control_budget_end')
        except BaseException as error: report.update(status='HOST_ERROR', close_error=repr(error), passed=False)
        finally: (a.out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__': main()
