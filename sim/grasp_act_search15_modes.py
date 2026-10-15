"""Independent opt-in search15 controls; profile provenance is never implicit."""
MODES = {'peer_reobserve': 'peer_reobserve_v1',
         'obstacle_reobserve': 'obstacle_reobserve_v1',
         'pregrasp_sampling': 'pregrasp_sampling_v1'}

from sim.grasp_act_search17 import MODES as SEARCH17_MODES
from sim.grasp_act_search18 import MODES as SEARCH18_MODES
from sim.grasp_act_search19 import MODES as SEARCH19_MODES
from sim.grasp_act_search20 import MODES as SEARCH20_MODES
from sim.grasp_act_search21 import MODES as SEARCH21_MODES
from sim.grasp_act_search22 import MODES as SEARCH22_MODES
from sim.grasp_act_search23 import MODES as SEARCH23_MODES
from sim.grasp_act_search24 import MODES as SEARCH24_MODES
from sim.grasp_act_search25 import MODES as SEARCH25_MODES
ALL_MODES = {**SEARCH25_MODES, **SEARCH24_MODES, **SEARCH23_MODES, **SEARCH22_MODES, **MODES, **SEARCH17_MODES, **SEARCH18_MODES, **SEARCH19_MODES, **SEARCH20_MODES, **SEARCH21_MODES}


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


    if values.get('search20', 'off') != 'off':
        if any(values.get(k, 'off') != v for k, v in SEARCH19_MODES.items()):
            raise ValueError('search20 requires both search19 modes')


    if values.get('search21', 'off') != 'off' and values.get('search20', 'off') == 'off':
        raise ValueError('search21 requires search20')

    if values.get('search22','off')!='off' and values.get('search21','off')=='off':
        raise ValueError('search22 requires search21')

    if values.get('search23','off')!='off' and values.get('search22','off')=='off':
        raise ValueError('search23 requires search22')
    if any(values.get(k,'off')!='off' for k in SEARCH24_MODES) and values.get('search23','off')=='off':
        raise ValueError('search24 requires search23')
    if any(values.get(k,'off')!='off' for k in SEARCH25_MODES):
        if any(values.get(k,'off')!=v for k,v in SEARCH24_MODES.items()):
            raise ValueError('search25 requires IRM and deterministic search24 budget')

def add_arguments(parser):
    for key, mode in ALL_MODES.items():
        parser.add_argument('--'+key.replace('_', '-'), choices=('off', mode), default='off')


def options(args):
    return {k: getattr(args, k, 'off') for k in ALL_MODES}


def match(record, expected, context):
    for key in ALL_MODES:
        if record.get(key, 'off') != expected.get(key, 'off'):
            raise ValueError(context+' '+key+' mode mismatch')
