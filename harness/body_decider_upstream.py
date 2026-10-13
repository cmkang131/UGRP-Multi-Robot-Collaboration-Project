"""Body-motion decider upstreams (Mac relay only): Liquid d1 and Jev.

Both expose the same choice schema: {model, state, [images], questions:{action:
{type:'choice', instructions, criteria:{label: description}}}} -> answers.action
{choice, probabilities, confidence}. Keys never leave relay memory.
"""
import json
import math
import time

LIQUID_URL = 'https://api.liquid.ai/decisions/v1/systemone'
D1 = 'd1'


def body(model, state, instructions, candidates, image_b64=None):
    out = dict(model=model, state=state, questions=dict(action=dict(
        type='choice', instructions=instructions, criteria=dict(candidates))))
    if image_b64:
        out['images'] = ['data:image/jpeg;base64,' + image_b64]
    return out


def parse(reply, candidates):
    a = reply['answers']['action']
    p = a.get('probabilities') or {}
    choice = a.get('choice')
    if choice not in candidates or set(p) - set(candidates):
        raise ValueError('INVALID_DECIDER_CHOICE')
    vals = [float(v) for v in p.values()]
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in vals):
        raise ValueError('INVALID_DECIDER_PROBABILITY')
    conf = a.get('confidence')
    return choice, {k: float(v) for k, v in p.items()}, None if conf is None else float(conf)


def decide(payload, *, keys, send, journal=lambda row: None):
    """One paid backend attempt; failures stop motion and are re-asked later."""
    backend = payload['backend']
    cands, state, instr = payload['candidates'], payload['state'], payload['instructions']
    image = payload.get('image_jpeg_b64')
    if backend == 'liquid_d1':
        tiers = [(D1, LIQUID_URL, 'liquid', image)]
    elif backend == 'jev':
        from harness.jev_decider_eval import JEV_URL, JEV_MODEL
        tiers = [(JEV_MODEL, JEV_URL, 'jev', None)]
    else:
        raise ValueError('UNKNOWN_BODY_BACKEND')
    attempts, started = [], time.monotonic()
    for model, url, key_name, img in tiers:
        req = body(model, state, instr, cands, img)
        result = send(req, url, keys[key_name], 20)
        row = dict(call_id=payload['call_id'], tier=model, status=result.get('status'),
                   http_status=result.get('http_status'), latency_s=result.get('latency_s'),
                   image_attached=bool(img), request={k: v for k, v in req.items() if k != 'images'})
        if result.get('status') == 'ok':
            try:
                choice, probs, conf = parse(result['body'], cands)
            except (KeyError, TypeError, ValueError) as exc:
                row.update(status='invalid_reply', error=str(exc), response=result.get('body'))
                attempts.append(row)
                journal(row)
                continue
            row.update(response=result['body'])
            attempts.append(row)
            journal(row)
            return dict(status='ok', tier=model, model=result['body'].get('model', model), choice=choice,
                        probabilities=probs, confidence=conf, usage=result['body'].get('usage'),
                        latency_s=time.monotonic() - started,
                        attempts=[{k: v for k, v in a.items() if k not in ('request', 'response')} for a in attempts])
        row.update(error=(result.get('raw_response') or '')[:300] or result.get('error_type'))
        attempts.append(row)
        journal(row)
    return dict(status='failed', latency_s=time.monotonic() - started,
                attempts=[{k: v for k, v in a.items() if k not in ('request', 'response')} for a in attempts])


def scrub(obj, secrets):
    text = json.dumps(obj)
    for s in secrets:
        if s:
            text = text.replace(s, '[REDACTED_SECRET]')
    return json.loads(text)
