"""One recovery-only matched S2 DEV after own-record prefix replay."""
import sys
from harness import zone_s2_realism_contract_v129 as contract
from harness.zone_solo_cyan_slip_recovery import Runtime
from harness.zone_final_pair_binding import bind
from scripts import run_s2_realism_v128 as previous
from scripts import run_s2_realism_v118 as entry


def parser():
    p=previous.parser();p.description=__doc__
    p.add_argument('--slip-recovery',choices=('off','slip_recovery_v1'),default='off')
    return p


def result_record(value,bundle,record):
    previous.result_record(value,bundle,record)
    value.update(slip_recovery=record.get('slip_recovery'),
                 recovery_replay_admission_pass=bundle['recovery_replay_admission_pass'],
                 recovery_replay=contract.REPLAY,slip_replay=contract.previous.REPLAY)
    return value


def run(bundle,out,**kwargs):
    return bind(previous.run,contract=contract,Runtime=Runtime,result_record=result_record)(bundle,out,**kwargs)


def main(argv=None):return bind(entry.main,contract=contract,parser=parser,run=run)(argv)


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(2)
