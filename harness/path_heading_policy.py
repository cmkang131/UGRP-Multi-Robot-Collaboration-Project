"""One default for new users of the shared calibrated driving layer.

Versioned S2 bundles through v143 are historical command replays. Missing
options in those bundles mean off; new callers default to path heading.
"""
import json
import re

DEFAULT = 'path_tangent_v1'
VISUAL_LOCK = 'unique_cyan_align_v1'


def mode_for_bundle(bundle):
    options = bundle.get('options', {})
    mode = options.get('heading_mode')
    if mode is None:
        old = re.fullmatch(r'zone-s2-realism-v(\d+)', bundle.get('execution_bundle_id', ''))
        mode = 'off' if old and int(old[1]) <= 143 else DEFAULT
    if mode not in ('off', DEFAULT):
        raise ValueError('unknown heading_mode')
    return mode


def result_record(path, value):
    """Annotate new bundle results, including HOST_ERROR, at the shared writer.

    No controller receives this file; old records without explicit options are
    returned untouched. The bundle itself is never rewritten after hashing.
    """
    if path.name != 'result.json' or not isinstance(value, dict):
        return value
    source = path.parent/'bundle.json'
    if not source.is_file():
        return value
    bundle = json.loads(source.read_text())
    options = bundle.get('options', bundle.get('controller_config', {}).get('options', {}))
    if 'heading_mode' not in options:
        return value
    mode = mode_for_bundle(dict(options=options))
    return {**value, 'heading_mode': mode,
            'heading_visual_lock': options.get('heading_visual_lock', 'off')}
