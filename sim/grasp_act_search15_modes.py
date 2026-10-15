"""Independent opt-in search15 controls; profile provenance is never implicit."""
MODES = {'peer_reobserve': 'peer_reobserve_v1',
         'obstacle_reobserve': 'obstacle_reobserve_v1',
         'pregrasp_sampling': 'pregrasp_sampling_v1'}


def validate(values, *, recovery, profile='visible_only', pose_source='issued', coordination='off'):
    for key, mode in MODES.items():
        if values.get(key, 'off') not in ('off', mode):
            raise ValueError('unknown '+key+' mode')
    if any(values.get(k, 'off') != 'off' for k in MODES):
        if (recovery != 'progress_view_recovery_v3' or profile != 'visible_only'
                or pose_source != 'issued' or coordination != 'off'):
            raise ValueError('search15 requires visible_only issued progress_view_recovery_v3 and coordination off')


def add_arguments(parser):
    for key, mode in MODES.items():
        parser.add_argument('--'+key.replace('_', '-'), choices=('off', mode), default='off')


def options(args):
    return {k: getattr(args, k) for k in MODES}


def match(record, expected, context):
    for key in MODES:
        if record.get(key, 'off') != expected.get(key, 'off'):
            raise ValueError(context+' '+key+' mode mismatch')
