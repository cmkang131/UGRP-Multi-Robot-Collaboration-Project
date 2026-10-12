"""S3 continuation candidate, with identity defaults for historical replays."""
import copy

from harness import zone_s3_no_prior as previous
from harness.zone_final_pair_binding import bind
from harness.zone_s3_global_diversity import attach as diversity
from harness.zone_s3_dev_light import attach as dev_light


def solo_factory(config):
    plain = copy.deepcopy(config)
    options = {k: plain['options'].pop(k, 'off') for k in ('global_diversity', 'mode_head_look')}
    plain['options'].pop('s3_dev_light', None)
    factory = previous.solo_factory(plain)
    return lambda *args, **kwargs: diversity(factory(*args, **kwargs), **options)


class Runtime(previous.Runtime):
    def __init__(self, *args, config, **kwargs):
        mode = config['options'].get('s3_dev_light', 'off')
        def pair_factory(*a, **kw):
            return dev_light(previous.PairRuntime(*a, **kw), s3_dev_light=mode)
        initialize = bind(previous.Runtime.__init__, solo_factory=solo_factory, PairRuntime=pair_factory)
        initialize(self, *args, config=config, **kwargs)
