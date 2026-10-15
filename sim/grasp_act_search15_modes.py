"""Independent opt-in search15 controls; profile provenance is never implicit."""
MODES = {'peer_reobserve': 'peer_reobserve_v1',
         'obstacle_reobserve': 'obstacle_reobserve_v1',
         'pregrasp_sampling': 'pregrasp_sampling_v1'}

from sim.grasp_act_search17 import MODES as SEARCH17_MODES
from sim.grasp_act_search18 import MODES as SEARCH18_MODES
from sim.grasp_act_search19 import MODES as SEARCH19_MODES
ALL_MODES = {**MODES, **SEARCH17_MODES, **SEARCH18_MODES, **SEARCH19_MODES}


def validate(values, *, recovery, profile='visible_only', pose_source='issued', coordination='off'):
    for key, mode in ALL_MODES.items():
        if values.get(key, 'off') not in ('off', mode):
            raise ValueError('unknown '+key+' mode')
    if any(values.get(k, 'off') != 'off' for k in ALL_MODES):
        if (recovery != 'progress_view_recovery_v3' or profile != 'visible_only'
                or pose_source != 'issued' or coordination != 'off'):
            raise ValueError('search15 requires visible_only issued progress_view_recovery_v3 and coordination off')
    if any(values.get(k, 'off') != 'off' for k in SEARCH19_MODES):
        if values.get('search18_footprint', 'off') != 'off':
            raise ValueError('search19 keeps search18 footprint off')


def add_arguments(parser):
    for key, mode in ALL_MODES.items():
        parser.add_argument('--'+key.replace('_', '-'), choices=('off', mode), default='off')


def options(args):
    return {k: getattr(args, k, 'off') for k in ALL_MODES}


def match(record, expected, context):
    for key in ALL_MODES:
        if record.get(key, 'off') != expected.get(key, 'off'):
            raise ValueError(context+' '+key+' mode mismatch')
