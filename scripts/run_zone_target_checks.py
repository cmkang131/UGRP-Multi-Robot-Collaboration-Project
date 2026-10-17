"""Finite T13 SIM checks through sim_cli; defaults to non-executing plan.

No physics, renderer or model is constructed until --execute. All six cells
use the same controller/config, with public action assignments recorded apart.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import traceback

from harness.zone_study_contract import digest
from scripts.zone_target_bundle import ROOT, BUNDLE_ID, cell_inputs, load_config, verify_bundle
from harness.zone_target_environment import execution_blockers, require_execution


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=str)+'\n')


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False, allow_nan=False, default=str)+'\n' for row in rows))


def selection(cfg, args):
    names = [args.cell] if args.cell else [k for k, c in cfg['cells'].items() if c['group'] == args.group]
    return {'cells': names, 'sim_cap_s': len(names)*cfg['sim_cap_s_per_cell'], 'condition': args.condition,
            'execution_bundle_id': BUNDLE_ID, 'scope': cfg['scope'], 'physics_run': False,
            'runnable': not execution_blockers(cfg), 'blocked_on': execution_blockers(cfg),
            'controller_config_sha256': digest({k: v for k, v in cfg.items() if k != 'cells'}),
            'role_assignment_sha256': digest({k: cfg['cells'][k] for k in names})}


def execute_cell(cfg, name, condition, out, bundle, bundle_sha):
    require_execution(cfg)  # also protects direct API calls before any native imports / writes
    from harness import zone_study_integration as zi
    from harness.zone_study_referee import HiddenEventSchedule, Referee
    from harness.zone_target_actor import TargetActor
    from scripts.zone_target_host import TargetStudyHost
    from sim.render_profile import verify_model
    cell, spec, hidden = cell_inputs(cfg, name)
    out.mkdir(parents=True, exist_ok=False)
    host = None
    actor = None
    started = time.monotonic()
    report = {'cell': name, 'condition': condition, 'sim_cap_s': 900, 'scope': cfg['scope'],
              'execution_bundle_id': BUNDLE_ID, 'bundle_sha256': bundle_sha,
              'controller_config_sha256': bundle['controller_config_sha256'],
              'role_assignment_sha256': digest(cell), 'load_average_start': os.getloadavg(),
              'terminal': 'HOST_ERROR', 'physical_success': None, 'llm_calls': 0,
              'event_recovery_verdict': 'requires_postrun_evidence_review'}
    truth = []
    referee = None
    try:
        write(out/'inputs.json', {'public_order_sheet': spec['order_sheet'], 'visual_catalogue': spec['visual_catalogue'],
                                 'actor_actions': {k: cell[k] for k in ('actor', 'order_id', 'start_after_s')},
                                 'controller_config_sha256': bundle['controller_config_sha256']})
        write(out/'eval_only/setup.json', {'placements': spec['target_placements'], 'events': hidden, 'focal': cell})
        provider = zi.pose_provider_spec(cfg['pose_provider'], map_id=cfg['map_id'])
        host = TargetStudyHost(spec, cfg['student'], root=ROOT, provider_spec=provider,
                               frames_dir=out/'own_frames', hidden=HiddenEventSchedule(hidden))
        for key in ('profile', 'base_profile', 'noslip_iterations', 'timestep_s'):
            if host.contact_record[key] != bundle['contact'][key]:
                raise ValueError('applied T13 contact profile mismatch: '+key)
        report['render_profile'] = verify_model(host.world.model, cfg['render_profile'])
        # Setup check is evaluation-only and precedes the first actor decision.
        actual = host.referee_truth()
        if set(actual) != {p['item_id'] for p in spec['target_placements']}:
            raise ValueError('T13 native scene dropped or added an object')
        for p in spec['target_placements']:
            row = actual[p['item_id']]
            if row['kind'] != p['kind'] or any(abs(row[k]-v) > .03 for k, v in zip(('x', 'y'), p['pose_m'])):
                raise ValueError('T13 native setup placement mismatch')
        actor = TargetActor(host.robots[cell['actor']].executor,
                            **{k: cell[k] for k in ('order_id', 'start_after_s')})
        referee = Referee(cfg['public_orders'], host.static)
        t = host.settle(.5)
        while t < cfg['sim_cap_s_per_cell']-1e-9:
            actor.tick(t)
            host.advance_to(min(cfg['sim_cap_s_per_cell'], round(t+.1, 6)))
            t = float(host.world.data.time)
            sample = host.referee_truth()
            truth.append({'sim_s': t, 'items': sample})
            referee.observe(t, sample)  # never returned to actor/target executor
            # Fixed SIM horizon: physical truth/target effect never stops or
            # repairs an actor; all event branches remain in their denominator.
        report.update(terminal='CAP', sim_s=float(host.world.data.time),
                      own_claim=host.robots[cell['actor']].executor.jobs.claim(cell['order_id']),
                      assigned_cells=1, physical_success=None)
    except Exception as error:
        report.update(error={'type': type(error).__name__, 'message': str(error),
                             'errno': getattr(error, 'errno', None),
                             'traceback': traceback.format_exc()},
                      terminal='HOST_ERROR' if isinstance(error, OSError) else 'RUN_ERROR')
    finally:
        if host is not None:
            try:
                host.close_episode('T13_'+report['terminal'])
                report['sim_s'] = float(host.world.data.time)
                report['weld_max_active'] = host.eval_only['max_eq_active']
                report['command_count'] = sum(len(s.commands) for s in host.robots.values())
                report['observation_count'] = sum(len(s.frames) for s in host.robots.values())
                write(out/'eval_only/host.json', host.eval_only)
                jsonl(out/'eval_only/truth.jsonl', truth)
                jsonl(out/'eval_only/hidden_events.jsonl', host.hidden_log)
                if referee is not None: write(out/'eval_only/referee.json', referee.record())
                for rid, slot in host.robots.items():
                    jsonl(out/rid/'commands.jsonl', slot.commands)
                    jsonl(out/rid/'frames.jsonl', slot.frames)
                    jsonl(out/rid/'cancellations.jsonl', slot.cancellations)
                    jsonl(out/rid/'decisions.jsonl', slot.decisions)
                    jsonl(out/rid/'target_jobs.jsonl', slot.executor.target_log)
                    jsonl(out/rid/'perception.jsonl', slot.executor.recognizer.log)
                    provider = getattr(slot.executor.pose, 'provider', slot.executor.pose)
                    write(out/rid/'provider.json', {'provider': provider.record(),
                                                   'delay_timing': slot.executor.pose.timing})
                    write(out/rid/'lower_jobs.json', slot.executor.jobs_done)
                    write(out/rid/'lower_controllers.json', slot.executor._summaries)
                    write(out/rid/'exception.json', slot.exception)
                if actor is not None: jsonl(out/'actor_actions.jsonl', actor.actions)
            except Exception as error:
                report['collection_error'] = {'type': type(error).__name__, 'message': str(error),
                                              'traceback': traceback.format_exc()}
                report['terminal'] = 'HOST_ERROR'
            finally:
                try:
                    host.close()
                except Exception as error:
                    report['cleanup_error'] = {'type': type(error).__name__, 'message': str(error)}
                    report['terminal'] = 'HOST_ERROR'
        report.update(wall_s=time.monotonic()-started, load_average_end=os.getloadavg())
        write(out/'result.json', report)
        files = [p for p in out.rglob('*') if p.is_file()]
        write(out/'artifacts.sha256.json', {str(p.relative_to(out)): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                                                                   'bytes': p.stat().st_size} for p in sorted(files)})
    return report


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    choose = p.add_mutually_exclusive_group(required=True)
    choose.add_argument('--group', choices=('t13a', 't13b'))
    choose.add_argument('--cell', choices=('I1', 'I2', 'M-U', 'M-H', 'D-H', 'D-U'))
    p.add_argument('--condition', choices=('no_comm', 'peer_ko', 'leader_ko', 'structured'), default='no_comm')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--expected-source-sha')
    p.add_argument('--output', type=Path)
    p.add_argument('--lock-owner', choices=('claude', 'codex', 'kiro'), default='codex')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    cfg = load_config()
    bundle, bundle_sha = verify_bundle()
    plan = {**selection(cfg, args), 'bundle_sha256': bundle_sha}
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    from scripts import agent_lock
    from sim.workflow_manager import environment_identity, git_identity
    code = git_identity(ROOT)
    if not args.expected_source_sha or args.expected_source_sha != code['source_sha'] or code['source_dirty']:
        raise SystemExit('execution requires clean committed source and exact --expected-source-sha')
    require_execution(cfg)  # before output directories, host locks, workers and physics
    if args.output is None or not args.output.is_absolute() or args.output.exists():
        raise SystemExit('execute requires a NEW absolute output directory')
    parent = args.output.parent
    parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(parent).free < 10*1024**3:
        raise SystemExit('HOST_ERROR: less than 10 GiB free')
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    # The runner owns/releases its own lock. Offline pytest never calls this.
    agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner=args.lock_owner, branch=branch,
                       purpose='T13 target checks', pid=os.getpid(), expected_minutes=120)
    try:
        args.output.mkdir(exist_ok=False)
        write(args.output/'manifest.json', {**plan, 'physics_run': True, 'code': code,
                                           'environment': environment_identity(), 'bundle': bundle})
        reports = []
        for name in plan['cells']:
            reports.append(execute_cell(cfg, name, args.condition, args.output/name, bundle, bundle_sha))
        write(args.output/'results.json', reports)
        return int(any(r['terminal'] in ('HOST_ERROR', 'RUN_ERROR') for r in reports))
    finally:
        agent_lock.release(agent_lock.DEFAULT_ROOT, owner=args.lock_owner)


if __name__ == '__main__':
    raise SystemExit(main())
