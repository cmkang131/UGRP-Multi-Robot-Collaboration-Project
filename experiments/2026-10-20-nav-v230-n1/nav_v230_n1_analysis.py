#!/usr/bin/env python3
"""Eval-only N1 recount: r5 acceptance table + stage-1 spawn-lane diagnostics.

N1 is r5 plus one stage-1 rule: until the ground-projection door pass (the r5
stage-2 latch) the aim direction is bounded to +-10 deg around the robot's own
spawn lane in the own-odometry frame.  Stage 2, the arming bearing and the
0.52 m / 1.0 m claim are r5-identical.

This tool reuses the already-validated r5 recount unchanged (VALID, GT 2/2,
claim 2/2, mismatch 0, FP 0, boundary 0, stage-2 and scene-contact diagnostics)
and adds only N1's *report-only* fields:

- the stage-1 lane bound: how many ticks it was active, how many it actually
  clamped, the raw/applied aim ranges in the lane frame, and that no bound tick
  survives the stage-2 latch (release);
- the **minimum base collision-box separation** as a report metric with a
  documented 0.10 m reference.  This is explicitly **not** an acceptance
  condition: the acceptance table stays the r5 table.
- an optional per-seed table (`--table`) that never pools the seeds: every seed
  keeps its own PASS/FAIL row.

Everything is evaluation-only: the static map, GT and contacts are read here and
never returned to a controller.  The script writes one JSON report and never
writes into the run directory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'ugrp.e2ewarp.nav_v230_n1_analysis.v1'
TABLE_SCHEMA = 'ugrp.e2ewarp.nav_v230_n1_seed_table.v1'
R5_TOOL = ROOT / 'experiments/2026-10-20-nav-v230-r5/nav_v230_r5_analysis.py'
R4_TOOL = ROOT / 'experiments/2026-10-19-nav-v230-r4/nav_v230_r4_analysis.py'
#: Report-only reference (prereg N1): the pair's base collision boxes should be
#: reported against 0.10 m.  This is NOT an acceptance constant and never
#: changes `acceptance.pass_`; it is a distance the pair should stay above.
BASE_BOX_REPORT_REFERENCE_M = 0.10


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R5 = _load(R5_TOOL, 'nav_v230_r5_analysis')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text())


def _num(value, digits=4):
    return None if value is None else round(float(value), digits)


def _rows(run):
    rows = load_json(Path(run) / 'localization.json') or []
    return sorted(rows, key=lambda r: (str(r.get('robot')), float(r['sim_s'])))


# --- N1 stage-1 spawn-lane bound --------------------------------------------
def spawn_lane_report(run):
    """Per-robot stage-1 lane-bound record from the own navigation reports.

    The fields exist only in an N1 run (`v230_n1`); on an r4/r5 run the report
    says ``available=False`` instead of inventing zeros.
    """
    rows = _rows(run)
    robots = sorted({str(r.get('robot')) for r in rows if r.get('robot')})
    out = {}
    for robot in robots:
        own = [(float(r['sim_s']), r.get('own_navigation') or {})
               for r in rows if str(r.get('robot')) == robot]
        limit = next((o.get('spawn_lane_limit_deg') for _t, o in own
                      if o.get('spawn_lane_limit_deg') is not None), None)
        active = [(t, o) for t, o in own if o.get('spawn_lane_active') is True]
        raw = [float(o['spawn_lane_aim_raw_deg']) for _t, o in active
               if o.get('spawn_lane_aim_raw_deg') is not None]
        applied = [float(o['spawn_lane_aim_applied_deg']) for _t, o in active
                   if o.get('spawn_lane_aim_applied_deg') is not None]
        follow_raw = [float(o['follow_bearing_raw_deg']) for _t, o in own
                      if o.get('follow_bearing_raw_deg') is not None]
        follow_applied = [float(o['follow_bearing_applied_deg']) for _t, o in own
                          if o.get('follow_bearing_applied_deg') is not None]
        clamp_ticks = sum(1 for _t, o in active
                          if o.get('spawn_lane_aim_raw_deg') is not None
                          and o.get('spawn_lane_aim_applied_deg') is not None
                          and abs(float(o['spawn_lane_aim_raw_deg'])
                                  - float(o['spawn_lane_aim_applied_deg'])) > 1e-9)
        stage2_s = next((t for t, o in own if o.get('slot_stage2_sim_s') is not None), None)
        stage2_active = [(t, o) for t, o in own if o.get('slot_stage2_active') is True]
        after = [t for t, o in active if stage2_s is not None and t >= stage2_s]
        out[robot] = dict(
            available=limit is not None,
            limit_deg=_num(limit, 3),
            stage2_activation_s=(None if stage2_s is None else round(stage2_s, 3)),
            stage2_active_ticks=len(stage2_active),
            active_ticks=len(active),
            clamped_ticks=clamp_ticks,
            first_active_s=(round(active[0][0], 3) if active else None),
            last_active_s=(round(active[-1][0], 3) if active else None),
            aim_raw_min_deg=(_num(min(raw), 3) if raw else None),
            aim_raw_max_deg=(_num(max(raw), 3) if raw else None),
            aim_applied_min_deg=(_num(min(applied), 3) if applied else None),
            aim_applied_max_deg=(_num(max(applied), 3) if applied else None),
            follow_raw_min_deg=(_num(min(follow_raw), 3) if follow_raw else None),
            follow_raw_max_deg=(_num(max(follow_raw), 3) if follow_raw else None),
            follow_applied_min_deg=(_num(min(follow_applied), 3) if follow_applied else None),
            follow_applied_max_deg=(_num(max(follow_applied), 3) if follow_applied else None),
            active_ticks_after_stage2=len(after),
            released_at_stage2=bool(stage2_s is not None and not after),
            note=('own-camera + own-odometry lane frame only; the aim is clamped to '
                  'the fixed code constant, never a map/GT input' if limit is not None
                  else 'not an N1 run: no spawn_lane_limit_deg field in the rows'))
    return out


# --- report-only base-box separation ---------------------------------------
def base_box_separation_report(base):
    contacts = base.get('contacts') or {}
    value = contacts.get('min_base_box_separation_m')
    available = bool(contacts.get('available') is True and value is not None)
    return dict(
        schema='ugrp.e2ewarp.nav_v230_n1_base_box_separation.v1', eval_only=True,
        available=available,
        min_m=_num(value, 4),
        min_s=(None if contacts.get('min_base_box_separation_s') is None
               else round(float(contacts['min_base_box_separation_s']), 3)),
        reference_m=BASE_BOX_REPORT_REFERENCE_M,
        at_or_above_reference=(None if not available
                               else bool(float(value) >= BASE_BOX_REPORT_REFERENCE_M)),
        report_only=True,
        note=('REPORT-ONLY metric (not an acceptance condition): GT base lower '
              'collision boxes (0.181 x 0.087 m), evaluation-only ledger. '
              'A positive box separation does not prove the real bodies did not '
              'touch; the MJWarp contact channels are the primary contact record.'))


def analyze(run, admission, expected_sha, preflight=None, seed=None):
    run = Path(run).resolve()
    base = R5.R4.recount(run, Path(admission).resolve(), expected_sha)
    robots = tuple(base.get('robots') or ())
    base['schema'] = SCHEMA
    base['tools'] = dict(
        r4=dict(path=str(R4_TOOL.relative_to(ROOT)), sha256=sha(R4_TOOL)),
        r5=dict(path=str(R5_TOOL.relative_to(ROOT)), sha256=sha(R5_TOOL)),
        n1=dict(path=str(Path(__file__).resolve().relative_to(ROOT)),
                sha256=sha(Path(__file__))))
    base['n1'] = dict(
        mode=base.get('queue_markers', {}).get('nav_gate_mode'),
        seed=seed,
        spawn_lane=spawn_lane_report(run),
        slot_stage2=R5.slot_stage2_report(run),
        scene_contacts=R5.scene_contact_report(run),
        wall_clearance=R5.wall_clearance_report(run, base),
        command_vs_gt=R5.command_vs_gt(run, base, robots),
        base_box_separation=base_box_separation_report(base),
        scope='r5 acceptance table unchanged; N1 adds the stage-1 lane bound and '
              'the report-only base-box separation')
    base['acceptance'] = R5.acceptance(base, n_robots=len(robots),
                                      preflight=preflight)
    return base


def summary(base):
    acceptance = base['acceptance']
    n1 = base['n1']
    sep = n1['base_box_separation']
    return dict(
        out=None, schema=SCHEMA, seed=n1.get('seed'),
        mode=n1.get('mode'), status=base.get('status'),
        valid=acceptance['valid'], pass_=acceptance['pass_'],
        gt_arrival_n=acceptance['gt_arrival_n'],
        claim_n=acceptance['claim_n'],
        mismatch=acceptance['claim_mismatch_n'],
        fp_render_zone_free_detections=acceptance['fp_render_zone_free_detections'],
        boundary_violations=acceptance['boundary_violations'],
        scene_contact_ticks=n1['scene_contacts']['contact_ticks'],
        lane={r: dict(active=v['active_ticks'], clamped=v['clamped_ticks'],
                      released=v['released_at_stage2'])
              for r, v in n1['spawn_lane'].items()},
        base_box_min_m=sep['min_m'], base_box_min_s=sep['min_s'],
        base_box_at_or_above_0_10=sep['at_or_above_reference'],
        base_box_note='report-only; not part of PASS')


def seed_table(paths):
    rows = []
    for path in paths:
        base = load_json(path)
        if not base:
            raise SystemExit('analysis JSON not found: ' + str(path))
        acceptance = base.get('acceptance') or {}
        sep = ((base.get('n1') or {}).get('base_box_separation') or {})
        lane = ((base.get('n1') or {}).get('spawn_lane') or {})
        rows.append(dict(
            analysis=str(path),
            seed=((base.get('n1') or {}).get('seed')),
            mode=((base.get('n1') or {}).get('mode')),
            status=base.get('status'),
            valid=acceptance.get('valid'),
            pass_=acceptance.get('pass_'),
            gt_arrival_n=acceptance.get('gt_arrival_n'),
            claim_n=acceptance.get('claim_n'),
            claim_mismatch_n=acceptance.get('claim_mismatch_n'),
            fp_render_zone_free_detections=acceptance.get('fp_render_zone_free_detections'),
            boundary_violations=acceptance.get('boundary_violations') or [],
            scene_contact_ticks=((base.get('n1') or {}).get('scene_contacts') or {}).get('contact_ticks'),
            base_box_min_m=sep.get('min_m'),
            base_box_at_or_above_0_10=sep.get('at_or_above_reference'),
            lane_active_ticks={r: v.get('active_ticks') for r, v in lane.items()},
            lane_clamped_ticks={r: v.get('clamped_ticks') for r, v in lane.items()},
            verdict=('PASS' if acceptance.get('pass_') else 'FAIL')))
    return dict(
        schema=TABLE_SCHEMA, eval_only=True, per_seed=rows,
        seed_verdicts={str(r['seed']): r['verdict'] for r in rows},
        pooling=False,
        note=('per-seed verdicts only; seeds are never pooled and no combined '
              'success rate is reported. The minimum base-box separation is a '
              'report-only metric, not an acceptance condition.'))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path)
    p.add_argument('--admission', type=Path)
    p.add_argument('--expected-source-sha')
    p.add_argument('--out', type=Path)
    p.add_argument('--preflight-render', type=Path,
                   help='render_check.py measure.json for the FP 0 row')
    p.add_argument('--seed', type=int, default=None)
    p.add_argument('--table', nargs='+', type=Path, default=None,
                   help='build the per-seed table from existing analysis JSONs')
    p.add_argument('--table-out', type=Path)
    a = p.parse_args(argv)
    if a.table:
        table = seed_table(a.table)
        out = a.table_out
        if out is not None:
            out.write_text(json.dumps(table, ensure_ascii=False, indent=1) + '\n')
            table['out'] = str(out)
        print(json.dumps(table, ensure_ascii=False, indent=1))
        return 0
    if not (a.run and a.admission and a.expected_source_sha):
        p.error('--run, --admission and --expected-source-sha are required')
    base = analyze(a.run, a.admission, a.expected_source_sha,
                   preflight=a.preflight_render, seed=a.seed)
    out = a.out or (a.run.resolve().parent / (a.run.name + '-n1-analysis.json'))
    out.write_text(json.dumps(base, ensure_ascii=False, indent=1) + '\n')
    result = summary(base)
    result['out'] = str(out)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
