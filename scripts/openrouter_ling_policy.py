"""Opt-in Ling transport: bounded retries, pacing, and safe error evidence."""
import datetime
import email.utils
import json
import math
import re

POLICY = 'ling_rate_limit_v1'
PARAMETERS = dict(max_attempts=3, max_concurrent=1, requests_per_second=.5,
                  backoff_base_s=2., backoff_cap_s=20., retry_after_priority=True)


def safe_headers(headers):
    return {k.lower():str(v) for k,v in headers.items()
            if k.lower() in ('retry-after','date','x-request-id','cf-ray') or k.lower().startswith('x-ratelimit-')}


def redact(value, secret):
    if isinstance(value,dict):
        return {k:('[REDACTED]' if any(x in k.lower() for x in ('authorization','api_key','apikey','access_token','secret'))
                   else redact(v,secret)) for k,v in value.items()}
    if isinstance(value,list):return [redact(v,secret) for v in value]
    if isinstance(value,str):
        value=value.replace(secret,'[REDACTED]') if secret else value
        return re.sub(r'(?i)bearer\s+[^\s"\x27,}]+|sk-or-[\w-]+','[REDACTED]',value)
    return value


def error_body(raw,secret):
    try:value=json.loads(raw)
    except (ValueError,UnicodeDecodeError):value={'unparsed_body':raw.decode('utf-8',errors='replace')[:32000]}
    return redact(value,secret)


def retry_delay(attempt,headers,random_value,now):
    hint=headers.get('retry-after')
    if hint is not None:
        try:delay=float(hint)
        except ValueError:
            try:delay=email.utils.parsedate_to_datetime(hint).timestamp()-now
            except (ValueError,TypeError,OverflowError):delay=-1
        if math.isfinite(delay) and delay>=0:return delay,'retry_after'
    cap=min(PARAMETERS['backoff_cap_s'],PARAMETERS['backoff_base_s']*2**(attempt-1))
    return cap*random_value,'exponential_full_jitter'


def reserve_cost(body, selection=None):
    # UTF-8 bytes conservatively bound text tokenizer output. Image URI bytes
    # overestimate images, intentionally; never assume cache hits or zero cost.
    from harness.task_planner_model import GEMMA_FP4, GEMMA_JSON
    prompt,completion=(.00000009,.00000034) if selection in (GEMMA_FP4,GEMMA_JSON) else (.000000021,.0000000616)
    return (len(json.dumps(body,ensure_ascii=True).encode())+4096)*prompt + body.get('max_tokens',768)*completion
