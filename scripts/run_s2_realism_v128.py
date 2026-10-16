"""One S2 closed-loop DEV under explicit administrator replay-gate deviation."""
import sys
from harness import zone_s2_realism_contract_v128 as contract
from harness.zone_solo_cyan_slip_detect import Runtime
from harness.zone_final_pair_binding import bind
from scripts import run_s2_realism_v126 as previous
from scripts import run_s2_realism_v118 as entry


def parser():
    p=previous.parser();p.description=__doc__
    p.add_argument('--slip-detection',choices=('off','slip_detect_v1'),default='off')
    p.add_argument('--stall-recovery',choices=('off',),default='off')
    return p


def result_record(value,bundle,record):
    previous.result_record(value,bundle,record)
    value.update(slip_detection=record.get('slip_detection'),
        intentional_deviation=bundle['intentional_deviation'],
        replay_admission_pass=False,slip_replay=contract.REPLAY,
        stall_recovery_option=bundle['options']['stall_recovery'])
    return value


def run(bundle,out,**kwargs):
    return bind(previous.run,contract=contract,Runtime=Runtime,result_record=result_record)(bundle,out,**kwargs)


def main(argv=None):return bind(entry.main,contract=contract,parser=parser,run=run)(argv)

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(2)
