"""Loaded-state (beam held) own-odometry fit: gain, latency, bias, drift rate (OFFLINE, eval-only GT).

Fits the hybrid carry's ``OwnOdometry`` (harness/hybrid_carry.py, config v2) from runs that already
exist: the -c4/-c5 carry pilot fetch (PILOT_ANALYSIS.md, ``analyze_pairact_pilot.py`` input layout),
the P2 smoke-1c run, and later hybrid smoke runs. GT is used ONLY here, offline, to label the motion;
the fitted numbers are runtime inputs, GT never is.

Per world the loaded ticks come from, in this order:
  1. ``raw/hybrid-drive.jsonl`` (hybrid smoke, CODE_CARRY ticks): the code's own applied commands.
  2. ``raw/result.json`` carry diagnostic + ``raw/eval-only.jsonl``: the GT carry teacher is a pure
     function of the recorded rows, so it is re-run offline on them (same Params, route mode,
     obstacles from the handover row). The replay is used only if its route and phase events equal
     the recorded ones and its drive_response equals the recorded ``carry-eval.json`` one.
  3. ``carry-eval.json`` drive_response aggregates alone are NOT a fit (forward/lateral/turn cannot be
     separated from per-phase means); such worlds are listed as excluded.

Model per robot and axis a in (forward m, lateral m, yaw deg), per 0.1 s tick k:
    d_k[a] = gain[a] * u_{k-L}[a] + bias[a] * moving_{k-L}
u = own command in percent-seconds (``hybrid_carry.wheel_body``), d = GT body-frame displacement over
the tick, L = one latency shared by the axes (scan 0..MAX_LATENCY), moving = any delayed axis != 0.
Drift rates for the pose trust gate: dead-reckon each world with the fitted model from the GT start
pose and take the worst final error per metre (xy) and per radian turned (yaw).

Seeds: only pilot 8343000-8343039 and P2 smoke worlds 1/11/17 (8420001/8420011/8420017). Any other
seed in a given run stops the tool (fail closed); it never silently drops a held-out world.

    python scripts/fit_loaded_odom.py --run <pilot-dir> [--run <smoke-1c-dir>] --out <dir>
Output: <out>/loaded-odom-fit.json (schema ugrp.pairact.loaded_odom_fit.v1) + loaded-odom-fit.md.
Then scripts/make_hybrid_config.py turns it into the hybrid config.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import hybrid_carry as hc                     # noqa: E402
from harness import pair_carry_eval as ce                  # noqa: E402
from harness import pair_carry_teacher_warp as ct          # noqa: E402
from harness.grasp_act_contract import wheel_mix           # noqa: E402

SCHEMA = hc.FIT_SCHEMA
DEFAULT_MAP = ROOT/'maps/zones_final_v3/zone_wide_two_doors_final_v3.json'
MAX_LATENCY = 5
MAX_DT = .15
MIN_TICKS = 50
AXES = ('forward', 'lateral', 'yaw')
LOADED_PHASES = tuple(ct.PHASES[:ct.PHASES.index('lower')])
DUMMY_ARM = {'place': {1: 1500, 3: 1500, 4: 1500, 5: 1500, 6: 1500},
             'hover': {1: 2000, 3: 1500, 4: 1500, 5: 1500, 6: 1500},
             'place_deep': {1: 1500, 3: 1500, 4: 1500, 5: 1500, 6: 1500}}


# ------------------------------------------------------------------ io (same layout as analyze_pairact_pilot)

def read_bytes(path):
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


def duty_wheels(drive, period=.1):
    """sim/grasp_act_port.duty_wheels, line for line (that module imports the simulator)."""
    desired = wheel_mix(drive); scale = max(.35, max(map(abs, desired)))
    wheels, durations = [], []
    for v in desired:
        dt = period*abs(v)/scale
        if dt < .001:
            wheels.append(0.); durations.append(0.)
        else:
            wheels.append(math.copysign(.35, v)); durations.append(dt)
    return wheels, durations


# ------------------------------------------------------------------ samples

def body_delta(a, b):
    """GT pose change a -> b in a's body frame: (forward m, lateral m, yaw deg)."""
    c, s = math.cos(a[2]), math.sin(a[2])
    dx, dy = b[0] - a[0], b[1] - a[1]
    return (c*dx + s*dy, -s*dx + c*dy, math.degrees(ct.wrap(b[2] - a[2])))


def sequences(cmd_by_t, rows, roles):
    """{rid: [contiguous [(u, d, pose_a)] runs]} pairing the command at t with GT motion t -> next row."""
    by_t = {round(r['t'], 6): r for r in rows}
    ts = sorted(by_t)
    nxt = dict(zip(ts, ts[1:]))
    out = {rid: [] for rid in roles}
    for rid in roles:
        cur, last = [], None
        for t in sorted(cmd_by_t):
            if t not in by_t or t not in nxt or nxt[t] - t > MAX_DT + 1e-9:
                if cur:
                    out[rid].append(cur)
                cur, last = [], None
                continue
            if last is not None and t - last > MAX_DT + 1e-9:
                out[rid].append(cur); cur = []
            a, b = by_t[t]['robots'][rid]['pose'], by_t[nxt[t]]['robots'][rid]['pose']
            cur.append((hc.wheel_body(cmd_by_t[t][rid]), body_delta(a, b), tuple(a)))
            last = t
        if cur:
            out[rid].append(cur)
    return out


def hybrid_log_commands(log):
    return {round(e['t'], 6): e['commands'] for e in log if e.get('segment') == 'CODE_CARRY'}


def replay_teacher(result, rows, static_map, roles):
    """Re-run the GT carry teacher on the recorded rows. Returns (teacher, check) or (None, check)."""
    carry = result.get('carry') or {}
    events = carry.get('events') or []
    hand = next((e for e in events if e.get('event') == 'handover'), None)
    if hand is None or not rows:
        return None, {'ok': False, 'reason': 'no_handover_or_rows'}
    t0 = hand['t']
    row0 = next((r for r in rows if abs(r['t'] - t0) < 1e-6), None)
    if row0 is None:
        return None, {'ok': False, 'reason': 'handover_row_missing'}
    params = dict(carry.get('params') or {})
    if not params:
        return None, {'ok': False, 'reason': 'params_missing'}
    p = ct.Params(**params)
    info = carry.get('route_info') or {}
    mode = 'detour_v1' if info.get('route_mode') == 'detour_v1' or info.get('variant') == 'detour' else 'straight_v1'
    pwm = {rid: {s: 1500 for s in (1, 3, 4, 5, 6)} for rid in roles}
    teacher = ct.PairCarryTeacherWarp(roles, row0, t0, static_map, {rid: DUMMY_ARM for rid in roles}, pwm,
                                      params=p, wheel_fn=duty_wheels, obstacles=ct.carry_obstacles(row0, roles),
                                      route_mode=mode)
    rec_route = carry.get('route') or []
    got_route = [[t, list(q)] for t, q in teacher.route]
    route_ok = len(rec_route) == len(got_route) and all(
        a[0] == b[0] and all(abs(x - y) < 1e-6 for x, y in zip(a[1], b[1])) for a, b in zip(rec_route, got_route))
    for r in rows:
        if r['t'] > t0 + 1e-9 and not teacher.done:
            teacher.step(r, r['t'])
    key = lambda e: (round(e['t'], 6), e.get('event'), e.get('to'), e.get('code'))  # noqa: E731
    rec_ev = [key(e) for e in events if e.get('event') in ('phase', 'fail')]
    got_ev = [key(e) for e in teacher.events if e.get('event') in ('phase', 'fail')]
    check = {'route_mode': mode, 'route_matches': route_ok, 'events_match': rec_ev == got_ev,
             'recorded_outcome': carry.get('outcome'), 'replayed_outcome': teacher.outcome}
    check['ok'] = route_ok and rec_ev == got_ev and carry.get('outcome') == teacher.outcome
    if not check['ok']:
        check['reason'] = 'replay_differs_from_record'
        return None, check
    return teacher, check


def drive_response_matches(recorded, rows, teacher, roles):
    """Recompute the eval-only drive_response from the replay and compare with the recorded one."""
    if not recorded:
        return None
    mine = ce.drive_response(rows, teacher.log, list(roles))
    a, b = (recorded.get('phases') or {}).get('all') or {}, (mine.get('phases') or {}).get('all') or {}
    for rid in roles:
        for k in ('ticks', 'cmd_speed_mps', 'gt_speed_mps', 'cmd_turn_radps', 'gt_turn_radps'):
            x, y = (a.get(rid) or {}).get(k), (b.get(rid) or {}).get(k)
            if x is None or y is None or abs(x - y) > 1e-6*max(1., abs(x)):
                return False
    return True


# ------------------------------------------------------------------ fit

def pairs(seqs, L):
    """(u_{k-L}, d_k, moving) for one latency over contiguous runs."""
    out = []
    for run in seqs:
        for k in range(L, len(run)):
            u = run[k - L][0]
            out.append((u, run[k][1], any(abs(x) > 0 for x in u)))
    return out


def solve_axis(P, a):
    """Least squares d = g*u + b*m (2x2 normal equations). Returns (g, b, sse, sst, n)."""
    suu = sum(u[a]*u[a] for u, _, _ in P); sum_ = sum(u[a]*m for u, _, m in P); smm = sum(m for _, _, m in P)
    sud = sum(u[a]*d[a] for u, d, _ in P); smd = sum(d[a]*m for _, d, m in P)
    det = suu*smm - sum_*sum_
    if abs(det) < 1e-12 or suu <= 0:
        return None
    g = (sud*smm - smd*sum_)/det
    b = (suu*smd - sum_*sud)/det
    mean = sum(d[a] for _, d, _ in P)/len(P)
    sse = sum((d[a] - g*u[a] - b*m)**2 for u, d, m in P)
    sst = sum((d[a] - mean)**2 for _, d, _ in P)
    return g, b, sse, sst, len(P)


def fit(all_seqs, max_latency=MAX_LATENCY):
    scan, best = [], None
    for L in range(max_latency + 1):
        P = pairs(all_seqs, L)
        if len(P) < MIN_TICKS:
            scan.append({'latency_ticks': L, 'n': len(P), 'cost': None})
            continue
        axes = [solve_axis(P, a) for a in range(3)]
        if any(x is None for x in axes):
            scan.append({'latency_ticks': L, 'n': len(P), 'cost': None})
            continue
        cost = sum(x[2] for x in axes)/max(1e-12, sum(x[3] for x in axes))
        scan.append({'latency_ticks': L, 'n': len(P), 'cost': cost})
        if best is None or cost < best[0] - 1e-12:
            best = (cost, L, axes)
    if best is None:
        raise SystemExit(f'FIT_FAILED: fewer than {MIN_TICKS} loaded moving ticks or a degenerate axis')
    _, L, axes = best
    per_axis = {name: {'gain': g, 'bias_per_tick': b, 'r2': 1 - sse/sst if sst > 0 else None, 'n': n}
                for name, (g, b, sse, sst, n) in zip(AXES, axes)}
    for name, v in per_axis.items():
        if not v['gain'] > 0:
            raise SystemExit(f'FIT_FAILED: non-positive {name} gain {v["gain"]!r}')
    cal = {'forward_m_per_pct_s': per_axis['forward']['gain'], 'lateral_m_per_pct_s': per_axis['lateral']['gain'],
           'yaw_deg_per_pct_s': per_axis['yaw']['gain'], 'latency_ticks': L,
           'forward_bias_m_per_s': per_axis['forward']['bias_per_tick']/hc.DT,
           'lateral_bias_m_per_s': per_axis['lateral']['bias_per_tick']/hc.DT,
           'yaw_bias_deg_per_s': per_axis['yaw']['bias_per_tick']/hc.DT}
    return cal, per_axis, scan


def drift(seqs, cal):
    """Dead-reckon one robot's loaded runs with the fitted model; worst error per metre / per radian."""
    worst_xy = worst_yaw = 0.
    path_total = 0.
    for run in seqs:
        if len(run) < 10:
            continue
        o = hc.OwnOdometry(cal, sigma_xy_per_m=0., sigma_yaw_per_rad=0., pose=run[0][2])
        gt, path, turn = run[0][2], 0., 0.
        for u, d, _a in run:
            o.pending.append(u); f, l, t = o.pending.pop(0)
            dx = f*cal['forward_m_per_pct_s']; dy = l*cal['lateral_m_per_pct_s']
            dth = math.radians(t*cal['yaw_deg_per_pct_s'])
            if f or l or t:
                dx += cal['forward_bias_m_per_s']*hc.DT; dy += cal['lateral_bias_m_per_s']*hc.DT
                dth += math.radians(cal['yaw_bias_deg_per_s']*hc.DT)
            o.pose = ct.compose(o.pose, (dx, dy, dth))
            gt = ct.compose(gt, (d[0], d[1], math.radians(d[2])))
            path += math.hypot(d[0], d[1]); turn += abs(math.radians(d[2]))
        path_total += path
        if path > .2:
            worst_xy = max(worst_xy, math.hypot(o.pose[0] - gt[0], o.pose[1] - gt[1])/path)
        worst_yaw = max(worst_yaw, abs(ct.wrap(o.pose[2] - gt[2]))/max(turn, .1))
    return worst_xy, worst_yaw, path_total


# ------------------------------------------------------------------ main

def world_samples(run, entry, static_map):
    raw = run/f"world-{entry['world']:03d}"/'raw'
    rec = {'run': str(run), 'world': entry['world'], 'seed': entry.get('seed')}
    result = read_json(raw/'result.json') or {}
    # beam-end roles from the recorded handover offsets (teal end at -x of the beam frame); the replay check guards it
    offsets = (result.get('carry') or {}).get('offsets') or {}
    roles = {rid: ('teal' if off[0] < 0 else 'blue') for rid, off in offsets.items()}
    rows = read_jsonl(raw/'eval-only.jsonl')
    hlog = read_jsonl(raw/'hybrid-drive.jsonl')
    if hlog and rows:
        cmds = hybrid_log_commands(hlog)
        roles = {rid: None for rid in sorted(next(iter(cmds.values())))} if cmds else roles
        rec.update(source='hybrid_code_log', ticks=len(cmds))
        return rec, sequences(cmds, rows, roles)
    if rows and result.get('carry'):
        teacher, check = replay_teacher(result, rows, static_map, roles)
        rec['replay'] = check
        if teacher is None:
            rec.update(excluded=check.get('reason'))
            return rec, None
        ev = read_json(raw/'carry-eval.json') or result.get('carry_eval') or {}
        rec['drive_response_matches'] = drive_response_matches(ev.get('drive_response'), rows, teacher, roles)
        if rec['drive_response_matches'] is False:
            rec.update(excluded='drive_response_differs_from_record')
            return rec, None
        cmds = {round(e['t'], 6): {rid: {'wheels': e['wheels'][rid], 'duration_s': e['duration_s'][rid]}
                                   for rid in roles}
                for e in teacher.log if e['issue_phase'] in LOADED_PHASES}
        rec.update(source='teacher_replay', ticks=len(cmds))
        return rec, sequences(cmds, rows, roles)
    rec.update(excluded='no_per_tick_source' if (result.get('carry') or read_json(raw/'carry-eval.json'))
               else 'no_carry')
    return rec, None


def run_fit(runs, *, static_map_path=DEFAULT_MAP, max_latency=MAX_LATENCY):
    static_map = json.loads(Path(static_map_path).read_text())
    worlds, seqs_all, per_robot = [], [], []
    for run in runs:
        summary = read_json(run/'summary.json')
        if summary is None:
            raise SystemExit(f'MISSING_SUMMARY: {run}/summary.json')
        for entry in summary.get('worlds') or []:
            if entry.get('seed') not in hc.FIT_SEEDS:
                raise SystemExit(f'SEED_NOT_ALLOWED: {run} world {entry.get("world")} seed {entry.get("seed")} '
                                 '(fit uses pilot 8343000-8343039 and smoke 8420001/8420011/8420017 only)')
            rec, seqs = world_samples(run, entry, static_map)
            worlds.append(rec)
            if seqs:
                for rid, s in seqs.items():
                    seqs_all.extend(s); per_robot.append((rec, rid, s))
    used = [w for w in worlds if 'excluded' not in w]
    if not used:
        raise SystemExit('NO_FIT_DATA: no world with per-tick loaded commands (see excluded reasons)')
    cal, per_axis, scan = fit(seqs_all, max_latency)
    sig_xy = sig_yaw = 0.
    for rec, rid, s in per_robot:
        exy, eyaw, path = drift(s, cal)
        rec.setdefault('drift', {})[rid] = {'xy_per_m': exy, 'yaw_per_rad': eyaw, 'path_m': path}
        sig_xy, sig_yaw = max(sig_xy, exy), max(sig_yaw, eyaw)
        P = pairs(s, cal['latency_ticks'])
        rec.setdefault('gains', {})[rid] = {n: (solve_axis(P, a) or (None,))[0] if len(P) >= 10 else None
                                            for a, n in enumerate(AXES)}
    if not (sig_xy > 0 and sig_yaw > 0):
        raise SystemExit('FIT_FAILED: zero drift estimate (too little loaded motion)')
    sigma = {'sigma_xy_per_m': sig_xy, 'sigma_yaw_per_rad': sig_yaw}
    return {'schema': SCHEMA, 'fit_quality': 'per_tick', 'calibration': cal, 'sigma': sigma,
            'values_sha256': hc.calibration_values_sha256(cal, sigma),
            'model': 'd_k = gain*u_{k-L} + bias*moving_{k-L}; u = own command percent-seconds (hybrid_carry.wheel_body)',
            'per_axis': per_axis, 'latency_scan': scan,
            'seeds': sorted({w['seed'] for w in used}), 'sources': sorted({f"{w['run']}/world-{w['world']:03d}"
                                                                           for w in used}),
            'worlds': worlds, 'excluded': [w for w in worlds if 'excluded' in w],
            'labels': ['offline_fit', 'gt_eval_only_labels', 'not_learned', 'pilot_and_smoke_seeds_only'],
            'tool': 'scripts/fit_loaded_odom.py', 'teacher_tree_sha': _head()}


def _head():
    try:
        return subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def markdown(rep):
    c, s = rep['calibration'], rep['sigma']
    L = ['# 적재 상태 오도메트리 적합 (offline, GT는 라벨로만 사용)', '',
         f"- 세계 {len(rep['worlds'])}개 중 사용 {len(rep['sources'])}개, seed {rep['seeds']}",
         f"- 지연 {c['latency_ticks']} tick, 이득 전진 {c['forward_m_per_pct_s']:.6g} m/(%·s), 횡 "
         f"{c['lateral_m_per_pct_s']:.6g} m/(%·s), 회전 {c['yaw_deg_per_pct_s']:.6g} deg/(%·s)",
         f"- 편향(이동 중) 전진 {c['forward_bias_m_per_s']:.4g} m/s, 횡 {c['lateral_bias_m_per_s']:.4g} m/s, 회전 "
         f"{c['yaw_bias_deg_per_s']:.4g} deg/s",
         f"- 최악 drift: {s['sigma_xy_per_m']:.4g} m/m, {s['sigma_yaw_per_rad']:.4g} rad/rad",
         f"- values_sha256 `{rep['values_sha256']}`", '',
         '| 축 | 이득 | 편향/tick | R² | n |', '|---|---|---|---|---|']
    for k, v in rep['per_axis'].items():
        L.append(f"| {k} | {v['gain']:.6g} | {v['bias_per_tick']:.4g} | "
                 f"{'-' if v['r2'] is None else format(v['r2'], '.3f')} | {v['n']} |")
    L += ['', '| 지연 tick | n | 정규화 잔차 |', '|---|---|---|']
    L += [f"| {x['latency_ticks']} | {x['n']} | {'-' if x['cost'] is None else format(x['cost'], '.4f')} |"
          for x in rep['latency_scan']]
    L += ['', '| run/world | seed | 출처 | tick | 제외 사유 |', '|---|---|---|---|---|']
    L += [f"| {Path(w['run']).name}/{w['world']} | {w['seed']} | {w.get('source', '-')} | {w.get('ticks', '-')} | "
          f"{w.get('excluded', '')} |" for w in rep['worlds']]
    return '\n'.join(L) + '\n'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--run', type=Path, action='append', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--static-map', type=Path, default=DEFAULT_MAP)
    p.add_argument('--max-latency', type=int, default=MAX_LATENCY)
    a = p.parse_args(argv)
    rep = run_fit(a.run, static_map_path=a.static_map, max_latency=a.max_latency)
    a.out.mkdir(parents=True, exist_ok=True)
    path = a.out/'loaded-odom-fit.json'
    path.write_text(json.dumps(rep, indent=1, ensure_ascii=False, allow_nan=False))
    (a.out/'loaded-odom-fit.md').write_text(markdown(rep))
    print(json.dumps({'fit': str(path), 'fit_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'values_sha256': rep['values_sha256'], 'calibration': rep['calibration'],
                      'sigma': rep['sigma'], 'used': len(rep['sources']), 'excluded': len(rep['excluded'])},
                     ensure_ascii=False))
    return rep


if __name__ == '__main__':
    main()
