"""SSH loopback transport for DEV; authentication stays at the audited Mac proxy.

The Mac relay checks the original proxy identity before EVERY forwarded POST.
The normal durable ledger, network fence, client and completion checks remain.
No credential is accepted by this module, in files, URLs, or CLI arguments.
"""
import hashlib
import json
import time
from pathlib import Path

from harness.pair_llm_live import PairLiveLedger
from harness.zone_study_llm_driver import HostError
from harness.zone_pilot_budget import PROXY_SHA256

URL = 'http://127.0.0.1:18391/v1/chat/completions'
MAX_RELAY_SECONDS = 28800  # 7 h E2E plus setup/flush, bounded by the VM's 8 h guard.


def validate_receipt(receipt, now=None, *, remote_url=URL):
    now = time.time() if now is None else now
    if remote_url not in (URL,'http://127.0.0.1:18393/v1/chat/completions'):
        raise HostError('unregistered loopback relay URL')
    single=receipt.get('driver_profile')=='study_gemma4_31b_v1'
    openrouter=receipt.get('upstream')=='openrouter_v1'
    source='scripts/openrouter_upstream.py' if openrouter else 'scripts/gemma_fallback_proxy.py'
    expected=hashlib.sha256((Path(__file__).resolve().parents[1]/source).read_bytes()).hexdigest() if single else PROXY_SHA256
    if openrouter:
        from scripts.openrouter_upstream import config
        if (not single or receipt.get('single_model') is not True or receipt.get('fallback_enabled') is not False
                or receipt.get('openrouter_v1') != dict(config(),source_sha256=expected)):
            raise HostError('pinned OpenRouter identity required')
    if receipt.get('decider','off')!='off':
        paths=('scripts/jev_relay_upstream.py','harness/e2e_jev_decider.py','harness/jev_decider_eval.py')
        hashes={p:hashlib.sha256((Path(__file__).resolve().parents[1]/p).read_bytes()).hexdigest() for p in paths}
        if not openrouter or receipt.get('decider')!='jev_v1' or receipt.get('jev_source_sha256')!=hashes:
            raise HostError('pinned Jev relay source required')
    if receipt.get('dialogue_decider','gemma_v0')!='gemma_v0':
        paths=('scripts/d1_dialogue_upstream.py','harness/e2e_dialogue_decider.py','harness/e2e_llm_memory.py')
        hashes={p:hashlib.sha256((Path(__file__).resolve().parents[1]/p).read_bytes()).hexdigest() for p in paths}
        if (not openrouter or receipt.get('dialogue_decider')!='d1_v1' or receipt.get('decider','off')!='off'
                or receipt.get('d1_dialogue_source_sha256')!=hashes):
            raise HostError('pinned d1 dialogue relay source required')
    if single and not openrouter and (receipt.get('single_model') is not True or receipt.get('fallback_enabled') is not False
                   or receipt.get('gemma_model_pin')!={'model_id':'gemma-4-31b-it','version':'001'}
                   or receipt.get('gemma_fallback',{}).get('image_input_confirmed') is not True):
        raise HostError('single Gemma identity/model/image verification missing')
    if (receipt.get('schema') != 'ugrp.s4_ssh_proxy.v1'
            or receipt.get('remote_url') != remote_url
            or receipt.get('proxy', {}).get('source_sha256') != expected
            or not 0 < receipt.get('valid_for_s', 3600) <= MAX_RELAY_SECONDS
            or not 0 <= now-receipt.get('checked_unix', 0) <= receipt.get('valid_for_s', 3600)
            or receipt.get('authentication') != 'existing_mac_proxy_no_credentials_transferred'
            or receipt.get('audit_per_post') is not True):
        raise HostError('S4 SSH relay identity expired or mismatched')
    return receipt


class TunnelLedger(PairLiveLedger):
    def __init__(self, *, receipt, remote_url=URL, **kwargs):
        self.remote_url=remote_url
        self.receipt_path = Path(receipt)
        raw = self.receipt_path.read_bytes()
        self.receipt_sha256 = hashlib.sha256(raw).hexdigest()
        self.receipt = validate_receipt(json.loads(raw),remote_url=remote_url)
        fallback_profile = 'dev_gemini_gemma_fallback_v1'
        requested = kwargs['profile'].get('profile_id', 'main_study_gemini_v1')
        offered = self.receipt.get('driver_profile', 'main_study_gemini_v1')
        if requested != offered:
            raise HostError('relay driver profile differs from selected run profile')
        if offered == fallback_profile and (self.receipt.get('dev_only') is not True or
                self.receipt.get('gemma_fallback', {}).get('image_input_confirmed') is not True):
            raise HostError('Gemma fallback requires DEV and verified image input')
        if kwargs['profile']['proxy_url'] != remote_url or kwargs.get('wire') is not None:
            raise HostError('S4 live relay requires its fixed loopback URL and real ledger wire')
        super().__init__(**kwargs)
        self.proxy_identity = self.receipt

    def _preflight_live(self):
        # Inside NetworkFence: no second socket or subprocess is used here.
        # The receiving Mac relay performs live PID/listener/source validation.
        if hashlib.sha256(self.receipt_path.read_bytes()).hexdigest() != self.receipt_sha256:
            raise HostError('S4 relay receipt changed during run')
        validate_receipt(self.receipt,remote_url=self.remote_url)
