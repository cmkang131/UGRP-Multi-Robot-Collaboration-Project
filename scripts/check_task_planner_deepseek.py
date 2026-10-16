"""Authorized 400+40+5 check, shared persistent 600 HTTP/$0.30 budget."""
from pathlib import Path
import sys,json,urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import check_task_planner_ling as check
from scripts.evaluate_task_planner_observed import key_remaining
from harness.task_planner_model import DEEPSEEK,ModelBudgetExceeded


def account_limits():
    from scripts.openrouter_upstream import keychain_key
    from harness.zone_study_llm_transport import no_redirect_opener
    key=key_remaining()
    req=urllib.request.Request('https://openrouter.ai/api/v1/credits',headers={'Authorization':'Bearer '+keychain_key()})
    with no_redirect_opener().open(req,timeout=15) as response:c=json.load(response)['data']
    key['account_balance']=c['total_credits']-c['total_usage']
    if min(key['account_balance'],key['limit_remaining'])-.30<1.5:raise ModelBudgetExceeded('BALANCE_OR_KEY_FLOOR')
    return key


def configure():
    check.MODEL=DEEPSEEK;check.PRICE_KEY='deepseek_fp8'
    check.PRICES={'deepseek_fp8':(.00000014,.00000042)}
    check.MAX_CALLS=600;check.MAX_USD=.30;check.MAX_REPAIRS=0
    check.RATE_POLICY='planner_rate_limit_v1';check.COHORT='deepseek_fp8'
    check.RESPONSE_PARSER='first_object_v1';check.MIN_RATE_DECISIONS=20
    check.CACHE_ORDER='static_first_v2';check.COUNT_ABNORMAL_FORMAT=True
    check.key_remaining=account_limits


if __name__=='__main__':
    configure();check.main()
