"""Recount saved validation slot probes using the exact wheel-label alphabet.

No inference, physics, labels or actor inputs change. Original float projections
are preserved: a nominal pure turn's ~1e-9 translation is not an end reversal.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path

from harness.grasp_act_data import read_json, sha256, write_json
from scripts.beamact1_runtime import require_gcp2
from scripts.grasp_act_training_guard import source_sha


def canonical(v):
    # The four-wheel mecanum sum uses coefficients +/-1/4. Each observed
    # categorical wheel is -0.35,0,+0.35; hence every unpulsed body component
    # is an integer multiple of0.35/4. This is algebra, not a fitted deadband.
    if len(v) != 3 or not all(math.isfinite(x) for x in v):
        raise ValueError('finite three-axis saved wheel mix required')
    return [round(x / (.35 / 4)) for x in v]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm', choices=('A', 'B'), required=True)
    p.add_argument('--summary', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); host = require_gcp2(training=False); source = source_sha()
    d = read_json(a.summary)
    if d['status'] != 'complete' or d['arm'] != a.arm or a.output.exists():
        raise ValueError('complete matching arm and new output required')
    lease = Path('/home/ugrp/ugrp-sim/leases') / ('beamact3-' + a.arm + '-role-direction.json')
    now = datetime.now(timezone.utc)
    with lease.open('x') as f:
        json.dump(dict(task='beamact3-' + a.arm + '-role-direction', pid=os.getpid(), start=now.isoformat(),
                       expected_end=(now + timedelta(minutes=5)).isoformat(), concurrency=0), f)
    try:
        rows = []; groups = defaultdict(list)
        for r in d['role_interventions']:
            u = canonical(r['original_motion']); v = canonical(r['swapped_motion'])
            dot = u[0] * v[0] + u[1] * v[1]
            cross = u[0] * v[1] - u[1] * v[0]
            one = bool(u[0] or u[1]); two = bool(v[0] or v[1])
            row = dict(seed=r['seed'], robot=r['robot'], probe=r['probe'], t=r['t'],
                       original_mix_quanta=u, swapped_mix_quanta=v,
                       wheel_class_changed=r['wheel_class_changed'],
                       raw_float_translation_reversed=r['translation_reversed'],
                       translation_reversed=dot < 0,
                       nonzero_heading_changed=bool(one and two and (cross or dot < 0)),
                       translation_starts_or_stops=one != two,
                       turn_sign_flipped=u[2] * v[2] < 0)
            rows.append(row); groups[r['probe']].append(row)
        fields = ('wheel_class_changed', 'raw_float_translation_reversed', 'translation_reversed',
                  'nonzero_heading_changed', 'translation_starts_or_stops', 'turn_sign_flipped')
        metrics = {name: dict(N=len(rs), **{key: sum(bool(r[key]) for r in rs) for key in fields})
                   for name, rs in groups.items()}
        write_json(a.output, dict(complete=True, arm=a.arm, host=host, source_sha=source,
            audit_script_sha256=sha256(Path(__file__)), input=str(a.summary), input_sha256=sha256(a.summary),
            original_analysis_source_sha=d['source_sha'], model_sha256=d['model_sha256'],
            method='integer unpulsed body mix quanta, exact observed wheel alphabet0.35 divided by4; no fitted deadband',
            metrics=metrics, rows=rows, new_inferences=0, new_physical_runs=0,
            scope='saved validation initial/first-approach role-only h0 probes; separate from pulse-weighted cold-start40; not correct-end success'))
        print(json.dumps(dict(arm=a.arm, metrics=metrics)))
    finally:
        lease.unlink()


if __name__ == '__main__':
    main()
