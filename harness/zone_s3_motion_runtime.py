"""S3 motion integration candidate. Historical options default to identity."""
import copy

from harness import zone_s3_continue as old
from harness import zone_s3_no_prior as base
from harness.zone_final_pair_binding import bind
from harness.zone_s3_exact_cache import attach as cache
from harness.zone_s3_pair_heading import attach_pair as heading
from harness.zone_s3_dev_light import attach as dev_light


def solo_factory(config):
    plain=copy.deepcopy(config)
    mode=plain['options'].pop('s3_exact_cache','off')
    plain['options'].pop('pair_heading','off')
    plain['options'].pop('s3_io','off')
    make=old.solo_factory(plain)
    return lambda *a,**kw: cache(make(*a,**kw),exact_cache=mode)


class Runtime(old.Runtime):
    def __init__(self,*args,config,**kwargs):
        def pair_factory(*a,**kw):
            pair=base.PairRuntime(*a,**kw)
            pair=dev_light(pair,s3_dev_light=config['options'].get('s3_dev_light','off'))
            return heading(pair,pair_heading=config['options'].get('pair_heading','off'))
        bind(base.Runtime.__init__,solo_factory=solo_factory,PairRuntime=pair_factory)(
            self,*args,config=config,**kwargs)
