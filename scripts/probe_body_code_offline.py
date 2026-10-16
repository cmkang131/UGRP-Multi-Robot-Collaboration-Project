"""Saved own RGB/map/issued commands -> actual code_v1 dispatch, no providers.

The saved scenes do not contain the complete costmap or current GO/ACK receipt.
This measures choosing a progress/recovery skill, not physical motion or safety
success. Mapping terminal flags are restored from the saved own navigator log.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS

from harness.e2e_body_controller import stop_like
from harness.e2e_body_code import WAIT
from scripts.probe_body_decider_offline import gate_for, strip


def read_json(path):
    return json.loads(subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else path.read_bytes())


def replay(scene):
    if scene['phase'] not in ('mapping', 'align'):
        return dict(queried=False, reason='current GO/ACK and queued batch not retained; not synthesized')
    terminal = scene.get('navigation_status') == 'exploration_finished'
    commands = [strip(c) for c in scene['next']]
    if not terminal and not any(not stop_like(c) for c in commands):
        return dict(queried=False, reason='no direct motion proposal; runtime intentionally does not query')
    g = gate_for(scene, skills=True, code=True)
    rid, now = scene['rid'], scene.get('decision_t', scene['t'])
    g.tr.failure = None; g.tr.done = False; g.tr.epoch = g.tr.seg = 0
    g.tr.robot_queue_until = {}; g.tr.aligned = {}; g.tr.align = {}
    events = []; g.tr.event = lambda *a, **k: events.append(dict(event=a, **k))
    if terminal:
        own = scene['explore_deadlock']
        goal = g.robots[rid].goal
        goal.stage = scene['goal_stage']; goal.done = False
        goal.explorer.navigator = NS(finished=own['finished'], failed=own['failed'], phase=own['phase'],
            sweep_pending=own['sweep_pending'], view_active=False,
            # Counts only: source target coordinates weren't retained. These
            # placeholders are never read as geometry or passed to the selector.
            blacklist=[None]*own['blacklist_count'], visited=[None]*own['visited_count'], reset_action=lambda: None)
    class NeverProvider:
        def decide(self, *a, **k):
            raise AssertionError('CODE_BACKEND_CALLED_PROVIDER')
    g.client = NeverProvider()
    emitted = g.filter(now, [(rid, c) for c in commands])
    if not g.rows:
        return dict(queried=False, reason='no body decision', terminal=terminal)
    row = g.rows[-1]
    return dict(queried=True, terminal=terminal, progress_skill=row['choice'] not in WAIT,
                recovery=row['choice'].startswith(('replan_', 'recover_', 'back_', 'scan_', 'detour_')),
                row=row, emitted=emitted, events=events, summary=g.summary())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scenes', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise ValueError('REFUSE_OVERWRITE_EVIDENCE')
    rows = []
    for path in a.scenes:
        for i, scene in enumerate(read_json(path)):
            result = replay(scene)
            rows.append(dict(source=path.name, index=i, rid=scene['rid'], t=scene['t'], phase=scene['phase'],
                             frame_sha256=scene['frame_sha256'], **result))
    groups = {}
    for r in rows:
        for group in ('all', r['source'], 'terminal_mapping' if r.get('terminal') else r['phase']):
            s = groups.setdefault(group, dict(scenes=0, queried=0, progress_skill=0, skipped=0, provider_calls=0))
            s['scenes'] += 1; s['queried'] += r['queried']; s['skipped'] += not r['queried']
            s['progress_skill'] += r.get('progress_skill', False)
            s['provider_calls'] += r.get('summary', {}).get('provider_calls', 0)
    out = dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
               input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in a.scenes},
               scope='saved scene skill admission only; missing full own costmap; no actual motion or provider',
               groups=groups, rows=rows)
    a.out.write_text(json.dumps(out, indent=1, ensure_ascii=False)+'\n')
    print(json.dumps(groups, indent=1))


if __name__ == '__main__':
    main()
