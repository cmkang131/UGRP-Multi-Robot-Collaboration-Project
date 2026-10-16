"""Managed, explicitly opted-in S2 DEV freeze profile; no auto-admitted probe."""
import json
import sys
from harness import zone_s2_realism_contract_v118 as contract
from harness.zone_final_pair_binding import bind
from scripts import run_s2_realism_v117 as previous


def parser():
    p = previous.parser()
    p.description = __doc__
    # A profile preview has no new seed. Execution requires a later committed
    # exploratory DEV admission; the historical v117 seed stays consumed.
    seed = next(a for a in p._actions if a.dest == 'seed')
    seed.choices, seed.required = None, False
    p.add_argument('--idle-robot-contacts', choices=('off','freeze_v1'), default='off')
    return p


def run(bundle, out, *, stage='place', runtime_factory=None, backend_factory=None):
    contract.require_execution(bundle)
    if stage != bundle['stage_probe']:
        raise ValueError('S2 stage differs from admitted bundle')
    if backend_factory is None:
        from sim.s2_idle_contacts import backend_class
        backend_factory = backend_class()
    def write(path, value):
        if path.name == 'result.json':
            value.update(result_condition=bundle['result_condition'],pool_with_previous_s2=False,
                         comparison_metrics=['wall_per_sim'])
        previous.write(path,value)

    result = bind(previous.run,contract=contract,write=write)(bundle,out,stage=stage,
        runtime_factory=runtime_factory,backend_factory=backend_factory)
    # The inherited writer copies the entire options dict, including freeze.
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    value = contract.bundle(args.expected_source_sha,seed=args.seed,stage_probe=args.stage_probe,
        pickup_slot=args.pickup_slot,**{k:getattr(args,k) for k in contract.NEW_OPTIONS})
    if not args.execute:
        print(json.dumps(dict(execution_started=False,execution_bundle_id=contract.BUNDLE_ID,
            source_sha=args.expected_source_sha,bundle_sha256=value['bundle_sha256'],task=value['task'],
            options=value['options'],policy=value['idle_robot_contacts_policy'],
            admitted_dev_runs=contract.old.hp.base.read(contract.ROOT/contract.PLAN)['dev_runs']),indent=2))
        return 0
    contract.require_execution(value)
    return bind(previous.main,contract=contract,parser=parser,run=run)(argv)


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr)
        raise SystemExit(2)
