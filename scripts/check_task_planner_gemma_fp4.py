"""One fixed r4 DEV check using Gemma fp4; no additional comparison cohort."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import check_task_planner_ling as check
from harness.task_planner_model import GEMMA_FP4


def configure():
    check.MODEL=GEMMA_FP4
    check.PRICE_KEY='gemma_fp4'
    check.PRICES={'gemma_fp4':(.00000009,.00000034)}
    check.MAX_USD=.30
    check.RATE_POLICY='planner_rate_limit_v1'
    check.COHORT='gemma_fp4'


if __name__=='__main__':
    configure()
    check.main()
