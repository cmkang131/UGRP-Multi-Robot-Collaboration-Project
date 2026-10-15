"""Build the delivery JSON from separately verified cohorts, never pooling runs."""
from pathlib import Path
import collections
import hashlib
import json

HERE=Path(__file__).resolve().parent
gate=json.loads((HERE/'gate-summary.json').read_text())
runtime=json.loads((HERE/'runtime-verification.json').read_text())
assert gate['stage']=='gate'
verified=(not gate['hash_errors'] and not gate['population_hash_errors'] and
          gate['false_accepts']==0 and gate['all_release25_mode'] and
          gate['all_pinned_scene'] and runtime['all_sources_pinned'])
cohorts=gate['cohorts']
ready=verified and all(c['N']==40 and c['success']>=38 and
          not any(c['categories'].get(k,0) for k in ('not_started','HOST_ERROR','supervisor_stop'))
          for c in cohorts.values())
files={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in
       ('gate-summary.json','gate-rejection_table.json','gate-population-funnels.json',
        'gate-candidate-funnels.json','gate-config.json','gate-DONE.json',
        'runtime-verification.json','gate-retrieval-verification.json')}
value=dict(task='release25',verdict='READY' if ready else 'NOT_READY',
    source_sha=gate['source_sha'],host='gcp2',cohorts=cohorts,
    categories=dict(collections.Counter(r['category'] for r in gate['runs'])),
    input_audit_all_zero=all(r.get('audit_ok') for r in gate['runs'] if r.get('started')),
    manifest_files_verified=gate['manifest_files_verified'],hash_errors=gate['hash_errors'],
    false_accepts=gate['false_accepts'],all_sources_pinned=runtime['all_sources_pinned'],
    first16_first30_wall_per_sim_median=json.loads((HERE/'gate-first30.json').read_text())['median'],
    toggle='release_sweep_wall_aware_v1',default='off',
    pr='https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/535',
    cause='Initial uncertainty-inflated robot footprint overlaps north wall; old whole-hull test rejects even a monotone wall-away translation. No northward sweep or body turn was commanded.',
    prior_results_pooled=False,training_rgb=False,model_calls=0,student_execution=False,
    mac_physics_render_gui=0,files_sha256=files,
    runs=[{k:r.get(k) for k in ('name','seed','candidate','category','raw','source_sha',
          'recount_success','audit','sim_s','wall_s','outcome','settled_s','settle_recount')}
          for r in gate['runs']],
    separate_short_rounds={label:json.loads((HERE/(label+'-summary.json')).read_text())['cohorts']
                           for label in ('short-r1','short-r2')},
    scope='New-scene C MuJoCo release teacher gate, gcp2 only. No ACT/student, unseen-scene, real-robot or merged-main claim. Raw remains on gcp2, not an independent backup.')
(HERE/'summary.json').write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps({k:v for k,v in value.items() if k in ('verdict','cohorts','categories','input_audit_all_zero','manifest_files_verified')}))
