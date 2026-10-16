"""Default-off native MJWarp E2E batch; one world = one episode.

Mac supports preparation/compile/unit tests only. --execute is Linux gcp6-only.
Smoke exposes pending components and cannot report student/transport success.
"""
from __future__ import annotations
import argparse
from collections import Counter, deque
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import time
import traceback
from urllib.request import urlopen

from harness.e2e_warp_runtime import (OPTION, OwnFrame, Channels, Planner, DiagnosticTask,
                                     encode, sha, rejection, first30)
from harness.e2e_warp_components import require_components, MissionRobot, load_actor, factory
from harness.zone_study_contract import MAIN_CONDITIONS, ROBOTS

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID = 'e2e-warp-batch-v446'
PROJECT, ACCOUNT, INSTANCE = 'ugrp-sim-f-1016', 'kcm5781kcm5781@gmail.com', 'ugrp-act-l4-gcp6'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def head():
    return subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()


def stack_config():
    path = ROOT/'configs/current_stack.json'
    return json.loads(path.read_text()), sha(path.read_bytes())


def prepare(a):
    stack, digest = stack_config()
    if a.mode == 'mission':
        require_components(a.components, ROOT)
    values = {r['id']: r['current'] for r in stack['rules'] if 'e2e_llm' in r['flows']}
    values['gcp_host'] = INSTANCE
    values['gcp_project'], values['gcp_account'] = PROJECT, ACCOUNT
    deviations = []
    if a.mode == 'smoke':
        actual = dict(nearfield_executor='dependency_wait', localization_path='own_gauge_LK_diagnostic',
                      setdown_lookaround_v1=False)
        for key, value in actual.items():
            values[key] = value
            deviations.append(dict(id=key, reason='first30 diagnostic; incomplete component blocked; no transport/student success',
                approval=dict(authority='user', evidence='2026-10-17 e2ewarp request §3(b): marked substitutions permitted for first30; pending parts interface/toggle only')))
    funnel = a.output/'rejection_table.json'
    queue = dict(schema='ugrp.e2ewarp.queue.v1', execution_bundle_id=BUNDLE_ID, flow='e2e_llm',
        source_sha=head(), option=OPTION, enabled=a.e2e_warp_batch == 'on_v1', mode=a.mode,
        round=a.round, nworld=a.nworld, condition=a.condition, seed=a.seed,
        sim_budget_s=30. if a.mode == 'smoke' else 1800.,
        stack_sha256=digest, stack_values=values, stack_deviations=deviations,
        host=dict(instance=INSTANCE, project_id=PROJECT, account=ACCOUNT),
        no_pooling=True, rejection_table=str(funnel.resolve()),
        record_tail=dict(hz=10, sim_s=10, purpose='recording_only; no control changes'),
        dependency_status='waiting for selected ACT / loaded FK / global registration / release API')
    a.output.mkdir(parents=True, exist_ok=False)
    write(funnel, dict(raw=str(a.output.resolve()), reproduction=a.command,
        stages=[dict(stage='queue_prepared', cumulative_pass_n=a.nworld, rejected_n=0),
                dict(stage='mission_dependencies_ready', cumulative_pass_n=0, rejected_n=a.nworld)],
        reasons=[dict(count=a.nworld, **rejection(queue['dependency_status']))], runtime_started=False))
    write(a.output/'queue.json', queue)
    from scripts.check_current_stack import check_document
    checks = check_document(queue, stack)
    blocked = [r for r in checks if r['status'] not in ('current', 'approved_deviation')]
    write(a.output/'stack-check.json', dict(ok=not blocked, scope='declared queue only; not runtime proof', rows=checks))
    if blocked:
        raise ValueError('CURRENT_STACK_QUEUE_BLOCKED:' + encode([r['id'] for r in blocked]))
    return queue


def admit(a, queue):
    if a.e2e_warp_batch != 'on_v1' or not queue.get('enabled'):
        raise ValueError('DEFAULT_OFF:explicit e2e_warp_batch_v1 required')
    if platform.system() != 'Linux' or platform.node().split('.')[0] != INSTANCE:
        raise ValueError('Linux gcp6 only; Mac step/render prohibited')
    if queue['source_sha'] != head() or head() != a.expected_source_sha:
        raise ValueError('FROZEN_SOURCE_SHA_REQUIRED')
    if (queue['mode'] != a.mode or queue['round'] != a.round or queue['nworld'] != a.nworld
            or queue['seed'] != a.seed or queue['condition'] != a.condition):
        raise ValueError('QUEUE_CLI_MISMATCH')
    if not Path(queue['rejection_table']).is_file():
        raise ValueError('EXISTING_ABSOLUTE_FUNNEL_REQUIRED')
    if not Path('/home/ugrp/ugrp-sim/leases/e2ewarp.json').is_file():
        raise ValueError('OWN_LEASE_REQUIRED')
    if not a.output.resolve().is_relative_to(Path('/home/ugrp/ugrp-sim/runs')):
        raise ValueError('PERSISTENT_GCP6_RUN_ROOT_REQUIRED')
    forbidden = [k for k in os.environ if any(s in k.upper() for s in ('OPENROUTER_API', 'OPENAI_API', 'KAGGLE_KEY', 'GOOGLE_APPLICATION_CREDENTIALS'))]
    if forbidden:
        raise ValueError('VM_CREDENTIAL_ENV_FORBIDDEN:' + ','.join(forbidden))
    proof = json.loads(a.host_receipt.read_text())
    if any(proof.get(k) != v for k, v in dict(instance=INSTANCE, project_id=PROJECT, account=ACCOUNT,
              idle_minutes=20, budget_stop=True, wall_cap=None, credentials_on_vm=False).items()):
        raise ValueError('LIVE_HOST_GUARD_RECEIPT_REQUIRED')
    if not a.relay_url.startswith('http://127.0.0.1:'):
        raise ValueError('SSH_LOOPBACK_RELAY_ONLY')
    with urlopen(a.relay_url.replace('/v1/chat/completions', '/identity'), timeout=30) as response:
        relay = json.load(response)
    pin = relay['upstream']
    if (pin['model'] != queue['stack_values']['planner_model'] or pin['provider'] != 'CoreWeave'
            or pin['quantization'] != 'fp4' or pin['allow_fallbacks'] is not False
            or relay.get('alerts') or relay.get('balance_usd', 0) <= 0):
        raise ValueError('PINNED_RELAY_ENDPOINT_CREDIT_REQUIRED')
    stack, digest = stack_config()
    if digest != queue['stack_sha256']:
        raise ValueError('CURRENT_STACK_CHANGED')
    from scripts.check_current_stack import check_document
    if any(r['status'] not in ('current', 'approved_deviation') for r in check_document(queue, stack)):
        raise ValueError('CURRENT_STACK_QUEUE_BLOCKED')
    return relay, proof


def run(a, queue):
    # Admission is complete before importing physics/render packages.
    relay, proof = admit(a, queue)
    components = require_components(a.components, ROOT) if a.mode == 'mission' else None
    actor = load_actor(components['ACT']) if components else None
    from scripts.e2e_warp_physics import build_context, transport, issue, own_map
    import numpy as np
    a.output.mkdir(parents=True, exist_ok=False)
    write(a.output/'queue.json', queue)
    write(a.output/'relay-identity.json', relay)
    write(a.output/'host-receipt.json', proof)
    write(a.output/'RUN_META.json', dict(class_='dev', branch='codex/e2ewarp', sha=head(), batch=a.output.name,
          **{'class': 'dev'}, source='e2ewarp', physics_backend='mjwarp_batch_v1'))
    contexts, planners, tasks, channels, ownstates, rings = [], {}, {}, [], {}, {}
    decisions, maprows, rejects, commands, evaluations, evalstates = [], [], [], [], [], []
    status, error, tick, hooks = 'HOST_ERROR', None, 0, None
    started = time.monotonic()
    try:
        for w in range(a.nworld):
            # Same static model/seed per batch; worlds have independent control.
            context = build_context(a.seed, a.output/f'world-{w:02d}', queue['stack_values'])
            contexts.append(context)
            scenario = context['scene'].scene['params']['scenario_setup']
            static = dict(orders=scenario['orders'], static_map=context['static_map'],
                          condition=a.condition, communication_schema=dict(
                              free=dict(body={'text': '한국어 문장'}), structured=dict(body={'act': 'inform', 'state': 'unknown'})),
                          input_boundary='own RGB and own issued commands only; no top/GT/contact')
            channels.append(Channels(a.condition, a.seed))
            for robot in ROBOTS:
                key = w, robot
                planners[key] = Planner(a.relay_url, a.output/f'world-{w:02d}'/'llm'/robot, static,
                                       run_id=a.output.name, world_id=w, robot=robot)
                tasks[key] = (MissionRobot(robot, static, components, actor) if components else DiagnosticTask(scenario['orders']))
                ownstates[key], rings[key] = {}, deque(maxlen=101)  # 10 SIM s at existing 10Hz + current
        hooks = transport(contexts, a.output, head(), queue['stack_values'])
        hooks.initialize(contexts)
        write(a.output/'runtime-applied.json', dict(flow='e2e_llm', stack_values=queue['stack_values'],
            stack_deviations=queue['stack_deviations'], host=queue['host'],
            contact_profile=dict(profile=queue['stack_values']['contact_profile'],
                noslip_iterations=int(hooks.m.opt.noslip_iterations)),
            gpu_noslip_iterations=int(hooks.wm.opt.noslip_iterations),
            camera=dict(robots=list(ROBOTS), resolution=[640, 480], hz=10, top_control=False),
            cpu_physics_steps=0, cpu_render_calls=0, legacy_equivalence_shims=False,
            xml_sha256=[sha(c['world'].scene_xml.encode()) for c in contexts]))
        rollout_start = time.monotonic()
        limit = round(queue['sim_budget_s']*10)
        for tick in range(limit+1):
            now = tick/10
            if (a.output/'SUPERVISOR_STOP.json').exists():
                status = 'SUPERVISOR_STOP'
                break
            frames = {}
            for key, task in tasks.items():
                w, robot = key
                jpeg = hooks.capture(w, contexts[w]['world'], robot)
                # Initial PWM is a declared setup command, not measured joints.
                if not task.command_history:
                    from harness.active_camera import SEARCH
                    task.command_history.append(dict(t=0., wheels=[0.]*4, duration_s=[0.]*4,
                        pwm={str(k): v for k, v in SEARCH.items()}))
                frame = OwnFrame(robot, w, tick, now, jpeg, tuple(task.command_history[-16:]))
                frames[key] = frame
                rings[key].append(frame)
                if tick % 10 == 0:  # review only; decision JPEGs are included
                    rgb_path = a.output/f'world-{w:02d}'/'review-rgb'/f'{robot}-{tick:06d}.jpg'
                    rgb_path.parent.mkdir(parents=True, exist_ok=True)
                    rgb_path.write_bytes(jpeg)
                report = task.observe(frame) if components else own_map(frame, ownstates[key])
                maprows.append(dict(world=w, robot=robot, sim_s=now, rgb_sha256=sha(jpeg), **report))
                # Smoke: 3 decision epochs within user-prescribed first30. Full
                # owner controller requests decisions on task/observation events.
                needs_decision = bool(getattr(task.component, 'needs_decision', False)) if components else tick in (0, 100, 200)
                if needs_decision:
                    dynamic = dict(robot_id=robot, world_id=w, sim_s=now, own_map=report,
                                   issued_commands=list(frame.issued), candidates=task.candidates(),
                                   **channels[w].inbox(robot))
                    answer, reason = planners[key].decide(frame, dynamic)
                    if answer is not None:
                        try:
                            channels[w].send(robot, answer['message'], now=now)
                            task.select(answer['act'], now)
                        except (ValueError, TypeError) as exc:
                            answer, reason = None, rejection(str(exc), category='message_or_selection')
                    if reason:
                        rejects.append(dict(world=w, robot=robot, sim_s=now, **reason))
                    decisions.append(dict(world=w, robot=robot, sim_s=now, **(answer or {'act': None}), reason=reason))
                if tick == limit:
                    continue
                command = task.command(now)
                # No action/message from a failed decision; hold last issued PWM.
                if needs_decision and answer is None:
                    command = dict(t=now, wheels=[0.]*4, duration_s=[0.]*4, pwm=frame.issued[-1]['pwm'])
                    task.command_history[-1] = command
                commands.append(dict(world=w, robot=robot, **command))
                issue(contexts[w], robot, command)
            # Evaluation is a separate sink. Never pass these values to a task,
            # mapper, ACT, LLM prompt, candidate filter or phase transition.
            for w, context in enumerate(contexts):
                evaluations.append(dict(world=w, sim_s=now, evaluation_only=True,
                    qpos_sha256=sha(context['world'].data.qpos.tobytes())))
            evalstates.append(np.stack([c['world'].data.qpos.copy() for c in contexts]))
            if tick == 300:
                rows = [r for p in planners.values() for r in p.rows]
                initial = first30(rows, decisions, 30., a.nworld, time.monotonic()-rollout_start)
                initial.update(scope='actual first30 prefix', full_transport_success=False)
                write(a.output/'first30.json', initial)
            if tick == limit:
                status = 'cap_end'
                break
            if components and all(task.complete for task in tasks.values()):
                status = 'OWN_COMPLETION_CLAIM'
                break
            hooks.step(contexts, np.ones(a.nworld, dtype=bool))
            if (tick+1) % 10 == 0:
                write(a.output/'progress.json', dict(sim_s=(tick+1)/10, model_calls=sum(p.calls for p in planners.values()),
                      batch_wall_s=time.monotonic()-rollout_start, status='running'))
        sim_s = tick/10
        rows = [r for p in planners.values() for r in p.rows]
        report = first30(rows, decisions, sim_s, a.nworld, time.monotonic()-rollout_start)
        report.update(status=status, stop_intervals='all wheel commands held in smoke; no global registration',
                      scope='raw first30 smoke' if not components else 'mission; separate physical evaluator required')
        write(a.output/'run-metrics.json', report)
    except BaseException as exc:
        error = traceback.format_exc()
        status = 'SUPERVISOR_STOP' if isinstance(exc, KeyboardInterrupt) else 'HOST_ERROR'
    finally:
        sim_s = tick/10
        allrows = [dict(world=w, robot=r, **row) for (w, r), p in planners.items() for row in p.rows]
        for name, rows in dict(decisions=decisions, localization=maprows, rejections=rejects,
                               commands=commands, llm_ledger=allrows, evaluation=evaluations).items():
            write(a.output/(name+'.json'), rows)
        if evalstates:
            np.savez_compressed(a.output/'evaluation-state.npz', qpos=np.asarray(evalstates), dt=.1)
        write(a.output/'messages.json', [dict(world=w, events=c.events) for w, c in enumerate(channels)])
        sizes = []
        for (w, robot), frames in rings.items():
            for f in frames:
                target = a.output/f'world-{w:02d}'/'terminal-ring'/f'{robot}-{f.tick:06d}.jpg'
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f.jpeg)
                sizes.append(dict(world=w, robot=robot, tick=f.tick, sim_s=f.sim_s, path=str(target.relative_to(a.output)),
                                  bytes=len(f.jpeg), sha256=sha(f.jpeg)))
        write(a.output/'terminal-ring.json', dict(hz=10, seconds=10, bytes=sum(r['bytes'] for r in sizes), frames=sizes))
        if hooks is not None:
            hooks.save_states()
        summary = dict(schema='ugrp.e2ewarp.result.v1', status=status, error=error, sim_s=sim_s,
            source_sha=head(), mode=a.mode, nworld=a.nworld, wall_s=time.monotonic()-started,
            physics_backend='mjwarp_batch_v1', contact_profile='warp_native_contact_v1',
            E2E_success=False, student_execution=bool(components), research_result=False,
            no_pooling=True, input_audit=dict(top_camera_control=False, held_world_reads=0,
                scope='capability boundary: controllers never receive world/model/evaluator; smoke has no holding'),
            raw=str(a.output), model_calls=len(allrows), decisions=len(decisions),
            rejection_distribution=dict(Counter(r['reason'] for r in rejects)),
            dependency_status=queue['dependency_status'])
        if not (a.output/'first30.json').exists():
            incomplete = first30(allrows, decisions, sim_s, a.nworld, time.monotonic()-started)
            incomplete.update(scope='incomplete prefix; first30 not reached', completed_first30=False)
            write(a.output/'first30.json', incomplete)
        if components and not error:
            # Post-run evaluator receives raw state files ONLY after controllers
            # stop. Its output never re-enters their observations or transitions.
            outcome = factory(components['evaluator_factory'])(raw=a.output)
            write(a.output/'physical-evaluation.json', outcome)
            worlds = outcome.get('worlds', [])
            eligible = len(worlds) == a.nworld and all(
                r.get('physical_success') is True and r.get('first_to_end_transport') is True
                and r.get('same_episode') is True and r.get('self_map_used') is True for r in worlds)
            summary['E2E_success'] = eligible and bool(allrows) and status == 'OWN_COMPLETION_CLAIM'
            summary['research_result'] = summary['E2E_success']
        if error and not rejects:
            rejects.append(dict(sim_s=sim_s, **rejection('HOST_ERROR', category='runtime', blocked_object='not_observed')))
            write(a.output/'rejections.json', rejects)
        write(a.output/'rejection_table.json', dict(raw=str(a.output), reproduction=a.command,
            stages=[dict(stage='world_attempted', cumulative_pass_n=a.nworld, rejected_n=0),
                    dict(stage='first30_complete', cumulative_pass_n=a.nworld if sim_s >= 30 else 0,
                         rejected_n=0 if sim_s >= 30 else a.nworld),
                    dict(stage='actual_transport', cumulative_pass_n=0, rejected_n=a.nworld if sim_s >= 30 else 0)],
            reasons=rejects or [dict(count=a.nworld, **rejection('marked_smoke_dependency_wait'))]))
        write(a.output/'result.json', summary)
        write(a.output/'sha256.json', {str(p.relative_to(a.output)): sha(p.read_bytes()) for p in a.output.rglob('*') if p.is_file()})
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--e2e-warp-batch', choices=('off', 'on_v1'), default='off')
    p.add_argument('--mode', choices=('smoke', 'mission'), default='smoke')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--round', type=int, choices=(1, 2, 3), default=1)
    p.add_argument('--nworld', type=int, choices=range(1, 41), default=1)
    p.add_argument('--seed', type=int, default=601)
    p.add_argument('--condition', choices=MAIN_CONDITIONS, default='no_comm')
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--queue', type=Path)
    p.add_argument('--expected-source-sha')
    p.add_argument('--host-receipt', type=Path)
    p.add_argument('--components', type=Path)
    p.add_argument('--relay-url', default='http://127.0.0.1:18627/v1/chat/completions')
    a = p.parse_args(argv)
    if a.mode == 'smoke' and a.nworld > 2:
        p.error('first30 smoke is restricted to 1–2 worlds')
    a.command = ['python', '-m', 'scripts.run_e2e_warp', *(argv if argv is not None else __import__('sys').argv[1:])]
    if a.prepare:
        if a.execute:
            p.error('prepare and execute are separate')
        queue = prepare(a)
        print(encode(dict(queue=str(a.output/'queue.json'), enabled=queue['enabled'])))
    elif a.execute:
        if not a.queue or not a.expected_source_sha or not a.host_receipt:
            p.error('queue, expected-source-sha and host-receipt required')
        try:
            result = run(a, json.loads(a.queue.read_text()))
        except Exception:
            if a.output.exists():
                raise  # preserve a previous run; never overwrite its result
            a.output.mkdir(parents=True)
            result = dict(status='HOST_ERROR', source_sha=head(), mode=a.mode,
                          sim_s=0, E2E_success=False, research_result=False,
                          error=traceback.format_exc(), phase='admission')
            write(a.output/'result.json', result)
        print(encode(result))
        return int(result['status'] == 'HOST_ERROR')
    else:
        print(encode(dict(execution_started=False, option=OPTION, default='off', bundle=BUNDLE_ID)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
