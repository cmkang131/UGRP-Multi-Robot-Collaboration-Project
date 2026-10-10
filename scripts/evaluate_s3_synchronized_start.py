"""Score the separate fixed v165 round with unchanged v164 outcomes."""
from harness.zone_final_pair_binding import bind
from scripts import evaluate_s3_synchronized_carry as previous
from scripts.run_s3_synchronized_start_cohort import PLAN
if __name__=='__main__':bind(previous.main,PLAN=PLAN)()
