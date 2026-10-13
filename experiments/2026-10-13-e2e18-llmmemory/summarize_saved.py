"""Read-only aggregation of inherited runs; never calls a provider or simulator."""
import argparse
import base64
import copy
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness import e2e_llm_memory as lm
from harness import e2e_vote_ref as vr


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split(request):
    return json.loads(next(p['text'] for p in request['messages'][1]['content']
                           if p.get('type') == 'text' and p['text'].lstrip().startswith('{')))


def memory_from_saved(body):
    # All rows were present in that call's request. No future response/evaluator is read.
    rows = [dict(call_id=f'saved-{i}', t=r['t'], did=r['did'], seg=r.get('seg'), epoch=r.get('epoch'),
                 accepted=r['result'] == 'accepted', reason=r.get('why'))
            for i, r in enumerate(body['own_decision_log'])]
    return dict(decisions=rows, windows=[])


def prepare(old, saved, with_ref=False):
    request = copy.deepcopy(old)
    body = split(request)
    system = request['messages'][0]['content']
    if with_ref:
        if body['dialogue']['key'] is not None:
            body['dialogue']['vote_ref'] = vr.ref_for(body['dialogue']['key'])
        system = vr.prompt(body, system)
    system = lm.apply(body, system, memory_from_saved(saved))
    # Historical snapshots have creation-window annotations but no delivery receipts.
    # Preserve known annotations; do not invent receipt time/epoch from send time.
    marks = {p['message_id']: p.get('window') for p in saved.get('peer_reports') or ()}
    for report in body.get('peer_reports') or ():
        if marks.get(report['message_id']) is not None:
            report['sent_window'] = copy.deepcopy(marks[report['message_id']])
            report['previous_segment'] = bool(body['dialogue']['key'] is not None
                and report['sent_window']['seg'] is not None and not report['sent_window']['current'])
    request['messages'][0]['content'] = system
    for part in request['messages'][1]['content']:
        if part.get('type') == 'text' and part['text'].lstrip().startswith('{'):
            part['text'] = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return request


def summarize(v0, v1):
    m0, m1 = load(v0/'manifest.json'), load(v1/'manifest.json')
    assert [(e['run'], e['call_id'], e['view']) for e in m0] == [(e['run'], e['call_id'], e['view']) for e in m1]
    identical = {}
    for variant in ('old', 'vote_ref'):
        identical[variant] = sum(sha(v0/e['variants'][variant]['file']) == sha(v1/e['variants'][variant]['file']) for e in m0)
        assert identical[variant] == len(m0)
    expected = {(e['run'], e['call_id']): e['expected'] for e in m0}
    groups, per_case = {}, {}
    for directory in (v0, v1):
        rows = [json.loads(line) for line in (directory/'results.jsonl').read_text().splitlines()]
        assert len({(r['run'], r['call_id'], r['variant'], r['rep']) for r in rows}) == len(rows)
        for variant in sorted({r['variant'] for r in rows}):
            selected = [r for r in rows if r['variant'] == variant]
            key = directory.name + '/' + variant
            def correct(r):
                target = expected[(r['run'], r['call_id'])]
                return r['status'] == 200 and r['outcome'] == (target if target == 'continue' else 'accepted_' + target)
            groups[key] = dict(correct=sum(map(correct, selected)), total=len(selected),
                completion_tokens_median=statistics.median(r['completion_tokens'] for r in selected if r['status'] == 200),
                wall_median_s=statistics.median(r['wall_s'] for r in selected if r['status'] == 200),
                http_errors=sum(r['status'] != 200 for r in selected))
            per_case[key] = [{**{k:e[k] for k in ('run','call_id','expected')},
                'correct': sum(correct(r) for r in selected if (r['run'],r['call_id']) == (e['run'],e['call_id'])),
                'total': sum((r['run'],r['call_id']) == (e['run'],e['call_id']) for r in selected)} for e in m0]
    return dict(schema='ugrp.llm_memory.saved_replay.v1', research_result=False,
        scope='Stored next-protocol-action proxy; not image grip correctness, full reply validation, live timing, or physical success',
        source_status='Inherited uncommitted Claude prototype; not the final Codex candidate',
        provider='openrouter_v1/google/gemma-4-31b-it/DeepInfra (inherited paid path; exact cost was not saved)',
        calls_this_analysis=0, identical_control_requests=identical, groups=groups, per_case=per_case,
        artifacts=[dict(path=str(p.resolve()), sha256=sha(p), bytes=p.stat().st_size)
                   for d in (v0,v1) for p in sorted(d.glob('*.json*')) if p.name != 'summary.json'])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--v0', type=Path, default=ROOT/'outputs/llmmemory-replay-v0')
    p.add_argument('--v1', type=Path, default=ROOT/'outputs/llmmemory-replay-v1')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--candidate-output', type=Path)
    a = p.parse_args()
    report = summarize(a.v0,a.v1)
    if a.candidate_output:
        a.candidate_output.mkdir(parents=True, exist_ok=False)
        manifest = load(a.v1/'manifest.json')
        for entry in manifest:
            old = load(a.v1/entry['variants']['old']['file'])
            saved = split(load(a.v1/entry['variants']['memory']['file']))
            for variant in ('memory', 'memory_vote_ref'):
                target = a.candidate_output/entry['variants'][variant]['file']
                target.write_text(json.dumps(prepare(old,saved,'vote_ref' in variant)))
                entry['variants'][variant] = dict(file=target.name,sha256=sha(target))
            entry['variants'] = {v:entry['variants'][v] for v in ('memory','memory_vote_ref')}
        (a.candidate_output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        report['final_candidate'] = dict(requests_prepared=20, model_calls=0,
            memory_source_sha256=sha(ROOT/'harness/e2e_llm_memory.py'),
            path=str(a.candidate_output.resolve()), delivery_receipts='unavailable in inherited replay snapshot')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['groups'],ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
