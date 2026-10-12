"""Same frozen full-route criteria; additional control/evaluation provenance."""
import argparse
import json
from pathlib import Path
from harness.zone_final_pair_binding import bind
from scripts import evaluate_s3_full_route as previous
from scripts import evaluate_s3_route_resume as route


def normalized_events(record):
    for e in route.events(record):
        yield e
        if e.get('event')=='checkpoint_carry_command_plan':
            # Event-schema adapter only; the sealed endpoint/hold criteria stay.
            yield {**e,'event':'synchronized_carry_plan'}


def evaluate(raw):
    route_evaluate=bind(route.evaluate,events=normalized_events)
    r=bind(previous.evaluate,previous=route_evaluate)(raw)
    b=json.loads((raw/'bundle.json').read_text())
    r['candidate']=b['checkpoint_correction']['candidate']
    r['checkpoint_correction']=json.loads((raw/'checkpoint-correction.json').read_text())
    return r


def main():return bind(previous.main,evaluate=evaluate)()
if __name__=='__main__':raise SystemExit(main())
