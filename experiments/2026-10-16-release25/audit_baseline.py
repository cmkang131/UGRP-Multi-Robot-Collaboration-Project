"""gcp2 saved-output audit only; no physics/rendering or controller feedback."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT = Path('/home/ugrp/ugrp-sim')
OLD = ROOT/'ops-reviews/gatesv5'
OUT = ROOT/'ops-reviews/release25'


def read(p):
    return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd', '-qdc', str(p)+'.zst']))


def main():
    sys.path.insert(0, str(ROOT/'src/a41781dd122b1e20b8eec7e43c553e779e6cfc30'))
    from harness.zone_final_environment import resolve
    from harness.static_keepouts import disc_footprint, polygon_at, rect_corners
    from sim.release23 import _polygon_gap
    done = read(OLD/'release-gate-a41781dd-attempt3/DONE.json')
    rows = []
    for attempt in done['completed']:
        raw = Path(attempt['raw']); d = read(raw/'result.json')
        static, _, _ = resolve(read(raw/'plan.json')['map_id'])
        wall = next(o for o in static['obstacles'] if o['id']=='wall_north')
        rect = (*wall['center_m'], *wall['half_extents_m'], wall.get('yaw_rad', 0.))
        gaps = [c['minimum_gap'] for s in d.get('release23_sweep_checks', [])
                for c in s['checks'] if c['blocking_object']=='wall_north']
        locs = {}
        for rid, value in (d.get('lookaround_result') or {}).items():
            l = value['localizer']; halo = max(.02, 2*max(l['final_sigma'][:2]))
            p = polygon_at(l['final_estimate'], disc_footprint(.18))
            locs[rid] = dict(pose=l['final_estimate'], sigma=l['final_sigma'], halo_m=halo,
                nominal_north_gap_m=_polygon_gap(p, rect_corners(rect)),
                inflated_north_gap_m=_polygon_gap(p, rect_corners(rect, margin=halo)),
                look_sweeps=[{k:v for k,v in s.items() if k in ('before','after','t0','sim_s','script')}
                             for s in value['evaluation']['sweeps']])
        source = raw/'result.json'; source = source if source.exists() else Path(str(source)+'.zst')
        rows.append(dict(run=attempt['name'], candidate=attempt['candidate'], seed=attempt['seed'],
            category=attempt['category'], outcome=d.get('release_outcome'), raw=str(raw),
            result_stored_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            north_min_swept_gap_m=min(gaps) if gaps else None, north_swept_gaps_m=gaps,
            localizers=locs, backoff=d.get('map_backoff_checks'), choices=d.get('code_decisions'),
            teachers=d.get('teachers'), input_audit={k:d.get('input_audit',{}).get(k)
                for k in ('invisible_measurements','held_world_reads','control_top_camera_reads')}))
    success = [r for r in rows if r['category']=='success']
    def quantiles(values):
        return dict(N=len(values), **{str(p):float(np.quantile(values,p)) for p in (0,.05,.25,.5,.75,.95,1)}) if values else dict(N=0)
    summary = dict(rows=rows, counts=dict(collections.Counter(r['category'] for r in rows)),
        success_north_sweep=quantiles([r['north_min_swept_gap_m'] for r in success if r['north_min_swept_gap_m'] is not None]),
        success_final_nominal=quantiles([l['nominal_north_gap_m'] for r in success for l in r['localizers'].values()]),
        success_final_inflated=quantiles([l['inflated_north_gap_m'] for r in success for l in r['localizers'].values()]),
        baseline_rejection_table=read(OLD/'release-gate-analysis-a41781dd-attempt3/rejection_table.json'),
        scope='Saved own estimates and issued geometry; evaluation poses only in labelled look_sweeps for diagnosis. Final pose gaps are not swept-path gaps. No truth is delivered to a controller.',
        reproduce=f'{ROOT}/ugrp/.venv-sim/bin/python {Path(__file__).resolve()}')
    OUT.mkdir(exist_ok=True)
    (OUT/'baseline-audit.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('rows','baseline_rejection_table')}, indent=2))


if __name__=='__main__':
    main()
