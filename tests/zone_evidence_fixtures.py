"""Pure JSON/sample fixtures shared by offline and optional TensorBoard jobs.

No executor, camera library, simulator or runner is imported; no model is called.
"""
import hashlib
import json
from pathlib import Path

from harness.zone_study_contract import digest, scenario_ref
from harness import zone_study_eval as ev
from scripts import zone_study_evidence_join as j
from scripts.zone_study_evidence_contract import identity_for, per_order_evaluation, seal_new_evidence, read_auxiliary
from tests.test_zone_study_eval import trial as metric_trial

MAP = json.loads((Path(__file__).resolve().parents[1] / 'maps/zones/zone_wide_door_tags_v2.json').read_text())


def at_zone(zone, **kwargs):
    x, y = MAP['regions'][f'zone_{zone}']['center_m']
    return {'kind': 'cyan', 'x': x, 'y': y, 'yaw': 0., 'z': .016,
            'held': False, 'speed': 0., **kwargs}


def feed(ref, t0, t1, items, dt=.1):
    t = t0
    while t <= t1 + 1e-9:
        ref.observe(round(t, 4), items(round(t, 4)) if callable(items) else items)
        t += dt


def planned(n=3, order_count=2):
    orders = [{'order_id': f'o{i}', 'item_ids': [f'item-{i}'], 'kind': 'cyan',
               'count': 1, 'destination_zone': 'A'} for i in range(order_count)]
    from harness import zone_study_referee as zr
    bundle = {'referee': zr.profile(), 'scene_static_map_sha256': digest(MAP), 'horizon_s': 12., 'host_spec': {'order_sheet': {'scenario_id': scenario_ref('synthetic'), 'orders': orders}}}
    identities = [identity_for(run_id=f'run-{i}', trial_id=f'trial-{i}', condition='no_comm', seed=i,
                               episode_id=f'episode-{i}', scenario='synthetic', attempt=1, bundle=bundle)
                  for i in range(n)]
    plan = j.freeze_plan([j.admission(identity, orders) for identity in identities])
    return plan, bundle


def claims(ref, plan):
    """Project pure referee samples into records without importing a runner."""
    from harness import zone_study_referee as zr
    identity = plan['admitted'][0]['identity']
    record = metric_trial(orders=ref.orders, end_sim_s=ref.last_t or 0., horizon=12.,
                          end_reason='sim_horizon', model={}, requests=[], provenance={})
    zr.apply_to_record(record, ref)
    record.update(evidence_identity=identity, plan_sha256=digest(plan))
    raw = {**ref.record(), **j.envelope_keys(identity, ref.orders),
           'evidence_identity': identity, 'plan_sha256': digest(plan)}
    return record, zr.evaluation_block(record, ref), raw, identity


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n')
    return path


def raw_source(root, plan, bundle, i, success=True):
    """Direct provisional JSON source. No runtime imports or fabricated calls."""
    admitted = plan['admitted'][i]
    identity, orders = admitted['identity'], admitted['orders']
    src = root / identity['run_id']
    # A successful publication now requires the independent raw referee too.
    # Use pure truth samples, never a world or a copied success declaration.
    from harness import zone_study_referee as zr
    referee = zr.Referee(orders, MAP, evidence_key=j.key_for(identity))
    if success:
        feed(referee, 2., 4., {o['item_ids'][0]: at_zone('A') for o in orders})
    deliveries = referee.trial_rows()
    record = metric_trial(condition='no_comm', scenario='synthetic', seed=i, orders=orders,
                          deliveries=deliveries, horizon=12., end_sim_s=5., model={}, requests=[], provenance={},
                          end_reason='orders_complete' if success else 'host_error')
    record.update(trial_id=identity['trial_id'], evidence_identity=identity, record_complete=True,
                  failure_class=None if success else 'infra:HOST_ERROR')
    if success:
        zr.apply_to_record(record, referee)
    record['referee']['status'] = 'evaluated'
    record['referee']['departed_unsettled'] = []
    metrics = ev.efficiency_metrics(record)
    assert metrics['success'] is success
    put(src, 'study/trial_record.json', record)
    (src / 'study/dispatch.jsonl').write_text('')
    (src / 'study/inputs.jsonl').write_text('')
    put(src, 'eval_only/referee.json', referee.record())
    put(src, 'eval_only/evaluation.json', {**metrics, 'orders': per_order_evaluation(record),
                                          'evidence_identity': identity})
    terminal = {'end_reason': record['end_reason'], 'end_sim_s': record['end_sim_s'],
                'failure_class': record['failure_class'], 'sim_horizon_s': 12., 'record_complete': True}
    put(src, 'result.json', {'schema': 'ugrp.zone_study_integration_run.v1', 'run_id': identity['run_id'],
                            'evidence_kind': 'synthetic', 'evidence_identity': identity, 'condition': 'no_comm',
                            'episode': identity['episode_id'], 'scenario': 'synthetic', 'seed': i,
                            'bundle_sha256': digest(bundle), 'terminal': True, 'sim_horizon_s': 12.,
                            'eval_only': {'evaluation': json.loads((src / 'eval_only/evaluation.json').read_text())},
                            'study': terminal, 'failure_class': record['failure_class']})
    put(src, 'manifest.json', {'schema': 'ugrp.zone_study_integration_run.v1', 'run_id': identity['run_id'],
                              'bundle': bundle, 'bundle_sha256': digest(bundle), 'evidence_identity': identity,
                              'terminal': terminal})
    seal_new_evidence(src, plan, digest(plan))
    return src


def read(src, name):
    return json.loads((src / name).read_text())


def refresh_receipts(src):
    """Recompute receipts only, NEVER verdicts, facts, IDs or the frozen plan.

    A checksum is not an independent assertion of cross-record consistency.
    These mutations model a bad join before sealing; no research raw is edited.
    """
    record = read(src, 'study/trial_record.json')
    evaluation = read(src, 'eval_only/evaluation.json')
    inputs = {name: hashlib.sha256((src / name).read_bytes()).hexdigest()
              for name in ('study/trial_record.json', 'eval_only/referee.json')
              if (src / name).exists()}
    evaluation['derived'] = j.derivations(
        {k: v for k, v in evaluation.items() if k != 'derived'}, inputs,
        [record['evidence_key'], *record['order_keys']],
    )
    put(src, 'eval_only/evaluation.json', evaluation)
    result = read(src, 'result.json')
    result['eval_only']['evaluation'] = evaluation
    if result['eval_only'].get('referee') is not None:
        result['eval_only']['referee'] = read(src, 'eval_only/referee.json')
    put(src, 'result.json', result)
    auxiliary = read_auxiliary(
        lambda name: read(src, name),
        lambda name: [json.loads(line) for line in (src / name).read_text().splitlines()],
        {str(p.relative_to(src)) for p in src.rglob('*') if p.is_file()},
    )
    put(src, 'study/record_index.json', j.record_index(record, record['evidence_identity'], auxiliary))
    reseal(src)


def reseal(src):
    manifest = read(src, 'manifest.json')
    manifest['files'] = {str(p.relative_to(src)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in src.rglob('*') if p.is_file() and p.name != 'manifest.json'}
    put(src, 'manifest.json', manifest)
