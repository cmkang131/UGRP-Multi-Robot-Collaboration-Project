"""Finalize derived metadata from closed originals on the owned L4."""
from pathlib import Path
from itertools import islice
from datetime import datetime, timezone
import hashlib
import json

B = Path('/home/ugrp/ugrp-sim')
R = B / 'runs/act16w-native-experiment-r1'


def read(p):
    return json.loads(p.read_text())


def receipt(p):
    return dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def write(name, value):
    with (R / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


d = read(R / 'independent-final40.json')
g = read(R / 'final40-geometry-summary.json')
assert d['complete'] and d['N'] == 40 and d['raw_recomputed_metrics_match_original']
eligible = d['rows'].copy()
funnel = [dict(gate='scored', passed=40, rejected=0)]
for key in ('bilateral_load_observed', 'lift_success', 'release_success', 'task_success'):
    previous = len(eligible)
    eligible = [row for row in eligible if row[key]]
    funnel.append(dict(gate=key, passed=len(eligible), rejected=previous-len(eligible)))
write('native-final-physical-funnel.json', dict(funnel=funnel,
    independent_sequence_done=d['independent_stage_counts']['issued_sequence_complete'],
    scope='cumulative physical order; original done-first conjunction funnel retained separately', source=receipt(R/'independent-final40.json')))
counterexamples = [row['seed'] for row in d['rows'] if row['lift_success'] and
    next(x for x in g['rows'] if x['seed'] == row['seed'])['alignment_rejection']]
write('native-alignment-diagnostic-counterexample.json', dict(
    alignment_rejections=g['alignment_rejections'], N=40, stable_lift_counterexamples=counterexamples,
    necessary_condition_validated=False, failure_cause_proven=False, thresholds_changed=False,
    explanation='teacher geometric readiness proxy is narrower than physical grasp success; do not treat rejection as a necessary condition or all-run cause',
    selection_unchanged='A/B/C/D1 validation successes0/8 and diagnostic counts8/8 tied; preregistered fallbackA remains frozen',
    sources=[receipt(R/'independent-final40.json'), receipt(R/'final40-geometry-summary.json')]))
first30 = read(R / 'native-final-first30-statistics.json')
prefix_rows = []
for row in first30['raw']:
    if 'preserved_prefix' not in row:
        continue
    with Path(row['original']).open('rb') as stream:
        original_prefix = b''.join(islice(stream, 300))
    saved = Path(row['preserved_prefix']).read_bytes()
    assert saved == original_prefix
    assert hashlib.sha256(saved).hexdigest() == row['prefix_sha256']
    prefix_rows.append(dict(original=row['original'], prefix_sha256=row['prefix_sha256']))
assert len(prefix_rows) == 7
write('native-final-first30-prefix-final-check.json', dict(status='verified', N=7,
    prefixes=prefix_rows, scope='live first300-line snapshots exactly match closed final originals'))
reviews = [R/f'native-final-{seed}-playback-review.json' for seed in (91620, 91621, 91637)]
assert all(read(p)['status'] == 'reviewed' for p in reviews)
montage = read(R / 'native-final-montage.json')
assert hashlib.sha256((R/'native-final-montage.png').read_bytes()).hexdigest() == montage['montage_sha256']
verification = B/'runs/act16w-native-release-public-verify-r1/summary.json'
public = read(verification)
assert public['complete'] and len(public['models']) == 4
assert all(row['loading_exit_code'] == 0 for row in public['models'])
report = read(R/'summary.json')
value = dict(schema='ugrp.act16w.native-final-results.v1', utc=datetime.now(timezone.utc).isoformat(),
    scientific_evaluation_complete=True, physical_ready=False, contact_profile='warp_native_contact_v1',
    execution_source_sha=report['execution_source_sha'], orchestration_source_sha=report['source_sha'],
    final_selection=read(R/'final-selection.json'),
    validation={arm: dict(n=row['n'], N=row['N'], alignment_rejections=row['alignment_rejections'])
                for arm, row in report['metrics'].items()},
    final=dict(n=d['n'], N=40, kinds=d['kinds'], n_any_same_kind=d['n_any_same_kind'],
               cap_end=d['cap_end'], resource_cap_end=d['resource_cap_end'], HOST_ERROR=0,
               independent_stages=d['independent_stage_counts'], cumulative_physical_funnel=funnel,
               initial_same_kind_visibility={key:value for key,value in read(R/'final40/summary.json')['initial_same_kind_visibility'].items() if key!='rows'}),
    geometric_diagnostic=dict(rejections=g['alignment_rejections'], stable_lift_counterexamples=counterexamples,
        necessary_condition_validated=False, causal_failure_claim=False),
    effects=dict(h4_observed_success_delta_pp=0, h5_observed_success_delta_pp=0,
                 scope='matched VAL8 only; not proof of zero general effect'),
    model_distribution=dict(artifacts=4, internal_files_verified=76, CPU_loading_verified=4,
                            verification=receipt(verification)),
    playback=dict(actual_student_task_success_examples=0, teacher_success_reference=True,
                  direct_reviews=[receipt(p) for p in reviews], montage=receipt(R/'native-final-montage.json')),
    raw=[receipt(R/'independent-final40.json'), receipt(R/'rejection-table-final40-enriched.json')],
    limits=['h1/h2/h3 off and unevaluated', 'DAgger290h0/270noninitial from7starts, not full recovery expert qualification',
            'C CPU physics comparisonN0', 'existing ACT environment CPU loading, not clean venv',
            'native and noslip10 results never pooled', 'draft PR, independent control/preregistration review outstanding'])
write('native-final40-results-v1.json', value)
print(json.dumps(dict(status='complete', n=d['n'], N=40, physical_funnel=funnel, alignment_counterexamples=counterexamples)))
