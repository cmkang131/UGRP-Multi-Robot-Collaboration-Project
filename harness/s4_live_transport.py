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


def validate_receipt(receipt, now=None):
    now = time.time() if now is None else now
    if (receipt.get('schema') != 'ugrp.s4_ssh_proxy.v1'
            or receipt.get('remote_url') != URL
            or receipt.get('proxy', {}).get('source_sha256') != PROXY_SHA256
            or not 0 < receipt.get('valid_for_s', 3600) <= 14400
            or not 0 <= now-receipt.get('checked_unix', 0) <= receipt.get('valid_for_s', 3600)
            or receipt.get('authentication') != 'existing_mac_proxy_no_credentials_transferred'
            or receipt.get('audit_per_post') is not True):
        raise HostError('S4 SSH relay identity expired or mismatched')
    return receipt


class TunnelLedger(PairLiveLedger):
    def __init__(self, *, receipt, **kwargs):
        self.receipt_path = Path(receipt)
        raw = self.receipt_path.read_bytes()
        self.receipt_sha256 = hashlib.sha256(raw).hexdigest()
        self.receipt = validate_receipt(json.loads(raw))
        if kwargs['profile']['proxy_url'] != URL or kwargs.get('wire') is not None:
            raise HostError('S4 live relay requires its fixed loopback URL and real ledger wire')
        super().__init__(**kwargs)
        self.proxy_identity = self.receipt

    def _preflight_live(self):
        # Inside NetworkFence: no second socket or subprocess is used here.
        # The receiving Mac relay performs live PID/listener/source validation.
        if hashlib.sha256(self.receipt_path.read_bytes()).hexdigest() != self.receipt_sha256:
            raise HostError('S4 relay receipt changed during run')
        validate_receipt(self.receipt)
