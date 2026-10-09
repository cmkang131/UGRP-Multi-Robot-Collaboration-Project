"""One fresh full S2 DEV after stationary AMCL replay admission."""
import sys
from harness import zone_s2_realism_contract_v126 as contract
from harness.zone_solo_cyan_floor_contact import Runtime
from harness.zone_final_pair_binding import bind
from scripts import run_s2_realism_v125 as previous
from scripts import run_s2_realism_v118 as entry


def parser():
    p=previous.parser();p.description=__doc__
    for key in ('visibility_policy','contact_filter'):
        p.add_argument('--'+key.replace('_','-'),choices=('off',contract.NEW_OPTIONS[key]),default='off')
    return p


def result_record(value,bundle,record):
    previous.result_record(value,bundle,record)
    value.update(visibility_policy=record.get('visibility_policy'),contact_filter=record.get('contact_filter'),
        contact_filter_offline_admission=contract.REPLAY)
    return value


def run(bundle,out,**kwargs):
    def runtime(*args,**kw):
        return Runtime(*args,**kw,floor_appearance=bundle['floor_appearance'])
    return bind(previous.run,contract=contract,Runtime=runtime,result_record=result_record)(bundle,out,**kwargs)


def main(argv=None):return bind(entry.main,contract=contract,parser=parser,run=run)(argv)

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(2)
