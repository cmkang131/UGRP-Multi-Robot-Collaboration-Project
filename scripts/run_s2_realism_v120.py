"""Managed one-shot S2 DEV in-hand RGB probe; no model or new sensor."""
import sys
from harness import zone_s2_realism_contract_v120 as contract
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_inhand import Runtime, PROBABLE
from scripts import run_s2_realism_v119 as previous


def parser():
    p=previous.parser();p.description=__doc__
    p.add_argument('--hold-check',choices=('off','inhand_rgb_v1'),default='off')
    return p


def run(bundle,out,*,stage='pick',runtime_factory=None,backend_factory=None):
    contract.require_execution(bundle)
    if stage!=bundle['stage_probe']:raise ValueError('stage mismatch')
    if runtime_factory is None:
        def runtime_factory(*args,**kwargs):
            return Runtime(*args,**kwargs,**{k:v for k,v in bundle['options'].items()
                if k not in ('drive_profile','stagnation_watch','idle_robot_contacts')},
                motion_model=bundle['motion_model'])
    if backend_factory is None:
        from sim.s2_idle_contacts import backend_class
        backend_factory=backend_class()
    def write(path,value):
        if path.name=='result.json':
            hold=value.get('pickup_site_status','unknown')
            passed=(value.get('stage_reached') is True and value.get('evaluation',{}).get('lifted') is True
                and hold==PROBABLE and value.get('status')=='STAGE_REACHED_UNQUALIFIED')
            value.update(result_condition=bundle['result_condition'],pool_with_previous_s2=False,
                comparison_metrics=['wall_per_sim'],probe_gate_passed=passed,
                probe_failure=None if passed else value.get('failure') or 'INHAND_OR_LIFT_UNCONFIRMED',
                hold_status=hold,pickup_site_status='not_evaluated_inhand_selected',
                grasp_claim='PROBABLE_HELD from own RGB; lift independently judged by eval',
                hold_check=bundle['options']['hold_check'],site_check='off')
        previous.previous.previous.write(path,value)
    return bind(previous.previous.previous.run,contract=contract,write=write)(bundle,out,stage=stage,
        runtime_factory=runtime_factory,backend_factory=backend_factory)


def main(argv=None):
    return bind(previous.previous.main,contract=contract,parser=parser,run=run)(argv)


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(2)
