"""Finite, loopback-only S4 forwarding through the existing audited Mac proxy."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path
import threading
import time
from urllib.request import Request
from urllib.error import HTTPError

from harness.zone_study_llm_driver import live_proxy, load_registry
from harness.zone_study_llm_transport import no_redirect_opener
from harness.s4_live_transport import URL, MAX_RELAY_SECONDS
from harness.s4_relay_journal import Journal
from harness.task_planner_model import add_model_options, selected, DEFAULT_MODEL


def accepted_call_id(value):
    # Explicit 2026-10-13 paired F16 cohort extension; historical cells unchanged.
    if re.fullmatch(r'e2e18-v(?:346|347|348|350|352|353|354|355|356|357|358|359|360|361|362|363|364|365|366|367|368|369|370|371|372|375|376|377|378|373|374|379|380)-s61013-r[1-9][0-9]*:call-\d+-r[123]:\d+',value):return True
    if re.fullmatch(r'e2e18-v[0-9]+-s610(?:0[1-9]|1[0-2])-r[1-9][0-9]*:call-\d+-r[123]:\d+',value):return True
    if value.startswith('speed-gate-'):
        return accepted_call_id(value[len('speed-gate-'):])
    if re.fullmatch(r'e2e-speed3-(?:base|dt1|dt2|adaptive)-s6100[1-3](?:-r[1-9])?:call-\d+-r[123]:\d+',value):return True
    if re.fullmatch(r'e2e-speed3-adaptive-s6100[1-6]-r3:call-\d+-r[123]:\d+',value):return True
    # Both registered runners use run_key:call_id:attempt; keep the historical
    # S4 namespace and explicitly admit only this E2E pilot's registered cells.
    return re.fullmatch(r'e2e-idle-[ab]-s6100[1-3]-r[2-9][0-9]*:call-\d+-r[123]:\d+',value) is not None or re.fullmatch(r'e2e-idle-a-s6100[4-9]:call-\d+-r[123]:\d+',value) is not None or re.fullmatch(r'e2e-(?:usstall|vomask|idle)-[ab]-s6100[1-3]:call-\d+-r[123]:\d+',value) is not None or value.startswith('s4live1-') or re.fullmatch(r'e2e14-[ab]-s6100[1-4](?:-r2)?:call-\d+-r[123]:\d+',value) is not None or re.fullmatch(r'e2e15-[ab]-s6100[1-3]:call-\d+-r[123]:\d+',value) is not None or re.fullmatch(r'e2e13-(?:profile|off|index|validate|copy|cell|geometry|validation|both)-s61001(?:-p[123])?:call-\d+-r[123]:\d+',value) is not None or re.fullmatch(
        r'(?:e2eaz1-(?:gemma|gemini)-s6100[1-4]-(?:on|off)(?:-r[1-3])?|e2e[89]-[ab]-s6100[1-4](?:-r[12])?|e2e10-(?:a-s6100[1-4]|[bc]-s6100[12])(?:-r2)?|e2e1[12]-[ab]-s6100[12](?:-r2)?):call-\d+-r[123]:\d+',value) is not None


def speech_idempotency_key(key):
    return hashlib.sha256((key+':speech').encode()).hexdigest()


def complete_dialogue(decider, fallback, body, call_id, key):
    """Keep provider status across speech assembly; never turn 402 into 502."""
    class UpstreamFailure(Exception):
        def __init__(self, response):
            self.response = response

    def speak(request):
        response = fallback.complete(json.dumps(request).encode(), call_id,
            idempotency_key=speech_idempotency_key(key))
        if response[0] != 200:
            raise UpstreamFailure(response)
        return json.loads(response[1])

    try:
        raw = decider.complete(json.loads(body), call_id, speak)
    except UpstreamFailure as exc:
        return exc.response
    return 200, json.dumps(raw).encode(), None


def request_dialogue_mode(request):
    """Legacy relay also serves plain-text requests; keep that default path."""
    from harness.e2e_dialogue_decider import unpack
    try:
        user, _ = unpack(request)
    except (ValueError, KeyError, TypeError, IndexError):
        return 'gemma_v0'
    return user.get('dialogue_decider','gemma_v0') if isinstance(user,dict) else 'gemma_v0'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--proxy-pid', type=int)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=3600)
    p.add_argument('--idempotent', action='store_true')
    p.add_argument('--listen-port',type=int,choices=(18392,18394,18414,18416,18424,18426),default=18392)
    p.add_argument('--remote-port',type=int,choices=(18391,18393),default=18391)
    p.add_argument('--gemini-port',type=int,choices=(8391,8395),default=8391)
    p.add_argument('--gemma-fallback', action='store_true', help='DEV only; default off')
    p.add_argument('--multi-key-v1', action='store_true', help='multi_key_v1; default off, Mac keys only')
    p.add_argument('--upstream', choices=('default', 'openrouter_v1'), default='default',
                   help='openrouter_v1: paid OpenRouter Gemma 4 31B (Keychain ugrp-openrouter); default off')
    p.add_argument('--openrouter-providers', default=None,
                   help='comma-separated pinned provider order (recorded in identity.json)')
    p.add_argument('--driver-profile',choices=('main_study_gemini_v1','study_gemma4_31b_v1'),
                   default='main_study_gemini_v1')
    p.add_argument('--decider',choices=('off','jev_v1'),default='off')
    p.add_argument('--task-planner-v1',action='store_true',help='Allow the registered E2E task JSON directly to Gemma, or zero-provider rule comparison.')
    p.add_argument('--dialogue-decider',choices=('gemma_v0','d1_v1','code_v1'),default='gemma_v0')
    p.add_argument('--gemma-state', type=Path,
        default=Path('/Users/changmin/projects/ugrp/outputs/gemma-fallback'))
    add_model_options(p)
    p.add_argument('--openrouter-max-attempts', type=int, choices=(1, 2, 3))
    p.add_argument('--openrouter-max-calls', type=int)
    a = p.parse_args()
    if not 0 < a.seconds <= MAX_RELAY_SECONDS: raise ValueError('finite <=8h relay required')
    a.output.mkdir(parents=True, exist_ok=False)
    single=a.driver_profile=='study_gemma4_31b_v1'
    if a.multi_key_v1 and not (single or a.gemma_fallback):
        raise ValueError('multi_key_v1 requires a Gemma profile')
    openrouter = a.upstream == 'openrouter_v1'
    if a.decider!='off' and not openrouter:raise ValueError('JEV_REQUIRES_OPENROUTER')
    if a.dialogue_decider in ('d1_v1','code_v1') and (not openrouter or a.decider!='off'):
        raise ValueError('D1_DIALOGUE_REQUIRES_OPENROUTER_NO_LEGACY_DECIDER')
    if openrouter and not single: raise ValueError('openrouter_v1 requires --driver-profile study_gemma4_31b_v1')
    if openrouter and (a.multi_key_v1 or a.gemma_fallback): raise ValueError('openrouter_v1 excludes multi_key_v1/gemma_fallback')
    if single and a.gemma_fallback:raise ValueError('single model cannot fallback')
    profile = load_registry()['driver_profiles'][a.driver_profile]
    if not single:profile={**profile,'proxy_url':f'http://127.0.0.1:{a.gemini_port}/v1/chat/completions'}
    if single:
        source=Path(__file__).parent/('openrouter_upstream.py' if openrouter else 'gemma_fallback_proxy.py')
        proxy=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        runtime=dict(provider='openrouter' if openrouter else 'google_aistudio_gemma',key_location='Mac Keychain only')
    else:
        if a.proxy_pid is None:raise ValueError('Gemini proxy PID required')
        proxy, runtime = live_proxy(profile, a.proxy_pid)
    fallback = None
    if openrouter:
        from scripts import openrouter_upstream as orp
        choice = selected(a)
        kwargs = dict(selection=choice, max_attempts=a.openrouter_max_attempts or (3 if choice.model == DEFAULT_MODEL else 1), max_calls=a.openrouter_max_calls)
        if a.openrouter_providers is not None:
            if choice.model != DEFAULT_MODEL or choice.provider != 'DeepInfra' or choice.reasoning != 'default':
                raise ValueError('USE_PLANNER_PROVIDER_WITH_PLANNER_MODEL')
            kwargs.update(selection=None, provider_order=tuple(x.strip() for x in a.openrouter_providers.split(',') if x.strip()))
        orp_cfg = orp.config(**kwargs)
        if choice.model != DEFAULT_MODEL:orp_cfg['selection_source_sha256'] = hashlib.sha256((Path(__file__).resolve().parents[1]/'harness/task_planner_model.py').read_bytes()).hexdigest()
        fallback = orp.OpenRouter(a.gemma_state/'openrouter', **kwargs)
    elif a.gemma_fallback or single:
        from scripts.gemma_fallback_proxy import Gemma
        registered = profile['model']['model'] if single else load_registry()['driver_profiles']['dev_gemini_gemma_fallback_v1']['fallback']['model_id']
        fallback = Gemma(a.gemma_state, expected_model=registered,standard=single,
                         expected_version='001' if single else None, multi_key_v1=a.multi_key_v1)
        fallback.require_image_probe()
    fb_source = Path(__file__).parent/('openrouter_upstream.py' if openrouter else 'gemma_fallback_proxy.py')
    receipt = dict(schema='ugrp.s4_ssh_proxy.v1', remote_url=f'http://127.0.0.1:{a.remote_port}/v1/chat/completions', proxy=proxy,
        runtime=runtime, checked_unix=time.time(), valid_for_s=a.seconds, audit_per_post=True,
        authentication='existing_mac_proxy_no_credentials_transferred')
    if a.task_planner_v1:
        if not openrouter or a.decider!='off':raise ValueError('TASK_PLANNER_PINNED_GEMMA_REQUIRED')
        receipt['task_planner_v1']=True
        from harness.e2e_task_planner_relay import source_hashes
        receipt['task_planner_source_sha256']=source_hashes(Path(__file__).resolve().parents[1])
    (a.output/'identity.json').write_text(json.dumps(receipt, indent=2)+'\n')

    jev = None
    d1 = None
    if a.dialogue_decider in ('d1_v1','code_v1'):
        from scripts.d1_dialogue_upstream import D1, Code
        d1=(D1 if a.dialogue_decider=='d1_v1' else Code)(a.output/(a.dialogue_decider+'-dialogue'))
        receipt['dialogue_decider']=a.dialogue_decider
        receipt['d1_dialogue_source_sha256']={p:hashlib.sha256((Path(__file__).resolve().parents[1]/p).read_bytes()).hexdigest()
            for p in ('scripts/d1_dialogue_upstream.py','harness/e2e_dialogue_decider.py','harness/e2e_llm_memory.py')}
    if a.decider=='jev_v1':
        from scripts.jev_relay_upstream import Jev
        jev=Jev(a.output/'jev')
        receipt['decider']='jev_v1'
        receipt['jev_source_sha256']={p:hashlib.sha256((Path(__file__).resolve().parents[1]/p).read_bytes()).hexdigest()
            for p in ('scripts/jev_relay_upstream.py','harness/e2e_jev_decider.py','harness/jev_decider_eval.py')}
        (a.output/'identity.json').write_text(json.dumps(receipt, indent=2)+'\n')
    lock = threading.Lock()
    journal = Journal(a.output/'responses', retry_rate_limits=single or not a.gemma_fallback, cache_errors=not openrouter) if a.idempotent or fallback else None
    receipt['idempotent_response_journal'] = bool(journal)
    if openrouter:
        receipt.update(driver_profile=a.driver_profile, single_model=True, fallback_enabled=False,
            upstream='openrouter_v1', openrouter_v1=dict(orp_cfg, source_sha256=hashlib.sha256(fb_source.read_bytes()).hexdigest()),
            cohort='openrouter_v1; separate from AI Studio runs')
    elif fallback:
        from scripts.gemma_fallback_proxy import PROFILE
        receipt.update(driver_profile=PROFILE, dev_only=True, gemma_fallback=dict(
            model_id=fallback.model_id, provider='google_aistudio_gemma',
            model_source='models.list', image_input_confirmed=True,
            source_sha256=hashlib.sha256((Path(__file__).parent/'gemma_fallback_proxy.py').read_bytes()).hexdigest(),
            attempts_per_request=1, key_location='macOS Keychain: ugrp-gemma-aistudio'))
        if single:
            receipt.update(driver_profile=a.driver_profile,single_model=True,gemma_model_pin=dict(
                model_id=fallback.model_id,version=fallback.model['version']),
                global_quota=dict(tpm=14400,rpm=27,rpd=12960),fallback_enabled=False)
        if a.multi_key_v1:
            receipt['multi_key_v1'] = True
            receipt['key_indexes'] = sorted(fallback._keys)
            if fallback.key_pool is not None:
                receipt['gemma_fallback']['attempts_per_request'] = len(fallback._keys)
                receipt['global_quota'] = dict(per_key=fallback.key_pool.LIMITS)
    if a.task_planner_v1:
        if not openrouter or a.decider!='off':raise ValueError('TASK_PLANNER_PINNED_GEMMA_REQUIRED')
        receipt['task_planner_v1']=True
        from harness.e2e_task_planner_relay import source_hashes
        receipt['task_planner_source_sha256']=source_hashes(Path(__file__).resolve().parents[1])
    (a.output/'identity.json').write_text(json.dumps(receipt, indent=2)+'\n')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_GET(self):
            if self.path != '/identity': self.send_error(404); return
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps(receipt).encode())

        def do_POST(self):
            if self.path != '/v1/chat/completions': self.send_error(404); return
            n = int(self.headers.get('Content-Length', '0'))
            call_id = self.headers.get('X-UGRP-Call-ID', '')
            if not 0 < n <= 8_000_000 or not accepted_call_id(call_id):
                self.send_error(400); return
            body = self.rfile.read(n)
            started = time.time()
            key = self.headers.get('X-UGRP-Idempotency-Key', '')
            def forward():
                retry_after = None
                try:
                    current = dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()) if single else live_proxy(profile,a.proxy_pid)[0]
                    if current != proxy: raise ValueError('proxy identity changed')
                    if fallback and hashlib.sha256(fb_source.read_bytes()).hexdigest() != (receipt['openrouter_v1'] if openrouter else receipt['gemma_fallback'])['source_sha256']:
                        raise ValueError('fallback source changed')
                    def primary():
                        request = Request(profile['proxy_url'], data=body, headers={
                            'Content-Type': 'application/json', 'X-UGRP-Call-ID': call_id})
                        try:
                            with no_redirect_opener().open(request, timeout=180) as response:
                                return response.status, response.read(8_000_000), None
                        except HTTPError as exc:
                            return exc.code, exc.read(8_000_000), exc.headers.get('Retry-After')
                    if single:
                        from harness.e2e_task_planner_relay import task_request, rule_response
                        task=task_request(json.loads(body)) if a.task_planner_v1 else None
                        request_mode=request_dialogue_mode(json.loads(body))
                        if task is None and request_mode!=a.dialogue_decider:
                            raise ValueError('DIALOGUE_DECIDER_REQUEST_RELAY_MISMATCH')
                        if task is not None:
                            if source_hashes(Path(__file__).resolve().parents[1])!=receipt['task_planner_source_sha256']:raise ValueError('TASK_PLANNER_SOURCE_CHANGED')
                            if task['planner_backend']=='rule_v1':
                                status,raw,retry_after=200,json.dumps(rule_response(task)).encode(),None
                            else:status,raw,retry_after=fallback.complete(body,call_id,idempotency_key=key)
                        elif d1 is not None:
                            for p,digest in receipt['d1_dialogue_source_sha256'].items():
                                if hashlib.sha256((Path(__file__).resolve().parents[1]/p).read_bytes()).hexdigest()!=digest:
                                    raise ValueError('D1_DIALOGUE_SOURCE_CHANGED')
                            status,raw,retry_after=complete_dialogue(d1,fallback,body,call_id,key)
                        else:
                            status,raw,retry_after=fallback.complete(body,call_id,idempotency_key=key)
                        if jev is not None and status==200:
                            for p,digest in receipt['jev_source_sha256'].items():
                                if hashlib.sha256((Path(__file__).resolve().parents[1]/p).read_bytes()).hexdigest()!=digest:
                                    raise ValueError('JEV_SOURCE_CHANGED')
                            raw=json.dumps(jev.complete(json.loads(body),json.loads(raw),call_id)).encode()
                    elif fallback:
                        from scripts.gemma_fallback_proxy import route
                        status, raw, retry_after = route(primary, body, call_id, fallback=fallback, idempotency_key=key)
                    else:
                        status, raw, retry_after = primary()
                except Exception as exc:
                    status = 502
                    raw = json.dumps({'error': 'relay_identity_or_transport', 'type': type(exc).__name__}).encode()
                return status, raw, retry_after
            value, disposition = journal.call(key, body, forward) if journal else (forward(), 'legacy')
            status, raw, retry_after = value
            row = dict(call_id=call_id, started_unix=started, wall_s=time.time()-started,
                status=status, request_sha256=hashlib.sha256(body).hexdigest(),
                response_sha256=hashlib.sha256(raw).hexdigest(), retry_after=retry_after,
                proxy_source_sha256=proxy['source_sha256'], idempotency_key=key,
                disposition=disposition, upstream_forwarded=disposition in ('forwarded', 'legacy'))
            if openrouter:
                try:
                    response = json.loads(raw)
                    row.update(upstream='openrouter_v1', response_model=response.get('model'),
                        provider=response.get('provider'), openrouter=response.get('ugrp_openrouter'),
                        jev=response.get('ugrp_jev'),
                        d1_dialogue=response.get('ugrp_d1_dialogue'),code_dialogue=response.get('ugrp_code_dialogue'),
                        host_error=response.get('host_error', False))
                except (ValueError, AttributeError): pass
            elif fallback:
                try:
                    response = json.loads(raw)
                    row.update(response_model=response.get('model'), provider=response.get('provider'),
                        route=response.get('ugrp_route'), key_index=response.get('key_index'),
                        retry_metrics=response.get('ugrp_retry_metrics'),
                        key_attempts=[{k:v for k,v in x.items() if k!='response_sha256'} for x in response.get('ugrp_key_attempts') or []] or None,
                        upstream_wall_s=response.get('ugrp_upstream_wall_s'))
                except (ValueError, AttributeError): pass
            with lock, (a.output/'receipts.jsonl').open('a') as f:
                f.write(json.dumps(row)+'\n')
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            if retry_after is not None: self.send_header('Retry-After', retry_after)
            self.send_header('Content-Length', str(len(raw))); self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass  # journal already durable

    server = ThreadingHTTPServer(('127.0.0.1', a.listen_port), Handler)
    timer = threading.Timer(a.seconds, server.shutdown); timer.daemon = True; timer.start()
    try: server.serve_forever()
    finally: timer.cancel(); server.server_close()


if __name__ == '__main__': main()
