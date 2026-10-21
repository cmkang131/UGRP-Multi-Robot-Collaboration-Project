"""Per-world cause table for a pairact P2 carry pilot (e.g. -c4 pilot 8343000-039).

Reads ONLY files the frozen runner already writes (read-only, never modifies a
run): ``summary.json`` of each run root and per world ``raw/result.json``,
``raw/carry-route.json`` (-c4 opt-in route modes only), ``raw/carry-eval.json``
and, for the offline route replay, ``raw/eval-only.jsonl`` (GT rows; the
teacher's obstacle discs are rebuilt from the handover row exactly as
``carry_obstacles`` did on the VM). ``*.zst`` variants written by
``compress_logs`` are decoded with the ``zstd`` binary.

Labels: this is a teacher yield check (GT teacher, not learned, not collected
data). The replay re-runs only the pure-Python route planner on the recorded
handover state; it says nothing about whether the motion would succeed.

    python scripts/analyze_pairact_pilot.py --run <pilot-dir> [--run <pilot-dir-B>] \
        --out <dir> [--replay] [--replay-modes detour_v1,detour_v2] [--verify]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = ROOT/'maps/zones_final_v3/zone_wide_two_doors_final_v3.json'
SCHEMA = 'ugrp.pairact.pilot_analysis.v1'
ROUTE_CODES = ('route_blocked', 'route_blocked_no_path', 'staging_unclear', 'door_clearance_insufficient',
               'zone_unreachable', 'arm_targets_missing')
MID_CARRY_CODES = ('carry_hold_lost', 'formation_stretch', 'formation_tracking_lost', 'carry_total_timeout',
                   'lower_no_floor_contact')


# ------------------------------------------------------------------ file io

def read_bytes(path):
    """path or path.zst (compress_logs); None if neither exists."""
    path = Path(path)
    if path.is_file():
        return path.read_bytes()
    z = Path(str(path) + '.zst')
    if z.is_file():
        return subprocess.check_output(['zstd', '-qdc', str(z)])
    return None


def read_json(path):
    b = read_bytes(path)
    return None if b is None else json.loads(b)


def read_jsonl(path):
    b = read_bytes(path)
    return None if b is None else [json.loads(x) for x in b.decode().splitlines() if x.strip()]


def verify_run(run):
    """Compare fetched files with the run's own artifact-sha256.json (missing files are listed, not fatal)."""
    manifest = read_json(run/'artifact-sha256.json')
    if manifest is None:
        return {'checked': 0, 'mismatch': [], 'missing_manifest': True}
    checked, bad = 0, []
    for rel, entry in manifest.items():
        p = run/rel
        if not p.is_file():
            continue
        checked += 1
        if hashlib.sha256(p.read_bytes()).hexdigest() != entry['sha256']:
            bad.append(rel)
    return {'checked': checked, 'mismatch': bad, 'missing_manifest': False}


# ---------------------------------------------------------- classification

def phase_at(events, t):
    """Teacher phase active at time t from the diagnostic phase events."""
    phase = 'carry_hold'
    for e in events or ():
        if e.get('event') == 'phase' and e['t'] <= t + 1e-9:
            phase = e['to']
    return phase


def fail_event(carry):
    return next((e for e in reversed((carry or {}).get('events') or []) if e.get('event') == 'fail'), None)


def classify(w):
    """(category, cause) for one world record built by world_record()."""
    if w['status'] == 'HOST_ERROR':
        return 'host_error', w.get('error_type') or 'HOST_ERROR'
    if not w['grasp_success']:
        if w['cap_end']:
            return 'grasp', 'grasp_cap_end'
        return 'grasp', 'grasp_teacher:' + ','.join(sorted({str(o) for o in w['grasp_teacher_outcomes'].values()}))
    if w['carry_success']:
        return 'success', 'carry_success'
    out = w['teacher_outcome']
    if not w['carry_started']:
        return 'carry_not_started', w.get('carry_not_started_reason') or 'unknown'
    if out in ROUTE_CODES:
        sub = out
        if out == 'route_blocked_no_path':
            sub += ':' + str((w.get('detour_search') or {}).get('reason'))
        if w.get('straight_blocked'):
            sb = w['straight_blocked']
            sub += f"@{sb.get('segment')}/{(sb.get('hit') or [None])[0]}"
        return 'route', sub
    if out in MID_CARRY_CODES or (out or '').endswith('_timeout'):
        return 'carry_teacher', f"{out}@{w.get('teacher_fail_phase')}"
    # teacher finished (or unknown) but the eval-only judge failed
    f = w['carry_failure'] or 'unknown'
    if f == 'drop':
        kinds = ','.join(sorted({d['kind'] for d in w.get('drop_events') or []}))
        return 'eval', f'drop:{kinds}@{w.get("drop_phase")}'
    return 'eval', f'{f}(teacher={out})'


def world_record(run, entry):
    raw = run/f"world-{entry['world']:03d}"/'raw'
    res = read_json(raw/'result.json') or {}
    route = read_json(raw/'carry-route.json')
    ev = read_json(raw/'carry-eval.json') or res.get('carry_eval') or {}
    carry = res.get('carry') or {}
    w = {'run': run.name, 'world': entry['world'], 'seed': entry.get('seed'), 'raw': str(raw),
         'files': {k: read_bytes(raw/k) is not None for k in ('result.json', 'carry-route.json', 'carry-eval.json',
                                                                 'eval-only.jsonl')},
         'status': res.get('status', 'missing_result'), 'error_type': res.get('error_type'),
         'grasp_success': bool(entry.get('success')), 'cap_end': bool(entry.get('cap_end')),
         'sim_s': entry.get('sim_s'), 'carry_success': bool(entry.get('carry_success')),
         'carry_failure': entry.get('carry_failure'), 'end_reason': res.get('end_reason'),
         'grasp_teacher_outcomes': {rid: (t or {}).get('outcome') for rid, t in (res.get('teachers') or {}).items()},
         'joint_held': res.get('joint_held'), 'carry_handover_sim_s': res.get('carry_handover_sim_s'),
         'carry_route_mode': res.get('carry_route', 'straight_v1'),
         'carry_started': carry.get('started', bool(carry)) is not False and bool(carry),
         'carry_not_started_reason': carry.get('reason') if carry.get('started') is False else None,
         'teacher_outcome': carry.get('outcome'), 'teacher_phase_end': carry.get('phase')}
    fe = fail_event(carry)
    w['teacher_fail_phase'] = fe.get('phase') if fe else None
    w['teacher_fail_t'] = fe.get('t') if fe else None
    info = carry.get('route_info') or (route or {}).get('route_info') or {}
    w['route_variant'] = info.get('variant')
    w['straight_blocked'] = info.get('straight_blocked')
    if w['straight_blocked'] is None and fe and carry.get('outcome') == 'route_blocked':
        w['straight_blocked'] = fe.get('detail')
    det = info.get('detour') or {}
    w['detour_search'] = det.get('search') or ((fe or {}).get('detail') or {}).get('search')
    w['detour_final_check'] = det.get('final_check')
    w['detour_min_clearance_m'] = det.get('min_clearance_m')
    w['route_plans'] = (route or {}).get('route_plans')
    w['plan_wall_s'] = (route or {}).get('plan_wall_s')
    w['formation_radius_m'] = info.get('formation_radius_m')
    w['west_staging'] = info.get('west_staging')
    w['max_stretch_m'] = carry.get('max_stretch_m')
    w['max_track_err_m'] = carry.get('max_track_err_m')
    w['retreat'] = carry.get('retreat')
    w['lower_mode'] = carry.get('lower_mode')
    w['zone_aligned'] = any(e.get('event') == 'zone_aligned' for e in carry.get('events') or [])
    w['funnel'] = ev.get('funnel')
    w['drop_events'] = ev.get('drop_events')
    w['drop_phase'] = phase_at(carry.get('events'), ev['drop_events'][0]['t']) if ev.get('drop_events') else None
    w['final_beam_pose'] = ev.get('final_beam_pose')
    w['final_min_z'] = ev.get('final_min_z')
    w['final_tilt_deg'] = ev.get('final_tilt_deg')
    w['carried_max_m'] = ev.get('carried_max_m')
    w['wall_contact_ticks'] = ev.get('wall_contact_ticks')
    w['robot_robot_contact_ticks'] = ev.get('robot_robot_contact_ticks')
    pr = ev.get('phase_report')
    if isinstance(pr, dict):
        w['phase_timeouts'] = pr.get('teacher_timeout') or pr.get('timeouts')
    w['category'], w['cause'] = classify(w)
    return w, res, carry


# ------------------------------------------------------------ route replay

def handover_row(rows, t0):
    best = None
    for r in rows:
        if r.get('t') is not None and r['t'] >= t0 - 1e-6:
            return r
        best = r
    return best


def replay_route(ct, rows, carry, static_map, modes):
    """Re-run the pure-Python route planner on the recorded handover state.

    Returns the straight check (and whether it matches the recorded failure
    detail), the start clearance against walls / object discs, the nearest
    obstacle, and the outcome of each requested route mode."""
    ev0 = next((e for e in carry.get('events') or [] if e.get('event') == 'handover'), None)
    if ev0 is None or not rows:
        return {'replayed': False, 'reason': 'no handover event or no eval-only rows'}
    row = handover_row(rows, ev0['t'])
    if row is None or 'objects' not in row:
        return {'replayed': False, 'reason': 'handover row lacks objects'}
    beam = tuple(ev0['beam'])
    offsets = {rid: tuple(v) for rid, v in ev0['offsets'].items()}
    roles = {rid: None for rid in offsets}
    obstacles = ct.carry_obstacles(row, roles)
    rects = ct.wall_rects(static_map)
    out = {'replayed': True, 'row_t': row['t'], 'handover_t': ev0['t'], 'n_obstacles': len(obstacles),
           'start_clearance_m': ct.formation_clearance(beam, offsets, rects, obstacles),
           'start_wall_clearance_m': ct.formation_clearance(beam, offsets, rects, ())}
    robots, _ = ct.formation_points(beam, offsets)
    near = []
    for o in obstacles:
        gap = min(math.dist(r[:2], o['xy']) - ct.ROBOT_RADIUS_M - o['radius'] for r in robots.values())
        near.append((gap, o['id'], o['radius']))
    near.sort()
    out['nearest_obstacles'] = [{'id': i, 'gap_m': g, 'radius_m': rad} for g, i, rad in near[:3]]
    try:
        route, info = ct.carry_route(beam, offsets, static_map)
    except ValueError as error:
        out['straight'] = {'code': str(error)}
        return out
    out['west_staging'] = list(info['west_staging'])
    west_rot = (info['west_staging'][0], info['west_staging'][1], route[1][1][2])
    out['west_staging_clearance_m'] = ct.formation_clearance(west_rot, offsets, rects, obstacles)
    _, blocked = ct.check_route(beam, route, offsets, rects, obstacles)
    straight = {'blocked': blocked is not None and not blocked[0],
                'rotate_first_used': bool(blocked is not None and blocked[0]),
                'detail': ({k: (list(v) if isinstance(v, tuple) else v) for k, v in blocked[1].items()}
                           if blocked else None)}
    rec = (carry.get('route_info') or {}).get('straight_blocked') or (fail_event(carry) or {}).get('detail')
    if isinstance(rec, dict) and 'straight' in rec:
        rec = rec['straight']
    if rec is not None and straight['detail'] is not None:
        straight['matches_record'] = (rec.get('segment') == straight['detail'].get('segment') and
                                      list(rec.get('hit') or []) == list(straight['detail'].get('hit') or []))
    out['straight'] = straight
    out['modes'] = {}
    for mode in modes:
        if mode not in getattr(ct, 'ROUTE_MODES', ()):
            out['modes'][mode] = {'available': False}
            continue
        teacher = ct.PairCarryTeacherWarp({rid: role for rid, role in zip(sorted(offsets), ('teal', 'blue'))},
                                          {'beam': {'pose': list(beam), 'min_z': .03, 'tilt_deg': 0.},
                                           'robots': {rid: {'pose': list(ct.compose(beam, off))}
                                                      for rid, off in offsets.items()},
                                           'contacts': {rid: [1., 1.] for rid in offsets}},
                                          ev0['t'], static_map,
                                          {rid: {'place': {s: 1500 for s in ct.SERVOS},
                                                 'hover': {s: 1500 for s in ct.SERVOS},
                                                 'place_deep': {s: 1500 for s in ct.SERVOS}} for rid in offsets},
                                          {rid: {s: 1500 for s in ct.SERVOS} for rid in offsets},
                                          obstacles=obstacles, route_mode=mode)
        ri = teacher.route_info
        det = ri.get('detour') or {}
        out['modes'][mode] = {'available': True, 'outcome': teacher.outcome, 'variant': ri.get('variant'),
                              'search': det.get('search'), 'min_clearance_m': det.get('min_clearance_m'),
                              'goal': det.get('goal'), 'fail_detail': (fail_event(teacher.diagnostic()) or {}).get('detail')}
    return out


def _json_safe(v):
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return v


# ------------------------------------------------------------------- report

def summarize(worlds):
    n = len(worlds)
    by_cat = Counter(w['category'] for w in worlds)
    by_cause = Counter(w['cause'] for w in worlds if w['category'] != 'success')
    return {'N': n, 'carry_success_n': by_cat['success'], 'grasp_success_n': sum(w['grasp_success'] for w in worlds),
            'cap_end_n': sum(w['cap_end'] for w in worlds), 'host_error_n': by_cat['host_error'],
            'by_category': dict(by_cat), 'by_cause': dict(by_cause),
            'teacher_outcomes': dict(Counter(str(w['teacher_outcome']) for w in worlds if w['grasp_success'])),
            'carry_failures': dict(Counter(str(w['carry_failure']) for w in worlds
                                           if w['grasp_success'] and not w['carry_success']))}


def markdown(summary, worlds, replay):
    L = ['# pairact pilot 실패 원인표 (teacher 수율 확인 · 학습 아님 · 수집 데이터 아님)', '',
         f"- carry 성공 {summary['carry_success_n']}/{summary['N']}, 파지 {summary['grasp_success_n']}/{summary['N']}, "
         f"cap_end {summary['cap_end_n']}, HOST_ERROR {summary['host_error_n']}", '',
         '| 분류 | 원인 | n |', '|---|---|---|']
    for cause, k in sorted(summary['by_cause'].items(), key=lambda x: -x[1]):
        cat = next(w['category'] for w in worlds if w['cause'] == cause)
        L.append(f'| {cat} | `{cause}` | {k} |')
    L += ['', '| run | world | seed | 분류 | 원인 | 교사 outcome | eval failure | variant | 탐색 reason | 운반 m |',
          '|---|---|---|---|---|---|---|---|---|---|']
    for w in worlds:
        if w['category'] == 'success':
            continue
        s = w.get('detour_search') or {}
        cm = w.get('carried_max_m')
        L.append(f"| {w['run']} | {w['world']} | {w['seed']} | {w['category']} | `{w['cause']}` | {w['teacher_outcome']} | "
                 f"{w['carry_failure']} | {w['route_variant']} | {s.get('reason')} | "
                 f"{'' if cm is None else f'{cm:.2f}'} |")
    if replay:
        L += ['', '## 경로 재생(오프라인, 계획기만 · 동작 성공 여부는 GPU에서만)', '',
              '| world | seed | 시작 틈 m | 벽만 틈 m | 최근접 물체(틈 m) | west 회전 틈 m | 직선 막힘 | 기록 일치 | ' +
              ' | '.join(sorted({m for r in replay.values() for m in (r.get('modes') or {})})) + ' |',
              '|---|---|---|---|---|---|---|---|' + '---|'*len({m for r in replay.values() for m in (r.get('modes') or {})})]
        modes = sorted({m for r in replay.values() for m in (r.get('modes') or {})})
        for w in worlds:
            r = replay.get((w['run'], w['world']))
            if not r or not r.get('replayed'):
                continue
            near = r['nearest_obstacles'][0] if r.get('nearest_obstacles') else None
            st = r.get('straight') or {}
            cells = []
            for m in modes:
                x = (r.get('modes') or {}).get(m) or {}
                cells.append('n/a' if not x.get('available') else
                             f"{x.get('outcome') or 'ok'}/{x.get('variant')}" +
                             (f"/{(x.get('search') or {}).get('reason')}" if x.get('outcome') else ''))
            L.append(f"| {w['world']} | {w['seed']} | {r['start_clearance_m']:.3f} | {r['start_wall_clearance_m']:.3f} | "
                     f"{near['id'] + ' (' + format(near['gap_m'], '.3f') + ')' if near else '-'} | "
                     f"{r.get('west_staging_clearance_m', float('nan')):.3f} | {st.get('blocked')} "
                     f"{(st.get('detail') or {}).get('segment', '')} | {st.get('matches_record')} | " + ' | '.join(cells) + ' |')
    return '\n'.join(L) + '\n'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--run', type=Path, action='append', required=True, help='pilot run root(s) with summary.json')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--static-map', type=Path, default=DEFAULT_MAP)
    p.add_argument('--replay', action='store_true', help='offline route-planner replay from eval-only.jsonl')
    p.add_argument('--replay-modes', default='detour_v1,detour_v2')
    p.add_argument('--teacher-src', type=Path, default=ROOT,
                   help='tree whose harness/pair_carry_teacher_warp.py is replayed (e.g. a -c6 worktree)')
    p.add_argument('--verify', action='store_true', help='check fetched files against artifact-sha256.json')
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    worlds, raw_cache, verify = [], {}, {}
    for run in a.run:
        summary = read_json(run/'summary.json')
        if summary is None:
            raise SystemExit(f'MISSING_SUMMARY: {run}/summary.json')
        if a.verify:
            verify[run.name] = verify_run(run)
        for entry in summary.get('worlds') or []:
            w, res, carry = world_record(run, entry)
            worlds.append(w)
            raw_cache[(run.name, entry['world'])] = (run, carry)
    replay = {}
    if a.replay:
        sys.path.insert(0, str(a.teacher_src))
        from harness import pair_carry_teacher_warp as ct
        static_map = json.loads(a.static_map.read_text())
        modes = [m for m in a.replay_modes.split(',') if m]
        for w in worlds:
            if not w['grasp_success'] or w['category'] == 'host_error':
                continue
            run, carry = raw_cache[(w['run'], w['world'])]
            rows = read_jsonl(run/f"world-{w['world']:03d}"/'raw'/'eval-only.jsonl')
            replay[(w['run'], w['world'])] = replay_route(ct, rows, carry, static_map, modes)
            w['replay'] = replay[(w['run'], w['world'])]
    summary = summarize(worlds)
    if replay:
        rec = Counter()
        for r in replay.values():
            for m, x in (r.get('modes') or {}).items():
                if x.get('available'):
                    rec[m + ':' + ('path' if x.get('outcome') is None else x['outcome'])] += 1
        summary['replay_modes'] = dict(rec)
        summary['replay_teacher_src'] = str(a.teacher_src)
        try:
            summary['replay_teacher_sha'] = subprocess.check_output(['git', '-C', str(a.teacher_src), 'rev-parse', 'HEAD'],
                                                                     text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            summary['replay_teacher_sha'] = None
    report = {'schema': SCHEMA, 'runs': [str(r) for r in a.run], 'labels': ['teacher', 'yield_check', 'not_learned',
                                                                         'not_collected_data'],
              'verify': verify, 'summary': summary, 'worlds': worlds}
    (a.out/'pilot-analysis.json').write_text(json.dumps(_json_safe(report), indent=1, ensure_ascii=False))
    (a.out/'pilot-analysis.md').write_text(markdown(summary, worlds, replay))
    print(json.dumps(_json_safe(summary), ensure_ascii=False))
    return report


if __name__ == '__main__':
    main()
