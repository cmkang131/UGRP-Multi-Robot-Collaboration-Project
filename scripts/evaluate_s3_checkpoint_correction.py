"""Same frozen full-route criteria; additional control/evaluation provenance."""
import argparse
import json
from pathlib import Path
from harness.zone_final_pair_binding import bind
from scripts import evaluate_s3_full_route as previous


def evaluate(raw):
    r=previous.evaluate(raw)
    b=json.loads((raw/'bundle.json').read_text())
    r['candidate']=b['checkpoint_correction']['candidate']
    r['checkpoint_correction']=json.loads((raw/'checkpoint-correction.json').read_text())
    return r


def main():return bind(previous.main,evaluate=evaluate)()
if __name__=='__main__':raise SystemExit(main())
