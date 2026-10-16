"""JSON-format continuation; cumulative HTTP ledger includes prior two calls."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import check_task_planner_ling as check
from harness.task_planner_model import GEMMA_JSON


def configure():
    check.MODEL=GEMMA_JSON
    check.PRICE_KEY='gemma_fp4'
    check.PRICES={'gemma_fp4':(.00000009,.00000034)}
    check.MAX_USD=.30
    check.RATE_POLICY='planner_rate_limit_v1'
    check.COHORT='gemma_json'
    check.RESPONSE_PARSER='first_object_v1'
    check.MIN_RATE_DECISIONS=20


if __name__=='__main__':
    configure()
    check.main()
