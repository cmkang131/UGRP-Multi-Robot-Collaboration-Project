"""Composite trial identity shared by raw event producers and evidence readers."""
from harness.zone_study_contract import MAIN_CONDITIONS

KEY_FIELDS = ('run_id', 'trial_id', 'condition', 'seed', 'order_id', 'attempt')
TRIAL_SCOPE = '__trial__'


def key_tuple(key):
    if not isinstance(key, dict) or set(key) != set(KEY_FIELDS):
        raise ValueError('INVALID: missing/extra composite key columns')
    if (any(type(key[k]) is not str or not key[k] for k in ('run_id', 'trial_id', 'order_id'))
            or type(key['condition']) is not str or key['condition'] not in MAIN_CONDITIONS
            or type(key['seed']) is not int or type(key['attempt']) is not int or key['attempt'] < 1):
        raise ValueError('INVALID: composite key type/value conflict')
    return tuple(key[k] for k in KEY_FIELDS)


def key_for(identity, order_id=TRIAL_SCOPE):
    key = {name: identity[name] for name in KEY_FIELDS if name != 'order_id'}
    key['order_id'] = order_id
    key_tuple(key)
    return key


def trial_key(key):
    value = key_tuple(key)
    if key['order_id'] != TRIAL_SCOPE:
        raise ValueError('INVALID: raw event needs a full trial key')
    return value
