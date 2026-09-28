"""Summarise zone-pair dev run folders (raw read-only). Post-hoc eval only.

Controller stage comes from the executor's own state events (pair_records.json);
physical stage (grasp/lift/door/place) comes from eval_only/result.json (GT, eval only).
usage: analyze_runs.py <run_dir> [...] > summary.json
"""
import collections, hashlib, json, sys
from pathlib import Path

ORDER = ['approach', 'align', 'pregrasp', 'close', 'lift', 'carry', 'place']


def stage(state):
    s = state or ''
    if s in ('wait_approach', 'approach', 'bootstrap', 'start_ready', 'reapproach'): return 'approach'
    if s.startswith('align'): return 'align'
    if s.startswith('pregrasp'): return 'pregrasp'
    if s in ('wait_close', 'grasp', 'close', 'closing', 'grip_check') or s.startswith('close'): return 'close'
    if s in ('wait_lift', 'lift') or s.startswith('lift'): return 'lift'
    if s in ('wait_carry', 'carry') or s.startswith('carry'): return 'carry'
    if s in ('lower', 'wait_open', 'cp_open', 'released', 'done') or s.startswith('lower'): return 'place'
    return None


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()


def summarise(d):
    d = Path(d)
    m = json.loads((d / 'manifest.json').read_text())
    ev = json.loads((d / 'eval_only/result.json').read_text())
    pr = json.loads((d / 'pair_records.json').read_text())[0]
    fails = [json.loads(l) for l in open(d / 'events.jsonl') if '"job_failed"' in l]
    cmds = collections.Counter()
    for l in open(d / 'commands.jsonl'):
        c = json.loads(l); cmds[(c['robot_id'], c['kind'])] += 1
    robots = {}
    for rid, r in pr['robots'].items():
        seq = []
        for e in r['events']:
            if e['event'] == 'state' and (not seq or seq[-1] != e['state']): seq.append(e['state'])
        names = collections.Counter(e['event'] for e in r['events'])
        stages = [stage(s) for s in seq if stage(s)]
        furthest = max(stages, key=ORDER.index) if stages else None
        tail = [{k: e.get(k) for k in ('event', 'sim_s', 'state', 'reason', 'frame_id', 'accepted', 'failure')
                 if e.get(k) is not None} for e in r['events'][-10:]]
        failed_checks = [e for e in r['events'] if e['event'].endswith('rejected') or e['event'].endswith('refused')]
        robots[rid] = {'states': list(dict.fromkeys(seq)), 'state_changes': len(seq), 'furthest_controller_stage': furthest,
                       'event_counts': dict(names), 'look_commands': cmds[(rid, 'look')],
                       'relook_triggers': sum(v for k, v in names.items() if 'relook_trigger' in k),
                       'scheduled_or_safety_looks': sum(v for k, v in names.items() if 'safety_look' in k or 'scheduled' in k),
                       'last_events': tail,
                       'last_rejection': ({k: v for k, v in failed_checks[-1].items() if k != 'robot_id'}
                                          if failed_checks else None),
                       'frames': len(list((d / 'frames' / rid).glob('*.jpg')))}
    video = d / 'eval_only/overview.mp4'
    checks = ev.get('checks', {})
    return {'run_id': m['run_id'], 'seed': m['seed'], 'pair_policy': m.get('pair_policy'),
            'state': m.get('state'), 'termination': m.get('termination'),
            'sim_start_s': m.get('simulator_start_s'), 'sim_end_s': m.get('sim_end_s'), 'wall_s': m.get('wall_s'),
            'loadavg_start': m['environment'].get('loadavg_at_start'), 'loadavg_end': m['environment'].get('loadavg_at_end'),
            'source_sha': m['source'].get('source_sha'), 'github_authorization': (m.get('github_authorization') or {}).get('ref'),
            'job_failed': [{'robot_id': f['robot_id'], 'reason': f['detail'].get('reason'), 'sim_s': f['sim_s']} for f in fails],
            'verdict': ev.get('verdict'), 'checks': {k: checks.get(k) for k in
                ('approach', 'joint_grasp', 'lift', 'door', 'placement_release', 'no_drop', 'contacts', 'weld_off')},
            'grasp_at_s': ev.get('evidence', {}).get('grasp_at_s'), 'lifted_at_s': ev.get('evidence', {}).get('lifted_at_s'),
            'go_times': ev.get('protocol', {}).get('go_times'), 'commands_motion': ev.get('commands'),
            'model_calls': ev.get('model_calls'), 'contact_counts': json.loads((d / 'eval_only/contacts.json').read_text()).get('counts'),
            'robots': robots,
            'overview_mp4': {'path': str(video), 'bytes': video.stat().st_size, 'sha256': sha(video)} if video.exists() else None,
            'artifacts_sha256_json': sha(d / 'artifacts.sha256.json')}


if __name__ == '__main__':
    print(json.dumps([summarise(a) for a in sys.argv[1:]], ensure_ascii=False, indent=1))
