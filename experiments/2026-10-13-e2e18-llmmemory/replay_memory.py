"""Offline replay of stored real GO/ACK failure requests with the new llm_memory context (Mac, no simulation).

Usage:  python3 -m experiments.2026-10-13-e2e18-llmmemory ... is not importable; run as a script from the repo root:
  python3 experiments/2026-10-13-e2e18-llmmemory/replay_memory.py build CASES_DIR OUT_DIR
  python3 experiments/2026-10-13-e2e18-llmmemory/replay_memory.py run OUT_DIR --reps 10 --threads 4 --proxy-url http://127.0.0.1:PORT/v1/chat/completions
  python3 experiments/2026-10-13-e2e18-llmmemory/replay_memory.py report OUT_DIR
CASES_DIR holds the fetched `<run>/raw/{llm/*.json,wire/*}` of the failing VM3 runs.
Keys stay inside the existing Mac relay. Paid relay requires separate explicit authorization.
Variants: old / memory / vote_ref / memory+vote_ref. Saved v0/v1 used the inherited direct
OpenRouter implementation; they are not represented as free AI Studio results.
"""
import copy
import hashlib
import json
import re
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness import e2e_llm_memory as lm          # noqa: E402
from harness import e2e_vote_ref as vr            # noqa: E402

CASES = [  # (run, call_id) = real calls whose reply the host rejected (GO/ACK family), VM3 raw
    ('e2e18-v304-s61006-r64', 'call-0014-r1'), ('e2e18-v320-s61006-r65', 'call-0014-r1'),
    ('e2e18-v321-s61006-r65', 'call-0020-r2'), ('e2e18-v321-s61006-r65', 'call-0021-r1'),
    ('e2e18-v321-s61006-r65', 'call-0023-r1'), ('e2e18-v321-s61006-r65', 'call-0024-r2'),
    ('e2e18-v321-s61006-r65', 'call-0025-r1'), ('e2e18-v321-s61006-r65', 'call-0026-r2'),
    ('e2e18-v322-s61006-r65', 'call-0014-r1'), ('e2e18-v323-s61006-r65', 'call-0018-r1')]
VARIANTS = ('old', 'memory', 'vote_ref', 'memory_vote_ref')


def load(path):
    return json.loads(Path(path).read_text())


def wire_file(run_dir, call_id, kind):
    return next((run_dir / 'wire').glob(f'*-{call_id}-{kind}.json'))


def parse_reply(response):
    text = response['choices'][0]['message']['content']
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
    return json.loads(text)


def memory_for(run_dir, actor, now):
    """Same records the live host keeps: dispatch_log + rejected replies (code, attempt) + epoch windows."""
    dispatch = load(run_dir / 'llm/dispatch.json')
    ledger = load(run_dir / 'llm/scheduler_ledger.json')
    rows = []
    for r in dispatch:
        if r['actor'] != actor:
            continue
        did, seg, epoch = lm.attempt_of(r['action'])
        rows.append(dict(call_id=r['call_id'], t=r['sim_s'], did=did, seg=seg, epoch=epoch, accepted=bool(r['accepted']),
                         reason=r['rejected_reason'] and lm.code_of(r['rejected_reason'])))
    for r in load(run_dir / 'llm/requests.json'):
        if r['robot'] == actor and r['status'] == 'invalid_json' and r.get('error'):
            finished = ledger[r['call_id']].get('finished_sim_s')
            try:
                action = parse_reply(load(wire_file(run_dir, r['call_id'], 'response'))).get('action')
            except (ValueError, KeyError, TypeError, StopIteration):
                action = None
            did, seg, epoch = lm.attempt_of(action)
            rows.append(dict(call_id=r['call_id'], t=finished, did=did, seg=seg, epoch=epoch, accepted=False,
                             reason=lm.code_of(r['error'])))
    windows = [(e['at'], e['key']) for e in load(run_dir / 'llm/dialogue.json')['events'] if e['kind'] == 'epoch_open']
    return dict(decisions=rows, windows=windows)


def split(request):
    """(system, body dict, content parts) of a stored wire request."""
    system = request['messages'][0]['content']
    parts = request['messages'][1]['content']
    text = next(p for p in parts if p.get('type') == 'text' and p['text'].lstrip().startswith('{'))
    return system, json.loads(text['text']), parts, text


def variant_request(request, memory, variant):
    system, body, parts, text = split(request)
    body = copy.deepcopy(body)
    if 'vote_ref' in variant:
        key = body['dialogue']['key']
        if key is not None:
            body['dialogue']['vote_ref'] = vr.ref_for(key)
        system = vr.prompt(body, system)
    if variant.startswith('memory'):
        system = lm.apply(body, system, memory)
    new = copy.deepcopy(request)
    new['messages'][0]['content'] = system
    for p in new['messages'][1]['content']:
        if p is not None and p.get('type') == 'text' and p['text'] == text['text']:
            p['text'] = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return new


def expected(view):
    """What the host would accept as the next vote from this captured view (host rules, no truth)."""
    if view['key'] is None:
        return 'continue'
    if not view['own_go_sent']:
        return 'GO'
    if not view['own_ack_sent'] and view['peer_go_ref'] is not None:
        return 'ACK'
    return 'continue'


def judge(reply, view, with_ref):
    """Outcome of a model reply under the host's closed-form rules."""
    try:
        action = parse_reply(reply)['action']
    except (ValueError, KeyError, TypeError):
        return 'unparsable'
    if not isinstance(action, dict) or action.get('kind') != 'route_vote':
        return 'continue' if isinstance(action, dict) and action.get('kind') == 'continue' else 'other_action'
    if with_ref:
        if set(action) != {'kind', 'choice', 'vote_ref'} or action['vote_ref'] != view.get('vote_ref'):
            return 'rejected_format'
        choice = action['choice']
    else:
        if set(action) != {'kind', 'choice', 'order_id', 'route_hash', 'grip_epoch', 'seg', 'peer_go_ref'}:
            return 'rejected_format'
        choice = action['choice']
        if view['key'] is None or [action['order_id'], action['route_hash'], action['grip_epoch'], action['seg']] != view['key']:
            return 'rejected_format'
        if (choice == 'ACK') != (action['peer_go_ref'] is not None) or (
                choice == 'ACK' and action['peer_go_ref'] != view['peer_go_ref']):
            return 'rejected_format'
    if choice == 'GO' and not view['own_go_sent'] and view['key'] is not None:
        return 'accepted_GO'
    if choice == 'ACK' and view['own_go_sent'] and not view['own_ack_sent'] and view['peer_go_ref'] is not None:
        return 'accepted_ACK'
    return 'rejected_state'


def build(cases_dir, out):
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for run, call_id in CASES:
        run_dir = Path(cases_dir) / run / 'raw'
        request = load(wire_file(run_dir, call_id, 'request'))
        system, body, _, _ = split(request)
        actor = body['robot_id']
        memory = memory_for(run_dir, actor, body['sim_time_s'])
        view = copy.deepcopy(body['dialogue'])
        if view['key'] is not None:
            view['vote_ref'] = vr.ref_for(view['key'])
        entry = dict(run=run, call_id=call_id, actor=actor, sim_time_s=body['sim_time_s'], expected=expected(view),
                     view={k: view[k] for k in ('key', 'own_go_sent', 'own_ack_sent', 'peer_go_ref', 'vote_ref') if k in view},
                     original_reply=None, variants={})
        try:
            entry['original_reply'] = judge(load(wire_file(run_dir, call_id, 'response')), view, False)
        except StopIteration:
            pass
        for v in VARIANTS:
            req = variant_request(request, memory, v)
            path = out / f'{run}__{call_id}__{v}.json'
            path.write_text(json.dumps(req))
            tokens_text = len(json.dumps(req['messages'][0]['content'])) + sum(
                len(p.get('text', '')) for p in req['messages'][1]['content'] if p.get('type') == 'text')
            entry['variants'][v] = dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                        text_chars=tokens_text)
        manifest.append(entry)
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    for e in manifest:
        print(e['run'][9:13], e['call_id'], e['actor'], 't=', e['sim_time_s'], 'expected', e['expected'], 'orig', e['original_reply'],
              {v: e['variants'][v]['text_chars'] for v in VARIANTS})


def run(out, reps, threads, variants=VARIANTS, *, proxy_url, allow_paid=False):
    """Use the existing Mac relay; no key lookup or silent paid-provider selection."""
    from urllib.parse import urlsplit
    from urllib.request import Request
    from urllib.error import HTTPError
    from harness.zone_study_llm_transport import no_redirect_opener
    from harness.llm_completion import assess_completion, normal_completion
    address = urlsplit(proxy_url)
    if (address.scheme != 'http' or address.hostname not in ('127.0.0.1', 'localhost')
            or address.username or address.password or address.query or address.fragment
            or address.path != '/v1/chat/completions'):
        raise ValueError('LOCAL_MAC_RELAY_URL_REQUIRED')
    opener = no_redirect_opener()
    with opener.open(f'{address.scheme}://{address.netloc}/identity', timeout=10) as response:
        identity = json.load(response)
    if identity.get('driver_profile') != 'study_gemma4_31b_v1' or not identity.get('single_model'):
        raise ValueError('SINGLE_STUDY_GEMMA_RELAY_REQUIRED')
    provider = identity.get('runtime', {}).get('provider')
    if provider != 'google_aistudio_gemma' and not (allow_paid and identity.get('upstream') == 'openrouter_v1'):
        raise ValueError('PAID_OR_UNKNOWN_RELAY_REQUIRES_EXPLICIT_AUTHORIZATION')
    if identity.get('decider', 'off') != 'off':
        raise ValueError('GEMMA_ONLY_REPLAY_REQUIRED')
    if time.time() >= identity['checked_unix'] + identity['valid_for_s']:
        raise ValueError('RELAY_EXPIRED')
    (out/'relay-identity.json').write_text(json.dumps(identity, indent=2)+'\n')
    manifest = load(out / 'manifest.json')
    if reps < 1 or threads < 1 or threads > 4 or not variants:
        raise ValueError('BOUNDED_REPLAY_REQUIRED')
    for e in manifest:
        for v in variants:
            if v not in VARIANTS or v not in e['variants']:
                raise ValueError('REPLAY_VARIANT_NOT_PREPARED')
            path = out/e['variants'][v]['file']
            if hashlib.sha256(path.read_bytes()).hexdigest() != e['variants'][v]['sha256']:
                raise ValueError('REPLAY_REQUEST_CHANGED')
    results_path = out / 'results.jsonl'
    done = set()
    if results_path.exists():
        for line in results_path.read_text().splitlines():
            r = json.loads(line)
            done.add((r['run'], r['call_id'], r['variant'], r['rep']))
    todo = [(e, v, i) for i in range(reps) for e in manifest for v in variants
            if (e['run'], e['call_id'], v, i) not in done]
    lock = threading.Lock()

    def worker():
        while True:
            with lock:
                if not todo:
                    return
                e, v, i = todo.pop(0)
            request = load(out / e['variants'][v]['file'])
            if hashlib.sha256((out / e['variants'][v]['file']).read_bytes()).hexdigest() != e['variants'][v]['sha256']:
                raise ValueError('REPLAY_REQUEST_CHANGED')
            payload = json.dumps(request).encode()
            request_hash = hashlib.sha256(payload).hexdigest()
            call_id = f'lm-{out.name}-{e["run"]}-{e["call_id"]}-{v}-{i}'
            post = Request(proxy_url, data=payload, headers={'Content-Type': 'application/json',
                'X-UGRP-Call-ID': call_id, 'Idempotency-Key': call_id+'-'+request_hash[:12]})
            began = time.time()
            try:
                try:
                    with opener.open(post, timeout=120) as response:
                        status, raw = response.status, response.read(8_000_000)
                except HTTPError as exc:
                    status, raw = exc.code, exc.read(8_000_000)
                reply = json.loads(raw)
            except Exception as exc:                      # recorded, never retried silently
                status, reply = 'error', {'error': type(exc).__name__}
            wall = time.time() - began
            usage = reply.get('usage') or {}
            row = dict(run=e['run'], call_id=e['call_id'], variant=v, rep=i, status=status, wall_s=round(wall, 3),
                       completion_tokens=usage.get('completion_tokens'), prompt_tokens=usage.get('prompt_tokens'),
                       usage=usage, model=reply.get('model'), request_sha256=request_hash)
            (out/(call_id+'-response.json')).write_text(json.dumps(reply, ensure_ascii=False)+'\n')
            if status == 200 and normal_completion(assess_completion(reply,study_json=False)):
                row['reply'] = reply['choices'][0]['message']['content']
                row['finish_reason'] = reply['choices'][0].get('finish_reason')
                row['outcome'] = judge(reply, {**e['view'], 'key': e['view']['key']}, 'vote_ref' in v)
            else:
                row['outcome'] = 'http_error' if status != 200 else 'non_normal_completion'
            with lock, results_path.open('a') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
                f.flush()
    pool = [threading.Thread(target=worker) for _ in range(threads)]
    [t.start() for t in pool]
    [t.join() for t in pool]


def report(out):
    manifest = load(out / 'manifest.json')
    rows = [json.loads(l) for l in (out / 'results.jsonl').read_text().splitlines()]
    exp = {(e['run'], e['call_id']): e['expected'] for e in manifest}
    summary = {}
    for v in VARIANTS:
        sel = [r for r in rows if r['variant'] == v]
        good = sum(1 for r in sel if r['outcome'] == 'accepted_' + exp[(r['run'], r['call_id'])]
                   or (exp[(r['run'], r['call_id'])] == 'continue' and r['outcome'] == 'continue'))
        counts = {}
        for r in sel:
            counts[r['outcome']] = counts.get(r['outcome'], 0) + 1
        ok = [r for r in sel if r['status'] == 200]
        summary[v] = dict(n=len(sel), correct=good, outcomes=counts,
                          completion_tokens_median=statistics.median([r['completion_tokens'] for r in ok if r['completion_tokens']] or [0]),
                          wall_median_s=statistics.median([r['wall_s'] for r in ok] or [0]),
                          prompt_tokens_median=statistics.median([r['prompt_tokens'] for r in ok if r['prompt_tokens']] or [0]))
    per_case = {}
    for e in manifest:
        k = f'{e["run"][9:13]}/{e["call_id"]}(exp {e["expected"]}, orig {e["original_reply"]})'
        per_case[k] = {v: sum(1 for r in rows if r['run'] == e['run'] and r['call_id'] == e['call_id'] and r['variant'] == v
                              and (r['outcome'] == 'accepted_' + e['expected'] or e['expected'] == 'continue' and r['outcome'] == 'continue'))
                       for v in VARIANTS}
    (out / 'summary.json').write_text(json.dumps(dict(summary=summary, per_case_correct=per_case), indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    for k, v in per_case.items():
        print(k, v)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'build':
        build(sys.argv[2], Path(sys.argv[3]))
    elif cmd == 'run':
        import argparse
        p = argparse.ArgumentParser(); p.add_argument('out', type=Path); p.add_argument('--reps', type=int, default=10)
        p.add_argument('--threads', type=int, default=4); p.add_argument('--variants', default=','.join(VARIANTS))
        p.add_argument('--proxy-url', required=True)
        p.add_argument('--allow-paid', action='store_true', help='Requires separate explicit paid-call authorization')
        a = p.parse_args(sys.argv[2:]); run(a.out, a.reps, a.threads, tuple(a.variants.split(',')),
                                         proxy_url=a.proxy_url, allow_paid=a.allow_paid)
    else:
        report(Path(sys.argv[2]))
