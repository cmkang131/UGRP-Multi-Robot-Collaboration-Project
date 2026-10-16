"""Default-off recorded output budget for complete typed OwnRoute messages."""
import copy
OPTION='1600_v1'


def profile_override(profile,option='off'):
    if option=='off':return profile
    if option!=OPTION:raise ValueError('UNKNOWN_ROUTE_TOKENS')
    value=copy.deepcopy(profile);value['model']['max_tokens']=1600
    return value


def compose(bundle,option):
    if option=='off':return
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v227':raise ValueError('ROUTE_TOKENS_REQUIRES_V227')
    bundle['e2e_options']['route_tokens']=option
    bundle['model_request_overrides']={'max_tokens':1600}
