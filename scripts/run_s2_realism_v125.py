"""One fresh full S2 DEV after stationary AMCL replay admission."""
import sys
from harness import zone_s2_realism_contract_v125 as contract
from harness.zone_solo_cyan_amcl_update import Runtime
from harness.zone_final_pair_binding import bind
from scripts import run_s2_realism_v124 as previous
from scripts import run_s2_realism_v118 as entry


def parser():
    p=previous.parser();p.description=__doc__
    p.add_argument('--amcl-update',choices=('off','ros_motion_v1','ros_motion_prob_v1'),default='off')
    p.add_argument('--dev-search',choices=('off','repeat_views_v1'),default='off')
    return p


def result_record(value,bundle,record):
    previous.result_record(value,bundle,record)
    value.update(amcl_update=record.get('amcl_update'),dev_search=record.get('dev_search'),
        effective_measurement='ros_motion_v1: unloaded and loaded',
        stationary_offline_admission=contract.REPLAY,user_override_old_geometry_gate=False)
    return value


def run(bundle,out,**kwargs):
    return bind(previous.run,contract=contract,Runtime=Runtime,result_record=result_record)(bundle,out,**kwargs)


def main(argv=None):return bind(entry.main,contract=contract,parser=parser,run=run)(argv)

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(2)
