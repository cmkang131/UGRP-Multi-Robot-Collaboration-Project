"""저장된 동일 입력의 결정론적 계약 재생. 라벨은 선택 뒤 평가에만 사용."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness import e2e_dialogue_decider as dd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=ROOT/'outputs/llmmemory-candidate-v3')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((args.input/'manifest.json').read_text())
    rows = []; inputs = []; cases = []
    for case in manifest:
        entry = case['variants']['memory']
        path = args.input/entry['file']; raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert digest == entry['sha256']
        request = json.loads(raw)
        user, images = dd.unpack(request)
        user['dialogue_decider'] = dd.CODE_MODE
        # No D1 visual categories, evaluator label, or synthesized command history.
        inputs.append(dict(source=str(path.relative_to(ROOT)), sha256=digest, user=user,
            image_data_url_sha256=[hashlib.sha256(s.encode()).hexdigest() for s in images]))
        case_rows = []
        for rep in range(10):
            started = time.perf_counter(); selected = dd.code_select(user)
            wall = time.perf_counter()-started
            action = dd.candidates(user)[selected['action']]
            actual = action.get('choice', action['kind'])
            row = dict(run=case['run'], call_id=case['call_id'], rep=rep, selected=selected,
                action=action, latency_s=wall, actual=actual, expected=case['expected'],
                correct=actual==case['expected'], decision_model_calls=0, decision_cost_usd=0)
            rows.append(row);case_rows.append(row)
        cases.append(dict(run=case['run'],call_id=case['call_id'],expected=case['expected'],
            correct=sum(r['correct'] for r in case_rows),n=len(case_rows)))
    go = [r for r in rows if r['expected']=='GO']
    sources = ['harness/e2e_dialogue_decider.py','harness/e2e_llm_memory.py',
               'harness/e2e_dialogue.py','scripts/d1_dialogue_upstream.py', str(Path(__file__).relative_to(ROOT))]
    summary = dict(schema='ugrp.code_protocol_replay.v1', source_parent=subprocess.check_output(
        ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
        correct=sum(r['correct'] for r in rows),n=len(rows), go_correct=sum(r['correct'] for r in go),go_n=len(go),
        cases=cases,latency_median_s=statistics.median(r['latency_s'] for r in rows),
        decision_model_calls=0,decision_cost_usd=0,gemma_calls=0,
        missing_observation=sum(r['selected']['observation_missing'] for r in rows),
        scope='10 saved requests x 10 deterministic repetitions, not 100 independent scenes; contract labels only; no physical grip labels or live completion',
        failures=[r for r in rows if not r['correct']])
    for name,value in [('summary.json',summary),('inputs.json',inputs),('results.json',rows)]:
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('correct','n','go_correct','go_n','latency_median_s','decision_model_calls','missing_observation')}))


if __name__=='__main__':main()
